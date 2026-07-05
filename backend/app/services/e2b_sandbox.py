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

def execute_on_gpu(user_code: str) -> dict:
    """
    Executes the given pandas code securely on an E2B Sandbox with cuDF.
    """
    logs = []
    
    start_time = time.perf_counter()
    
    # Initialize the Sandbox
    logger.info("Initializing E2B Sandbox...")
    logs.append("Initializing E2B Sandbox...")
    try:
        sandbox = Sandbox.create(api_key=settings.e2b_api_key)
    except Exception as e:
        logger.error(f"Failed to initialize sandbox: {e}")
        return {"execution_time_sec": 0, "results": [], "logs": logs + [f"Failed to initialize sandbox: {e}"]}
    
    try:
        # Check if the parquet file exists locally to upload
        if os.path.exists(PARQUET_FILE_PATH):
            logger.info("Uploading parquet data to Sandbox...")
            logs.append("Uploading parquet data to Sandbox...")
            with open(PARQUET_FILE_PATH, "rb") as f:
                sandbox.files.write("/home/user/data.parquet", f)
        else:
            logger.warning("Local parquet file not found. Sandbox will not have data.")
            logs.append("Warning: Local parquet file not found.")

        # Prepare the injection payload
        setup_code = """
import sys
import subprocess

# Ensure pyarrow is installed to read parquet
try:
    import pyarrow
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyarrow"], stdout=subprocess.DEVNULL)

# Try to use cuDF (GPU accelerated pandas) if available
try:
    import cudf.pandas
    cudf.pandas.install()
    print("cuDF enabled for GPU acceleration.", file=sys.stderr)
except Exception as e:
    print(f"cuDF not available, falling back to standard CPU pandas. (Reason: {e})", file=sys.stderr)

import pandas as pd
import json

# Load the dataset
try:
    df = pd.read_parquet('/home/user/data.parquet')
except Exception as e:
    print(f"Error loading data: {e}", file=sys.stderr)
"""
        
        current_code = user_code
        retry_count = 0
        final_results = None
        
        while retry_count < MAX_RETRIES:
            full_code = setup_code + "\n\n" + current_code
            logger.info(f"Executing code on Sandbox (Attempt {retry_count + 1})...")
            logs.append(f"Executing attempt {retry_count + 1}...")
            
            execution = sandbox.run_code(full_code)
            
            if execution.error:
                error_msg = f"{execution.error.name}: {execution.error.value}\n{execution.error.traceback}"
                logger.warning(f"Execution Error: {error_msg}")
                logs.append(f"Execution Error: {error_msg}")
                
                # Fallback logic to fix the code
                if retry_count < MAX_RETRIES - 1:
                    logger.info("Falling back to Gemini to fix code...")
                    logs.append("Falling back to Gemini to fix code...")
                    current_code = fix_code(current_code, error_msg)
                retry_count += 1
            else:
                # Execution successful
                # Try to parse the printed output as JSON
                logger.info("Execution successful.")
                logs.append("Execution successful.")
                
                if execution.logs.stdout:
                    # Collect all stdout lines
                    output_str = "\n".join(execution.logs.stdout).strip()
                    logs.append(f"Stdout:\n{output_str}")
                    try:
                        # Find the first valid JSON block if there are multiple prints
                        # For simplicity, let's assume the whole output is the JSON
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

    finally:
        logger.info("Killing E2B Sandbox...")
        sandbox.kill()

    end_time = time.perf_counter()
    execution_time = end_time - start_time
    
    return {
        "execution_time_sec": execution_time,
        "results": final_results if isinstance(final_results, list) else [final_results],
        "logs": logs
    }
