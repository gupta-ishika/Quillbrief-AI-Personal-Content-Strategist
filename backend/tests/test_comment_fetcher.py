import json
import os
from pathlib import Path

from app.tools.comment_fetcher import (
    filter_and_rank_comments,
    is_emoji_only,
    is_spam,
    is_too_short,
)


def test_is_emoji_only() -> None:
    assert is_emoji_only("🔥🔥🔥") is True
    assert is_emoji_only("👍👏") is True
    assert is_emoji_only("❤️❤️❤️") is True
    assert is_emoji_only("   🎉✨🙌   ") is True
    assert is_emoji_only("🔥 ! ?") is True

    # Text with emojis should NOT be emoji-only
    assert is_emoji_only("Great video! 🔥") is False
    assert is_emoji_only("Thanks for the explanation 👍") is False
    assert is_emoji_only("How do you handle worker queues?") is False


def test_is_spam() -> None:
    assert is_spam("Earn $500 daily trading crypto! Click here: bit.ly/spam-crypto-scam") is True
    assert is_spam("Join my telegram group t.me/free_crypto_signals") is True
    assert is_spam("Contact me on WhatsApp +1234567890 for investment advice") is True
    assert is_spam("Check out my channel and sub to my channel!") is True
    assert is_spam("sub4sub anyone?") is True

    # Legitimate comments
    assert is_spam("Could you do a dedicated video on authentication with FastAPI?") is False
    assert is_spam("Please provide the GitHub repo link for this architecture!") is False
    assert (
        is_spam(
            "TaskGroups are much better than asyncio.gather. The exception handling semantics make cancellation so much easier."
        )
        is False
    )


def test_is_too_short() -> None:
    assert is_too_short("hi") is True
    assert is_too_short("ok") is True
    assert is_too_short("a") is True
    assert is_too_short("   ") is True
    assert is_too_short("...") is True

    assert is_too_short("FastAPI question: how do you persist checkpoints?") is False
    assert is_too_short("Nice explanation") is False


def test_filter_and_rank_on_fixtures() -> None:
    """UT-09 / ARCHITECTURE.md: Cap, deduplication, spam & emoji filtering, coverage count."""
    fixtures_dir = Path(__file__).parent / "fixtures"
    comments_file = fixtures_dir / "comments.json"
    assert os.path.exists(comments_file)

    with open(comments_file, encoding="utf-8") as f:
        raw_comments = json.load(f)

    # 14 raw comments in fixture
    assert len(raw_comments) == 14

    # Run with cap = 5
    result = filter_and_rank_comments(raw_comments, cap=5)

    assert result.coverage_total == 14
    assert result.coverage_analyzed == 5
    assert len(result.comments) == 5

    # Check filter breakdown
    assert result.filter_stats.filtered_emoji_only == 2  # cmt_004 ('🔥🔥🔥') and cmt_010 ('👍👏')
    assert result.filter_stats.filtered_spam == 1  # cmt_005 ('Earn $500 daily...')
    assert result.filter_stats.valid_candidates == 11
    assert result.filter_stats.returned_count == 5

    # Verify ranking: top comment must have high engagement
    # In fixture: cmt_014 has 110 likes and 15 replies; cmt_006 has 88 likes and 12 replies
    top_comment = result.comments[0]
    assert top_comment.comment_id in ("cmt_014", "cmt_006")
    assert top_comment.like_count >= 80

    # Verify no filtered IDs in returned list
    returned_ids = {c.comment_id for c in result.comments}
    assert "cmt_004" not in returned_ids
    assert "cmt_005" not in returned_ids
    assert "cmt_010" not in returned_ids


def test_deduplication() -> None:
    raw = [
        {"comment_id": "c1", "text": "This is a great video on LangGraph!", "likes": 5},
        {"comment_id": "c1", "text": "This is a great video on LangGraph!", "likes": 5},
        {"comment_id": "c2", "text": "this is a great video on langgraph!", "likes": 2},
        {"comment_id": "c3", "text": "Unique comment explaining checkpointing.", "likes": 10},
    ]

    result = filter_and_rank_comments(raw, cap=10, deduplicate_enabled=True)
    assert result.coverage_total == 4
    assert result.filter_stats.filtered_duplicates == 2
    assert len(result.comments) == 2
    assert result.comments[0].comment_id in ("c1", "c3")


def test_author_anonymity_enforced() -> None:
    """ADR-016: Comment text, likes, reply counts, dates only. Never usernames/author metadata."""
    raw = [
        {
            "comment_id": "c_anon_1",
            "text": "How do you handle worker queues?",
            "author": "Alice Developer",
            "author_channel_url": "https://youtube.com/@alicedev",
            "author_profile_image": "https://avatar.com/alice.jpg",
            "likes": 12,
        }
    ]

    result = filter_and_rank_comments(raw, cap=5)
    assert len(result.comments) == 1
    comment = result.comments[0]

    # Verify comment fields
    comment_dict = comment.model_dump()
    assert "author" not in comment_dict
    assert "author_channel_url" not in comment_dict
    assert "author_profile_image" not in comment_dict
    assert comment.text == "How do you handle worker queues?"
    assert comment.like_count == 12
