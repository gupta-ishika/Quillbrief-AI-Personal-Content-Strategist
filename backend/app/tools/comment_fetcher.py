import logging
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Emoji unicode range pattern
EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff"  # Supplemental symbols, pictographs, emojis
    r"\u2600-\u26ff"  # Miscellaneous symbols
    r"\u2700-\u27bf"  # Dingbats
    r"\u2300-\u23ff"  # Miscellaneous Technical
    r"\u2b50\u2b55"  # Stars, circles
    r"\ufe00-\ufe0f"  # Variation Selectors
    r"\u200d"  # Zero-width joiner
    r"]+",
    flags=re.UNICODE,
)

# Common spam indicator patterns
SPAM_URL_PATTERN = re.compile(
    r"(https?://\S+|www\.\S+|bit\.ly/\S+|t\.me/\S+|wa\.me/\S+|tinyurl\.com/\S+|goo\.gl/\S+)",
    re.IGNORECASE,
)

SPAM_KEYWORDS = [
    "earn $",
    "daily profit",
    "crypto",
    "trading scam",
    "trading signal",
    "whatsapp me",
    "message me on",
    "telegram",
    "sub to my channel",
    "subscribe to my channel",
    "sub4sub",
    "check out my channel",
    "passive income guaranteed",
]


class CleanComment(BaseModel):
    """Anonymized comment stripped of any author metadata (ADR-016, ADR-033)."""

    comment_id: str
    text: str
    like_count: int = 0
    reply_count: int = 0
    published_at: datetime | None = None
    video_id: str | None = None


class CommentFilterStats(BaseModel):
    total_raw: int = 0
    filtered_duplicates: int = 0
    filtered_spam: int = 0
    filtered_emoji_only: int = 0
    filtered_too_short: int = 0
    valid_candidates: int = 0
    returned_count: int = 0
    coverage_total: int = 0
    coverage_analyzed: int = 0


class CommentFetchResult(BaseModel):
    comments: list[CleanComment] = Field(default_factory=list)
    coverage_total: int = 0
    coverage_analyzed: int = 0
    filter_stats: CommentFilterStats = Field(default_factory=CommentFilterStats)


def is_emoji_only(text: str) -> bool:
    """Detects comments that contain only emojis, symbols, punctuation and whitespace."""
    stripped = text.strip()
    if not stripped:
        return True

    # If it contains any alphanumeric character, it is not emoji-only
    has_alphanumeric = bool(re.search(r"[\w\d]", stripped, re.UNICODE))
    if has_alphanumeric:
        # Check if the text is just a single character with multiple emojis
        clean_words = re.sub(r"[^\w\s]", "", stripped)
        if len(clean_words.strip()) >= 2:
            return False

    # Remove all emojis
    no_emoji = EMOJI_PATTERN.sub("", stripped)
    # Remove punctuation and whitespace
    no_punct = re.sub(r"[\s\.,!?;:\-_'\"/\\#@$%^&*()+=\[\]{}<>|~`]+", "", no_emoji)
    return len(no_punct) == 0


def is_spam(text: str) -> bool:
    """Detects commercial spam, scam links, and self-promotional bots."""
    lower = text.lower()

    if SPAM_URL_PATTERN.search(text):
        return True

    for keyword in SPAM_KEYWORDS:
        if keyword in lower:
            return True

    # Check for whatsapp phone number promotion patterns
    if "whatsapp" in lower and any(char.isdigit() for char in lower):
        return True

    return False


def is_too_short(text: str, min_length: int = 4) -> bool:
    """Detects very short or low-information noise (e.g. 'hi', 'ok', 'nice')."""
    stripped = text.strip()
    if len(stripped) < min_length:
        return True

    # Count alphanumeric characters
    alnum_chars = sum(1 for c in stripped if c.isalnum())
    return alnum_chars < 3


def parse_datetime(val: Any) -> datetime | None:
    if isinstance(val, datetime):
        return val
    if isinstance(val, str) and val.strip():
        try:
            # Handles ISO strings like '2026-09-16T11:20:00Z'
            clean_str = val.replace("Z", "+00:00")
            return datetime.fromisoformat(clean_str)
        except Exception:
            return None
    return None


def filter_and_rank_comments(
    raw_comments: list[dict[str, Any]],
    cap: int = 1000,
    min_length: int = 4,
    filter_spam_enabled: bool = True,
    filter_emoji_enabled: bool = True,
    deduplicate_enabled: bool = True,
) -> CommentFetchResult:
    """Filters, deduplicates, anonymizes, ranks, and caps raw comments.

    Invariants (ADR-016, ADR-033, ARCHITECTURE.md Section 6 & 10):
    - Completely strips author names, handles, profile pictures (author anonymity).
    - Removes spam, emoji-only, and noise comments.
    - Prefers recent and highly engaged comments.
    - Accurately tracks coverage_total and coverage_analyzed.
    """
    total_raw = len(raw_comments)
    stats = CommentFilterStats(total_raw=total_raw, coverage_total=total_raw)

    seen_ids: set[str] = set()
    seen_texts: set[str] = set()

    candidates: list[tuple[CleanComment, float]] = []

    for idx, item in enumerate(raw_comments):
        # Extract comment ID
        comment_id = str(
            item.get("comment_id") or item.get("id") or item.get("external_id") or f"cmt_gen_{idx}"
        )
        text = str(item.get("text") or item.get("comment_text") or "").strip()

        # 1. Deduplication check
        if deduplicate_enabled:
            normalized_text = re.sub(r"\s+", " ", text.lower())
            if comment_id in seen_ids or (normalized_text and normalized_text in seen_texts):
                stats.filtered_duplicates += 1
                continue
            seen_ids.add(comment_id)
            if normalized_text:
                seen_texts.add(normalized_text)

        # 2. Emoji-only check (must run before length check so emoji strings are counted as emojis)
        if filter_emoji_enabled and is_emoji_only(text):
            stats.filtered_emoji_only += 1
            continue

        # 3. Too short / empty check
        if is_too_short(text, min_length=min_length):
            stats.filtered_too_short += 1
            continue

        # 4. Spam check
        if filter_spam_enabled and is_spam(text):
            stats.filtered_spam += 1
            continue

        # Extract engagement & published timestamp
        likes = int(item.get("likes") or item.get("like_count") or 0)
        replies = int(item.get("reply_count") or item.get("replies") or 0)
        pub_dt = parse_datetime(item.get("published_at"))
        video_id = str(item.get("video_id") or "") if item.get("video_id") else None

        clean = CleanComment(
            comment_id=comment_id,
            text=text,
            like_count=likes,
            reply_count=replies,
            published_at=pub_dt,
            video_id=video_id,
        )

        # Ranking score: engagement weighted with timestamp recency
        # likes weighted 2x, replies 1x
        engagement_score = float((likes * 2) + replies)
        recency_timestamp = pub_dt.timestamp() if pub_dt else 0.0

        # Composite score prioritizing engagement then recency
        candidates.append((clean, engagement_score * 1000000.0 + (recency_timestamp / 1000.0)))

    stats.valid_candidates = len(candidates)

    # Sort descending by composite ranking score
    candidates.sort(key=lambda x: x[1], reverse=True)

    # Apply cap
    capped_candidates = candidates[:cap]
    final_comments = [c[0] for c in capped_candidates]

    stats.returned_count = len(final_comments)
    stats.coverage_analyzed = len(final_comments)

    return CommentFetchResult(
        comments=final_comments,
        coverage_total=stats.coverage_total,
        coverage_analyzed=stats.coverage_analyzed,
        filter_stats=stats,
    )
