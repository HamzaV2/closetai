import logging
from pathlib import Path
from typing import Any
from uuid import UUID
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.item import ClothingItem, ItemStatus
from app.models.outfit import Outfit, OutfitItem
from app.models.tryon import OutfitTryOn3DJob, TryOn3DStatus
from app.models.user import User
from app.services.ai_service import AIService, ClothingTags
from app.services.tryon_pipeline_service import GarmentInput, TryOnPipelineService

logger = logging.getLogger(__name__)
settings = get_settings()

# Module-level engine and session factory (initialized once at startup)
_engine = None
_session_factory = None


def get_engine():
    """Get or create the database engine (singleton)."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            str(settings.database_url),
            echo=settings.database_echo,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory():
    """Get or create the session factory (singleton)."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db_session() -> AsyncSession:
    """Get a database session from the pool."""
    return get_session_factory()()


def tags_to_item_fields(tags: ClothingTags, raw_response: str | None = None) -> dict[str, Any]:
    """Convert ClothingTags to item database fields."""
    # Build the tags JSONB object for frontend display
    tags_jsonb = {
        "colors": tags.colors or [],
        "pattern": tags.pattern,
        "material": tags.material,
        "style": tags.style or [],
        "season": tags.season or [],
        "formality": tags.formality,
        "fit": tags.fit,
        "occasion": tags.occasion or [],
        "brand": tags.brand,
        "condition": tags.condition,
        "features": tags.features or [],
    }

    fields = {
        "type": tags.type,
        "subtype": tags.subtype,
        "primary_color": tags.primary_color,
        "colors": tags.colors,
        "pattern": tags.pattern,
        "material": tags.material,
        "style": tags.style,
        "formality": tags.formality,
        "season": tags.season,
        "tags": tags_jsonb,  # Populate the tags JSONB field for frontend
        "ai_processed": True,
        "ai_confidence": tags.confidence,
        "ai_description": tags.description,  # Human-readable description
        "status": ItemStatus.ready,
    }
    if raw_response:
        fields["ai_raw_response"] = {"raw_text": raw_response}
    return fields


async def update_item_status_to_error(item_id: str, error_msg: str) -> None:
    """Update item status to error in database."""
    try:
        db = await get_db_session()
        try:
            result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
            item = result.scalar_one_or_none()
            if item:
                item.status = ItemStatus.error
                item.ai_raw_response = {"error": error_msg}
                await db.commit()
        finally:
            await db.close()
    except Exception as e:
        logger.error(f"Failed to update item {item_id} status to error: {e}")


async def tag_item_image(ctx: dict, item_id: str, image_path: str) -> dict[str, Any]:
    """
    Analyze an item's image and update it with AI-generated tags.

    Args:
        ctx: arq context
        item_id: UUID of the item to tag
        image_path: Path to the image file

    Returns:
        Dict with status and tags
    """
    logger.info(f"Starting AI tagging for item {item_id}")

    try:
        # Verify image exists
        path = Path(image_path)
        if not path.exists():
            error_msg = f"Image not found: {image_path}"
            logger.error(error_msg)
            await update_item_status_to_error(item_id, error_msg)
            return {"status": "error", "error": "Image not found"}

        # Get user's AI endpoints from preferences
        ai_endpoints = None
        db = await get_db_session()
        try:
            # Get the item to find user_id
            result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
            item = result.scalar_one_or_none()
            if item:
                # Get user's preferences for AI endpoints
                from app.models.preference import UserPreference

                pref_result = await db.execute(
                    select(UserPreference).where(UserPreference.user_id == item.user_id)
                )
                prefs = pref_result.scalar_one_or_none()
                if prefs and prefs.ai_endpoints:
                    ai_endpoints = prefs.ai_endpoints
                    logger.info(
                        f"Using {len(ai_endpoints)} custom AI endpoints for user {item.user_id}"
                    )
        finally:
            await db.close()

        # Analyze with AI (uses custom endpoints if available)
        ai_service = AIService(endpoints=ai_endpoints)
        tags = await ai_service.analyze_image(path)

        logger.info(
            f"AI analysis complete for item {item_id}: type={tags.type}, color={tags.primary_color}"
        )

        # Update item in database
        db = await get_db_session()
        try:
            result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
            item = result.scalar_one_or_none()

            if item is None:
                logger.error(f"Item not found: {item_id}")
                return {"status": "error", "error": "Item not found"}

            # Update item fields - only update if user hasn't already set a value
            # Always update: ai_processed, ai_confidence, status, ai_raw_response
            # Conditionally update: type, subtype, primary_color, colors, pattern, material, style, formality, season
            ai_fields = tags_to_item_fields(tags, tags.raw_response)

            for field, value in ai_fields.items():
                # Always update AI metadata fields (including tags JSONB and description)
                if field in (
                    "ai_processed",
                    "ai_confidence",
                    "status",
                    "ai_raw_response",
                    "tags",
                    "ai_description",
                ):
                    setattr(item, field, value)
                # Only update content fields if user hasn't set them (or they're default/unknown)
                elif field == "type":
                    if not item.type or item.type == "unknown":
                        setattr(item, field, value)
                elif field == "subtype":
                    if not item.subtype:
                        setattr(item, field, value)
                elif field == "primary_color":
                    if not item.primary_color or item.primary_color == "unknown":
                        setattr(item, field, value)
                else:
                    # For other fields (colors, pattern, material, style, etc.), only set if not already set
                    current_value = getattr(item, field, None)
                    if (
                        current_value is None
                        or current_value == []
                        or current_value == ""
                        or current_value == {}
                    ):
                        setattr(item, field, value)

            await db.commit()
            logger.info(f"Updated item {item_id} with AI tags (status=ready)")

            return {
                "status": "success",
                "item_id": item_id,
                "tags": tags.model_dump(exclude={"raw_response"}),
            }

        finally:
            await db.close()

    except Exception as e:
        error_msg = str(e)
        logger.exception(f"Error tagging item {item_id}: {error_msg}")
        await update_item_status_to_error(item_id, error_msg)
        return {"status": "error", "error": error_msg}


async def _update_tryon_job(
    db: AsyncSession,
    job: OutfitTryOn3DJob,
    *,
    status: str | None = None,
    step_status: dict | None = None,
    error: str | None = None,
) -> None:
    if status:
        job.status = status
    if step_status:
        merged = dict(job.step_status or {})
        merged.update(step_status)
        job.step_status = merged
    if error is not None:
        job.error = error
    if status == TryOn3DStatus.completed.value:
        job.completed_at = datetime.utcnow()
    await db.commit()


async def run_tryon_3d_pipeline(ctx: dict, job_id: str, user_prompt: str = "") -> dict[str, Any]:
    db = await get_db_session()
    try:
        result = await db.execute(
            select(OutfitTryOn3DJob)
            .where(OutfitTryOn3DJob.id == UUID(job_id))
        )
        job = result.scalar_one_or_none()
        if not job:
            raise RuntimeError(f"Try-on job not found: {job_id}")

        await _update_tryon_job(
            db,
            job,
            status=TryOn3DStatus.running.value,
            step_status={"fashn": "running", "gemini": "pending", "meshy": "pending"},
            error=None,
        )

        outfit_result = await db.execute(
            select(Outfit).where(Outfit.id == job.outfit_id, Outfit.user_id == job.user_id)
        )
        outfit = outfit_result.scalar_one_or_none()
        if not outfit:
            raise RuntimeError("Outfit not found for try-on job")

        user_result = await db.execute(select(User).where(User.id == job.user_id))
        user = user_result.scalar_one_or_none()
        if not user or not user.tryon_model_image_path:
            raise RuntimeError("User try-on model image is not configured")

        item_rows = await db.execute(
            select(OutfitItem, ClothingItem)
            .join(ClothingItem, ClothingItem.id == OutfitItem.item_id)
            .where(OutfitItem.outfit_id == outfit.id)
            .order_by(OutfitItem.position.asc())
        )
        ordered_items = item_rows.all()
        if not ordered_items:
            raise RuntimeError("Outfit has no items to render")

        model_path = Path(settings.storage_path) / user.tryon_model_image_path
        if not model_path.exists():
            raise RuntimeError("Saved try-on model image file not found")
        model_bytes = model_path.read_bytes()

        garments: list[GarmentInput] = []
        for _, item in ordered_items:
            path = Path(settings.storage_path) / item.image_path
            if not path.exists():
                logger.warning("Skipping missing outfit item image %s", path)
                continue
            garments.append(GarmentInput(item_type=item.type, image_bytes=path.read_bytes()))

        if not garments:
            raise RuntimeError("No valid outfit item images found for try-on")

        service = TryOnPipelineService()
        pipeline = await service.run_pipeline(
            model_image_bytes=model_bytes,
            garments=garments,
            user_prompt=user_prompt,
        )

        await _update_tryon_job(
            db,
            job,
            step_status={"fashn": "completed", "gemini": "completed", "meshy": "running"},
        )

        job.fashn_result_image_path = service.store_data_uri_image(job.user_id, pipeline.fashn_data_uri)
        job.gemini_texture_prompt = pipeline.gemini_texture_prompt
        job.meshy_task_id = (
            pipeline.meshy_data.get("result")
            or pipeline.meshy_data.get("id")
            or job.meshy_task_id
        )

        model_urls = pipeline.meshy_data.get("model_urls", {})
        if model_urls.get("glb"):
            glb_data = await service.download_file(model_urls["glb"])
            job.glb_path = service.store_output_bytes(job.user_id, "glb", glb_data)
        if model_urls.get("fbx"):
            fbx_data = await service.download_file(model_urls["fbx"])
            job.fbx_path = service.store_output_bytes(job.user_id, "fbx", fbx_data)
        if model_urls.get("usdz"):
            usdz_data = await service.download_file(model_urls["usdz"])
            job.usdz_path = service.store_output_bytes(job.user_id, "usdz", usdz_data)

        job.metadata_json = {"meshy": pipeline.meshy_data}
        await _update_tryon_job(
            db,
            job,
            status=TryOn3DStatus.completed.value,
            step_status={"meshy": "completed"},
        )
        return {"status": "success", "job_id": job_id}
    except Exception as e:
        logger.exception("Try-on pipeline failed for job %s: %s", job_id, e)
        try:
            result = await db.execute(select(OutfitTryOn3DJob).where(OutfitTryOn3DJob.id == UUID(job_id)))
            job = result.scalar_one_or_none()
            if job:
                await _update_tryon_job(
                    db,
                    job,
                    status=TryOn3DStatus.failed.value,
                    step_status={"fashn": "failed" if not job.fashn_result_image_path else "completed"},
                    error=str(e),
                )
        except Exception:
            logger.exception("Failed to persist try-on error state for job %s", job_id)
        return {"status": "error", "job_id": job_id, "error": str(e)}
    finally:
        await db.close()


async def startup(ctx: dict) -> None:
    """Worker startup hook."""
    logger.info("Tagging worker starting up...")
    ctx["ai_service"] = AIService()
    health = await ctx["ai_service"].check_health()
    logger.info(f"AI service health: {health}")


async def shutdown(ctx: dict) -> None:
    """Worker shutdown hook."""
    logger.info("Tagging worker shutting down...")


class WorkerSettings:
    """arq worker settings for tagging and notifications."""

    # Import notification functions
    from arq import cron

    from app.workers.notifications import (
        check_scheduled_notifications,
        retry_failed_notifications,
        send_notification,
    )

    functions = [
        tag_item_image,
        run_tryon_3d_pipeline,
        send_notification,
        retry_failed_notifications,
        check_scheduled_notifications,
    ]

    cron_jobs = [
        # Retry failed notifications every 5 minutes
        cron(retry_failed_notifications, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        # Check scheduled notifications every minute
        cron(check_scheduled_notifications, minute=None),
    ]

    on_startup = startup
    on_shutdown = shutdown

    # Import redis settings
    from app.workers.settings import get_redis_settings

    redis_settings = get_redis_settings()

    # Worker configuration
    max_jobs = 5
    job_timeout = 600  # 10 minutes per job (Pi's tinyllama is slow)
    max_tries = 3
    health_check_interval = 30

    # Queue name - must match the queue used in items.py
    queue_name = "arq:tagging"
