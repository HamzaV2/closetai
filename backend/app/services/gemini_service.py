import base64
from io import BytesIO

import httpx
from PIL import Image

from app.config import get_settings

settings = get_settings()

GEMINI_MESHY_SYSTEM = (
    "You are a 3D texturing expert. Analyze the fashion photo and write a concise "
    "Meshy texture prompt (max 200 characters) describing fabrics, materials, colors, "
    "and finish. Output only the prompt text."
)


def image_data_uri_to_base64(data_uri: str) -> str:
    if "," in data_uri:
        return data_uri.split(",", 1)[1]
    return data_uri


def image_base64_to_jpeg_base64(image_base64: str) -> str:
    raw = base64.b64decode(image_base64)
    image = Image.open(BytesIO(raw))
    if image.mode != "RGB":
        image = image.convert("RGB")
    output = BytesIO()
    image.save(output, format="JPEG", quality=92)
    return base64.b64encode(output.getvalue()).decode()


class GeminiService:
    def __init__(self) -> None:
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model

    async def generate_meshy_texture_prompt(self, image_data_uri: str) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not configured")

        image_b64 = image_data_uri_to_base64(image_data_uri)
        jpeg_b64 = image_base64_to_jpeg_base64(image_b64)
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )

        payload = {
            "system_instruction": {"parts": [{"text": GEMINI_MESHY_SYSTEM}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": "Analyze this outfit photo and write the Meshy texture prompt."},
                        {"inline_data": {"mime_type": "image/jpeg", "data": jpeg_b64}},
                    ],
                }
            ],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 300},
        }

        async with httpx.AsyncClient(timeout=settings.ai_timeout) as client:
            response = await client.post(url, json=payload)
            if response.status_code >= 400:
                raise RuntimeError(f"Gemini error {response.status_code}: {response.text}")
            data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")

        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
        if not text:
            raise RuntimeError("Gemini returned empty prompt")
        return text.strip('"').strip("'")[:600]
