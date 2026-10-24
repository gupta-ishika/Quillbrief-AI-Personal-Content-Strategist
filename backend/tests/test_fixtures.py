import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_creator_fixture() -> None:
    path = FIXTURES_DIR / "creator.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "creator_id" in data
    assert "channel_id" in data
    assert data["profile_source"] == "declared"
    assert len(data["niche"]) <= 200
    assert len(data["tone_instructions"]) <= 500


def test_videos_fixture() -> None:
    path = FIXTURES_DIR / "videos.json"
    assert path.exists()
    videos = json.loads(path.read_text(encoding="utf-8"))
    assert len(videos) >= 5
    own_videos = [v for v in videos if v["is_own_video"]]
    competitor_videos = [v for v in videos if not v["is_own_video"]]
    assert len(own_videos) >= 3
    assert len(competitor_videos) >= 2
    for v in videos:
        assert "video_id" in v
        assert "title" in v
        assert "published_at" in v
        assert v["view_count"] > 0
        assert v["duration_seconds"] > 0


def test_comments_fixture_anonymity_and_fields() -> None:
    path = FIXTURES_DIR / "comments.json"
    assert path.exists()
    comments = json.loads(path.read_text(encoding="utf-8"))
    assert len(comments) >= 10
    forbidden_keys = {"username", "author", "author_name", "reply_text", "replies"}
    for c in comments:
        assert "comment_id" in c
        assert "video_id" in c
        assert "text" in c
        assert "likes" in c
        assert "reply_count" in c
        assert "published_at" in c
        # Strict UT-14 check: no author identification or reply text
        for key in forbidden_keys:
            assert key not in c, (
                f"Forbidden author/reply field '{key}' found in comment {c['comment_id']}"
            )


def test_performance_metrics_fixture() -> None:
    path = FIXTURES_DIR / "performance_metrics.json"
    assert path.exists()
    metrics = json.loads(path.read_text(encoding="utf-8"))
    assert len(metrics) >= 3
    for m in metrics:
        assert "video_id" in m
        assert "views" in m
        assert 0.0 <= m["retention_at_30s"] <= 1.0
        assert 0.0 <= m["click_through_rate"] <= 1.0


def test_evaluation_cases_fixture() -> None:
    path = FIXTURES_DIR / "evaluation_cases.json"
    assert path.exists()
    cases = json.loads(path.read_text(encoding="utf-8"))
    assert len(cases) == 5
    case_ids = {c["case_id"] for c in cases}
    assert "eval_01_new_creator" in case_ids
    assert "eval_02_established_creator" in case_ids
    assert "eval_03_rejected_plan" in case_ids
    assert "eval_04_weak_hook_revision" in case_ids
    assert "eval_05_brief_no_new_posts" in case_ids
    for c in cases:
        assert len(c["expected_route"]) >= 2
        assert "starting_state" in c
        assert "goal" in c
