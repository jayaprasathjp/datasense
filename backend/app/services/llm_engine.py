import logging
import httpx
import re
from app.core.config import settings
from app.data.bigquery import DATASET_SCHEMA
from app.services.cache import get_cached_code, set_cached_code

logger = logging.getLogger(__name__)

# ── Demo mode fallback ─────────────────────────────────────────
# Pre-written code for each known inquiry so the frontend works
# without a live Modal endpoint (cold-start can take 10+ min).

MODEL_NAME = "Gemma-4-E2B (LoRA) via Modal"

MOCK_CODE: dict[str, dict[str, str]] = {
    "gpu": {
        "predict risk_label": """
import cuml
from cuml.ensemble import RandomForestClassifier as cuRFC
features = ["feat_1","feat_2","feat_3","feat_4","price","qty","discount_pct","ticket_age_hours","sentiment","days_since_restock"]
X = df[features].astype("float32")
y = df["risk_label"].astype("int32")
clf = cuRFC(n_estimators=50, max_depth=10, random_state=42)
clf.fit(X, y)
proba = clf.predict_proba(X)
df["pred_risk"] = proba.iloc[:, 1]
result = df.sort_values("pred_risk", ascending=False)[["risk_label","pred_risk"] + features].head(20).to_pandas()
""",
        "rolling": """
df_sorted = df.sort_values(["store_id","date"])
df_sorted["revenue_7d_avg"] = df_sorted.groupby("store_id")["revenue"].transform(lambda x: x.rolling(7, min_periods=1).mean())
df_sorted["revenue_pct_diff"] = (df_sorted["revenue"] - df_sorted["revenue_7d_avg"]) / df_sorted["revenue_7d_avg"]
anomalies = df_sorted[df_sorted["revenue_pct_diff"] < -0.2]
result = anomalies[["store_id","date","revenue","revenue_7d_avg","revenue_pct_diff"]].drop_duplicates("store_id").head(10).to_pandas()
""",
        "priority": """
df["priority_score"] = (df["return_flag"] * 0.45 + (df["ticket_age_hours"] / (df["ticket_age_hours"].max() + 1e-9)) * 0.20 + (1.0 - df["sentiment"].clip(-2, 2) / 2) * 0.20 + (df["days_since_restock"] / (df["days_since_restock"].max() + 1e-9)) * 0.15)
result = df.sort_values("priority_score", ascending=False)[["store_id","region","return_flag","ticket_age_hours","days_since_restock","sentiment","priority_score","margin"]].head(25).to_pandas()
""",
        "dashboard": """
result = df.groupby(["region","support_tier"]).agg(total_revenue=("revenue","sum"),avg_margin=("margin","mean"),return_rate=("return_flag","mean"),avg_ticket_age=("ticket_age_hours","mean"),avg_sentiment=("sentiment","mean")).reset_index().to_pandas()
""",
    },
    "cpu": {
        "predict risk_label": """
import pandas as pd
from sklearn.ensemble import RandomForestClassifier as RF
features = ["feat_1","feat_2","feat_3","feat_4","price","qty","discount_pct","ticket_age_hours","sentiment","days_since_restock"]
X = df[features]
y = df["risk_label"]
clf = RF(n_estimators=50, max_depth=10, random_state=42)
clf.fit(X, y)
proba = clf.predict_proba(X)
df["pred_risk"] = proba[:, 1]
result = df.sort_values("pred_risk", ascending=False)[["risk_label","pred_risk"] + features].head(20)
""",
        "rolling": """
df_sorted = df.sort_values(["store_id","date"])
df_sorted["revenue_7d_avg"] = df_sorted.groupby("store_id")["revenue"].transform(lambda x: x.rolling(7, min_periods=1).mean())
df_sorted["revenue_pct_diff"] = (df_sorted["revenue"] - df_sorted["revenue_7d_avg"]) / df_sorted["revenue_7d_avg"]
anomalies = df_sorted[df_sorted["revenue_pct_diff"] < -0.2]
result = anomalies[["store_id","date","revenue","revenue_7d_avg","revenue_pct_diff"]].drop_duplicates("store_id").head(10)
""",
        "priority": """
df["priority_score"] = (df["return_flag"] * 0.45 + (df["ticket_age_hours"] / (df["ticket_age_hours"].max() + 1e-9)) * 0.20 + (1.0 - df["sentiment"].clip(-2, 2) / 2) * 0.20 + (df["days_since_restock"] / (df["days_since_restock"].max() + 1e-9)) * 0.15)
result = df.sort_values("priority_score", ascending=False)[["store_id","region","return_flag","ticket_age_hours","days_since_restock","sentiment","priority_score","margin"]].head(25)
""",
        "dashboard": """
result = df.groupby(["region","support_tier"]).agg(total_revenue=("revenue","sum"),avg_margin=("margin","mean"),return_rate=("return_flag","mean"),avg_ticket_age=("ticket_age_hours","mean"),avg_sentiment=("sentiment","mean")).reset_index()
""",
    },
}

def _get_mock_code(query: str, mode: str) -> str | None:
    """Return pre-written code for a known query, or None."""
    q = query.lower()
    if "risk" in q or "classif" in q:
        return MOCK_CODE[mode]["predict risk_label"]
    if "rolling" in q or "7-day" in q or "anomal" in q:
        return MOCK_CODE[mode]["rolling"]
    if "priorit" in q or "triage" in q:
        return MOCK_CODE[mode]["priority"]
    if "dashboard" in q or "summar" in q or "aggregat" in q:
        return MOCK_CODE[mode]["dashboard"]
    return None

CUDF_CHEATSHEET = """
# ════════════════════════════════════════════════════════════════
# cuDF / cuML CHEAT-SHEET  (few-shot examples — read carefully)
# ════════════════════════════════════════════════════════════════
#
# The variable `df` is ALREADY a cuDF DataFrame.
# Do NOT call cudf.from_pandas() or read any file.
#
# 1. groupby + agg  (identical syntax to pandas)
#    out = df.groupby(["store_id", "region"]).agg({"revenue": "sum", "qty": "mean"})
#
# 2. merge / join  (identical syntax to pandas)
#    out = df.merge(other_df, on="store_id", how="left")
#
# 3. sort  (identical syntax to pandas)
#    out = df.sort_values("revenue", ascending=False)
#
# 4. rolling window  (identical syntax to pandas)
#    out = df.sort_values("date").groupby("store_id")["revenue"].rolling(7).mean()
#
# 5. boolean filter  (identical syntax to pandas)
#    out = df[df["risk_score"] > 0.5]
#
# 6. priority score / ranking  (vectorized ONLY — DO NOT use df.apply or lambda row)
#    df["priority_score"] = (
#        df["return_flag"] * 0.45
#        + (df["ticket_age_hours"] / (df["ticket_age_hours"].max() + 1e-9)) * 0.20
#        + (1.0 - df["sentiment"].clip(-2, 2)/2) * 0.20
#        + (df["days_since_restock"] / (df["days_since_restock"].max() + 1e-9)) * 0.15
#    )
#    result = df.sort_values("priority_score", ascending=False).head(25)
#
# 7. cuML classifier  (sklearn-style API — use cuml, NOT sklearn)
#    import cuml
#    from cuml.ensemble import RandomForestClassifier as cuRFC
#    X = df[["feat_1", "feat_2", "feat_3", "feat_4"]].astype("float32")
#    y = df["risk_label"].astype("int32")
#    clf = cuRFC(n_estimators=50, max_depth=10)
#    clf.fit(X, y)
#    proba = clf.predict_proba(X)   # returns cuDF DataFrame/Series
#    # Use .iloc to access the column securely
#    df["pred_risk"] = proba.iloc[:, 1] if hasattr(proba, "iloc") else proba[:, 1]
#
# 8. convert result to pandas at the END only (for display)
#    result = df.head(20).to_pandas()
#
# CRITICAL RULES:
#   - The module name is `cudf` (all lowercase) — NOT `cuDF` or `CuDF`
#   - `cudf` is ALREADY imported — do NOT write `import cudf` at the top
#   - `df` is ALREADY a cuDF DataFrame — do NOT call cudf.from_pandas()
#   - .astype("float32") for ML feature columns
#   - .astype("int32")   for integer label columns
#   - DO NOT use: df.apply(lambda ...), df.iterrows(), df.itertuples()
#   - DO NOT import pandas — use cuDF methods only
#   - DO NOT import sklearn — use cuml equivalents only
# ════════════════════════════════════════════════════════════════
"""

SYSTEM_PROMPT_CUDF = (
    "You are DataSense, a GPU-accelerated data-science agent.\n"
    "You write cuDF + cuML code to answer questions about tabular datasets.\n"
    + CUDF_CHEATSHEET +
    "\nRESPONSE FORMAT:\n"
    "- Write exactly ONE ```python code block. No explanation outside it.\n"
    "- Assign the final answer to a variable named `result`.\n"
    "- Follow the cheat-sheet above exactly — no pandas, no sklearn.\n"
    "- NEVER generate comments about dummy data or create a dummy DataFrame. Assume `df` is already in memory."
)

# ── Pandas system prompt (from notebook Section E SYSTEM_PROMPT_PANDAS) ──────
SYSTEM_PROMPT_PANDAS = (
    "You are DataSense, a data-science agent.\n"
    "You write pandas + sklearn code to answer questions about tabular datasets.\n"
    "The dataframe `df` is ALREADY a pandas DataFrame — do NOT import or recreate it.\n"
    "NEVER use pd.read_csv(), pd.read_parquet(), open(), or any file I/O.\n"
    "ALL data is in the variable `df` — use it directly.\n"
    "\nCRITICAL RULES:\n"
    "1. Only use column names listed in the schema below.\n"
    "2. Write vectorised operations — avoid row-by-row loops.\n"
    "3. Do NOT call .to_pandas() — `df` is already a pandas DataFrame.\n"
    "4. Do NOT import cudf or use any cuDF/cuML APIs.\n"
    "\nRESPONSE FORMAT:\n"
    "- Write exactly ONE ```python code block. No explanation outside it.\n"
    "- Assign the final answer to a variable named `result`.\n"
    "- NEVER generate comments about dummy data or create a dummy DataFrame. Assume `df` is already in memory."
).strip()


import json

def _call_modal(system_prompt: str, user_prompt: str, token_callback=None) -> str:
    """Helper to send prompt to the Modal vLLM serverless inference endpoint.
    
    Falls back to mock code if the endpoint is unreachable (cold-start, auth error, etc.).
    """
    if not settings.modal_url or not settings.modal_api_key:
        logger.warning("MODAL_URL or MODAL_API_KEY not set — using mock code.")
        return ""
        
    logger.info(f"Sending prompt to Modal LLM Endpoint: {settings.modal_url}")
    
    headers = {
        "Authorization": f"Bearer {settings.modal_api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_new_tokens": 512,
        "temperature": 0.2
    }
    
    if token_callback:
        payload["stream"] = True

    # We use a long timeout since Modal might have to cold-start
    # Modal uses 303 Redirects for long-running executions, so follow_redirects=True is required
    try:
        with httpx.Client(timeout=300.0, follow_redirects=True) as client:
            if token_callback:
                full_text = []
                with client.stream("POST", settings.modal_url, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    
                    # Check if the server actually returned a stream
                    content_type = resp.headers.get("content-type", "")
                    if "text/event-stream" not in content_type:
                        full_resp = resp.read()
                        try:
                            data = json.loads(full_resp)
                            content = data["choices"][0]["message"]["content"]
                            token_callback(content)
                            return content
                        except Exception as e:
                            raise ValueError(f"Failed to parse non-stream response: {full_resp}") from e

                    for line in resp.iter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                data_json = json.loads(data_str)
                                delta = data_json["choices"][0].get("delta", {})
                                if "content" in delta:
                                    token = delta["content"]
                                    full_text.append(token)
                                    token_callback(token)
                            except (json.JSONDecodeError, KeyError, IndexError):
                                pass
                result_text = "".join(full_text)
            else:
                resp = client.post(settings.modal_url, headers=headers, json=payload)
                resp.raise_for_status()
                result_text = resp.json()["choices"][0]["message"]["content"]
            
        logger.debug(f"LLM response ({len(result_text)} chars): {result_text[:500]}")
        return result_text
    except Exception as e:
        logger.warning(f"Modal LLM call failed ({e}) — falling back to mock code.")
        return ""

def _ensure_result_assignment(code: str) -> str:
    """
    If the code does NOT contain an assignment to `result =`, try to identify
    a trailing expression and prepend `result = ` to it.
    
    This handles the case where the LLM forgets to assign to `result`.
    """
    lines = code.splitlines()
    # Already has result = somewhere → nothing to do
    if any(line.strip().startswith("result ") and "=" in line for line in lines):
        return code
    
    stripped = code.strip()
    # No meaningful code → set a safe default
    if not stripped:
        return "result = df.head(5)"
    
    # Walk backwards to find the last "expression line" (not import/comment/blank/control-flow)
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        if not line or line.startswith(("#", "import ", "from ", "return ", "if ", "elif ", "else:", "for ", "while ", "try:", "except", "finally:", "with ", "def ", "class ", "@")):
            continue
        if "=" in line:
            continue
        # This looks like a bare expression — wrap it
        lines[i] = f"result = {line}"
        logger.debug(f"Auto-wrapped trailing expression: {line}")
        break
    else:
        device_hint = (".to_pandas()" if "cudf" in code else "")
        lines.append(f"result = df.head(5){device_hint}")
    
    return "\n".join(lines)

def _extract_code(text: str) -> str:
    code = text.strip()
    if code.startswith("```python"):
        code = code[9:]
    elif code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
    
    # LLMs occasionally capitalize cuDF, which breaks the python import (it must be all lowercase 'cudf')
    code = code.replace("cuDF", "cudf")
    
    # Forcefully strip out any dummy dataframe generation so it doesn't overwrite our real `df`
    # Remove multiline data = { ... } blocks
    code = re.sub(r'data\s*=\s*\{.*?\}', '', code, flags=re.DOTALL)
    # Remove df = cudf.DataFrame(...) or pd.DataFrame(...)
    code = re.sub(r'df\s*=\s*(cudf|pd)\.DataFrame\(.*?\)', '', code, flags=re.DOTALL)
    
    code = code.strip()
    code = _ensure_result_assignment(code)
    return code

def synthesize_code(query: str, task_type: str = "data_analysis", token_callback=None) -> str:
    """
    Translates a natural language query into cuDF code using the fine-tuned model on Modal.
    Falls back to pre-written code if the LLM is unavailable.
    """
    logger.info(f"Synthesizing GPU (cuDF) code for query: {query}")

    cached = get_cached_code(DATASET_SCHEMA, query, "gpu")
    if cached:
        logger.info("Using cached GPU code.")
        if token_callback:
            import time
            for chunk in cached.split(" "):
                token_callback(chunk + " ")
                time.sleep(0.015)
        return cached

    user_prompt = f"""
Task Type: {task_type}
Query: {query}

Dataset schema:
{DATASET_SCHEMA}

Assume there is a pre-loaded cuDF DataFrame named `df` with the columns above.
"""

    model_output = _call_modal(SYSTEM_PROMPT_CUDF, user_prompt, token_callback)

    if model_output.strip():
        code = _extract_code(model_output)
        return code

    mock = _get_mock_code(query, "gpu")
    if mock:
        logger.info("Using mock GPU code (LLM unavailable).")
        return mock.strip()

    logger.warning("No mock code available for this query — returning generic placeholder.")
    return "result = df.head(5).to_pandas()"

def synthesize_cpu_code(query: str, task_type: str = "data_analysis", token_callback=None) -> str:
    """
    Translates a natural language query into pandas code using the fine-tuned model on Modal.
    Uses SYSTEM_PROMPT_PANDAS — a separate prompt that explicitly forbids cudf/cuml.
    Falls back to pre-written code if the LLM is unavailable.
    """
    logger.info(f"Synthesizing CPU (pandas) code for query: {query}")

    cached = get_cached_code(DATASET_SCHEMA, query, "cpu")
    if cached:
        logger.info("Using cached CPU code.")
        if token_callback:
            import time
            for chunk in cached.split(" "):
                token_callback(chunk + " ")
                time.sleep(0.015)
        return cached

    user_prompt = f"""
Task Type: {task_type}
Query: {query}

Dataset schema:
{DATASET_SCHEMA}

Assume there is a pre-loaded pandas DataFrame named `df` with the columns above.
"""
    model_output = _call_modal(SYSTEM_PROMPT_PANDAS, user_prompt, token_callback)
    
    if model_output.strip():
        code = _extract_code(model_output)
        return code

    mock = _get_mock_code(query, "cpu")
    if mock:
        logger.info("Using mock CPU code (LLM unavailable).")
        return mock.strip()

    logger.warning("No mock code available for this query — returning generic placeholder.")
    return "result = df.head(5)"


def fix_code(original_code: str, error_message: str, mode: str = "gpu") -> str:
    """
    Asks the fine-tuned model to fix the code based on an execution error.
    Uses the correct system prompt depending on whether it's a CPU or GPU task.
    Falls back to original code if the LLM is unavailable.
    """
    logger.info(f"Sending code to Modal LLM for error fixing (mode={mode})...")
    
    if mode == "gpu":
        sys_prompt = SYSTEM_PROMPT_CUDF
        backend_name = "cuDF"
    else:
        sys_prompt = SYSTEM_PROMPT_PANDAS
        backend_name = "pandas"
        
    user_prompt = f"""
The following {backend_name} code was executed but resulted in an error. 
Please fix the code. Assume there is a pre-loaded {backend_name} DataFrame named `df`.
Assign the final output to a variable named `result`.

Original Code:
{original_code}

Error Message:
{error_message}

Output ONLY the corrected valid Python code. No markdown, no explanations.
"""
    
    model_output = _call_modal(sys_prompt, user_prompt)
    if model_output.strip():
        return _extract_code(model_output)
    logger.warning("LLM fix unavailable — returning original code.")
    return original_code

RELEVANCE_SYSTEM_PROMPT = (
    "You are a strict relevance classifier for a data analytics platform.\n"
    "You are given a dataset schema and a user's natural language question.\n"
    "Decide whether the question can plausibly be answered using ONLY the columns in the schema.\n"
    "Respond with EXACTLY one word: YES or NO. Nothing else."
)


def check_query_relevance(query: str) -> bool | None:
    """
    Best-effort LLM relevance check, used as a fallback when the cheap keyword
    heuristic (see app.services.query_validator) finds no signal at all.

    Returns True/False, or None if the LLM call itself fails (e.g. Modal
    credentials not configured) — callers should treat None as "unknown" and
    fall back to a conservative default rather than raising.
    """
    user_prompt = f"Dataset schema:\n{DATASET_SCHEMA}\n\nUser question: {query}\n"
    try:
        output = _call_modal(RELEVANCE_SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        logger.warning(f"Relevance check LLM call failed, falling back to heuristic only: {e}")
        return None
    return output.strip().upper().startswith("YES")