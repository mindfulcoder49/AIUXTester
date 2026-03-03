from typing import List, Type

import google.generativeai as genai
from pydantic import BaseModel

from config import GEMINI_API_KEY
from llm.utils import extract_json


class GeminiClient:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not set")
        genai.configure(api_key=GEMINI_API_KEY)

    def _build_parts(self, user_prompt: str, images: List[bytes]):
        parts = [user_prompt]
        for img in images:
            try:
                from google.generativeai.types import Part
                parts.append(Part.from_data(data=img, mime_type="image/png"))
            except Exception:
                parts.append(f"[image/png {len(img)} bytes not attached]")
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
        model_obj = genai.GenerativeModel(model=model, system_instruction=system_prompt)
        response = model_obj.generate_content(
            self._build_parts(user_prompt, images),
            generation_config={"temperature": temperature},
        )
        text = response.text or ""
        data = extract_json(text)
        return schema.model_validate(data)
