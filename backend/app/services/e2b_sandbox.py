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
    and pre-loads the cuDF DataFrame into the GPU memory so it's instantly 
    ready for all future requests.
    """
    global global_sandbox
    if global_sandbox is not None:
        return
        
    logger.info("Initializing persistent E2B Sandbox (GPU)...")
    global_sandbox = Sandbox.create(api_key=settings.e2b_api_key)
    
    if os.path.exists(PARQUET_FILE_PATH):
        logger.info(f"Uploading massive parquet data to Sandbox ONCE...")
        with open(PARQUET_FILE_PATH, "rb") as f:
            global_sandbox.files.write("/home/user/data.parquet", f)
    else:
        logger.warning("Local parquet file not found. Sandbox will not have data.")
        
    logger.info("Pre-warming GPU and loading data into cuDF DataFrame in the Sandbox memory...")
    setup_code = """
import sys
import subprocess

try:
    import pyarrow
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyarrow"], stdout=subprocess.DEVNULL)

try:
    import cudf
    import json
    import numpy as np
    print("Loading data into GPU memory...", file=sys.stderr)
    df = cudf.read_parquet('/home/user/data.parquet')
    print(f"Loaded {len(df)} rows into cuDF.", file=sys.stderr)
except Exception as e:
    print(f"Error during Sandbox initialization: {e}", file=sys.stderr)
"""
    execution = global_sandbox.run_code(setup_code)
    if execution.error:
        logger.error(f"Failed to pre-warm sandbox: {execution.error}")
    else:
        logger.info("Sandbox pre-warmed and ready.")


def execute_on_gpu(user_code: str) -> dict:
    """
    Executes the given cuDF code securely on the pre-warmed E2B Sandbox.
    """
    global global_sandbox
    logs = []
    
    start_time = time.perf_counter()
    
    if global_sandbox is None:
        logs.append("Sandbox was not initialized. Initializing now...")
        init_sandbox()
        
    current_code = user_code
    retry_count = 0
    final_results = None
    pure_exec_time = None
    
    while retry_count < MAX_RETRIES:
        logger.info(f"Executing code on Sandbox (Attempt {retry_count + 1})...")
        logs.append(f"Executing attempt {retry_count + 1}...")
        
        # Wrap the code to measure the exact millisecond execution time strictly inside the VM
        wrapper_code = f"""
import time
import sys
__e2b_start = time.perf_counter()
try:
    exec({repr(current_code)})
finally:
    __e2b_end = time.perf_counter()
    print(f"__E2B_EXEC_TIME_SEC__:{{__e2b_end - __e2b_start}}", file=sys.stderr)
"""
        
        execution = global_sandbox.run_code(wrapper_code)
        
        if execution.error:
            error_msg = f"{execution.error.name}: {execution.error.value}\n{execution.error.traceback}"
            logger.warning(f"Execution Error: {error_msg}")
            logs.append(f"Execution Error: {error_msg}")
            
            # Fallback logic to fix the code
            if retry_count < MAX_RETRIES - 1:
                logger.info("Falling back to LLM to fix code...")
                logs.append("Falling back to LLM to fix code...")
                current_code = fix_code(current_code, error_msg)
            retry_count += 1
        else:
            # Execution successful
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

    # Note: We NO LONGER kill the sandbox here, so it stays alive for the next request!
    # global_sandbox.kill()

    end_time = time.perf_counter()
    overall_time = end_time - start_time
    
    # Use pure_exec_time if we successfully intercepted it, otherwise fallback to overall time
    final_time = pure_exec_time if pure_exec_time is not None else overall_time
    
    return {
        "execution_time_sec": final_time,
        "results": final_results if isinstance(final_results, list) else [final_results],
        "logs": logs
    }
