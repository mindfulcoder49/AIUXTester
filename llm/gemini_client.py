from typing import List, Type

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from config import GEMINI_API_KEY
from llm.utils import extract_json


class GeminiClient:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not set")
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def _build_parts(self, user_prompt: str, images: List[bytes]):
        parts = []
        for img in images:
            parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))
        parts.append(user_prompt)
        return parts

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
        response = self.client.models.generate_content(
            model=model,
            contents=self._build_parts(user_prompt, images),
            config={
                "system_instruction": system_prompt,
                "temperature": temperature,
                "response_mime_type": "application/json",
                "response_json_schema": schema.model_json_schema(),
            },
        )
        text = response.text or ""
        try:
            return schema.model_validate_json(text)
        except ValidationError:
            data = extract_json(text)
            return schema.model_validate(data)
