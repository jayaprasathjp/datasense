import io
import re
import sys
import json
import time
import logging
import contextlib
import httpx
import pandas as pd
import numpy as np
from app.core.config import settings
from app.data.bigquery import get_dataframe, DATASET_SCHEMA
from app.services.llm_engine import _generate_summary as _llm_summary

logger = logging.getLogger(__name__)

AGENT_SYSTEM_PROMPT = (
    "You are DataSense, a personal data science and data engineering agent.\n"
    "You explore large databases, clean messy data, analyze, model, visualize, and explain findings.\n"
    "\n"
    "Workflow for every task:\n"
    "1. THINK — inspect schema, row counts, nulls, dtypes before analysis\n"
    "2. EXPLORE — head(), describe(), value_counts() on key columns\n"
    "3. EXECUTE — one focused code step at a time; use the <result> to decide next step\n"
    "4. DEBUG — read tracebacks; fix column names, dtypes, and syntax yourself\n"
    "5. CONCLUDE — when you have the answer, output **Answer:** and **Summary:**\n"
    "\n"
    "The dataframe `df` is already loaded — do NOT import or recreate it.\n"
    "Use pandas and numpy only (already imported).\n"
    "Write ONE ```python code block per response.\n"
    "After execution you receive <result> — use it to decide next step.\n"
    "\n"
    "Final step: print ONLY the answer value as the last line of your last code block.\n"
    "Then write:\n"
    "**Answer:** <raw value only — True, False, 0, 32.0, Atlanta, etc.>\n"
    "**Summary:** <plain English explanation>\n"
)

DONE_MARKERS = ("**Summary:**", "**Finding:**", "**Conclusion:**", "**Results:**")
FINISH_MARKERS = DONE_MARKERS + ("**Answer:**", "**ANSWER:**", "Final Answer:", "final answer:")


class AgentContext:
    def __init__(self, system_prompt: str, max_tokens: int = 6000):
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.messages: list[dict] = []
        self.pinned_first_msg: dict | None = None

    def add_user(self, content: str):
        msg = {"role": "user", "content": content}
        if self.pinned_first_msg is None:
            self.pinned_first_msg = msg
        self.messages.append(msg)

    def add_assistant(self, content: str):
        self.messages.append({"role": "assistant", "content": content})

    def add_result(self, content: str):
        self.messages.append({
            "role": "user",
            "content": f"<result>\n[EXEC:real]\n{content[:2000]}\n</result>",
        })

    def get_messages(self) -> list[dict]:
        recent = self._trim_to_budget()
        full: list[dict] = [{"role": "system", "content": self.system_prompt}]
        if self.pinned_first_msg:
            full.append(self.pinned_first_msg)
            if recent and recent[0].get("content") == self.pinned_first_msg.get("content"):
                recent = recent[1:]
        full.extend(recent)
        return full

    def _trim_to_budget(self) -> list[dict]:
        budget = self.max_tokens
        trimmed: list[dict] = []
        for msg in reversed(self.messages):
            tokens = len(msg["content"].split()) * 1.3
            if budget - tokens < 0:
                break
            trimmed.insert(0, msg)
            budget -= tokens
        return trimmed


async def _call_modal_messages(messages: list[dict]) -> str:
    if not settings.modal_url or not settings.modal_api_key:
        logger.warning("MODAL_URL or MODAL_API_KEY not set")
        return ""

    headers = {
        "Authorization": f"Bearer {settings.modal_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": messages,
        "max_new_tokens": 512,
        "temperature": 0.2,
    }

    try:
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            resp = await client.post(settings.modal_url, headers=headers, json=payload)
            resp.raise_for_status()
            body = resp.json()
            if "choices" in body:
                return body["choices"][0]["message"]["content"]
            elif "response" in body:
                return body["response"]
            return str(body)
    except Exception as e:
        logger.warning(f"Agent LLM call failed: {type(e).__name__}: {e}")
        return ""


def extract_code_blocks(text: str) -> list[str]:
    blocks = re.findall(r"```python\n(.*?)```", text, re.DOTALL)
    if not blocks:
        blocks = re.findall(r"```\n(.*?)```", text, re.DOTALL)
    return blocks


def extract_answer(text: str, exec_outputs: list[str] | None = None) -> str:
    exec_outputs = exec_outputs or []
    for pat in (
        r"\*\*Answer:\*\*\s*(.+?)(?:\n|$)",
        r"\*\*ANSWER:\*\*\s*(.+?)(?:\n|$)",
        r"Final Answer:\s*(.+?)(?:\n|$)",
        r"final answer:\s*(.+?)(?:\n|$)",
    ):
        m = re.search(pat, text)
        if m:
            ans = m.group(1).strip().strip("*").strip()
            if ans and not ans.startswith("```"):
                return ans
    for stdout in reversed(exec_outputs):
        if stdout and stdout.strip():
            lines = stdout.strip().splitlines()
            label_lines = [ln.strip() for ln in lines if any(k in ln.lower() for k in ("revenue", "total", "average", "percentage", "percent", "sum", "mean", "highest", "lowest", "top", "bottom", "answer", "result", "max", "min", "count"))]
            if label_lines:
                last_label = label_lines[-1]
                idx = next(i for i, ln in enumerate(lines) if ln.strip() == last_label)
                rest = "\n".join(lines[idx:]).strip()
                return rest[:500]
            last_line = lines[-1].strip()
            if last_line and last_line not in ("(no output)",) and not last_line[0].isdigit():
                return last_line
    summary = extract_summary(text)
    if summary:
        return summary
    text_no_code = re.sub(r"```.*?```", "", text, flags=re.DOTALL).strip()
    lines = [ln.strip() for ln in text_no_code.splitlines() if ln.strip()]
    if lines:
        return "\n".join(lines[-3:])[:500]
    return ""


def extract_summary(text: str) -> str:
    for prefix in ("**Summary:**", "**Finding:**", "**Conclusion:**", "**Results:**"):
        if prefix in text:
            tail = text.split(prefix, 1)[1].strip()
            line = tail.split("\n")[0].strip()
            if line:
                return line[:1500]
    return ""


def _build_natural_answer(all_rows: list[list[dict]], exec_outputs: list[str]) -> str:
    flat = [r for batch in all_rows for r in batch if isinstance(r, dict)]
    if not flat:
        for out in reversed(exec_outputs):
            txt = out.strip()
            if txt and txt != "(no output)":
                return txt[:500]
        return ""
    keys = list(flat[0].keys())
    if keys == ["output"]:
        vals = [r["output"] for r in flat[:5]]
        return "\n".join(vals)[:500]
    items = []
    for r in flat[:8]:
        parts = [f"{k}: {v}" for k, v in r.items()]
        items.append(", ".join(parts))
    return "\n".join(items)[:500]


def _convert_to_safe(obj):
    if isinstance(obj, dict):
        return {k: _convert_to_safe(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_convert_to_safe(v) for v in obj]
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif isinstance(obj, pd.Timedelta):
        return str(obj)
    return obj


def execute_code_locally(code: str) -> dict:
    df = get_dataframe()
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    result_val = None

    try:
        with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
            _globals = {"df": df, "np": np, "pd": pd}
            exec(code, _globals)
            result_val = _globals.get("result")
    except Exception as e:
        return {
            "success": False,
            "stdout": stdout_capture.getvalue()[:3000],
            "stderr": f"{type(e).__name__}: {e}"[:2000],
            "result": None,
            "result_rows": [],
        }

    stdout = stdout_capture.getvalue()[:3000]
    stderr = stderr_capture.getvalue()[:2000]

    result_rows = []
    result_str = ""
    if result_val is not None:
        if hasattr(result_val, "to_pandas"):
            result_val = result_val.to_pandas()
        if hasattr(result_val, "to_dict"):
            result_rows = _convert_to_safe(result_val.head(20).to_dict("records"))
            result_str = result_val.head(20).to_string()
        elif isinstance(result_val, (list, dict)):
            result_str = json.dumps(result_val, default=str, indent=2)[:2000]
            if isinstance(result_val, list):
                result_rows = [{"output": json.dumps(d, default=str)} for d in result_val[:20]]
            else:
                result_rows = [{"output": result_str}]
        else:
            result_str = str(result_val)[:2000]
            result_rows = [{"output": result_str}]

    return {
        "success": True,
        "stdout": stdout,
        "stderr": stderr,
        "result": result_str,
        "result_rows": result_rows,
    }


async def run_agent(query: str, max_steps: int = 6):
    context = AgentContext(AGENT_SYSTEM_PROMPT)

    user_msg = f"""Dataset schema:
{DATASET_SCHEMA}

User query: {query}

Follow the workflow. Start by inspecting the data."""
    context.add_user(user_msg)

    exec_outputs: list[str] = []
    final_text = ""
    has_error = False
    all_rows: list[list[dict]] = []

    logger.info(f"Agent starting: query='{query[:50]}...' max_steps={max_steps}")
    for step in range(1, max_steps + 1):
        try:
            logger.info(f"Agent step {step}/{max_steps}")
            yield {"event": "status", "data": {"phase": "reasoning", "step": step, "max_steps": max_steps, "message": f"Step {step}/{max_steps}"}}

            messages = context.get_messages()
            response = await _call_modal_messages(messages)
            logger.info(f"Agent step {step} LLM response: {len(response)} chars")
            if not response:
                logger.warning(f"Agent step {step}: empty LLM response")
                yield {"event": "error", "data": {"message": "LLM unavailable for agent step."}}
                has_error = True
                break

            context.add_assistant(response)
            final_text = response
            yield {"event": "agent_text", "data": {"text": response, "step": step}}

            if any(m in response for m in FINISH_MARKERS):
                break

            code_blocks = extract_code_blocks(response)
            if not code_blocks:
                break

            for code in code_blocks:
                logger.info(f"Agent step {step}: executing code ({len(code)} chars)")
                yield {"event": "code_ready", "data": {"code": code.strip(), "step": step}}
                yield {"event": "status", "data": {"phase": "executing", "step": step, "message": f"Executing step {step}..."}}

                exec_result = execute_code_locally(code.strip())
                logger.info(f"Agent step {step}: execution result success={exec_result['success']} rows={len(exec_result['result_rows'])}")

                stdout = exec_result["stdout"]
                stderr = exec_result["stderr"]
                result_val = exec_result["result"]
                success = exec_result["success"]

                rows = exec_result.get("result_rows", [])
                yield {"event": "exec_result", "data": {
                    "stdout": stdout[:1500],
                    "stderr": stderr[:1000],
                    "success": success,
                    "step": step,
                    "result_rows": rows,
                }}
                if rows:
                    all_rows.append(rows)

                if success:
                    raw = stdout.strip()
                    stored = raw
                    if result_val:
                        stored += f"\n{result_val}"
                    if raw:
                        exec_outputs.append(stored)
                    context.add_result(stored or "(no output)")
                else:
                    context.add_result(f"Error: {stderr}")

        except Exception as e:
            logger.exception(f"Agent step {step} failed")
            yield {"event": "error", "data": {"message": f"Step {step} error: {e}"}}
            has_error = True
            break

    if not has_error:
        ans = extract_answer(final_text, exec_outputs)
        if not ans:
            ans = _build_natural_answer(all_rows, exec_outputs)
        if ans:
            cleaned = ans.replace("**", "").strip()
            yield {"event": "answer", "data": {"text": cleaned}}

        exec_ctx = "\n".join(exec_outputs[-3:]) if exec_outputs else ""
        summary = _llm_summary(query, all_rows, exec_ctx)
        if not summary:
            summary = cleaned
        yield {"event": "summary", "data": {"text": summary}}

    yield {"event": "done", "data": {}}
