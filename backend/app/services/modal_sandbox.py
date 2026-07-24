import json
import logging
import os
import sys
import time
import threading

import modal
from modal.exception import AuthError

from app.core.config import settings
from app.data.bigquery import PARQUET_FILE_PATH
from app.services.llm_engine import fix_code

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Force the Modal SDK to use the credentials from .env / Cloud Run env vars
# instead of falling back to the local ~/.modal.toml file.
# This ensures sandboxes are created on the teammate's workspace.
# ─────────────────────────────────────────────────────────────────────────────
if settings.modal_token_id:
    os.environ["MODAL_TOKEN_ID"] = settings.modal_token_id
if settings.modal_token_secret:
    os.environ["MODAL_TOKEN_SECRET"] = settings.modal_token_secret

MAX_RETRIES = 3

# ─────────────────────────────────────────────────────────────────────────────
# Modal Image Definitions
# These are evaluated once at module import time. Modal caches built images so
# repeated calls do NOT rebuild from scratch.
# ─────────────────────────────────────────────────────────────────────────────

# CPU sandbox — lightweight, pandas + sklearn only
cpu_image = (
    modal.Image.debian_slim()
    .pip_install("pandas", "pyarrow", "scikit-learn", "numpy")
)

# GPU sandbox — RAPIDS (cuDF + cuML) via NVIDIA's PyPI index
gpu_image = (
    modal.Image.debian_slim()
    .pip_install(
        "cudf-cu12",
        "cuml-cu12",
        "pyarrow",
        "numpy",
        extra_index_url="https://pypi.nvidia.com",
    )
)


def _build_wrapper_code(user_code: str, mode: str) -> str:
    """
    Wraps the LLM-generated user_code with:
      - A pre-warm step that forces library/CUDA initialisation BEFORE the timer.
      - A precise perf_counter timer around the user code ONLY (post-warmup).
      - Emits __WARMUP_TIME_SEC__ and __EXEC_TIME_SEC__ on stderr for the caller.
      - Expects `result` to be set by user_code; prints it as JSON to stdout.

    GPU warmup triggers:
      • cuDF import (lazy JIT compilation)
      • A tiny cuDF groupby → forces CUDA context creation and GPU memory alloc
    CPU warmup mirrors the same pattern with pandas so timings stay comparable.
    """
    if mode == "gpu":
        import_line = "import cudf; df = cudf.read_parquet('/tmp/data.parquet')"
        # Force CUDA context + cuDF JIT on a tiny slice — do NOT use the full df
        warmup_block = """\
# ── GPU warmup: force CUDA context + cuDF JIT before the real timer ──
import cudf as _cudf_warmup
_tiny = _cudf_warmup.DataFrame({'x': [1, 2, 3], 'g': [0, 1, 0]})
_ = _tiny.groupby('g')['x'].sum()          # forces CUDA kernel compile
del _tiny, _cudf_warmup
"""
    else:
        import_line = "import pandas as pd; df = pd.read_parquet('/tmp/data.parquet')"
        # Mirror op so CPU warmup overhead is also measured and excluded
        warmup_block = """\
# ── CPU warmup: lazy pandas/numpy imports + trivial op ──
import pandas as _pd_warmup, numpy as _np_warmup
_tiny = _pd_warmup.DataFrame({'x': [1, 2, 3], 'g': [0, 1, 0]})
_ = _tiny.groupby('g')['x'].sum()
del _tiny, _pd_warmup, _np_warmup
"""

    return f"""\
import sys, time, json, numpy as np

# ---------- Data loading ----------
{import_line}

# ---------- Warmup (timed, then discarded) ----------
__warmup_t0 = time.perf_counter()
{warmup_block}
__warmup_elapsed = time.perf_counter() - __warmup_t0
print(f"__WARMUP_TIME_SEC__:{{__warmup_elapsed}}", file=sys.stderr)

# ---------- User code (timed AFTER warmup) ----------
result = None
__t0 = time.perf_counter()
try:
    exec({repr(user_code)}, {{"df": df, "np": np}})
except Exception as _user_exc:
    print(f"Exception in user code: {{type(_user_exc).__name__}}: {{_user_exc}}", file=sys.stderr)
    sys.exit(1)
finally:
    __elapsed = time.perf_counter() - __t0
    print(f"__EXEC_TIME_SEC__:{{__elapsed}}", file=sys.stderr)

# ---------- Serialise result ----------
try:
    # cuDF -> pandas for JSON serialisation
    if hasattr(result, "to_pandas"):
        result = result.to_pandas()
    if hasattr(result, "to_dict"):
        output = result.head(20).to_dict("records")
    elif result is None:
        output = []
    else:
        output = str(result)
    # Convert numpy scalar types and pandas Timestamps to native Python for json.dumps
    def _json_fallback(o):
        if hasattr(o, "item"): return o.item()
        if hasattr(o, "isoformat"): return o.isoformat()
        return str(o)
        
    output = json.loads(json.dumps(output, default=_json_fallback))
    print(json.dumps(output))
except Exception as _ser_exc:
    print(f"Serialisation Error: {{type(_ser_exc).__name__}}: {{_ser_exc}}", file=sys.stderr)
    print(json.dumps([]))
"""


def execute_in_modal(user_code: str, mode: str = "gpu") -> dict:
    """
    Executes LLM-generated code inside a Modal Sandbox.

    mode="gpu"  → provisions a T4 GPU sandbox running cuDF + cuML
    mode="cpu"  → provisions a CPU-only sandbox running pandas + sklearn

    Auth: Modal reads MODAL_TOKEN_ID and MODAL_TOKEN_SECRET from the
    environment automatically — no explicit client construction needed.

    Returns a dict with:
        execution_time_sec  float   — pure user-code wall time
        results             list    — up to 20 rows as list-of-dicts
        logs                list    — human-readable event log
    """
    logs: list[str] = []
    image = gpu_image if mode == "gpu" else cpu_image
    gpu_spec = "T4" if mode == "gpu" else None
    mode_label = "GPU (cuDF)" if mode == "gpu" else "CPU (pandas)"
    logs.append(f"Mode: {mode_label}")

    current_code = user_code
    pure_exec_time: float | None = None
    warmup_time: float | None = None
    final_results = None

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"Modal Sandbox [{mode.upper()}] attempt {attempt}/{MAX_RETRIES}")
        logs.append(f"Attempt {attempt}/{MAX_RETRIES}: spinning up Modal Sandbox...")

        sb = None
        try:
            # Look up (or lazily create) the app — no server-side state kept
            app = modal.App.lookup("datasense-sandbox", create_if_missing=True)

            # Provision the sandbox — wrap with enable_output() so image build
            # progress (pip installs etc.) streams to the uvicorn console.
            create_kwargs = dict(app=app, image=image, timeout=1800)
            if gpu_spec:
                create_kwargs["gpu"] = gpu_spec

            with modal.enable_output():
                sb = modal.Sandbox.create(**create_kwargs)
            logs.append(f"Sandbox created: {sb.object_id}")

            # Upload parquet data into the sandbox at runtime
            if os.path.exists(PARQUET_FILE_PATH):
                sb.filesystem.copy_from_local(PARQUET_FILE_PATH, "/tmp/data.parquet")
                logs.append("Dataset uploaded to sandbox.")
            else:
                raise FileNotFoundError(
                    f"Parquet file not found at {PARQUET_FILE_PATH}. "
                    "Did fetch_ecommerce_data() run successfully?"
                )

            # Build the full wrapper script
            wrapper_code = _build_wrapper_code(current_code, mode)

            # ── Execute by piping code through stdin ──────────────────────────
            # -u = unbuffered so we get logs in real time
            process = sb.exec("python", "-u", "-")
            process.stdin.write(wrapper_code.encode("utf-8"))
            process.stdin.write_eof()
            process.stdin.drain()  # CRITICAL: flush the buffer to the sandbox

            # ── Stream stdout + stderr concurrently while process runs ─────────
            # Collect both streams in background threads so neither blocks the other.
            stdout_chunks: list[str] = []
            stderr_chunks: list[str] = []

            def _read_stdout():
                for line in process.stdout:
                    stdout_chunks.append(line)
                    logger.debug(f"[sandbox stdout] {line.rstrip()}")

            def _read_stderr():
                for line in process.stderr:
                    stderr_chunks.append(line)
                    logger.info(f"[sandbox stderr] {line.rstrip()}")

            t_out = threading.Thread(target=_read_stdout, daemon=True)
            t_err = threading.Thread(target=_read_stderr, daemon=True)
            t_out.start()
            t_err.start()

            return_code = process.wait()
            t_out.join(timeout=10)
            t_err.join(timeout=10)

            stdout_lines = "".join(stdout_chunks)
            stderr_lines = "".join(stderr_chunks)

            # ── Parse exec time and warmup time from stderr ─────────────────
            for line in (stderr_lines or "").splitlines():
                if "__EXEC_TIME_SEC__:" in line:
                    try:
                        pure_exec_time = float(line.split("__EXEC_TIME_SEC__:")[1].strip())
                    except ValueError:
                        pass
                elif "__WARMUP_TIME_SEC__:" in line:
                    try:
                        warmup_time = float(line.split("__WARMUP_TIME_SEC__:")[1].strip())
                        logs.append(f"Warmup time (excluded from benchmark): {warmup_time:.3f}s")
                    except ValueError:
                        pass

            if return_code != 0:
                error_msg = stderr_lines or "Non-zero exit code with no stderr."
                logger.warning(f"Sandbox execution failed (rc={return_code}): {error_msg}")
                logs.append(f"Execution error: {error_msg}")

                if attempt < MAX_RETRIES:
                    logs.append("Asking LLM to fix code...")
                    current_code = fix_code(current_code, error_msg, mode=mode)
                continue  # retry

            # ── Parse JSON result from stdout ────────────────────────────────
            stdout_str = (stdout_lines or "").strip()
            logs.append(f"Stdout received ({len(stdout_str)} chars).")

            if stdout_str:
                try:
                    final_results = json.loads(stdout_str)
                    if not isinstance(final_results, list):
                        final_results = [final_results]
                except json.JSONDecodeError:
                    logs.append("Could not parse stdout as JSON — storing raw.")
                    final_results = [{"raw_output": stdout_str}]
            else:
                logs.append("No stdout output from user code.")
                final_results = []

            logs.append("Execution successful.")
            break  # done

        except AuthError as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error(f"Modal AuthError on attempt {attempt}: {error_msg}")
            logs.append(f"AuthError: {error_msg}")
            break  # fail fast — retrying won't fix bad credentials
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error(f"Modal Sandbox error on attempt {attempt}: {error_msg}")
            logs.append(f"Error: {error_msg}")

            if attempt < MAX_RETRIES:
                logs.append("Retrying...")
        finally:
            if sb is not None:
                try:
                    sb.terminate()
                    logs.append("Sandbox terminated.")
                except Exception as term_exc:
                    logger.warning(f"Failed to terminate sandbox: {term_exc}")

    if final_results is None:
        logs.append("Max retries reached — execution failed.")
        final_results = []

    return {
        "execution_time_sec": pure_exec_time if pure_exec_time is not None else 0.0,
        "warmup_time_sec": warmup_time if warmup_time is not None else 0.0,
        "results": final_results if isinstance(final_results, list) else [final_results],
        "logs": logs,
        "attempts_used": attempt,
    }


def confidence_from_attempts(attempts: int) -> str:
    """
    Reliability tier for a result, derived from how many attempts it took.
    Scales with MAX_RETRIES rather than hardcoding attempt counts, so this
    stays correct if the retry budget changes.
    """
    if attempts <= 1:
        return "high"
    if attempts >= MAX_RETRIES:
        return "low"
    return "medium"


# ─────────────────────────────────────────────────────────────────────────────
# Convenience wrappers (match the old e2b_sandbox.py interface exactly)
# ─────────────────────────────────────────────────────────────────────────────

def execute_on_gpu(user_code: str) -> dict:
    """Run user_code on a Modal GPU (T4) sandbox using cuDF."""
    return execute_in_modal(user_code, mode="gpu")


def execute_on_cpu(user_code: str) -> dict:
    """Run user_code on a Modal CPU sandbox using pandas."""
    return execute_in_modal(user_code, mode="cpu")


# ─────────────────────────────────────────────────────────────────────────────
# Pre-warm API — create sandbox + upload data BEFORE code is ready
# Used by /api/benchmark to overlap sandbox startup with LLM inference time.
# ─────────────────────────────────────────────────────────────────────────────

def prewarm_sandbox(mode: str) -> modal.Sandbox:
    """
    Creates a Modal Sandbox and uploads the parquet dataset into it.
    The sandbox stays alive via 'sleep infinity' until terminate() is called.
    Intended to run concurrently with LLM code synthesis so the sandbox is
    ready the moment code arrives.
    """
    image = gpu_image if mode == "gpu" else cpu_image
    gpu_spec = "T4" if mode == "gpu" else None

    logger.info(f"Pre-warming [{mode.upper()}] sandbox...")
    app = modal.App.lookup("datasense-sandbox", create_if_missing=True)

    create_kwargs = dict(
        app=app,
        image=image,
        # 1800s timeout: first-run RAPIDS image pull can take 10+ minutes
        timeout=1800,
    )
    if gpu_spec:
        create_kwargs["gpu"] = gpu_spec

    # By passing NO positional arguments, the sandbox stays alive waiting for .exec()
    sb = modal.Sandbox.create(**create_kwargs)

    if not os.path.exists(PARQUET_FILE_PATH):
        sb.terminate()
        raise FileNotFoundError(
            f"Parquet file not found at {PARQUET_FILE_PATH}. "
            "Did fetch_ecommerce_data() run at startup?"
        )

    sb.filesystem.copy_from_local(PARQUET_FILE_PATH, "/tmp/data.parquet")
    logger.info(f"[{mode.upper()}] sandbox pre-warmed and data uploaded.")
    return sb


def execute_on_prewarmed_sandbox(sb: modal.Sandbox, user_code: str, mode: str) -> dict:
    """
    Executes LLM-generated code on an already-running, pre-warmed sandbox.
    Skips sandbox creation and data upload (already done in prewarm_sandbox).
    """
    logs: list[str] = []
    mode_label = "GPU (cuDF)" if mode == "gpu" else "CPU (pandas)"
    logs.append(f"Mode: {mode_label} [pre-warmed]")

    current_code = user_code
    pure_exec_time: float | None = None
    warmup_time: float | None = None
    final_results = None

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"Executing on pre-warmed [{mode.upper()}] sandbox, attempt {attempt}/{MAX_RETRIES}")
        logs.append(f"Attempt {attempt}: executing on pre-warmed sandbox...")
        try:
            wrapper_code = _build_wrapper_code(current_code, mode)

            process = sb.exec("python", "-u", "-")
            process.stdin.write(wrapper_code.encode("utf-8"))
            process.stdin.write_eof()
            return_code = process.wait()

            stdout_lines = process.stdout.read()
            stderr_lines = process.stderr.read()

            for line in (stderr_lines or "").splitlines():
                if "__EXEC_TIME_SEC__:" in line:
                    try:
                        pure_exec_time = float(line.split("__EXEC_TIME_SEC__:")[1].strip())
                    except ValueError:
                        pass
                elif "__WARMUP_TIME_SEC__:" in line:
                    try:
                        warmup_time = float(line.split("__WARMUP_TIME_SEC__:")[1].strip())
                        logs.append(f"Warmup (excluded from benchmark): {warmup_time:.3f}s")
                    except ValueError:
                        pass

            if return_code != 0:
                error_msg = stderr_lines or "Non-zero exit with no stderr."
                logs.append(f"Execution error: {error_msg}")
                if attempt < MAX_RETRIES:
                    logs.append("Asking LLM to fix code...")
                    current_code = fix_code(current_code, error_msg)
                continue

            stdout_str = (stdout_lines or "").strip()
            if stdout_str:
                try:
                    final_results = json.loads(stdout_str)
                    if not isinstance(final_results, list):
                        final_results = [final_results]
                except json.JSONDecodeError:
                    final_results = [{"raw_output": stdout_str}]
            else:
                final_results = []

            logs.append("Execution successful.")
            break

        except AuthError as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error(f"AuthError on pre-warmed sandbox: {error_msg}")
            logs.append(f"AuthError: {error_msg}")
            break
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error(f"Execution error on pre-warmed sandbox attempt {attempt}: {error_msg}")
            logs.append(f"Error: {error_msg}")
            if attempt < MAX_RETRIES:
                logs.append("Retrying...")

    if final_results is None:
        logs.append("Max retries reached — execution failed.")
        final_results = []

    return {
        "execution_time_sec": pure_exec_time if pure_exec_time is not None else 0.0,
        "warmup_time_sec": warmup_time if warmup_time is not None else 0.0,
        "results": final_results if isinstance(final_results, list) else [final_results],
        "logs": logs,
    }
