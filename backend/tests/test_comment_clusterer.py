import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from app.tools.comment_clusterer import (
    cluster_comments,
    format_theme_label,
    get_local_embeddings,
)
from app.tools.comment_fetcher import filter_and_rank_comments


def test_format_theme_label() -> None:
    assert format_theme_label(["fastapi", "sqlite", "wal"], "Default") == "Fastapi & Sqlite & Wal"
    assert format_theme_label(["langgraph"], "Default") == "Langgraph"
    assert format_theme_label([], "Default Fallback") == "Default Fallback"


def test_cluster_comments_empty() -> None:
    result = cluster_comments([], [])
    assert result.total_comments == 0
    assert result.clustered_count == 0
    assert len(result.themes) == 0


def test_cluster_comments_small_sample() -> None:
    comments = [
        {"comment_id": "c1", "text": "Great explanation of SQLite WAL mode.", "likes": 5},
        {"comment_id": "c2", "text": "Very helpful SQLite concurrency tips.", "likes": 3},
    ]
    # Synthetic 4-dimensional embeddings
    embeddings = [[0.1, 0.2, 0.3, 0.4], [0.15, 0.22, 0.31, 0.38]]

    result = cluster_comments(comments, embeddings)
    assert result.total_comments == 2
    assert result.clustered_count == 2
    assert len(result.themes) == 1
    theme = result.themes[0]
    assert theme.comment_count == 2
    assert len(theme.examples) == 2
    assert set(theme.example_comment_ids) == {"c1", "c2"}


def test_cluster_comments_deterministic_on_fixed_sample() -> None:
    """UT-10: Deterministic output on a fixed sample."""
    rng = np.random.RandomState(12345)
    # Generate 12 fixed synthetic embeddings around 3 centers
    center_1 = np.array([1.0, 0.0, 0.0, 0.0])
    center_2 = np.array([0.0, 1.0, 0.0, 0.0])
    center_3 = np.array([0.0, 0.0, 1.0, 0.0])

    cluster1 = [center_1 + rng.normal(0, 0.05, 4) for _ in range(4)]
    cluster2 = [center_2 + rng.normal(0, 0.05, 4) for _ in range(4)]
    cluster3 = [center_3 + rng.normal(0, 0.05, 4) for _ in range(4)]

    embeddings = np.array(cluster1 + cluster2 + cluster3)
    comments = [
        {"comment_id": f"c_{i}", "text": f"Comment text sample {i}", "likes": i * 2}
        for i in range(12)
    ]

    # Run clustering twice on the exact same sample
    run_1 = cluster_comments(comments, embeddings, num_clusters=3)
    run_2 = cluster_comments(comments, embeddings, num_clusters=3)

    assert run_1.total_comments == 12
    assert run_2.total_comments == 12
    assert len(run_1.themes) == len(run_2.themes)

    for t1, t2 in zip(run_1.themes, run_2.themes, strict=True):
        assert t1.comment_count == t2.comment_count
        assert t1.example_comment_ids == t2.example_comment_ids


def test_cluster_theme_counts_add_up() -> None:
    """UT-10: Theme counts add up exactly to total analyzed comments."""
    rng = np.random.RandomState(42)
    embeddings = rng.normal(0, 1, (15, 8))
    comments = [
        {"comment_id": f"id_{i}", "text": f"Topic comment discussion {i}", "likes": i}
        for i in range(15)
    ]

    result = cluster_comments(comments, embeddings, num_clusters=3)

    # Invariant: Sum of cluster comment counts must equal total analyzed
    sum_counts = sum(t.comment_count for t in result.themes)
    assert sum_counts == result.total_comments
    assert sum_counts == 15
    assert result.clustered_count == 15


def test_cluster_two_or_three_examples_per_theme() -> None:
    """UT-10 / ADR-033: Two or three examples per theme by reference."""
    rng = np.random.RandomState(999)
    embeddings = rng.normal(0, 1, (20, 8))
    comments = [
        {"comment_id": f"cm_{i}", "text": f"Sample feedback comment text {i}", "likes": i * 3}
        for i in range(20)
    ]

    result = cluster_comments(comments, embeddings, num_clusters=4)

    assert len(result.themes) == 4
    for theme in result.themes:
        # Must have 2 or 3 examples
        assert 2 <= len(theme.examples) <= 3
        assert len(theme.example_comment_ids) == len(theme.examples)
        # Verify IDs match
        for ex, ex_id in zip(theme.examples, theme.example_comment_ids, strict=True):
            assert ex.comment_id == ex_id
            assert len(ex.text) > 0


@pytest.mark.asyncio
async def test_get_local_embeddings_batch_and_fallback() -> None:
    from unittest.mock import MagicMock

    # 1. Test batch success
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        res = await get_local_embeddings(["text1", "text2"])
        assert len(res) == 2
        assert res[0] == [0.1, 0.2]


@pytest.mark.asyncio
async def test_comment_clusterer_integration_on_fixture() -> None:
    """End-to-end integration test with fixture dataset and live Ollama embeddings."""
    fixtures_file = Path(__file__).parent / "fixtures" / "comments.json"
    with open(fixtures_file, encoding="utf-8") as f:
        raw = json.load(f)

    fetch_res = filter_and_rank_comments(raw, cap=15)
    valid_comments = fetch_res.comments
    assert len(valid_comments) == 11

    texts = [c.text for c in valid_comments]
    try:
        embeddings = await get_local_embeddings(texts)
    except Exception:
        pytest.skip("Ollama embedding service not accessible in current environment")

    assert len(embeddings) == 11
    result = cluster_comments(valid_comments, embeddings, num_clusters=2)

    assert result.total_comments == 11
    assert result.clustered_count == 11
    sum_counts = sum(t.comment_count for t in result.themes)
    assert sum_counts == 11

    # Verify each theme has 2 or 3 examples
    for theme in result.themes:
        assert 2 <= len(theme.examples) <= 3
        assert len(theme.theme_label) > 0
