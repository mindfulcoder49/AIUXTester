import base64
import json
import random
import re
import time
from typing import List, Type

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from config import OPENAI_API_KEY
from llm.utils import extract_json


class OpenAIClient:
    def __init__(self):
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not set")
        self.client = OpenAI(api_key=OPENAI_API_KEY)

    def _encode_images(self, images: List[bytes]):
        content = []
        for img in images:
            b64 = base64.b64encode(img).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        return content

    def generate_action(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        images: List[bytes],
        schema: Type[BaseModel],
        temperature: float,
        model: str,
    ) -> BaseModel:
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    *self._encode_images(images),
                ],
            },
        ]

        response = self._chat_completion_with_retries(
            model=model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content or ""
        try:
            data = extract_json(text)
        except ValueError:
            data = self._repair_payload(
                model=model,
                temperature=temperature,
                system_prompt=system_prompt,
                invalid_payload=text,
                schema=schema,
            )
        try:
            return schema.model_validate(data)
        except ValidationError:
            repaired = self._repair_payload(
                model=model,
                temperature=temperature,
                system_prompt=system_prompt,
                invalid_payload=data,
                schema=schema,
            )
            try:
                return schema.model_validate(repaired)
            except ValidationError:
                if self._looks_like_agent_action_schema(schema):
                    fallback = self._coerce_action_like_payload(repaired)
                    return schema.model_validate(fallback)
                raise

    def _repair_payload(
        self,
        *,
        model: str,
        temperature: float,
        system_prompt: str,
        invalid_payload: object,
        schema: Type[BaseModel],
    ) -> dict:
        schema_json = json.dumps(schema.model_json_schema(), separators=(",", ":"))
        repair_messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Your previous response did not match the required JSON schema.\n"
                    f"Schema: {schema_json}\n"
                    f"Invalid response: {json.dumps(invalid_payload, ensure_ascii=True)}\n"
                    "Return ONLY one corrected JSON object that exactly matches the schema."
                ),
            },
        ]
        response = self._chat_completion_with_retries(
            model=model,
            messages=repair_messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content or ""
        data = extract_json(text)
        if not isinstance(data, dict):
            raise ValueError("Repaired payload is not a JSON object")
        return data

    def _coerce_action_like_payload(self, payload: object) -> dict:
        if isinstance(payload, dict):
            coerced = dict(payload)
        else:
            coerced = {}
        action = coerced.get("action")
        if not isinstance(action, str):
            coerced["action"] = "execute_js"
        params = coerced.get("params")
        if not isinstance(params, dict):
            coerced["params"] = {"script": "return 'fallback';"}
        reasoning = coerced.get("reasoning")
        if not isinstance(reasoning, str) or not reasoning.strip():
            coerced["reasoning"] = "Fallback action because the model response did not follow the required schema."
        if "memory_update" not in coerced:
            coerced["memory_update"] = None
        if "intent" not in coerced:
            coerced["intent"] = "Recover from invalid model output and keep exploring."
        self._normalize_action_params(coerced)
        return coerced

    def _looks_like_agent_action_schema(self, schema: Type[BaseModel]) -> bool:
        fields = getattr(schema, "model_fields", {})
        required = {"action", "params", "reasoning"}
        return required.issubset(set(fields.keys()))

    def _normalize_action_params(self, action_obj: dict) -> None:
        action = action_obj.get("action")
        params = action_obj.get("params")
        if not isinstance(params, dict):
            params = {}
            action_obj["params"] = params
        if action == "finish" and not isinstance(params.get("summary"), str):
            summary = action_obj.get("intent") or action_obj.get("reasoning") or "Task completed."
            params["summary"] = str(summary)
        elif action in {"fail", "give_up"} and not isinstance(params.get("reason"), str):
            reason = action_obj.get("reasoning") or "Unable to proceed."
            params["reason"] = str(reason)
        elif action == "navigate" and not isinstance(params.get("url"), str):
            params["url"] = "about:blank"
        elif action == "execute_js" and not isinstance(params.get("script"), str):
            params["script"] = "return 'fallback';"

    def _chat_completion_with_retries(self, **kwargs):
        max_retries = 4
        attempt = 0
        request_kwargs = dict(kwargs)
        if not self._supports_temperature(request_kwargs.get("model", "")):
            request_kwargs.pop("temperature", None)
        while True:
            try:
                return self.client.chat.completions.create(**request_kwargs)
            except Exception as exc:
                if self._is_unsupported_temperature_error(exc) and "temperature" in request_kwargs:
                    request_kwargs.pop("temperature", None)
                    continue
                if not self._is_rate_limit_error(exc) or attempt >= max_retries:
                    raise
                retry_after = self._extract_retry_after_seconds(str(exc))
                base = retry_after if retry_after is not None else min(0.5 * (2 ** attempt), 5.0)
                sleep_for = min(base + random.uniform(0.05, 0.2), 6.0)
                time.sleep(sleep_for)
                attempt += 1

    def _is_rate_limit_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return (
            "rate limit" in text
            or "rate_limit_exceeded" in text
            or exc.__class__.__name__.lower() == "ratelimiterror"
        )

    def _extract_retry_after_seconds(self, text: str) -> float | None:
        ms_match = re.search(r"try again in\s+(\d+)ms", text, re.IGNORECASE)
        if ms_match:
            return max(float(ms_match.group(1)) / 1000.0, 0.05)
        sec_match = re.search(r"try again in\s+([0-9]*\.?[0-9]+)s", text, re.IGNORECASE)
        if sec_match:
            return max(float(sec_match.group(1)), 0.05)
        return None

    def _is_unsupported_temperature_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return "unsupported value" in text and "temperature" in text

    def _supports_temperature(self, model: str) -> bool:
        return not (model or "").startswith("gpt-5")
