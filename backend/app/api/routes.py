import time
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from app.services.llm_engine import synthesize_code
from app.services.e2b_sandbox import execute_on_gpu, execute_on_cpu

router = APIRouter()

class SynthesizeRequest(BaseModel):
    query: str
    task_type: str = "data_analysis"

class SynthesizeResponse(BaseModel):
    cpu_code: str
    gpu_code: str

class ExecuteRequest(BaseModel):
    code: str

class ExecuteResponse(BaseModel):
    execution_time_sec: float
    results: Optional[List[Dict[str, Any]]] = None
    logs: List[str] = []
    status: str = "success"

@router.post("/api/synthesize", response_model=SynthesizeResponse)
def synthesize(request: SynthesizeRequest):
    try:
        gpu_code = synthesize_code(request.query, request.task_type)
        # Convert cuDF code → pandas code for CPU execution
        cpu_code = gpu_code.replace("import cudf", "import pandas as pd").replace("cudf.", "pd.")
        return SynthesizeResponse(cpu_code=cpu_code, gpu_code=gpu_code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/execute-cpu", response_model=ExecuteResponse)
def execute_cpu(request: ExecuteRequest):
    """Execute pandas code on CPU inside the E2B Sandbox for fair benchmarking."""
    try:
        response_data = execute_on_cpu(request.code)
        return ExecuteResponse(
            execution_time_sec=response_data["execution_time_sec"],
            results=response_data["results"],
            logs=response_data["logs"],
            status="success"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/execute-gpu", response_model=ExecuteResponse)
def execute_gpu(request: ExecuteRequest):
    """Execute cuDF code on GPU inside the E2B Sandbox for fair benchmarking."""
    try:
        response_data = execute_on_gpu(request.code)
        return ExecuteResponse(
            execution_time_sec=response_data["execution_time_sec"],
            results=response_data["results"],
            logs=response_data["logs"],
            status="success"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
