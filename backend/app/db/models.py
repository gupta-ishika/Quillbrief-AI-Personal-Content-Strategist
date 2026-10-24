from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_uuid, utc_now


class Creator(Base):
    __tablename__ = "creators"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    display_name: Mapped[str] = mapped_column(String(200), default="Creator")
    audience_level: Mapped[str] = mapped_column(String(50), default="intermediate")
    youtube_channel_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    youtube_channel_handle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    youtube_channel_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    youtube_channel_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    instagram_account_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    goals: Mapped[list["Goal"]] = relationship("Goal", back_populates="creator")
    content_items: Mapped[list["ContentItem"]] = relationship(
        "ContentItem", back_populates="creator"
    )
    comment_insights: Mapped[list["CommentInsight"]] = relationship(
        "CommentInsight", back_populates="creator"
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    creator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("creators.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    creator: Mapped["Creator"] = relationship("Creator", back_populates="goals")
    runs: Mapped[list["Run"]] = relationship("Run", back_populates="goal")


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "run_type IN ('goal', 'weekly_brief', 'post_mortem')", name="ck_runs_run_type"
        ),
        CheckConstraint("depth_level IN ('quick', 'standard', 'deep')", name="ck_runs_depth_level"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'WAITING_APPROVAL', 'COMPLETED', 'FAILED', 'STOPPED', 'INTERRUPTED')",
            name="ck_runs_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    goal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("goals.id", ondelete="SET NULL"), nullable=True
    )
    run_type: Mapped[str] = mapped_column(String(50), default="goal")
    depth_level: Mapped[str] = mapped_column(String(50), default="standard")
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    thread_id: Mapped[str] = mapped_column(String(100), default=generate_uuid)
    step_count: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    stop_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    degraded_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    goal: Mapped["Goal | None"] = relationship("Goal", back_populates="runs")
    tasks: Mapped[list["Task"]] = relationship(
        "Task", back_populates="run", cascade="all, delete-orphan"
    )
    routing_logs: Mapped[list["RoutingLog"]] = relationship(
        "RoutingLog", back_populates="run", cascade="all, delete-orphan"
    )
    run_events: Mapped[list["RunEvent"]] = relationship(
        "RunEvent", back_populates="run", cascade="all, delete-orphan"
    )
    token_usage: Mapped[list["TokenUsage"]] = relationship(
        "TokenUsage", back_populates="run", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["Approval"]] = relationship("Approval", back_populates="run")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("status IN ('TODO', 'DONE', 'SKIPPED', 'FAILED')", name="ck_tasks_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    agent: Mapped[str] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="TODO")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    run: Mapped["Run"] = relationship("Run", back_populates="tasks")


class RoutingLog(Base):
    __tablename__ = "routing_logs"
    __table_args__ = (
        CheckConstraint("decided_by IN ('model', 'code')", name="ck_routing_logs_decided_by"),
        CheckConstraint(
            "output_status IN ('valid', 'retried_valid', 'fallback')",
            name="ck_routing_logs_output_status",
        ),
        CheckConstraint(
            "invalid_category IS NULL OR invalid_category IN ('bad_json', 'schema_violation', 'ineligible_node', 'timeout')",
            name="ck_routing_logs_invalid_category",
        ),
        Index("ix_routing_logs_run_step", "run_id", "step_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id", ondelete="CASCADE"))
    step_number: Mapped[int] = mapped_column(Integer)
    from_node: Mapped[str] = mapped_column(String(100))
    to_node: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(String(50))
    eligible_nodes_json: Mapped[Any] = mapped_column(JSON)
    output_status: Mapped[str] = mapped_column(String(50))
    invalid_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    run: Mapped["Run"] = relationship("Run", back_populates="routing_logs")


class TokenUsage(Base):
    __tablename__ = "token_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id", ondelete="CASCADE"))
    node: Mapped[str] = mapped_column(String(100))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    run: Mapped["Run"] = relationship("Run", back_populates="token_usage")


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('tool_result', 'tool_error', 'limit_reached', 'model_fallback', 'recovery', 'note')",
            name="ck_run_events_event_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(50))
    payload_json: Mapped[Any] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    run: Mapped["Run"] = relationship("Run", back_populates="run_events")


class ContentItem(Base):
    __tablename__ = "content_items"
    __table_args__ = (
        CheckConstraint("owner_type IN ('own', 'similar')", name="ck_content_items_owner_type"),
        UniqueConstraint("platform", "external_id", name="uq_content_items_platform_external_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    creator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("creators.id", ondelete="CASCADE")
    )
    platform: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(200))
    owner_type: Mapped[str] = mapped_column(String(50))
    channel_external_id: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    creator: Mapped["Creator"] = relationship("Creator", back_populates="content_items")
    comments: Mapped[list["Comment"]] = relationship(
        "Comment", back_populates="content_item", cascade="all, delete-orphan"
    )


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        UniqueConstraint("content_item_id", "external_id", name="uq_comments_item_external_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    content_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_items.id", ondelete="CASCADE")
    )
    external_id: Mapped[str] = mapped_column(String(200))
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cluster_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    content_item: Mapped["ContentItem"] = relationship("ContentItem", back_populates="comments")


class CommentInsight(Base):
    __tablename__ = "comment_insights"
    __table_args__ = (
        CheckConstraint("status IN ('current', 'superseded')", name="ck_comment_insights_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    creator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("creators.id", ondelete="CASCADE")
    )
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id", ondelete="CASCADE"))
    theme_label: Mapped[str] = mapped_column(String(200))
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    coverage_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    coverage_total: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="current")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    creator: Mapped["Creator"] = relationship("Creator", back_populates="comment_insights")
    sources: Mapped[list["CommentInsightSource"]] = relationship(
        "CommentInsightSource", back_populates="insight", cascade="all, delete-orphan"
    )
    examples: Mapped[list["CommentInsightExample"]] = relationship(
        "CommentInsightExample", back_populates="insight", cascade="all, delete-orphan"
    )


class CommentInsightSource(Base):
    __tablename__ = "comment_insight_sources"

    insight_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("comment_insights.id", ondelete="CASCADE"), primary_key=True
    )
    content_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True
    )

    insight: Mapped["CommentInsight"] = relationship("CommentInsight", back_populates="sources")
    content_item: Mapped["ContentItem"] = relationship("ContentItem")


class CommentInsightExample(Base):
    __tablename__ = "comment_insight_examples"

    insight_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("comment_insights.id", ondelete="CASCADE"), primary_key=True
    )
    comment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("comments.id", ondelete="CASCADE"), primary_key=True
    )

    insight: Mapped["CommentInsight"] = relationship("CommentInsight", back_populates="examples")
    comment: Mapped["Comment"] = relationship("Comment")


class ResearchFinding(Base):
    __tablename__ = "research_findings"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('opportunity', 'similar_creator', 'trend', 'gap')",
            name="ck_research_findings_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(50))
    topic: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[Any] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ContentPlan(Base):
    __tablename__ = "content_plans"
    __table_args__ = (
        CheckConstraint(
            "created_by IN ('strategist', 'creator')", name="ck_content_plans_created_by"
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'SUPERSEDED')",
            name="ck_content_plans_status",
        ),
        UniqueConstraint("lineage_id", "version", name="uq_content_plans_lineage_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    lineage_id: Mapped[str] = mapped_column(String(36), default=generate_uuid)
    version: Mapped[int] = mapped_column(Integer, default=1)
    previous_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("content_plans.id", ondelete="SET NULL"), nullable=True
    )
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id", ondelete="CASCADE"))
    created_by: Mapped[str] = mapped_column(String(50), default="strategist")
    status: Mapped[str] = mapped_column(String(50), default="DRAFT")
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["PlanItem"]] = relationship(
        "PlanItem", back_populates="plan", cascade="all, delete-orphan"
    )


class PlanItem(Base):
    __tablename__ = "plan_items"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('comment', 'similar_creator', 'own_idea')",
            name="ck_plan_items_source_type",
        ),
        CheckConstraint(
            "status IN ('PLANNED', 'DRAFTING', 'DONE', 'DROPPED')", name="ck_plan_items_status"
        ),
        UniqueConstraint("plan_id", "item_key", name="uq_plan_items_plan_item_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_plans.id", ondelete="CASCADE")
    )
    item_key: Mapped[str] = mapped_column(String(100), default=generate_uuid)
    topic: Mapped[str] = mapped_column(String(200))
    format: Mapped[str] = mapped_column(String(50))
    platform: Mapped[str] = mapped_column(String(50))
    objective: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(50))
    source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    scheduled_day: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="PLANNED")

    plan: Mapped["ContentPlan"] = relationship("ContentPlan", back_populates="items")


class Draft(Base):
    __tablename__ = "drafts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('script', 'title', 'description', 'community_post', 'caption', 'linkedin_post', 'x_thread')",
            name="ck_drafts_kind",
        ),
        CheckConstraint("created_by IN ('model', 'creator')", name="ck_drafts_created_by"),
        CheckConstraint(
            "status IN ('WRITING', 'IN_REVIEW', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'SUPERSEDED', 'POSTED')",
            name="ck_drafts_status",
        ),
        CheckConstraint(
            "posted_ref IS NULL OR posted_ref IN ('url', 'platform_id', 'none')",
            name="ck_drafts_posted_ref",
        ),
        UniqueConstraint("lineage_id", "version", name="uq_drafts_lineage_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    lineage_id: Mapped[str] = mapped_column(String(36), default=generate_uuid)
    version: Mapped[int] = mapped_column(Integer, default=1)
    previous_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("drafts.id", ondelete="SET NULL"), nullable=True
    )
    plan_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("plan_items.id", ondelete="SET NULL"), nullable=True
    )
    item_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parent_draft_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("drafts.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(50))
    platform: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(50), default="model")
    status: Mapped[str] = mapped_column(String(50), default="WRITING")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_ref: Mapped[str | None] = mapped_column(String(50), nullable=True)
    posted_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    posted_platform_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(
            "item_type IN ('plan', 'draft', 'depth_increase')", name="ck_approvals_item_type"
        ),
        CheckConstraint(
            "status IN ('PENDING', 'DECIDED', 'CANCELLED')", name="ck_approvals_status"
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('APPROVED', 'REJECTED', 'EDITED')",
            name="ck_approvals_decision",
        ),
        Index("ix_approvals_status_requested", "status", "requested_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=True
    )
    item_type: Mapped[str] = mapped_column(String(50))
    item_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    decision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    resulting_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped["Run | None"] = relationship("Run", back_populates="approvals")


class CacheEntry(Base):
    __tablename__ = "cache_entries"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
