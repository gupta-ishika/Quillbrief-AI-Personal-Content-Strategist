import pytest

from app.tools.mcp_adapter import (
    UnauthorizedToolCallError,
    mcp_adapter,
)
from app.tools.metrics_calculator import (
    ConfidenceLevel,
    calculate_correlation,
    calculate_summary,
    compare_cohorts,
    determine_confidence,
    metrics_calculator_tool,
)


def test_determine_confidence_levels() -> None:
    """UT-08: Confidence labels by sample size: <3 low, 3-9 moderate, >=10 high."""
    assert determine_confidence(0) == ConfidenceLevel.LOW
    assert determine_confidence(1) == ConfidenceLevel.LOW
    assert determine_confidence(2) == ConfidenceLevel.LOW

    assert determine_confidence(3) == ConfidenceLevel.MODERATE
    assert determine_confidence(5) == ConfidenceLevel.MODERATE
    assert determine_confidence(9) == ConfidenceLevel.MODERATE

    assert determine_confidence(10) == ConfidenceLevel.HIGH
    assert determine_confidence(25) == ConfidenceLevel.HIGH
    assert determine_confidence(100) == ConfidenceLevel.HIGH


def test_calculate_summary_statistics() -> None:
    """UT-08: Averages, medians, ranges, and confidence labeling."""
    # Empty list
    empty_summary = calculate_summary([], metric_name="views")
    assert empty_summary.sample_size == 0
    assert empty_summary.mean == 0.0
    assert empty_summary.median == 0.0
    assert empty_summary.confidence == "low"

    # Single item
    single_summary = calculate_summary([500.0], metric_name="views")
    assert single_summary.sample_size == 1
    assert single_summary.mean == 500.0
    assert single_summary.median == 500.0
    assert single_summary.std_dev == 0.0
    assert single_summary.confidence == "low"

    # Small sample (moderate confidence)
    samples = [10.0, 20.0, 30.0, 40.0, 50.0]
    summary = calculate_summary(samples, metric_name="retention_rate")
    assert summary.sample_size == 5
    assert summary.mean == 30.0
    assert summary.median == 30.0
    assert summary.min == 10.0
    assert summary.max == 50.0
    assert round(summary.std_dev, 2) == 15.81
    assert summary.confidence == "moderate"

    # Large sample (high confidence)
    large_samples = [float(i * 10) for i in range(1, 13)]  # 12 samples
    large_summary = calculate_summary(large_samples, metric_name="impressions")
    assert large_summary.sample_size == 12
    assert large_summary.confidence == "high"


def test_compare_cohorts() -> None:
    """UT-08: Comparisons between cohorts (treatment vs baseline), percentage changes, directions, and sample sizes."""
    treatment = [1200.0, 1400.0, 1600.0]  # mean: 1400.0
    baseline = [1000.0, 1000.0, 1000.0]  # mean: 1000.0

    cmp_higher = compare_cohorts(treatment, baseline, metric_name="views")
    assert cmp_higher.treatment_mean == 1400.0
    assert cmp_higher.baseline_mean == 1000.0
    assert cmp_higher.absolute_difference == 400.0
    assert cmp_higher.percentage_change == 40.0
    assert cmp_higher.direction == "higher"
    assert cmp_higher.sample_size_treatment == 3
    assert cmp_higher.sample_size_baseline == 3
    assert cmp_higher.sample_size == 6
    assert cmp_higher.confidence == "moderate"
    assert "higher than baseline" in cmp_higher.summary

    # Lower performance
    treatment_lower = [600.0, 800.0, 700.0]  # mean: 700.0
    cmp_lower = compare_cohorts(treatment_lower, baseline, metric_name="views")
    assert cmp_lower.direction == "lower"
    assert cmp_lower.percentage_change == -30.0
    assert "lower than baseline" in cmp_lower.summary

    # Equal performance
    cmp_equal = compare_cohorts(baseline, baseline, metric_name="views")
    assert cmp_equal.direction == "equal"
    assert cmp_equal.percentage_change == 0.0

    # Confidence constrained by smaller cohort
    small_treatment = [1500.0, 1600.0]  # n=2 (<3 -> low)
    large_baseline = [1000.0] * 15  # n=15 (high)
    cmp_constrained = compare_cohorts(small_treatment, large_baseline, metric_name="views")
    assert cmp_constrained.confidence == "low"

    # Both large cohorts -> high confidence
    large_treatment = [1500.0] * 12
    cmp_large = compare_cohorts(large_treatment, large_baseline, metric_name="views")
    assert cmp_large.confidence == "high"


def test_calculate_correlation_and_causation_distinction() -> None:
    """UT-08 & PRD FR-8: Correlation calculation and explicit distinction between correlation and causation."""
    # Positive correlation
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [2.0, 4.0, 6.0, 8.0, 10.0]
    corr_pos = calculate_correlation(x, y)
    assert corr_pos.correlation_coefficient == 1.0
    assert corr_pos.direction == "positive"
    assert corr_pos.confidence == "moderate"
    assert "Correlation does not imply causation" in corr_pos.distinction_note

    # Negative correlation
    y_neg = [10.0, 8.0, 6.0, 4.0, 2.0]
    corr_neg = calculate_correlation(x, y_neg)
    assert corr_neg.correlation_coefficient == -1.0
    assert corr_neg.direction == "negative"

    # Constant / zero variance
    y_const = [5.0, 5.0, 5.0, 5.0, 5.0]
    corr_zero = calculate_correlation(x, y_const)
    assert corr_zero.correlation_coefficient == 0.0
    assert corr_zero.direction == "neutral"

    # High confidence with 10+ samples
    x_large = [float(i) for i in range(12)]
    y_large = [float(i * 2) for i in range(12)]
    corr_large = calculate_correlation(x_large, y_large)
    assert corr_large.confidence == "high"

    # Mismatched length raises ValueError
    with pytest.raises(ValueError, match="same length"):
        calculate_correlation([1.0, 2.0], [1.0])


def test_metrics_calculator_tool_dispatch() -> None:
    """Tests the LangChain tool interface dispatching summary, compare, correlation, and batch."""
    # 1. Summary
    res_summary = metrics_calculator_tool(
        "summary",
        {"values": [100.0, 200.0, 300.0], "metric_name": "likes"},
    )
    assert res_summary["source"] == "metrics_calculator"
    assert res_summary["verified"] is True
    assert res_summary["result"]["mean"] == 200.0
    assert res_summary["result"]["confidence"] == "moderate"

    # 2. Compare
    res_compare = metrics_calculator_tool(
        "compare",
        {
            "treatment": [500.0, 600.0, 700.0],
            "baseline": [300.0, 400.0, 500.0],
            "metric_name": "retention_seconds",
        },
    )
    assert res_compare["result"]["direction"] == "higher"
    assert res_compare["result"]["percentage_change"] == 50.0

    # 3. Correlation
    res_corr = metrics_calculator_tool(
        "correlation",
        {"x": [1.0, 2.0, 3.0, 4.0], "y": [4.0, 3.0, 2.0, 1.0]},
    )
    assert res_corr["result"]["correlation_coefficient"] == -1.0

    # 4. Batch summary
    res_batch = metrics_calculator_tool(
        "batch_summary",
        {
            "metrics": {
                "views": [1000.0, 2000.0],
                "likes": [50.0, 150.0],
            }
        },
    )
    assert "views" in res_batch["result"]["metrics"]
    assert "likes" in res_batch["result"]["metrics"]
    assert res_batch["result"]["metrics"]["views"]["mean"] == 1500.0

    # 5. Unknown operation
    res_err = metrics_calculator_tool("unknown_op", {})
    assert "error" in res_err["result"]


def test_analyst_tool_allowlist_and_mcp_access() -> None:
    """Verifies that the metrics_calculator is registered for 'analyst' and that analyst allowlist is enforced."""
    # Analyst calling metrics_calculator should succeed
    calc_result = mcp_adapter.execute_for_agent(
        agent_name="analyst",
        tool_name="metrics_calculator",
        kwargs={
            "operation": "summary",
            "data": {"values": [10.0, 20.0, 30.0], "metric_name": "shares"},
        },
    )
    assert calc_result["source"] == "metrics_calculator"
    assert calc_result["result"]["mean"] == 20.0

    # Analyst calling research or listener tools should be rejected by allowlist
    with pytest.raises(UnauthorizedToolCallError):
        mcp_adapter.execute_for_agent(
            agent_name="analyst",
            tool_name="web_search",
            kwargs={"query": "Competitor analysis"},
        )
