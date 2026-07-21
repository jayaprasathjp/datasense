import logging

from app.data.bigquery import DATASET_COLUMNS
from app.services.llm_engine import check_query_relevance

logger = logging.getLogger(__name__)

# Domain words that a legitimate question about this dataset is likely to use,
# even if it doesn't spell out an exact column name (e.g. "sales" for "revenue").
_DOMAIN_SYNONYMS = {
    "revenue", "sales", "sale", "order", "orders", "transaction", "transactions",
    "purchase", "purchases", "customer", "customers", "discount", "discounted",
    "return", "returns", "refund", "refunds", "risk", "risky", "margin", "profit",
    "inventory", "stock", "restock", "region", "regional", "store", "stores",
    "product", "products", "price", "pricing", "qty", "quantity", "units",
    "rank", "ranking", "top", "trend", "trending", "average", "rolling",
    "classify", "classification", "predict", "prediction", "forecast",
    "anomaly", "anomalies", "aggregate", "aggregation", "summary", "dashboard",
    "sentiment", "ticket", "tickets", "support", "date", "daily", "weekly",
    "monthly",
}


def _build_keyword_set() -> set[str]:
    words = set(_DOMAIN_SYNONYMS)
    for col in DATASET_COLUMNS:
        words.update(col["name"].lower().split("_"))
    # Drop 1-2 letter tokens (e.g. "id") — too generic to signal relevance on their own.
    return {w for w in words if len(w) > 2}


_KEYWORDS = _build_keyword_set()


def _looks_relevant_by_keywords(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _KEYWORDS)


def validate_query(query: str) -> tuple[bool, str | None]:
    """
    Checks whether a user-submitted natural language query is plausibly
    answerable from the dataset schema, BEFORE we spend an LLM call on code
    synthesis and a Modal sandbox on execution.

    Two layers, cheapest first:
      1. Keyword heuristic — does the query mention any column name or a
         known domain synonym? Free, instant, no external dependency.
      2. LLM fallback — only runs if (1) found zero signal. Asks the model
         for a yes/no verdict. If the LLM call itself fails (e.g. Modal
         credentials missing locally), we conservatively treat the query as
         not relevant rather than silently letting anything through.

    Returns (is_relevant, error_message). error_message is None when relevant.
    """
    if not query or not query.strip():
        return False, "The query is empty. Please enter a question about the dataset."

    if _looks_relevant_by_keywords(query):
        return True, None

    llm_verdict = check_query_relevance(query)
    if llm_verdict is True:
        return True, None

    example_columns = ", ".join(c["name"] for c in DATASET_COLUMNS[:10])
    message = (
        "This query doesn't look relevant to the dataset. "
        "Please ask a question about the available data — e.g. columns like "
        f"{example_columns}, etc."
    )
    return False, message
