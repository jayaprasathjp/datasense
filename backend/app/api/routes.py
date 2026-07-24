import time
import json
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from app.services.llm_engine import synthesize_code, synthesize_cpu_code, MODEL_NAME
from app.services.modal_sandbox import execute_on_gpu, execute_on_cpu, confidence_from_attempts
from app.services.query_validator import validate_query
from app.services.risk_ranking import enrich_results
from app.services.insight_summary import generate_summary
from app.data.bigquery import get_dataset_info

router = APIRouter()

class DatasetColumn(BaseModel):
    name: str
    dtype: str
    description: str

class DatasetInfoResponse(BaseModel):
    dataset_name: str
    row_count: int
    model_name: str
    columns: List[DatasetColumn]

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
    warmup_time_sec: float = 0.0  # library/CUDA init cost, excluded from benchmark
    results: Optional[List[Dict[str, Any]]] = None
    logs: List[str] = []
    status: str = "success"
    attempts_used: int = 1
    confidence: str = "high"  # "high" | "medium" | "low" — derived from attempts_used
class BenchmarkResult(BaseModel):
    execution_time_sec: float
    warmup_time_sec: float = 0.0
    results: Optional[List[Dict[str, Any]]] = None
    logs: List[str] = []
    status: str = "success"
    attempts_used: int = 1
    confidence: str = "high"  # "high" | "medium" | "low" — derived from attempts_used
    summary: str = ""  # one-line plain-language summary of `results`

class BenchmarkResponse(BaseModel):
    gpu_code: str
    cpu_code: str
    gpu: BenchmarkResult
    cpu: BenchmarkResult
    total_wall_time_sec: float


@router.get("/api/dataset-info", response_model=DatasetInfoResponse)
def dataset_info():
    """Dataset schema, row count, and model label — single source of truth for the frontend."""
    info = get_dataset_info()
    return DatasetInfoResponse(**info, model_name=MODEL_NAME)


@router.post("/api/synthesize", response_model=SynthesizeResponse)
def synthesize(request: SynthesizeRequest):
    is_relevant, reason = validate_query(request.query)
    if not is_relevant:
        raise HTTPException(status_code=400, detail=reason)

    try:
        # Each backend gets its own LLM call with the correct system prompt
        gpu_code = synthesize_code(request.query, request.task_type)
        cpu_code = synthesize_cpu_code(request.query, request.task_type)
        return SynthesizeResponse(cpu_code=cpu_code, gpu_code=gpu_code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/execute-cpu", response_model=ExecuteResponse)
def execute_cpu(request: ExecuteRequest):
    """Execute pandas code on CPU inside a Modal CPU Sandbox for fair benchmarking."""
    try:
        response_data = execute_on_cpu(request.code)
        attempts_used = response_data.get("attempts_used", 1)
        return ExecuteResponse(
            execution_time_sec=response_data["execution_time_sec"],
            warmup_time_sec=response_data["warmup_time_sec"],
            results=response_data["results"],
            logs=response_data["logs"],
            status="success",
            attempts_used=attempts_used,
            confidence=confidence_from_attempts(attempts_used),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/execute-gpu", response_model=ExecuteResponse)
def execute_gpu(request: ExecuteRequest):
    """Execute cuDF code on GPU (T4) inside a Modal GPU Sandbox for fair benchmarking."""
    try:
        response_data = execute_on_gpu(request.code)
        attempts_used = response_data.get("attempts_used", 1)
        return ExecuteResponse(
            execution_time_sec=response_data["execution_time_sec"],
            warmup_time_sec=response_data["warmup_time_sec"],
            results=response_data["results"],
            logs=response_data["logs"],
            status="success",
            attempts_used=attempts_used,
            confidence=confidence_from_attempts(attempts_used),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/benchmark", response_model=BenchmarkResponse)
def benchmark(request: SynthesizeRequest):
    """
    All-in-one benchmark endpoint.

    Runs two full pipelines CONCURRENTLY in background threads:
      Thread A: GPU  → synthesize cuDF code  → create GPU sandbox → execute
      Thread B: CPU  → synthesize pandas code → create CPU sandbox → execute

    This is simpler and more reliable than the pre-warm approach.
    Modal Sandboxes stay alive because .exec() is called immediately
    after create() within the same thread — no race condition.
    """
    is_relevant, reason = validate_query(request.query)
    if not is_relevant:
        raise HTTPException(status_code=400, detail=reason)

    t_start = time.perf_counter()

    def run_gpu():
        code = synthesize_code(request.query, request.task_type)
        result = execute_on_gpu(code)
        result["code"] = code
        return result

    def run_cpu():
        code = synthesize_cpu_code(request.query, request.task_type)
        result = execute_on_cpu(code)
        result["code"] = code
        return result

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_gpu = pool.submit(run_gpu)
            f_cpu = pool.submit(run_cpu)
            gpu_res = f_gpu.result()
            cpu_res = f_cpu.result()

        total_wall = time.perf_counter() - t_start

        # Rank + recommendation, rule-based — only kicks in for the risk/alert
        # task types (classification, rolling_window, ranking); no-op otherwise.
        gpu_results = enrich_results(gpu_res["results"], request.task_type)
        cpu_results = enrich_results(cpu_res["results"], request.task_type)

        gpu_attempts = gpu_res.get("attempts_used", 1)
        cpu_attempts = cpu_res.get("attempts_used", 1)

        return BenchmarkResponse(
            gpu_code=gpu_res.get("code", ""),
            cpu_code=cpu_res.get("code", ""),
            gpu=BenchmarkResult(
                execution_time_sec=gpu_res["execution_time_sec"],
                warmup_time_sec=gpu_res["warmup_time_sec"],
                results=gpu_results,
                logs=gpu_res["logs"],
                status="success",
                attempts_used=gpu_attempts,
                confidence=confidence_from_attempts(gpu_attempts),
                summary=generate_summary(gpu_results, request.task_type),
            ),
            cpu=BenchmarkResult(
                execution_time_sec=cpu_res["execution_time_sec"],
                warmup_time_sec=cpu_res["warmup_time_sec"],
                results=cpu_results,
                logs=cpu_res["logs"],
                status="success",
                attempts_used=cpu_attempts,
                confidence=confidence_from_attempts(cpu_attempts),
                summary=generate_summary(cpu_results, request.task_type),
            ),
            total_wall_time_sec=round(total_wall, 3),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

