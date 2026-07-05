import os
import time
import json
import logging
from e2b_code_interpreter import Sandbox
from app.core.config import settings
from app.data.bigquery import PARQUET_FILE_PATH
from app.services.llm_engine import fix_code

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

global_sandbox: Sandbox | None = None

def init_sandbox() -> None:
    """
    Initializes a persistent E2B Sandbox, uploads the parquet file ONCE,
    and pre-loads the data into BOTH cuDF (GPU) and pandas (CPU) DataFrames
    so both backends are instantly ready for fair benchmarking.
    """
    global global_sandbox
    if global_sandbox is not None:
        return
        
    logger.info("Initializing persistent E2B Sandbox...")
    global_sandbox = Sandbox.create(api_key=settings.e2b_api_key)
    
    if os.path.exists(PARQUET_FILE_PATH):
        logger.info("Uploading parquet data to Sandbox ONCE...")
        with open(PARQUET_FILE_PATH, "rb") as f:
            global_sandbox.files.write("/home/user/data.parquet", f)
    else:
        logger.warning("Local parquet file not found. Sandbox will not have data.")
        
    logger.info("Pre-warming: loading data into BOTH cuDF (GPU) and pandas (CPU)...")
    setup_code = """
import sys
import subprocess

try:
    import pyarrow
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyarrow"], stdout=subprocess.DEVNULL)

import pandas as pd
import json
import numpy as np

# Load into pandas (CPU) — stored as `pdf`
print("Loading data into pandas (CPU)...", file=sys.stderr)
pdf = pd.read_parquet('/home/user/data.parquet')
print(f"Loaded {len(pdf)} rows into pandas.", file=sys.stderr)

# Load into cuDF (GPU) — stored as `gdf`
try:
    import cudf
    print("Loading data into cuDF (GPU)...", file=sys.stderr)
    gdf = cudf.read_parquet('/home/user/data.parquet')
    print(f"Loaded {len(gdf)} rows into cuDF.", file=sys.stderr)
except Exception as e:
    print(f"cuDF not available: {e}", file=sys.stderr)
    gdf = None
"""
    execution = global_sandbox.run_code(setup_code)
    if execution.error:
        logger.error(f"Failed to pre-warm sandbox: {execution.error}")
    else:
        logger.info("Sandbox pre-warmed and ready (both CPU and GPU data loaded).")


def execute_in_sandbox(user_code: str, mode: str = "gpu") -> dict:
    """
    Executes code inside the persistent E2B Sandbox.
    
    mode="gpu" → sets df = gdf (cuDF DataFrame) before running user code
    mode="cpu" → sets df = pdf (pandas DataFrame) before running user code
    
    This ensures a fair apples-to-apples comparison where the ONLY difference
    is the DataFrame engine, not network overhead.
    """
    global global_sandbox
    logs = []
    
    if global_sandbox is None:
        logs.append("Sandbox was not initialized. Initializing now...")
        init_sandbox()
    
    # Pick the right DataFrame based on mode
    if mode == "gpu":
        df_assign = "df = gdf"
        logs.append("Mode: GPU (cuDF)")
    else:
        df_assign = "df = pdf"
        logs.append("Mode: CPU (pandas)")

    current_code = user_code
    retry_count = 0
    final_results = None
    pure_exec_time = None
    
    while retry_count < MAX_RETRIES:
        logger.info(f"Executing {mode.upper()} code on Sandbox (Attempt {retry_count + 1})...")
        logs.append(f"Executing attempt {retry_count + 1}...")
        
        # Wrap user code with:
        # 1. df assignment (pandas or cuDF)
        # 2. Internal timer that measures PURE execution time
        wrapper_code = f"""
import time
import sys
{df_assign}
__e2b_start = time.perf_counter()
try:
    exec({repr(current_code)})
finally:
    __e2b_end = time.perf_counter()
    print(f"__E2B_EXEC_TIME_SEC__:{{__e2b_end - __e2b_start}}", file=sys.stderr)
"""
        
        try:
            execution = global_sandbox.run_code(wrapper_code)
        except Exception as e:
            error_str = str(e).lower()
            if "not found" in error_str or "timeout" in error_str:
                logger.warning("E2B Sandbox timed out or was not found. Re-initializing...")
                logs.append("Sandbox timed out. Re-initializing...")
                global_sandbox = None
                init_sandbox()
                continue  # Retry with the new sandbox
            else:
                # If it's a different exception from E2B SDK, we should still fail or handle it
                logger.error(f"E2B SDK Error: {e}")
                logs.append(f"E2B SDK Error: {e}")
                break
        
        if execution.error:
            error_msg = f"{execution.error.name}: {execution.error.value}\n{execution.error.traceback}"
            logger.warning(f"Execution Error: {error_msg}")
            logs.append(f"Execution Error: {error_msg}")
            
            if retry_count < MAX_RETRIES - 1:
                logger.info("Falling back to LLM to fix code...")
                logs.append("Falling back to LLM to fix code...")
                current_code = fix_code(current_code, error_msg)
            retry_count += 1
        else:
            logger.info("Execution successful.")
            logs.append("Execution successful.")
            
            # Extract the pure execution time from stderr
            if execution.logs.stderr:
                for line in execution.logs.stderr:
                    if "__E2B_EXEC_TIME_SEC__:" in line:
                        try:
                            pure_exec_time = float(line.split("__E2B_EXEC_TIME_SEC__:")[1].strip())
                        except Exception:
                            pass

            if execution.logs.stdout:
                output_str = "\n".join(execution.logs.stdout).strip()
                logs.append(f"Stdout:\n{output_str}")
                try:
                    final_results = json.loads(output_str)
                except json.JSONDecodeError:
                    logs.append("Could not parse output as JSON. Storing raw string.")
                    final_results = [{"raw_output": output_str}]
            else:
                logs.append("No stdout generated.")
                final_results = []
            
            break
            
    if retry_count == MAX_RETRIES and final_results is None:
        logs.append("Max retries reached. Failed to execute code successfully.")
        final_results = []

    return {
        "execution_time_sec": pure_exec_time if pure_exec_time is not None else 0.0,
        "results": final_results if isinstance(final_results, list) else [final_results],
        "logs": logs
    }


# Convenience wrappers
def execute_on_gpu(user_code: str) -> dict:
    return execute_in_sandbox(user_code, mode="gpu")

def execute_on_cpu(user_code: str) -> dict:
    return execute_in_sandbox(user_code, mode="cpu")
