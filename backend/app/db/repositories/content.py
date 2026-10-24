from datetime import datetime

from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import (
    Comment,
    CommentInsight,
    CommentInsightExample,
    CommentInsightSource,
    ContentItem,
)


def upsert_content_item(
    db: Session,
    creator_id: str,
    platform: str,
    external_id: str,
    owner_type: str,
    channel_external_id: str,
    title: str,
    description: str = "",
    published_at: datetime | None = None,
    transcript_text: str | None = None,
) -> ContentItem:
    item = db.query(ContentItem).filter_by(platform=platform, external_id=external_id).first()
    if item:
        item.title = title
        item.description = description
        item.transcript_text = transcript_text
        item.fetched_at = utc_now()
    else:
        item = ContentItem(
            creator_id=creator_id,
            platform=platform,
            external_id=external_id,
            owner_type=owner_type,
            channel_external_id=channel_external_id,
            title=title,
            description=description,
            published_at=published_at or utc_now(),
            transcript_text=transcript_text,
            fetched_at=utc_now(),
        )
        db.add(item)
    db.commit()
    db.refresh(item)
    return item


def create_comment(
    db: Session,
    content_item_id: str,
    external_id: str,
    text: str | None,
    like_count: int = 0,
    reply_count: int | None = None,
    published_at: datetime | None = None,
) -> Comment:
    comment = (
        db.query(Comment)
        .filter_by(content_item_id=content_item_id, external_id=external_id)
        .first()
    )
    if comment:
        comment.text = text
        comment.like_count = like_count
        comment.reply_count = reply_count
    else:
        comment = Comment(
            content_item_id=content_item_id,
            external_id=external_id,
            text=text,
            like_count=like_count,
            reply_count=reply_count,
            published_at=published_at or utc_now(),
        )
        db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def get_unprocessed_comments(
    db: Session,
    content_item_ids: list[str],
) -> list[Comment]:
    return (
        db.query(Comment)
        .filter(
            Comment.content_item_id.in_(content_item_ids),
            Comment.processed_at.is_(None),
            Comment.text.is_not(None),
        )
        .all()
    )


def mark_comments_processed(db: Session, comment_ids: list[str]) -> int:
    now = utc_now()
    count = (
        db.query(Comment)
        .filter(Comment.id.in_(comment_ids))
        .update({"processed_at": now}, synchronize_session="fetch")
    )
    db.commit()
    return count


def create_comment_insight(
    db: Session,
    creator_id: str,
    run_id: str,
    theme_label: str,
    comment_count: int,
    coverage_analyzed: int,
    coverage_total: int,
    source_item_ids: list[str],
    example_comment_ids: list[str],
) -> CommentInsight:
    insight = CommentInsight(
        creator_id=creator_id,
        run_id=run_id,
        theme_label=theme_label,
        comment_count=comment_count,
        coverage_analyzed=coverage_analyzed,
        coverage_total=coverage_total,
        status="current",
    )
    db.add(insight)
    db.flush()

    for item_id in source_item_ids:
        source = CommentInsightSource(insight_id=insight.id, content_item_id=item_id)
        db.add(source)

    for comment_id in example_comment_ids:
        example = CommentInsightExample(insight_id=insight.id, comment_id=comment_id)
        db.add(example)

    db.commit()
    db.refresh(insight)
    return insight


def get_current_insights_for_channel(db: Session, channel_external_id: str) -> list[CommentInsight]:
    """Implements ADR-032 Channel rule:

    Current plans and analysis use an insight only if all its sources are own content
    of the channel currently saved. Insights from previous channels are excluded.
    """
    if not channel_external_id:
        return []

    insights = db.query(CommentInsight).filter(CommentInsight.status == "current").all()

    eligible_insights = []
    for insight in insights:
        if not insight.sources:
            continue
        all_match = all(
            src.content_item.owner_type == "own"
            and src.content_item.channel_external_id == channel_external_id
            for src in insight.sources
        )
        if all_match:
            eligible_insights.append(insight)

    return eligible_insights
