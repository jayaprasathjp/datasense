"""
Rule-based rank + recommendation enrichment for risk/alert-style query results.

Scope is intentionally narrow: only the three task types below have a
reasonably predictable "this row matters more than that row" signal.
Generic custom queries return arbitrary columns we can't safely interpret,
so this deliberately does NOT try to enrich those — task_type is the gate.
"""

from typing import Any, Dict, List, Optional

# For each task type: which column name(s) to look for (first match wins,
# case-insensitive substring match), and the four recommendation bands from
# highest-signal to lowest.
_TASK_CONFIG = {
    "classification": {
        "candidates": ["pred_risk", "pred_prob", "risk_score", "probability", "risk_label"],
        "labels": [
            "Escalate immediately — high risk",
            "Review soon — elevated risk",
            "Monitor — moderate risk",
            "Low risk — no action needed",
        ],
    },
    "rolling_window": {
        "candidates": ["deviation", "pct_change", "pct_diff", "diff", "delta", "anomaly_score"],
        "labels": [
            "Investigate immediately — sharp deviation",
            "Investigate soon",
            "Monitor closely",
            "Within normal range",
        ],
    },
    "ranking": {
        "candidates": ["priority_score", "priority", "rank_score"],
        "labels": [
            "Handle first — highest priority",
            "High priority",
            "Standard priority",
            "Low priority — can wait",
        ],
    },
}


def _find_score_column(columns: List[str], candidates: List[str]) -> Optional[str]:
    for cand in candidates:
        for col in columns:
            if cand in col.lower():
                return col
    return None


def _to_number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _band_label(percentile: float, labels: List[str]) -> str:
    """percentile in [0, 1], where 1.0 = the highest-signal row in this batch."""
    if percentile >= 0.75:
        return labels[0]
    if percentile >= 0.5:
        return labels[1]
    if percentile >= 0.25:
        return labels[2]
    return labels[3]


def enrich_results(results: List[Dict[str, Any]], task_type: str) -> List[Dict[str, Any]]:
    """
    Adds `rank` (1-based, most urgent first) and `recommendation` (human-readable
    action band) to each row, for the risk/alert-relevant task types only.
    Returns the input unchanged for any other task_type or empty results.
    """
    config = _TASK_CONFIG.get(task_type)
    if not config or not results:
        return results

    columns = list(results[0].keys())
    score_col = _find_score_column(columns, config["candidates"])

    if score_col:
        # Results already come back sorted by whatever the LLM-generated code did;
        # re-rank by the detected score column so `rank` is trustworthy even if not.
        indexed = sorted(enumerate(results), key=lambda pair: _to_number(pair[1].get(score_col)), reverse=True)
        values = [_to_number(row.get(score_col)) for _, row in indexed]
        lo, hi = min(values), max(values)
        spread = (hi - lo) or 1.0

        enriched = []
        for rank, (_, row) in enumerate(indexed, start=1):
            percentile = (_to_number(row.get(score_col)) - lo) / spread
            new_row = dict(row)
            new_row["rank"] = rank
            new_row["recommendation"] = _band_label(percentile, config["labels"])
            enriched.append(new_row)
        return enriched

    # No recognizable score column in this batch — fall back to positional
    # banding. The query already asked for "top N", so row order still carries
    # signal even without a named score column.
    n = len(results)
    enriched = []
    for i, row in enumerate(results):
        percentile = 1 - (i / max(n - 1, 1))
        new_row = dict(row)
        new_row["rank"] = i + 1
        new_row["recommendation"] = _band_label(percentile, config["labels"])
        enriched.append(new_row)
    return enriched
