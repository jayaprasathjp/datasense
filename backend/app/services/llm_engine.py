import asyncio
import json
import logging
import httpx
import re
from app.core.config import settings
import app.data.bigquery as bq

logger = logging.getLogger(__name__)

# ── Demo mode fallback ─────────────────────────────────────────
# Pre-written code for each known inquiry so the frontend works
# without a live Modal endpoint (cold-start can take 10+ min).
MOCK_CODE: dict[str, dict[str, str]] = {
    "gpu": {
        "fallback": "result = df.head(100).to_pandas()",
    },
    "cpu": {
        "fallback": "result = df.head(100)",
    },
}

def _get_mock_code(query: str, mode: str) -> str | None:
    """Return fallback code when LLM is unavailable."""
    return MOCK_CODE[mode]["fallback"]

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
    
    try:
        with httpx.Client(timeout=200.0, follow_redirects=True) as client:
            resp = client.post(settings.modal_url, headers=headers, json=payload)
            resp.raise_for_status()
            result_text = resp.json()["choices"][0]["message"]["content"]
        logger.debug(f"LLM response ({len(result_text)} chars): {result_text[:500]}")
        return result_text
    except Exception as e:
        logger.warning(f"Modal LLM call failed ({e}) — falling back to mock code.")
        return ""


async def _call_modal_stream(system_prompt: str, user_prompt: str, platform: str = "cpu"):
    """Stream code from the Modal LLM endpoint, yielding tokens char-by-char.

    Tries SSE streaming first (new Modal app). Falls back to full JSON response
    (old Modal app) and emits characters one at a time.
    Falls back to mock code on timeout/failure after 30s.
    """
    if not settings.modal_url or not settings.modal_api_key:
        mock = MOCK_CODE.get(platform, {}).get("fallback", MOCK_CODE["cpu"]["fallback"])
        for ch in mock:
            yield {"token": ch}
        yield {"code": mock}
        yield {"done": True}
        return

    logger.info(f"Streaming from Modal LLM Endpoint: {settings.modal_url}")

    headers = {
        "Authorization": f"Bearer {settings.modal_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_new_tokens": 512,
        "temperature": 0.2,
        "stream": True,
    }

    accumulated = ""
    is_sse = False
    response_body = b""

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            async with client.stream("POST", settings.modal_url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    response_body += chunk
                    text = chunk.decode("utf-8", errors="replace")

                    for line in text.splitlines():
                        sl = line.strip()
                        if sl.startswith("data: "):
                            is_sse = True
                            try:
                                d = json.loads(sl[6:])
                                if "token" in d:
                                    accumulated += d["token"]
                                    yield {"token": d["token"]}
                                elif d.get("done"):
                                    break
                            except json.JSONDecodeError:
                                pass

        if not is_sse:
            full_body = response_body.decode("utf-8", errors="replace")
            try:
                resp_data = json.loads(full_body)
                full_text = resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if full_text:
                    for ch in full_text:
                        accumulated += ch
                        yield {"token": ch}
                        await asyncio.sleep(0)
                else:
                    accumulated = full_text
            except json.JSONDecodeError:
                accumulated = full_body
                logger.warning("Could not parse Modal response as JSON — sending raw.")

        logger.debug(f"LLM response accumulated ({len(accumulated)} chars)")
    except Exception as e:
        logger.warning(f"Modal LLM stream failed ({e}) — sending empty code.")

    if not accumulated.strip():
        mock = MOCK_CODE.get(platform, {}).get("fallback", MOCK_CODE["cpu"]["fallback"])
        for ch in mock:
            accumulated += ch
            yield {"token": ch}

    yield {"code": accumulated}
    yield {"done": True}


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

def synthesize_code(query: str, task_type: str = "data_analysis") -> str:
    """
    Translates a natural language query into cuDF code using the fine-tuned model on Modal.
    Falls back to pre-written code if the LLM is unavailable.
    """
    logger.info(f"Synthesizing GPU (cuDF) code for query: {query}")

    user_prompt = f"""
Task Type: {task_type}
Query: {query}

Dataset schema:
{bq.DATASET_SCHEMA}

Assume there is a pre-loaded cuDF DataFrame named `df` with the columns above.
"""
    model_output = _call_modal(SYSTEM_PROMPT_CUDF, user_prompt)

    if model_output.strip():
        return _extract_code(model_output)

    mock = _get_mock_code(query, "gpu")
    if mock:
        logger.info("Using mock GPU code (LLM unavailable).")
        return mock.strip()

    logger.warning("No mock code available for this query — returning generic placeholder.")
    return "result = df.head(5).to_pandas()"


def synthesize_cpu_code(query: str, task_type: str = "data_analysis") -> str:
    """
    Translates a natural language query into pandas code using the fine-tuned model on Modal.
    Uses SYSTEM_PROMPT_PANDAS — a separate prompt that explicitly forbids cudf/cuml.
    Falls back to pre-written code if the LLM is unavailable.
    """
    logger.info(f"Synthesizing CPU (pandas) code for query: {query}")

    user_prompt = f"""
Task Type: {task_type}
Query: {query}

Dataset schema:
{bq.DATASET_SCHEMA}

Assume there is a pre-loaded pandas DataFrame named `df` with the columns above.
"""
    model_output = _call_modal(SYSTEM_PROMPT_PANDAS, user_prompt)
    
    if model_output.strip():
        return _extract_code(model_output)

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


SUMMARY_PROMPT = (
    "You are DataSense, a data-science assistant. "
    "Given a user's query and the analysis results (a table of rows), "
    "write a concise 2-3 sentence natural-language summary of what the results show. "
    "Be specific — mention column names, values, and patterns you observe. "
    "Interpret the numbers — e.g. 'the average revenue is $X', "
    "'the highest correlated pair is Y and Z at 0.85', "
    "'the top store by priority score is S042 at 0.82'. "
    "Do NOT mention the code or technical implementation. "
    "Just describe what the data says in plain English."
)


def _generate_summary(query: str, results: list, exec_context: str = "", platform: str = "cpu") -> str:
    """
    Generate a natural-language summary of analysis results.
    Calls Modal LLM with a short timeout (already warm from code generation),
    falls back to a template summary.
    """
    has_rows = len(results) > 0 and len(results[0]) > 0 if results else False

    if not settings.modal_url or not settings.modal_api_key:
        return _template_summary(results, exec_context)

    if exec_context:
        user_prompt = f"User query: {query}\n\nExecution output:\n{exec_context[:1500]}\n\nWrite a 2-3 sentence plain-English summary of what these results show."
    elif has_rows:
        sample = json.dumps(results[:5], default=str)
        n_rows = len(results)
        user_prompt = f"User query: {query}\n\nResults ({n_rows} rows):\n{sample}\n\nWrite a 2-3 sentence plain-English summary of what these results show."
    else:
        return f"The analysis for '{query}' is complete. Review the results above for details."

    headers = {
        "Authorization": f"Bearer {settings.modal_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "max_new_tokens": 256,
        "temperature": 0.3,
    }

    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.post(settings.modal_url, headers=headers, json=payload)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            if text:
                return text
    except Exception as e:
        logger.warning(f"Summary LLM call failed ({e}) — using template.")

    return _template_summary(results, exec_context)


def _template_summary(results: list, exec_context: str = "") -> str:
    if exec_context:
        lines = [l for l in exec_context.splitlines() if l.strip()][:5]
        preview = " | ".join(lines)
        return f"The analysis shows: {preview[:300]}."
    try:
        flat = [r for sub in results if isinstance(sub, list) for r in sub] or results
        flat = [r for r in flat if isinstance(r, dict)]
        if flat:
            cols = list(flat[0].keys())
            col_list = ', '.join(cols[:5])
            sample = ', '.join(f"{k}={v}" for k, v in list(flat[0].items())[:4])
            return f"Analysis returned {len(flat)} rows (columns: {col_list}). Sample: {sample}."
    except Exception:
        pass
    return "Analysis complete. Review the results above for details."
