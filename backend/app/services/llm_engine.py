import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

CUDF_CHEATSHEET = """
# ════════════════════════════════════════════════════════════════
# cuDF / cuML CHEAT-SHEET  (few-shot examples — read carefully)
# ════════════════════════════════════════════════════════════════
#
# The variable `df` is ALREADY a cuDF DataFrame.
# Do NOT call cudf.DataFrame.from_pandas() or read any file.
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
# 6. add a computed column  (identical syntax to pandas)
#    df["priority_score"] = df["return_flag"] * 0.6 + df["ticket_age_hours"] * 0.4
#
# 7. cuML classifier  (sklearn-style API — use cuml, NOT sklearn)
#    import cuml
#    from cuml.ensemble import RandomForestClassifier as cuRFC
#    X = df[["feat_1", "feat_2", "feat_3", "feat_4"]].astype("float32")
#    y = df["risk_label"].astype("int32")
#    clf = cuRFC(n_estimators=50, max_depth=10)
#    clf.fit(X, y)
#    proba = clf.predict_proba(X)   # column 1 = positive-class probability
#    df["pred_risk"] = proba[:, 1]
#
# 8. convert result to pandas at the END only (for display)
#    result = df.head(20).to_pandas()
#
# CRITICAL RULES:
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
    "- You MUST output the result as a valid JSON string using `json.dumps()`.\n"
    "- Ensure you convert any numpy data types (like np.float64) to native Python types (float, int) before calling json.dumps(), otherwise it will fail to serialize.\n"
    "- Example: `import json; print(json.dumps({'result': float(final_value)}))`\n"
    "- Follow the cheat-sheet above exactly — no pandas, no sklearn."
)

def _call_modal(system_prompt: str, user_prompt: str) -> str:
    """Helper to send prompt to the Modal serverless inference endpoint."""
    if not settings.modal_url:
        raise ValueError("MODAL_URL is not set in the environment variables.")
        
    logger.info(f"Sending prompt to Modal LLM Endpoint: {settings.modal_url}")
    payload = {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt
    }
    
    # We use a long timeout since Modal might have to cold-start (pull the 4GB model)
    with httpx.Client(timeout=300.0) as client:
        resp = client.post(settings.modal_url, json=payload)
        resp.raise_for_status()
        result_text = resp.json().get("result", "")
        
    return result_text

def _extract_code(text: str) -> str:
    code = text.strip()
    if code.startswith("```python"):
        code = code[9:]
    elif code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
    return code.strip()

def synthesize_code(query: str, task_type: str = "data_analysis") -> str:
    """
    Translates a natural language query into cuDF code using the fine-tuned model on Modal.
    """
    logger.info(f"Synthesizing code for query: {query}")
    
    user_prompt = f"""
Task Type: {task_type}
Query: {query}

Assume there is a pre-loaded cuDF DataFrame named `df`.
The DataFrame has the following columns: id, order_id, user_id, product_id, sale_price, created_at, status.
"""
    
    model_output = _call_modal(SYSTEM_PROMPT_CUDF, user_prompt)
    return _extract_code(model_output)


def fix_code(original_code: str, error_message: str) -> str:
    """
    Asks the fine-tuned model to fix the cuDF code based on an execution error.
    """
    logger.info("Sending code to Modal LLM for error fixing...")
    
    user_prompt = f"""
The following cuDF code was executed but resulted in an error. 
Please fix the code. Assume there is a pre-loaded cuDF DataFrame named `df`.
Ensure the final output is printed to stdout using `print()` and `json.dumps()`.

Original Code:
{original_code}

Error Message:
{error_message}

Output ONLY the corrected valid Python code. No markdown, no explanations.
"""
    
    model_output = _call_modal(SYSTEM_PROMPT_CUDF, user_prompt)
    return _extract_code(model_output)
