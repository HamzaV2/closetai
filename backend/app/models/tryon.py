import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.outfit import Outfit
    from app.models.user import User


class TryOn3DStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    failed = "failed"
    completed = "completed"


class OutfitTryOn3DJob(Base):
    __tablename__ = "outfit_tryon_3d_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    outfit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outfits.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[str] = mapped_column(String(20), default=TryOn3DStatus.queued.value, index=True)
    step_status: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)

    # Outputs from each pipeline phase
    fashn_result_image_path: Mapped[str | None] = mapped_column(String(500))
    gemini_texture_prompt: Mapped[str | None] = mapped_column(Text)
    meshy_task_id: Mapped[str | None] = mapped_column(String(255))
    glb_path: Mapped[str | None] = mapped_column(String(500))
    fbx_path: Mapped[str | None] = mapped_column(String(500))
    usdz_path: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship("User", back_populates="tryon_jobs")
    outfit: Mapped["Outfit"] = relationship("Outfit", back_populates="tryon_jobs")
