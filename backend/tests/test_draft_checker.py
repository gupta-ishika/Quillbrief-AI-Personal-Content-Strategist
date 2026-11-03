"""Tests for Draft Checker Tool (TOOL-05, UT-07).

Validates:
- Word count and character count calculation
- Required sections detection (Hook, Body, CTA)
- Platform length limits (YouTube title/description, X 280-char limit, Instagram caption)
"""

from app.tools.draft_checker import check_draft


def test_youtube_title_length_limit():
    # Valid short title
    valid_res = check_draft(
        content="How to Build Autonomous AI Agents in 2026",
        kind="title",
        platform="youtube",
    )
    assert valid_res.passed is True
    assert valid_res.char_count < 100

    # Oversized title (>100 chars)
    long_title = "This is an extremely long and unnecessarily verbose YouTube video title that easily surpasses one hundred characters limit easily"
    long_res = check_draft(
        content=long_title,
        kind="title",
        platform="youtube",
    )
    assert long_res.passed is False
    assert any("exceeds 100 characters" in issue for issue in long_res.issues)


def test_youtube_script_required_sections():
    # Script with hook, body, and cta
    good_script = """
    # Hook
    Did you know 90% of developers build LLM apps the wrong way? Here is why.

    # Body
    When designing multi-agent workflows, you must enforce deterministic boundary checks.
    First, avoid letting models call arbitrary tools without allowlists.
    Second, always use explicit schema validation for every agent output.
    Third, store checkpoints in an isolated SQLite database to survive unexpected restarts.

    # CTA
    If you found this useful, hit the subscribe button and let me know your agent architecture in the comments!
    """
    res = check_draft(content=good_script, kind="script", platform="youtube")
    assert res.passed is True
    assert "hook" in res.detected_sections
    assert "body" in res.detected_sections
    assert "cta" in res.detected_sections
    assert res.word_count > 50

    # Script missing CTA
    bad_script = """
    # Hook
    Did you know 90% of developers build LLM apps the wrong way?

    # Body
    Agents need strong validation and bounded token limits.
    """
    res_bad = check_draft(content=bad_script, kind="script", platform="youtube")
    assert res_bad.passed is False
    assert "cta" in res_bad.missing_sections


def test_x_thread_length_limits_and_split():
    # Valid 3-tweet thread under 280 chars each
    valid_thread = """
    1/ Here are 3 architecture rules for production AI systems:

    2/ Rule 1: Always enforce strict depth budgets and cycle detection so agents cannot loop forever.
    Rule 2: Keep model thinking disabled for deterministic tool formatting.

    3/ What is your biggest challenge with local LLM agents? Repost this thread if you learned something!
    """
    res = check_draft(content=valid_thread, kind="x_thread", platform="x")
    assert res.passed is True
    assert res.metrics.get("tweet_count") == 3

    # Thread with an oversized tweet (> 280 chars)
    oversized_tweet = "A" * 290
    bad_thread = f"""
    1/ Normal hook tweet.

    2/ {oversized_tweet}

    3/ Conclusion and bookmark reminder!
    """
    bad_res = check_draft(content=bad_thread, kind="x_thread", platform="x")
    assert bad_res.passed is False
    assert any("exceeds 280 characters" in issue for issue in bad_res.issues)


def test_instagram_caption_limits():
    # Caption exceeding hashtag limits (>30)
    many_hashtags = " ".join([f"#tag{i}" for i in range(35)])
    caption_content = f"Great insights on local models.\n\n{many_hashtags}"
    res = check_draft(content=caption_content, kind="caption", platform="instagram")
    assert res.passed is False
    assert any("maximum allowed is 30" in issue for issue in res.issues)


def test_empty_draft_fails():
    res = check_draft(content="   ", kind="script", platform="youtube")
    assert res.passed is False
    assert "Draft content is empty." in res.issues
