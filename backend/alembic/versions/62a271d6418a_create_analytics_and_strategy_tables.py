"""create_analytics_and_strategy_tables

Revision ID: 62a271d6418a
Revises: a70eaf65ceb1
Create Date: 2026-11-09 09:42:07.392810

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '62a271d6418a'
down_revision: str | Sequence[str] | None = 'a70eaf65ceb1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "performance_metrics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("draft_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("metric_name", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('public', 'owner')",
            name=op.f("ck_performance_metrics_`ck_performance_metrics_source`"),
        ),
        sa.ForeignKeyConstraint(
            ["draft_id"],
            ["drafts.id"],
            name=op.f("fk_performance_metrics_draft_id_drafts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_performance_metrics")),
        sa.UniqueConstraint(
            "draft_id",
            "metric_name",
            "collected_at",
            name=op.f("uq_performance_metrics_draft_id"),
        ),
    )

    op.create_table(
        "analyst_findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("draft_id", sa.String(length=36), nullable=True),
        sa.Column("finding", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=50), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence IN ('low', 'moderate', 'high')",
            name=op.f("ck_analyst_findings_`ck_analyst_findings_confidence`"),
        ),
        sa.ForeignKeyConstraint(
            ["draft_id"],
            ["drafts.id"],
            name=op.f("fk_analyst_findings_draft_id_drafts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name=op.f("fk_analyst_findings_run_id_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analyst_findings")),
    )

    op.create_table(
        "strategy_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("creator_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("supporting_finding_ids_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'superseded')",
            name=op.f("ck_strategy_entries_`ck_strategy_entries_status`"),
        ),
        sa.ForeignKeyConstraint(
            ["creator_id"],
            ["creators.id"],
            name=op.f("fk_strategy_entries_creator_id_creators"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategy_entries")),
    )
    op.create_index(
        "ix_strategy_entries_creator_key_status",
        "strategy_entries",
        ["creator_id", "key", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_strategy_entries_creator_key_status", table_name="strategy_entries")
    op.drop_table("strategy_entries")
    op.drop_table("analyst_findings")
    op.drop_table("performance_metrics")
