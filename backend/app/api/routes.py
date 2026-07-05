import time
import sys
import io
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from app.services.llm_engine import synthesize_code
from app.services.e2b_sandbox import execute_on_gpu
from app.data.bigquery import get_dataframe

router = APIRouter()

class SynthesizeRequest(BaseModel):
    query: str
    task_type: str = "data_analysis"

class SynthesizeResponse(BaseModel):
    cpu_code: str
    gpu_code: str

class ExecuteRequest(BaseModel):
    code: str

class ExecuteCpuResponse(BaseModel):
    execution_time_sec: float
    status: str
    results: Optional[List[Dict[str, Any]]] = None

class ExecuteGpuResponse(BaseModel):
    execution_time_sec: float
    results: List[Dict[str, Any]]
    logs: List[str]

@router.post("/api/synthesize", response_model=SynthesizeResponse)
def synthesize(request: SynthesizeRequest):
    try:
        code = synthesize_code(request.query, request.task_type)
        return SynthesizeResponse(cpu_code=code, gpu_code=code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/execute-cpu", response_model=ExecuteCpuResponse)
def execute_cpu(request: ExecuteRequest):
    try:
        # Get the global dataframe
        df = get_dataframe()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data not loaded: {str(e)}")

    start_time = time.perf_counter()
    
    # We capture stdout to get the result that the code prints
    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()
    
    try:
        # Provide the dataframe in the local environment
        local_env = {"df": df, "pd": __import__("pandas")}
        exec(request.code, local_env)
        execution_time = time.perf_counter() - start_time
        
        # Parse the printed output
        output_str = redirected_output.getvalue().strip()
        results = []
        if output_str:
            try:
                parsed = json.loads(output_str)
                results = parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                results = [{"raw_output": output_str}]
                
        return ExecuteCpuResponse(
            execution_time_sec=execution_time,
            status="success",
            results=results
        )
    except Exception as e:
        execution_time = time.perf_counter() - start_time
        return ExecuteCpuResponse(
            execution_time_sec=execution_time,
            status=f"error: {str(e)}"
        )
    finally:
        sys.stdout = old_stdout

@router.post("/api/execute-gpu", response_model=ExecuteGpuResponse)
def execute_gpu(request: ExecuteRequest):
    try:
        response_data = execute_on_gpu(request.code)
        return ExecuteGpuResponse(**response_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
