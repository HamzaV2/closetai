import base64
import asyncio
import logging
from io import BytesIO

import httpx
from PIL import Image, ImageOps

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def preprocess_image_to_data_uri(image_bytes: bytes, max_px: int = 1024) -> str:
    image = Image.open(BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="JPEG", quality=92)
    encoded = base64.b64encode(output.getvalue()).decode()
    return f"data:image/jpeg;base64,{encoded}"


class FashnService:
    def __init__(self) -> None:
        self.api_key = settings.fashn_api_key
        self.run_url = settings.fashn_run_url
        self.status_url = settings.fashn_status_url
        self.timeout = settings.ai_timeout

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("FASHN_API_KEY not configured")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def submit(self, model_image_b64: str, product_image_b64: str, prompt: str) -> str:
        payload = {
            "model_name": "tryon-max",
            "inputs": {
                "model_image": model_image_b64,
                "product_image": product_image_b64,
                "prompt": prompt,
                "resolution": "1k",
                "generation_mode": "balanced",
                "output_format": "png",
                "return_base64": True,
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.run_url, headers=self._headers(), json=payload)
            if response.status_code not in (200, 201, 202):
                raise RuntimeError(f"Fashn error {response.status_code}: {response.text}")
            prediction_id = response.json().get("id")
            if not prediction_id:
                raise RuntimeError("Fashn did not return prediction id")
            return prediction_id

    async def poll(self, prediction_id: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.status_url}/{prediction_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            return response.json()

    async def wait_for_result(self, prediction_id: str, timeout_seconds: int = 600) -> str:
        elapsed = 0
        while elapsed < timeout_seconds:
            data = await self.poll(prediction_id)
            status = str(data.get("status", "")).lower()
            if status == "completed":
                output = data.get("output", [])
                if not output:
                    raise RuntimeError("Fashn returned empty output")
                result = output[0]
                if isinstance(result, str) and result.startswith("data:"):
                    return result
                return f"data:image/png;base64,{result}"
            if status in ("failed", "error"):
                raise RuntimeError(data.get("error", "Fashn request failed"))
            elapsed += 5
            await asyncio.sleep(5)
        raise TimeoutError("Fashn timed out after 10 minutes")
