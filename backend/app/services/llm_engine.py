import logging
import httpx
from app.core.config import settings
from app.data.bigquery import DATASET_SCHEMA

logger = logging.getLogger(__name__)

# Human-readable label for the model powering code synthesis — surfaced to the
# frontend via /api/dataset-info instead of being hardcoded client-side.
MODEL_NAME = "Gemma-4-E2B (LoRA) via Modal"

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


def _call_modal(system_prompt: str, user_prompt: str) -> str:
    """Helper to send prompt to the Modal vLLM serverless inference endpoint."""
    if not settings.modal_url or not settings.modal_api_key:
        raise ValueError("MODAL_URL or MODAL_API_KEY is not set in the environment variables.")
        
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
    
    # We use a long timeout since Modal might have to cold-start
    # Modal uses 303 Redirects for long-running executions, so follow_redirects=True is required
    with httpx.Client(timeout=300.0, follow_redirects=True) as client:
        resp = client.post(settings.modal_url, headers=headers, json=payload)
        resp.raise_for_status()
        result_text = resp.json()["choices"][0]["message"]["content"]
        
    return result_text


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
    import re
    # Remove multiline data = { ... } blocks
    code = re.sub(r'data\s*=\s*\{.*?\}', '', code, flags=re.DOTALL)
    # Remove df = cudf.DataFrame(...) or pd.DataFrame(...)
    code = re.sub(r'df\s*=\s*(cudf|pd)\.DataFrame\(.*?\)', '', code, flags=re.DOTALL)
    
    return code.strip()

def synthesize_code(query: str, task_type: str = "data_analysis") -> str:
    """
    Translates a natural language query into cuDF code using the fine-tuned model on Modal.
    """
    logger.info(f"Synthesizing GPU (cuDF) code for query: {query}")

    user_prompt = f"""
Task Type: {task_type}
Query: {query}

Dataset schema:
{DATASET_SCHEMA}

Assume there is a pre-loaded cuDF DataFrame named `df` with the columns above.
"""
    model_output = _call_modal(SYSTEM_PROMPT_CUDF, user_prompt)
    return _extract_code(model_output)


def synthesize_cpu_code(query: str, task_type: str = "data_analysis") -> str:
    """
    Translates a natural language query into pandas code using the fine-tuned model on Modal.
    Uses SYSTEM_PROMPT_PANDAS — a separate prompt that explicitly forbids cudf/cuml.
    """
    logger.info(f"Synthesizing CPU (pandas) code for query: {query}")

    user_prompt = f"""
Task Type: {task_type}
Query: {query}

Dataset schema:
{DATASET_SCHEMA}

Assume there is a pre-loaded pandas DataFrame named `df` with the columns above.
"""
    model_output = _call_modal(SYSTEM_PROMPT_PANDAS, user_prompt)
    code = _extract_code(model_output)
    
    return code


def fix_code(original_code: str, error_message: str, mode: str = "gpu") -> str:
    """
    Asks the fine-tuned model to fix the code based on an execution error.
    Uses the correct system prompt depending on whether it's a CPU or GPU task.
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
    return _extract_code(model_output)
