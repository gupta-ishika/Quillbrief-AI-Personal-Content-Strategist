"""create_critic_evaluations_table

Revision ID: a70eaf65ceb1
Revises: 1acdbc5cf370
Create Date: 2026-10-27 18:04:17.099751

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a70eaf65ceb1"
down_revision: str | Sequence[str] | None = "1acdbc5cf370"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "critic_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("draft_id", sa.String(length=36), nullable=False),
        sa.Column("review_number", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("rubric_json", sa.JSON(), nullable=False),
        sa.Column("deterministic_json", sa.JSON(), nullable=False),
        sa.Column("feedback_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "review_number BETWEEN 1 AND 3",
            name=op.f("ck_critic_evaluations_`ck_critic_evaluations_review_number`"),
        ),
        sa.ForeignKeyConstraint(
            ["draft_id"],
            ["drafts.id"],
            name=op.f("fk_critic_evaluations_draft_id_drafts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_critic_evaluations")),
        sa.UniqueConstraint("draft_id", name=op.f("uq_critic_evaluations_draft_id")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("critic_evaluations")
