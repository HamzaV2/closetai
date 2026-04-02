import base64
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import httpx

from app.config import get_settings
from app.services.fashn_service import FashnService, preprocess_image_to_data_uri
from app.services.gemini_service import GeminiService
from app.services.meshy_service import MeshyService

settings = get_settings()

CHAIN_PROMPTS = {
    "bottom": "wearing the bottom garment",
    "top": "tuck in shirt if appropriate",
    "outerwear": "drape jacket open over the outfit",
    "scarf_hat": (
        "scarf loosely around neck if available in the image, "
        "hat on head if available in the image"
    ),
    "shoes": "wearing the shoes",
}

TYPE_TO_SLOT = {
    "pants": "bottom",
    "jeans": "bottom",
    "shorts": "bottom",
    "skirt": "bottom",
    "dress": "bottom",
    "shirt": "top",
    "t-shirt": "top",
    "blouse": "top",
    "sweater": "top",
    "hoodie": "top",
    "jacket": "outerwear",
    "coat": "outerwear",
    "blazer": "outerwear",
    "cardigan": "outerwear",
    "scarf": "scarf_hat",
    "hat": "scarf_hat",
    "cap": "scarf_hat",
    "shoes": "shoes",
    "sneakers": "shoes",
    "boots": "shoes",
    "sandals": "shoes",
}


@dataclass
class GarmentInput:
    item_type: str
    image_bytes: bytes


@dataclass
class TryOnPipelineResult:
    fashn_data_uri: str
    gemini_texture_prompt: str
    meshy_data: dict


def decode_data_uri(data_uri: str) -> bytes:
    encoded = data_uri.split(",", 1)[1] if "," in data_uri else data_uri
    return base64.b64decode(encoded)


class TryOnPipelineService:
    def __init__(self) -> None:
        self.fashn = FashnService()
        self.gemini = GeminiService()
        self.meshy = MeshyService()

    def _sort_garments(self, garments: list[GarmentInput]) -> list[GarmentInput]:
        order = ["bottom", "top", "outerwear", "scarf_hat", "shoes"]

        def slot_for(item_type: str) -> str:
            return TYPE_TO_SLOT.get(item_type.lower(), "top")

        return sorted(garments, key=lambda g: order.index(slot_for(g.item_type)))

    async def run_pipeline(
        self,
        model_image_bytes: bytes,
        garments: list[GarmentInput],
        user_prompt: str = "",
    ) -> TryOnPipelineResult:
        if not garments:
            raise RuntimeError("No garment images provided for try-on")

        current_b64 = preprocess_image_to_data_uri(model_image_bytes)
        ordered_garments = self._sort_garments(garments)

        for garment in ordered_garments:
            garment_b64 = preprocess_image_to_data_uri(garment.image_bytes)
            slot = TYPE_TO_SLOT.get(garment.item_type.lower(), "top")
            prompt = " ".join(
                filter(None, [CHAIN_PROMPTS.get(slot, "wearing the garment"), user_prompt.strip()])
            )
            prediction_id = await self.fashn.submit(current_b64, garment_b64, prompt)
            current_b64 = await self.fashn.wait_for_result(prediction_id)

        gemini_prompt = await self.gemini.generate_meshy_texture_prompt(current_b64)
        meshy_task_id = await self.meshy.submit(
            image_data_uri=current_b64,
            texture_prompt=gemini_prompt,
            remove_lighting=True,
            enable_pbr=True,
        )
        meshy_data = await self.meshy.wait_for_result(meshy_task_id)
        return TryOnPipelineResult(
            fashn_data_uri=current_b64,
            gemini_texture_prompt=gemini_prompt,
            meshy_data=meshy_data,
        )

    async def download_file(self, url: str) -> bytes:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    def store_output_bytes(self, user_id: UUID, suffix: str, data: bytes) -> str:
        user_folder = Path(settings.storage_path) / str(user_id) / "tryon3d"
        user_folder.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid4().hex}.{suffix}"
        full_path = user_folder / filename
        full_path.write_bytes(data)
        return f"{user_id}/tryon3d/{filename}"

    def store_data_uri_image(self, user_id: UUID, data_uri: str) -> str:
        png_bytes = decode_data_uri(data_uri)
        return self.store_output_bytes(user_id, "png", png_bytes)
