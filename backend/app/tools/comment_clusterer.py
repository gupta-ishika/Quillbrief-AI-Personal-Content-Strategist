import logging
import re
from typing import Any

import httpx
import numpy as np
from pydantic import BaseModel, Field
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from app.config import settings
from app.tools.comment_fetcher import CleanComment

logger = logging.getLogger(__name__)


class ClusterExample(BaseModel):
    """Representative comment example for a theme cluster (UT-10, ADR-033)."""

    comment_id: str
    text: str
    like_count: int = 0
    reply_count: int = 0


class CommentTheme(BaseModel):
    """Synthesized theme cluster from comment embeddings (no LLM tokens used)."""

    theme_label: str
    comment_count: int
    keywords: list[str] = Field(default_factory=list)
    example_comment_ids: list[str] = Field(
        default_factory=list, description="Two or three comment IDs referencing examples (ADR-033)"
    )
    examples: list[ClusterExample] = Field(
        default_factory=list, description="Two or three representative example comments"
    )


class ClusteringResult(BaseModel):
    """Overall result of local embedding clustering (UT-10, ARCHITECTURE.md)."""

    themes: list[CommentTheme] = Field(default_factory=list)
    total_comments: int = 0
    clustered_count: int = 0
    coverage_analyzed: int = 0
    coverage_total: int = 0


async def get_local_embeddings(
    texts: list[str],
    base_url: str | None = None,
    model_name: str | None = None,
    timeout: float = 30.0,
) -> list[list[float]]:
    """Generates embeddings using Ollama local embedding model (nomic-embed-text).

    Tries the batch /api/embed endpoint first, falling back to sequential /api/embeddings.
    """
    if not texts:
        return []

    url = base_url or settings.ollama_base_url
    model = model_name or settings.embedding_model

    async with httpx.AsyncClient(timeout=timeout) as client:
        # 1. Try batch /api/embed
        try:
            resp = await client.post(f"{url}/api/embed", json={"model": model, "input": texts})
            if resp.status_code == 200:
                data = resp.json()
                embeddings: list[list[float]] = data.get("embeddings", [])
                if len(embeddings) == len(texts):
                    return embeddings
        except Exception as e:
            logger.debug("Ollama /api/embed failed, trying sequential /api/embeddings: %s", e)

        # 2. Fallback to /api/embeddings per item
        results: list[list[float]] = []
        for text in texts:
            resp = await client.post(f"{url}/api/embeddings", json={"model": model, "prompt": text})
            resp.raise_for_status()
            results.append(resp.json().get("embedding", []))
        return results


def format_theme_label(keywords: list[str], default_label: str) -> str:
    """Formats 2-3 keywords into a concise, human-readable theme title."""
    if not keywords:
        return default_label
    cleaned = [re.sub(r"[^\w\s-]", "", kw).strip().title() for kw in keywords[:3] if kw.strip()]
    if not cleaned:
        return default_label
    return " & ".join(cleaned)


def cluster_comments(
    comments: list[CleanComment] | list[dict[str, Any]],
    embeddings: list[list[float]] | np.ndarray,
    num_clusters: int | None = None,
    coverage_total: int | None = None,
) -> ClusteringResult:
    """Groups comment embeddings into deterministic theme clusters (UT-10).

    Invariants:
    - Deterministic output on a fixed sample (random_state=42).
    - Theme counts add up exactly to the total comments analyzed.
    - Two or three examples per theme by reference (ADR-033).
    - Zero LLM tokens consumed (local scikit-learn + nomic-embed-text).
    """
    if not comments:
        return ClusteringResult()

    # Normalize comments to CleanComment models
    normalized_comments: list[CleanComment] = []
    for c in comments:
        if isinstance(c, CleanComment):
            normalized_comments.append(c)
        else:
            normalized_comments.append(
                CleanComment(
                    comment_id=str(c.get("comment_id") or c.get("id") or ""),
                    text=str(c.get("text") or ""),
                    like_count=int(c.get("like_count") or c.get("likes") or 0),
                    reply_count=int(c.get("reply_count") or c.get("replies") or 0),
                )
            )

    n_items = len(normalized_comments)
    emb_array = np.array(embeddings, dtype=float)

    if len(emb_array) != n_items:
        raise ValueError(f"Mismatch: {n_items} comments but {len(emb_array)} embeddings provided.")

    cov_total = coverage_total if coverage_total is not None else n_items

    # Edge case 1: Very few comments (1 to 3)
    if n_items <= 3:
        examples = [
            ClusterExample(
                comment_id=c.comment_id,
                text=c.text,
                like_count=c.like_count,
                reply_count=c.reply_count,
            )
            for c in normalized_comments
        ]
        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=3)
        try:
            vec.fit([c.text for c in normalized_comments])
            kws = list(vec.get_feature_names_out())
        except Exception:
            kws = []
        theme = CommentTheme(
            theme_label=format_theme_label(kws, "General Audience Feedback"),
            comment_count=n_items,
            keywords=kws,
            example_comment_ids=[e.comment_id for e in examples],
            examples=examples,
        )
        return ClusteringResult(
            themes=[theme],
            total_comments=n_items,
            clustered_count=n_items,
            coverage_analyzed=n_items,
            coverage_total=cov_total,
        )

    # General case: Determine number of clusters k
    if num_clusters is not None:
        k = max(1, min(num_clusters, n_items))
    else:
        # Heuristic: min 2, max 6, ~ sqrt(N)
        k = min(max(2, int(n_items**0.5)), min(6, n_items))

    # Deterministic KMeans clustering
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    cluster_labels = kmeans.fit_predict(emb_array)
    centroids = kmeans.cluster_centers_

    themes: list[CommentTheme] = []
    total_assigned = 0

    for cluster_idx in range(k):
        # Indices in this cluster
        indices = [i for i, label in enumerate(cluster_labels) if label == cluster_idx]
        if not indices:
            continue

        cluster_comments_list = [normalized_comments[i] for i in indices]
        count = len(cluster_comments_list)
        total_assigned += count

        # Extract top keywords using TF-IDF on cluster texts
        cluster_texts = [c.text for c in cluster_comments_list]
        try:
            vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=4)
            vec.fit(cluster_texts)
            keywords = list(vec.get_feature_names_out())
        except Exception:
            keywords = []

        label = format_theme_label(keywords, f"Theme Cluster {cluster_idx + 1}")

        # Representative examples: 2 or 3 examples closest to cluster centroid
        cluster_embeddings = emb_array[indices]
        centroid = centroids[cluster_idx]
        # Euclidean distance to centroid
        distances = np.linalg.norm(cluster_embeddings - centroid, axis=1)

        # Composite score: prefer central comments with higher engagement
        # lower distance = better, higher likes = better
        scored_indices = []
        for local_idx, dist in enumerate(distances):
            cmt = cluster_comments_list[local_idx]
            engagement_bonus = (cmt.like_count * 0.05) + (cmt.reply_count * 0.02)
            score = float(dist) - engagement_bonus
            scored_indices.append((local_idx, score))

        scored_indices.sort(key=lambda x: x[1])

        # Pick 2 or 3 examples
        num_examples = min(count, 3 if count >= 3 else 2)
        top_examples: list[ClusterExample] = []
        top_ids: list[str] = []

        for local_idx, _ in scored_indices[:num_examples]:
            cmt = cluster_comments_list[local_idx]
            top_examples.append(
                ClusterExample(
                    comment_id=cmt.comment_id,
                    text=cmt.text,
                    like_count=cmt.like_count,
                    reply_count=cmt.reply_count,
                )
            )
            top_ids.append(cmt.comment_id)

        themes.append(
            CommentTheme(
                theme_label=label,
                comment_count=count,
                keywords=keywords,
                example_comment_ids=top_ids,
                examples=top_examples,
            )
        )

    # Sort themes descending by comment count
    themes.sort(key=lambda t: t.comment_count, reverse=True)

    return ClusteringResult(
        themes=themes,
        total_comments=n_items,
        clustered_count=total_assigned,
        coverage_analyzed=n_items,
        coverage_total=cov_total,
    )
