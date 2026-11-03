"""Draft checker tool providing deterministic quality and constraint checks (TOOL-05, UT-07).

Checks:
- Word count and character count metrics
- Platform-specific length limits
- Format-specific required sections (Hook, Body, CTA / Outro)
"""

import re
from typing import Any

from pydantic import BaseModel, Field


class DraftCheckResult(BaseModel):
    passed: bool
    word_count: int
    char_count: int
    detected_sections: list[str] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


# Platform length limits (UT-07)
PLATFORM_LIMITS: dict[str, dict[str, Any]] = {
    "youtube": {
        "title_max_chars": 100,
        "description_max_chars": 5000,
        "short_max_words": 250,
        "video_min_words": 100,
        "video_max_words": 6000,
        "community_post_max_chars": 5000,
    },
    "instagram": {
        "caption_max_chars": 2200,
        "max_hashtags": 30,
    },
    "linkedin": {
        "post_max_chars": 3000,
        "post_min_words": 20,
    },
    "x": {
        "tweet_max_chars": 280,
        "max_thread_tweets": 25,
    },
}

# Required section keywords and patterns
SECTION_PATTERNS = {
    "hook": re.compile(
        r"(?:^|\n)(?:#+\s*)?(?:\[?hook\]?|intro(?:duction)?|the hook|opening):?",
        re.IGNORECASE,
    ),
    "body": re.compile(
        r"(?:^|\n)(?:#+\s*)?(?:\[?(?:body|main|content|points|step \d+|tip \d+|takeaway)\]?):?",
        re.IGNORECASE,
    ),
    "cta": re.compile(
        r"(?:^|\n)(?:#+\s*)?(?:\[?(?:cta|call to action|outro|conclusion|question)\]?):?",
        re.IGNORECASE,
    ),
    "chapters": re.compile(
        r"(?:^|\n)(?:#+\s*)?(?:\[?(?:chapters|timestamps)\]?|\d{1,2}:\d{2}):?",
        re.IGNORECASE,
    ),
}


def _split_x_thread(content: str) -> list[str]:
    """Splits an X thread into individual tweets by numbering, separators, or double newlines."""
    # Look for common thread separators like '---' or tweet numbering like '1/', '1.', '[1/5]'
    if "---" in content:
        parts = [p.strip() for p in content.split("---") if p.strip()]
        return parts

    lines = content.strip().split("\n")
    tweets: list[str] = []
    current_tweet: list[str] = []

    numbered_start = re.compile(r"^(?:\[?\d+[\/.)\]]|\(\d+\))\s*")

    for line in lines:
        if numbered_start.match(line.strip()) and current_tweet:
            tweets.append("\n".join(current_tweet).strip())
            current_tweet = [line]
        else:
            current_tweet.append(line)

    if current_tweet:
        tweets.append("\n".join(current_tweet).strip())

    if len(tweets) <= 1:
        # Fall back to double blank lines if not explicitly numbered
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if len(paragraphs) > 1:
            return paragraphs

    return tweets if tweets else [content.strip()]


def check_draft(
    content: str,
    kind: str,
    platform: str = "youtube",
) -> DraftCheckResult:
    """Deterministically checks a draft against rubric requirements, length limits, and sections.

    Zero LLM tokens are used. Returns pass/fail and itemized issues.
    """
    clean_content = content.strip()
    char_count = len(clean_content)
    words = clean_content.split()
    word_count = len(words)

    issues: list[str] = []
    detected_sections: list[str] = []
    missing_sections: list[str] = []
    metrics: dict[str, Any] = {
        "word_count": word_count,
        "char_count": char_count,
        "kind": kind,
        "platform": platform,
    }

    if not clean_content:
        return DraftCheckResult(
            passed=False,
            word_count=0,
            char_count=0,
            detected_sections=[],
            missing_sections=["content"],
            issues=["Draft content is empty."],
            metrics=metrics,
        )

    # 1. Platform-Specific Length Checks
    norm_platform = platform.lower()
    norm_kind = kind.lower()

    if norm_platform == "youtube":
        limits = PLATFORM_LIMITS["youtube"]
        if norm_kind == "title":
            if char_count > limits["title_max_chars"]:
                issues.append(
                    f"YouTube title exceeds {limits['title_max_chars']} characters ({char_count} chars)."
                )
        elif norm_kind == "description":
            if char_count > limits["description_max_chars"]:
                issues.append(
                    f"YouTube description exceeds {limits['description_max_chars']} characters ({char_count} chars)."
                )
        elif norm_kind == "community_post":
            if char_count > limits["community_post_max_chars"]:
                issues.append(
                    f"YouTube community post exceeds {limits['community_post_max_chars']} characters ({char_count} chars)."
                )
        elif norm_kind == "script":
            # Check if short or long-form video
            if "short" in content.lower()[:100] or word_count <= 250:
                if word_count > limits["short_max_words"]:
                    issues.append(
                        f"YouTube Short script exceeds {limits['short_max_words']} words ({word_count} words)."
                    )
            else:
                if word_count < limits["video_min_words"]:
                    issues.append(
                        f"YouTube video script is too brief; expected at least {limits['video_min_words']} words ({word_count} words)."
                    )

    elif norm_platform == "instagram":
        limits = PLATFORM_LIMITS["instagram"]
        if char_count > limits["caption_max_chars"]:
            issues.append(
                f"Instagram caption exceeds {limits['caption_max_chars']} characters ({char_count} chars)."
            )
        hashtags = re.findall(r"#\w+", clean_content)
        metrics["hashtag_count"] = len(hashtags)
        if len(hashtags) > limits["max_hashtags"]:
            issues.append(
                f"Instagram caption contains {len(hashtags)} hashtags; maximum allowed is {limits['max_hashtags']}."
            )

    elif norm_platform == "linkedin":
        limits = PLATFORM_LIMITS["linkedin"]
        if char_count > limits["post_max_chars"]:
            issues.append(
                f"LinkedIn post exceeds {limits['post_max_chars']} characters ({char_count} chars)."
            )
        if word_count < limits["post_min_words"]:
            issues.append(
                f"LinkedIn post is too short ({word_count} words); expected at least {limits['post_min_words']} words."
            )

    elif norm_platform == "x":
        limits = PLATFORM_LIMITS["x"]
        if norm_kind == "x_thread":
            tweets = _split_x_thread(clean_content)
            metrics["tweet_count"] = len(tweets)
            if len(tweets) > limits["max_thread_tweets"]:
                issues.append(
                    f"X thread has {len(tweets)} tweets; maximum recommended is {limits['max_thread_tweets']}."
                )
            for idx, tweet in enumerate(tweets, 1):
                if len(tweet) > limits["tweet_max_chars"]:
                    issues.append(
                        f"Tweet {idx} exceeds {limits['tweet_max_chars']} characters ({len(tweet)} chars)."
                    )
        else:
            if char_count > limits["tweet_max_chars"]:
                issues.append(
                    f"X post exceeds {limits['tweet_max_chars']} characters ({char_count} chars)."
                )

    # 2. Required Section Checks (UT-07)
    if norm_kind in ("script", "video"):
        # Script must have Hook, Body, and CTA
        required = ["hook", "body", "cta"]
        for sec in required:
            pattern = SECTION_PATTERNS[sec]
            if pattern.search(clean_content):
                detected_sections.append(sec)
            else:
                # Also check heuristic for hook (first line) and cta (last lines with subscribe/follow/comment)
                if sec == "hook" and word_count >= 15:
                    detected_sections.append("hook")
                elif sec == "body" and word_count >= 50:
                    detected_sections.append("body")
                elif sec == "cta" and re.search(
                    r"(?:subscribe|follow|comment|share|like|check out|link in)",
                    clean_content,
                    re.IGNORECASE,
                ):
                    detected_sections.append("cta")
                else:
                    missing_sections.append(sec)
                    issues.append(f"Script is missing required section: '{sec.upper()}'.")

    elif norm_kind in ("x_thread", "thread"):
        # Thread must have hook tweet, body tweets, and conclusion / CTA
        tweets = _split_x_thread(clean_content)
        if len(tweets) < 2:
            issues.append("X thread must contain at least 2 distinct tweets.")
            missing_sections.append("multi_tweet_structure")
        else:
            detected_sections.append("hook_tweet")
            detected_sections.append("body_tweets")
            # Check last tweet for CTA / conclusion
            last_tweet = tweets[-1]
            if re.search(
                r"(?:repost|retweet|follow|like|comment|bookmark|link|t.co)",
                last_tweet,
                re.IGNORECASE,
            ):
                detected_sections.append("cta_tweet")
            else:
                missing_sections.append("cta_tweet")
                issues.append("X thread ending tweet should include a closing takeaway or CTA.")

    elif norm_kind in ("linkedin_post", "post"):
        # Should have hook / opener, body points, and CTA/question
        if word_count >= 30:
            detected_sections.append("hook")
            detected_sections.append("body")
            if re.search(
                r"(?:what do you think|\?|agree|thoughts|comment below|share your)",
                clean_content,
                re.IGNORECASE,
            ):
                detected_sections.append("cta")
            else:
                missing_sections.append("cta")
                issues.append("LinkedIn post is missing an engaging CTA or discussion question.")
        else:
            issues.append("LinkedIn post needs more substance (min 30 words).")

    elif norm_kind == "description":
        # Check for overview and timestamps/chapters/links
        detected_sections.append("overview")
        if SECTION_PATTERNS["chapters"].search(clean_content) or re.search(
            r"http[s]?://", clean_content
        ):
            detected_sections.append("resources_or_timestamps")
        else:
            missing_sections.append("resources_or_timestamps")
            issues.append("Description should include resource links or chapters/timestamps.")

    elif norm_kind == "title":
        if word_count < 2:
            issues.append("Title is too brief (less than 2 words).")
        else:
            detected_sections.append("title")

    passed = len(issues) == 0

    return DraftCheckResult(
        passed=passed,
        word_count=word_count,
        char_count=char_count,
        detected_sections=detected_sections,
        missing_sections=missing_sections,
        issues=issues,
        metrics=metrics,
    )
