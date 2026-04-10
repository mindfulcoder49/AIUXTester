import base64
from typing import List, Type

import anthropic
from pydantic import BaseModel, ValidationError

from config import ANTHROPIC_API_KEY
from llm.utils import extract_json


class ClaudeClient:
    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def _encode_images(self, images: List[bytes]):
        content = []
        for img in images:
            b64 = base64.b64encode(img).decode("utf-8")
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64},
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
            {
                "role": "user",
                "content": [
                    *self._encode_images(images),
                    {"type": "text", "text": user_prompt},
                ],
            }
        ]
        response = self.client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=temperature,
            system=system_prompt,
            messages=messages,
        )
        text = "".join([block.text for block in response.content if getattr(block, "text", None)])
        data = extract_json(text)
        try:
            return schema.model_validate(data)
        except ValidationError:
            if isinstance(data, str):
                return schema.model_validate_json(data)
            raise
