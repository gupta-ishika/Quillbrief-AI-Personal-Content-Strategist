import logging
from datetime import datetime
from typing import Any

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import (
    Comment,
    CommentInsight,
    CommentInsightExample,
    CommentInsightSource,
)
from app.db.repositories.content import (
    create_comment,
    get_current_insights_for_channel,
    upsert_content_item,
)
from app.db.repositories.plans import (
    create_draft_version,
    create_plan_version,
    get_latest_draft_version,
    get_latest_plan_version,
)
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def _with_session(db: Session | None) -> tuple[Session, bool]:
    if db is not None:
        return db, False
    return SessionLocal(), True


def save_content_item(
    creator_id: str,
    platform: str,
    external_id: str,
    owner_type: str,
    channel_external_id: str,
    title: str,
    description: str = "",
    published_at: datetime | None = None,
    transcript_text: str | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Saves or updates a content item with provenance tracking (UT-32)."""
    session, should_close = _with_session(db)
    try:
        item = upsert_content_item(
            db=session,
            creator_id=creator_id,
            platform=platform,
            external_id=external_id,
            owner_type=owner_type,
            channel_external_id=channel_external_id,
            title=title,
            description=description,
            published_at=published_at,
            transcript_text=transcript_text,
        )
        return {
            "content_item_id": item.id,
            "platform": item.platform,
            "external_id": item.external_id,
            "owner_type": item.owner_type,
            "title": item.title,
            "source": "database",
            "timestamp": utc_now().isoformat(),
        }
    finally:
        if should_close:
            session.close()


def save_comments_batch(
    content_item_id: str,
    comments: list[dict[str, Any]],
    db: Session | None = None,
) -> dict[str, Any]:
    """Persists a list of comments for a content item with provenance tracking."""
    session, should_close = _with_session(db)
    try:
        saved_count = 0
        for c in comments:
            ext_id = str(c.get("comment_id") or c.get("external_id") or "")
            text = c.get("text")
            likes = int(c.get("like_count") or c.get("likes") or 0)
            replies = c.get("reply_count") or c.get("replies")
            published_at = c.get("published_at")
            if ext_id:
                create_comment(
                    db=session,
                    content_item_id=content_item_id,
                    external_id=ext_id,
                    text=text,
                    like_count=likes,
                    reply_count=replies,
                    published_at=published_at,
                )
                saved_count += 1
        return {
            "saved_count": saved_count,
            "content_item_id": content_item_id,
            "source": "database",
            "timestamp": utc_now().isoformat(),
        }
    finally:
        if should_close:
            session.close()


def save_comment_insights(
    creator_id: str,
    run_id: str,
    themes: list[dict[str, Any]],
    source_content_item_ids: list[str],
    db: Session | None = None,
) -> dict[str, Any]:
    """Persists synthesized comment insights, linking sources and example references (ADR-033)."""
    session, should_close = _with_session(db)
    try:
        saved_insights: list[dict[str, Any]] = []
        for theme_data in themes:
            theme_label = str(theme_data["theme_label"])
            comment_count = int(theme_data["comment_count"])
            cov_analyzed = int(theme_data.get("coverage_analyzed", comment_count))
            cov_total = int(theme_data.get("coverage_total", comment_count))
            ex_ids = list(theme_data.get("example_comment_ids", []))

            # Supersede older insights with exact same label for this creator
            session.query(CommentInsight).filter(
                CommentInsight.creator_id == creator_id,
                CommentInsight.theme_label == theme_label,
                CommentInsight.status == "current",
            ).update({"status": "superseded"})

            insight = CommentInsight(
                creator_id=creator_id,
                run_id=run_id,
                theme_label=theme_label,
                comment_count=comment_count,
                coverage_analyzed=cov_analyzed,
                coverage_total=cov_total,
                status="current",
            )
            session.add(insight)
            session.flush()

            # Link sources
            for item_id in source_content_item_ids:
                src = CommentInsightSource(insight_id=insight.id, content_item_id=item_id)
                session.add(src)

            # Link example comments by reference
            for c_id in ex_ids:
                ex = CommentInsightExample(insight_id=insight.id, comment_id=c_id)
                session.add(ex)

            saved_insights.append(
                {
                    "insight_id": insight.id,
                    "theme_label": insight.theme_label,
                    "comment_count": insight.comment_count,
                    "example_count": len(ex_ids),
                }
            )

        session.commit()
        return {
            "insights": saved_insights,
            "count": len(saved_insights),
            "source": "database",
            "timestamp": utc_now().isoformat(),
        }
    finally:
        if should_close:
            session.close()


def load_channel_insights(
    channel_external_id: str,
    db: Session | None = None,
) -> dict[str, Any]:
    """Loads current insights for the active channel (enforcing ADR-032 channel rule)."""
    session, should_close = _with_session(db)
    try:
        insights = get_current_insights_for_channel(session, channel_external_id)
        results: list[dict[str, Any]] = []

        for ins in insights:
            # Examples by reference: retrieve text if not cleared (ADR-033)
            examples_data = []
            for ex in ins.examples:
                cmt = session.query(Comment).filter_by(id=ex.comment_id).first()
                if cmt and cmt.text:
                    examples_data.append(
                        {
                            "comment_id": cmt.id,
                            "text": cmt.text,
                            "like_count": cmt.like_count,
                        }
                    )
                else:
                    examples_data.append(
                        {
                            "comment_id": ex.comment_id,
                            "text": None,
                            "status": "unavailable_retention_cleared",
                        }
                    )

            results.append(
                {
                    "id": ins.id,
                    "theme_label": ins.theme_label,
                    "comment_count": ins.comment_count,
                    "coverage_analyzed": ins.coverage_analyzed,
                    "coverage_total": ins.coverage_total,
                    "examples": examples_data,
                    "created_at": ins.created_at.isoformat() if ins.created_at else None,
                }
            )

        return {
            "insights": results,
            "channel_external_id": channel_external_id,
            "source": "database",
            "timestamp": utc_now().isoformat(),
        }
    finally:
        if should_close:
            session.close()


def save_plan_version(
    lineage_id: str,
    version: int,
    run_id: str,
    items: list[dict[str, Any]],
    created_by: str = "strategist",
    previous_version_id: str | None = None,
    status: str = "DRAFT",
    feedback_text: str | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Saves a plan version with immutable lineage and item identity (ADR-029, VER-01)."""
    session, should_close = _with_session(db)
    try:
        plan = create_plan_version(
            db=session,
            lineage_id=lineage_id,
            version=version,
            run_id=run_id,
            items=items,
            created_by=created_by,
            previous_version_id=previous_version_id,
            status=status,
            feedback_text=feedback_text,
        )
        return {
            "plan_id": plan.id,
            "lineage_id": plan.lineage_id,
            "version": plan.version,
            "status": plan.status,
            "item_count": len(plan.items),
            "source": "database",
            "timestamp": utc_now().isoformat(),
        }
    finally:
        if should_close:
            session.close()


def load_latest_plan(
    lineage_id: str,
    db: Session | None = None,
) -> dict[str, Any]:
    """Loads latest plan and items for a given lineage."""
    session, should_close = _with_session(db)
    try:
        plan = get_latest_plan_version(session, lineage_id)
        if not plan:
            return {
                "plan": None,
                "lineage_id": lineage_id,
                "source": "database",
                "timestamp": utc_now().isoformat(),
            }

        items_data = [
            {
                "id": it.id,
                "item_key": it.item_key,
                "topic": it.topic,
                "format": it.format,
                "platform": it.platform,
                "objective": it.objective,
                "reason": it.reason,
                "source_type": it.source_type,
                "source_ref": it.source_ref,
                "priority": it.priority,
                "status": it.status,
            }
            for it in plan.items
        ]

        return {
            "plan": {
                "id": plan.id,
                "lineage_id": plan.lineage_id,
                "version": plan.version,
                "status": plan.status,
                "items": items_data,
                "created_at": plan.created_at.isoformat() if plan.created_at else None,
            },
            "source": "database",
            "timestamp": utc_now().isoformat(),
        }
    finally:
        if should_close:
            session.close()


def save_draft_version(
    lineage_id: str,
    version: int,
    kind: str,
    platform: str,
    content: str,
    created_by: str = "model",
    plan_item_id: str | None = None,
    item_key: str | None = None,
    previous_version_id: str | None = None,
    status: str = "WRITING",
    db: Session | None = None,
) -> dict[str, Any]:
    """Saves a draft version with immutable lineage (VER-02)."""
    session, should_close = _with_session(db)
    try:
        draft = create_draft_version(
            db=session,
            lineage_id=lineage_id,
            version=version,
            kind=kind,
            platform=platform,
            content=content,
            created_by=created_by,
            plan_item_id=plan_item_id,
            item_key=item_key,
            previous_version_id=previous_version_id,
            status=status,
        )
        return {
            "draft_id": draft.id,
            "lineage_id": draft.lineage_id,
            "version": draft.version,
            "status": draft.status,
            "kind": draft.kind,
            "source": "database",
            "timestamp": utc_now().isoformat(),
        }
    finally:
        if should_close:
            session.close()


def load_latest_draft(
    lineage_id: str,
    db: Session | None = None,
) -> dict[str, Any]:
    """Loads latest draft for a lineage."""
    session, should_close = _with_session(db)
    try:
        draft = get_latest_draft_version(session, lineage_id)
        if not draft:
            return {
                "draft": None,
                "lineage_id": lineage_id,
                "source": "database",
                "timestamp": utc_now().isoformat(),
            }

        return {
            "draft": {
                "id": draft.id,
                "lineage_id": draft.lineage_id,
                "version": draft.version,
                "kind": draft.kind,
                "platform": draft.platform,
                "content": draft.content,
                "status": draft.status,
                "created_at": draft.created_at.isoformat() if draft.created_at else None,
            },
            "source": "database",
            "timestamp": utc_now().isoformat(),
        }
    finally:
        if should_close:
            session.close()


# ==========================================
# LangChain ReAct Tools for Agents (TOOL-03)
# ==========================================


@tool
def db_load_channel_insights_tool(channel_external_id: str) -> dict[str, Any]:
    """Reads current audience comment insights for the connected channel.

    Enforces ADR-032: only insights derived from own content of the specified channel.
    """
    return load_channel_insights(channel_external_id)


@tool
def db_save_plan_tool(
    lineage_id: str,
    version: int,
    run_id: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persists a new content plan version with item-level objectives and reasons."""
    return save_plan_version(
        lineage_id=lineage_id,
        version=version,
        run_id=run_id,
        items=items,
        created_by="strategist",
        status="DRAFT",
    )


@tool
def db_load_latest_plan_tool(lineage_id: str) -> dict[str, Any]:
    """Loads the latest version of a content plan by its lineage ID."""
    return load_latest_plan(lineage_id=lineage_id)
