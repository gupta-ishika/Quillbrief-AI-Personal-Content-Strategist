"""Metrics calculator tool providing deterministic calculations of performance averages,
comparisons, sample sizes, confidence levels, and correlation analysis (TOOL-06, UT-08).

Key requirements:
- Averages (mean, median, min, max, std dev)
- Comparisons (treatment vs baseline, delta, percentage change, direction)
- Sample size tracking
- Confidence levels ('low' for <3 samples, 'moderate' for 3-9 samples, 'high' for >=10 samples)
- Clear distinction between correlation and causation (PRD FR-8, PRD FR-11)
"""

import math
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.db.base import utc_now
from app.tools.mcp_adapter import MCPAdapter, mcp_adapter


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


def determine_confidence(sample_size: int) -> ConfidenceLevel:
    """Assigns confidence based on sample size (UT-08, PRD Section 11):
    - < 3: low (small sample gives weak conclusions)
    - 3 - 9: moderate
    - >= 10: high
    """
    if sample_size < 3:
        return ConfidenceLevel.LOW
    if sample_size < 10:
        return ConfidenceLevel.MODERATE
    return ConfidenceLevel.HIGH


class MetricSummary(BaseModel):
    metric_name: str
    sample_size: int
    mean: float
    median: float
    min: float
    max: float
    std_dev: float
    confidence: str


class MetricComparison(BaseModel):
    metric_name: str
    sample_size_treatment: int
    sample_size_baseline: int
    treatment_mean: float
    baseline_mean: float
    absolute_difference: float
    percentage_change: float
    direction: str  # "higher", "lower", "equal"
    confidence: str
    sample_size: int
    summary: str


class CorrelationResult(BaseModel):
    sample_size: int
    correlation_coefficient: float
    direction: str  # "positive", "negative", "neutral"
    confidence: str
    distinction_note: str = Field(
        default="Correlation does not imply causation. External factors (such as platform distribution, topic popularity, or timing) may drive both variables."
    )


def calculate_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def calculate_median(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def calculate_std_dev(values: list[float], mean: float | None = None) -> float:
    if len(values) < 2:
        return 0.0
    m = mean if mean is not None else calculate_mean(values)
    variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def calculate_summary(values: list[float], metric_name: str = "metric") -> MetricSummary:
    """Calculates summary statistics and confidence label for a metric series."""
    sample_size = len(values)
    if sample_size == 0:
        return MetricSummary(
            metric_name=metric_name,
            sample_size=0,
            mean=0.0,
            median=0.0,
            min=0.0,
            max=0.0,
            std_dev=0.0,
            confidence=ConfidenceLevel.LOW.value,
        )

    mean_val = calculate_mean(values)
    median_val = calculate_median(values)
    min_val = min(values)
    max_val = max(values)
    std_val = calculate_std_dev(values, mean=mean_val)
    confidence = determine_confidence(sample_size).value

    return MetricSummary(
        metric_name=metric_name,
        sample_size=sample_size,
        mean=round(mean_val, 4),
        median=round(median_val, 4),
        min=round(min_val, 4),
        max=round(max_val, 4),
        std_dev=round(std_val, 4),
        confidence=confidence,
    )


def compare_cohorts(
    treatment_values: list[float],
    baseline_values: list[float],
    metric_name: str = "metric",
) -> MetricComparison:
    """Compares a treatment cohort against a baseline cohort with confidence and direction."""
    n_treatment = len(treatment_values)
    n_baseline = len(baseline_values)

    treatment_mean = calculate_mean(treatment_values)
    baseline_mean = calculate_mean(baseline_values)

    diff = treatment_mean - baseline_mean

    if baseline_mean != 0.0:
        pct_change = (diff / abs(baseline_mean)) * 100.0
    else:
        pct_change = 0.0 if diff == 0.0 else (100.0 if diff > 0 else -100.0)

    if diff > 0.0001:
        direction = "higher"
    elif diff < -0.0001:
        direction = "lower"
    else:
        direction = "equal"

    # Confidence is constrained by the smaller group
    effective_sample_size = min(n_treatment, n_baseline)
    confidence = determine_confidence(effective_sample_size).value

    pct_str = f"{pct_change:+.1f}%" if pct_change != 0.0 else "0.0%"
    summary_text = (
        f"{metric_name} in treatment (n={n_treatment}, mean={treatment_mean:.2f}) is "
        f"{pct_str} {direction} than baseline (n={n_baseline}, mean={baseline_mean:.2f}) "
        f"[confidence: {confidence}]"
    )

    return MetricComparison(
        metric_name=metric_name,
        sample_size_treatment=n_treatment,
        sample_size_baseline=n_baseline,
        treatment_mean=round(treatment_mean, 4),
        baseline_mean=round(baseline_mean, 4),
        absolute_difference=round(diff, 4),
        percentage_change=round(pct_change, 2),
        direction=direction,
        confidence=confidence,
        sample_size=n_treatment + n_baseline,
        summary=summary_text,
    )


def calculate_correlation(
    x_values: list[float],
    y_values: list[float],
) -> CorrelationResult:
    """Calculates Pearson correlation with sample size, confidence, and causation distinction note."""
    if len(x_values) != len(y_values):
        raise ValueError("x_values and y_values must have the same length")

    n = len(x_values)
    if n < 2:
        return CorrelationResult(
            sample_size=n,
            correlation_coefficient=0.0,
            direction="neutral",
            confidence=ConfidenceLevel.LOW.value,
        )

    mean_x = calculate_mean(x_values)
    mean_y = calculate_mean(y_values)

    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values, strict=False))
    sum_sq_x = sum((x - mean_x) ** 2 for x in x_values)
    sum_sq_y = sum((y - mean_y) ** 2 for y in y_values)

    denominator = math.sqrt(sum_sq_x * sum_sq_y)
    if denominator == 0.0:
        r = 0.0
    else:
        r = cov / denominator
        # Bound numerical floating point inaccuracies
        r = max(min(r, 1.0), -1.0)

    if r > 0.1:
        direction = "positive"
    elif r < -0.1:
        direction = "negative"
    else:
        direction = "neutral"

    confidence = determine_confidence(n).value

    return CorrelationResult(
        sample_size=n,
        correlation_coefficient=round(r, 4),
        direction=direction,
        confidence=confidence,
    )


def metrics_calculator_tool(
    operation: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic metrics calculator for averages, comparisons, correlations, and confidence (TOOL-06).

    Supported operations:
    - 'summary': data = {'values': list[float], 'metric_name': str (optional)}
    - 'compare': data = {'treatment': list[float], 'baseline': list[float], 'metric_name': str (optional)}
    - 'correlation': data = {'x': list[float], 'y': list[float]}
    - 'batch_summary': data = {'metrics': dict[str, list[float]]}
    """
    clean_op = operation.strip().lower()

    if clean_op == "summary":
        values = [float(v) for v in data.get("values", [])]
        metric_name = str(data.get("metric_name", "metric"))
        res = calculate_summary(values, metric_name=metric_name)
        result_dict = res.model_dump()

    elif clean_op == "compare":
        treatment = [float(v) for v in data.get("treatment", [])]
        baseline = [float(v) for v in data.get("baseline", [])]
        metric_name = str(data.get("metric_name", "metric"))
        cmp_res = compare_cohorts(treatment, baseline, metric_name=metric_name)
        result_dict = cmp_res.model_dump()

    elif clean_op == "correlation":
        x = [float(v) for v in data.get("x", [])]
        y = [float(v) for v in data.get("y", [])]
        corr_res = calculate_correlation(x, y)
        result_dict = corr_res.model_dump()

    elif clean_op == "batch_summary":
        metrics_dict: dict[str, list[float]] = data.get("metrics", {})
        summaries = {}
        for m_name, vals in metrics_dict.items():
            float_vals = [float(v) for v in vals]
            summaries[m_name] = calculate_summary(float_vals, metric_name=m_name).model_dump()
        result_dict = {"metrics": summaries}

    else:
        result_dict = {
            "error": f"Unknown operation: '{operation}'. Supported: 'summary', 'compare', 'correlation', 'batch_summary'."
        }

    return {
        "operation": clean_op,
        "result": result_dict,
        "source": "metrics_calculator",
        "timestamp": utc_now().isoformat(),
        "verified": True,
    }


def register_analyst_tools(adapter: MCPAdapter | None = None) -> None:
    """Registers the metrics calculator tool in the specified or global MCP adapter under 'analyst' server."""
    target_adapter = adapter or mcp_adapter

    tools_to_register: list[tuple[str, str, Callable[..., Any]]] = [
        (
            "metrics_calculator",
            "Calculates averages, cohort comparisons, sample sizes, confidence levels, and correlations in code.",
            metrics_calculator_tool,
        ),
    ]

    for name, desc, fn in tools_to_register:
        st = StructuredTool.from_function(func=fn, name=name, description=desc)
        target_adapter.register_tool(st, server_name="analyst")


# Automatically register on import
register_analyst_tools()
