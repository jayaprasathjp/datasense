"""
One-line, plain-language summary of a query result — the sentence that closes
the gap between "here is a dataframe" and "here is an insight."

Deliberately rule-based (no extra LLM round-trip on the critical path): reuses
the same score-column detection and recommendation bands as risk_ranking.py
so the language stays consistent with the `recommendation` column already
shown in the results table.
"""

from typing import Any, Dict, List

from app.services.risk_ranking import _TASK_CONFIG, _find_score_column, _to_number


def _numeric_columns(row: Dict[str, Any]) -> List[str]:
    return [k for k, v in row.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]


def generate_summary(results: List[Dict[str, Any]], task_type: str) -> str:
    if not results:
        return "No rows returned — nothing to summarize."

    n = len(results)
    columns = list(results[0].keys())

    config = _TASK_CONFIG.get(task_type)
    if config:
        top_label = config["labels"][0]
        top_count = sum(1 for r in results if r.get("recommendation") == top_label)
        if top_count:
            short_label = top_label.split(" — ", 1)[-1]
            score_col = _find_score_column(columns, config["candidates"])
            if score_col:
                top_value = max(_to_number(r.get(score_col)) for r in results)
                return f"{top_count} of {n} rows need attention now — {short_label} (top score {top_value:.2f})."
            return f"{top_count} of {n} rows need attention now — {short_label}."

    numeric_cols = _numeric_columns(results[0])
    if numeric_cols:
        col = numeric_cols[0]
        values = [_to_number(r.get(col)) for r in results]
        return f"{n} rows returned — {col.replace('_', ' ')} ranges from {min(values):.2f} to {max(values):.2f}."

    return f"{n} rows returned across {len(columns)} columns."
