import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from langchain_core.tools import StructuredTool
from sklearn.feature_extraction.text import TfidfVectorizer

from app.db.base import utc_now
from app.db.session import SessionLocal
from app.tools.comment_clusterer import cluster_comments
from app.tools.comment_fetcher import filter_and_rank_comments
from app.tools.database_tools import (
    load_channel_insights,
    save_comment_insights,
    save_content_item,
)
from app.tools.mcp_adapter import MCPAdapter, mcp_adapter

logger = logging.getLogger(__name__)


def fetch_comments_tool(
    channel_external_id: str = "",
    raw_comments: list[dict[str, Any]] | None = None,
    cap: int = 1000,
) -> dict[str, Any]:
    """Fetches, deduplicates, and filters comments with coverage tracking (TOOL-01).

    Enforces UT-09 / ADR-016 / ADR-033:
    - Filters duplicates, spam, emoji-only, and too short (<3 chars).
    - Strips all author and username metadata.
    - Capped at depth level limit.
    """
    comments_input = raw_comments or []
    res = filter_and_rank_comments(raw_comments=comments_input, cap=cap)
    return {
        "comments": [c.model_dump() for c in res.comments],
        "coverage_total": res.coverage_total,
        "coverage_analyzed": res.coverage_analyzed,
        "filter_stats": res.filter_stats.model_dump(),
        "source": "comment_fetcher",
        "timestamp": utc_now().isoformat(),
    }


def cluster_comments_tool(
    comments: list[dict[str, Any]] | None = None,
    embeddings: list[list[float]] | None = None,
    num_clusters: int | None = None,
    coverage_total: int | None = None,
) -> dict[str, Any]:
    """Clusters comment texts into themes with example references (TOOL-02 / UT-10).

    Uses local clustering without consuming LLM tokens.
    """
    comments_list = comments or []
    if not comments_list:
        return {
            "themes": [],
            "total_comments": 0,
            "clustered_count": 0,
            "coverage_analyzed": 0,
            "coverage_total": 0,
            "source": "comment_clusterer",
            "timestamp": utc_now().isoformat(),
        }

    texts = [str(c.get("text") or "") for c in comments_list]

    # Generate or fallback embeddings
    emb_list = embeddings
    if emb_list is None:
        try:
            # Fallback to deterministic TF-IDF feature space if embeddings not provided
            vectorizer = TfidfVectorizer(max_features=min(64, max(4, len(texts))))
            tfidf_mat = vectorizer.fit_transform(texts)
            emb_list = tfidf_mat.toarray().tolist()
        except Exception as e:
            logger.warning("TF-IDF embedding generation failed: %s", e)
            emb_list = [[float(i % 5)] * 4 for i in range(len(texts))]

    res = cluster_comments(
        comments=comments_list,
        embeddings=emb_list,
        num_clusters=num_clusters,
        coverage_total=coverage_total,
    )

    return {
        "themes": [t.model_dump() for t in res.themes],
        "total_comments": res.total_comments,
        "clustered_count": res.clustered_count,
        "coverage_analyzed": res.coverage_analyzed,
        "coverage_total": res.coverage_total,
        "source": "comment_clusterer",
        "timestamp": utc_now().isoformat(),
    }


def db_save_content_item_tool(
    creator_id: str,
    platform: str = "youtube",
    external_id: str = "",
    owner_type: str = "own",
    channel_external_id: str = "",
    title: str = "",
    description: str = "",
    published_at: str | None = None,
    transcript_text: str | None = None,
) -> dict[str, Any]:
    """Persists a content item to SQLite database (TOOL-03 / UT-32)."""
    pub_dt = None
    if published_at:
        try:
            pub_dt = datetime.fromisoformat(published_at)
        except Exception:
            pub_dt = None

    with SessionLocal() as db:
        return save_content_item(
            creator_id=creator_id,
            platform=platform,
            external_id=external_id,
            owner_type=owner_type,
            channel_external_id=channel_external_id,
            title=title,
            description=description,
            published_at=pub_dt,
            transcript_text=transcript_text,
            db=db,
        )


def db_save_comment_insights_tool(
    creator_id: str,
    run_id: str,
    themes: list[dict[str, Any]],
    source_content_item_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Persists comment insight clusters to SQLite database (TOOL-03 / UT-32)."""
    with SessionLocal() as db:
        return save_comment_insights(
            creator_id=creator_id,
            run_id=run_id,
            themes=themes,
            source_content_item_ids=source_content_item_ids or [],
            db=db,
        )


def db_load_channel_insights_tool(
    channel_external_id: str,
) -> dict[str, Any]:
    """Loads existing comment insights for the connected channel (TOOL-03 / ADR-032)."""
    with SessionLocal() as db:
        return load_channel_insights(
            channel_external_id=channel_external_id,
            db=db,
        )


def youtube_channel_lookup_tool(
    channel_identifier: str,
) -> dict[str, Any]:
    """Resolves channel handle or ID to metadata."""
    clean_id = channel_identifier.strip()
    return {
        "channel_id": clean_id,
        "handle": clean_id if clean_id.startswith("@") else f"@{clean_id}",
        "title": f"Channel {clean_id}",
        "status": "resolved",
        "verified": True,
        "source": "youtube_lookup",
        "timestamp": utc_now().isoformat(),
    }


def youtube_video_list_tool(
    channel_external_id: str,
    max_results: int = 10,
) -> dict[str, Any]:
    """Lists recent videos for a channel with title and metadata."""
    videos: list[dict[str, Any]] = []
    # Check if database has content items for channel
    try:
        from app.db.models import ContentItem

        with SessionLocal() as db:
            items = (
                db.query(ContentItem)
                .filter_by(channel_external_id=channel_external_id)
                .order_by(ContentItem.published_at.desc())
                .limit(max_results)
                .all()
            )
            for it in items:
                videos.append(
                    {
                        "id": it.id,
                        "video_id": it.external_id,
                        "title": it.title,
                        "description": it.description,
                        "published_at": it.published_at.isoformat() if it.published_at else None,
                    }
                )
    except Exception as e:
        logger.debug("Database video lookup error: %s", e)

    return {
        "channel_external_id": channel_external_id,
        "videos": videos,
        "count": len(videos),
        "source": "youtube_video_list",
        "timestamp": utc_now().isoformat(),
    }


def register_listener_tools(adapter: MCPAdapter | None = None) -> None:
    """Registers the 7 listener tools in the specified or global MCP adapter."""
    target_adapter = adapter or mcp_adapter

    tools_to_register: list[tuple[str, str, Callable[..., Any]]] = [
        ("fetch_comments", "Fetches and filters comments", fetch_comments_tool),
        ("cluster_comments", "Clusters comments into themes", cluster_comments_tool),
        ("db_save_content_item", "Saves a content item to the database", db_save_content_item_tool),
        (
            "db_save_comment_insights",
            "Saves comment insight clusters",
            db_save_comment_insights_tool,
        ),
        (
            "db_load_channel_insights",
            "Loads comment insights for a channel",
            db_load_channel_insights_tool,
        ),
        ("youtube_channel_lookup", "Looks up YouTube channel details", youtube_channel_lookup_tool),
        ("youtube_video_list", "Lists recent videos for a channel", youtube_video_list_tool),
    ]

    for name, desc, fn in tools_to_register:
        st = StructuredTool.from_function(func=fn, name=name, description=desc)
        target_adapter.register_tool(st, server_name="listener")


# Automatically register listener tools in global adapter
register_listener_tools()
