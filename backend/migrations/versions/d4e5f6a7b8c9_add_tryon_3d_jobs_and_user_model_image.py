from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "45702c628c1f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tryon_model_image_path", sa.String(length=500), nullable=True))

    op.create_table(
        "outfit_tryon_3d_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outfit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("step_status", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("fashn_result_image_path", sa.String(length=500), nullable=True),
        sa.Column("gemini_texture_prompt", sa.Text(), nullable=True),
        sa.Column("meshy_task_id", sa.String(length=255), nullable=True),
        sa.Column("glb_path", sa.String(length=500), nullable=True),
        sa.Column("fbx_path", sa.String(length=500), nullable=True),
        sa.Column("usdz_path", sa.String(length=500), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["outfit_id"], ["outfits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_outfit_tryon_3d_jobs_status", "outfit_tryon_3d_jobs", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_outfit_tryon_3d_jobs_status", table_name="outfit_tryon_3d_jobs")
    op.drop_table("outfit_tryon_3d_jobs")
    op.drop_column("users", "tryon_model_image_path")
