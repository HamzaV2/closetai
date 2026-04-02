import asyncio
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()


class MeshyService:
    def __init__(self) -> None:
        self.api_key = settings.meshy_api_key
        self.url = settings.meshy_image_to_3d_url
        self.timeout = settings.ai_timeout

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("MESHY_API_KEY not configured")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def submit(
        self,
        image_data_uri: str,
        texture_prompt: str = "",
        remove_lighting: bool = True,
        enable_pbr: bool = True,
    ) -> str:
        payload: dict[str, Any] = {
            "image_url": image_data_uri,
            "ai_model": "meshy-6",
            "topology": "quad",
            "should_remesh": True,
            "should_texture": True,
            "enable_pbr": enable_pbr,
            "remove_lighting": remove_lighting,
        }
        if texture_prompt.strip():
            payload["texture_prompt"] = texture_prompt.strip()[:600]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.url, headers=self._headers(), json=payload)
            if response.status_code not in (200, 201, 202):
                raise RuntimeError(f"Meshy error {response.status_code}: {response.text}")
            data = response.json()

        task_id = data.get("result") or data.get("id")
        if not task_id:
            raise RuntimeError("Meshy did not return task id")
        return task_id

    async def poll(self, task_id: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.url}/{task_id}", headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def wait_for_result(self, task_id: str, timeout_seconds: int = 600) -> dict:
        elapsed = 0
        while elapsed < timeout_seconds:
            data = await self.poll(task_id)
            status = str(data.get("status", "")).upper()
            if status == "SUCCEEDED":
                return data
            if status in ("FAILED", "EXPIRED"):
                raise RuntimeError(f"Meshy task {status.lower()}")
            elapsed += 5
            await asyncio.sleep(5)
        raise TimeoutError("Meshy timed out after 10 minutes")
