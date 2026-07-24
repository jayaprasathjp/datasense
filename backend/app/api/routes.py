import asyncio
import time
import json
import os
import io
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from app.services.llm_engine import synthesize_code, synthesize_cpu_code, _call_modal_stream, _extract_code, _generate_summary
from app.services.llm_engine import SYSTEM_PROMPT_CUDF, SYSTEM_PROMPT_PANDAS
from app.services.modal_sandbox import execute_on_gpu, execute_on_cpu
from app.data.bigquery import PARQUET_FILE_PATH, get_dataframe, get_current_source, load_external_dataset, DATASET_SCHEMA
from app.data.datasets import list_datasets

router = APIRouter()

# ── Request / Response models ────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    query: str
    task_type: str = "data_analysis"
    platform: Optional[str] = None  # "auto" (default), "cpu", "gpu"

class AnalyzeResponse(BaseModel):
    code: str
    platform: str
    execution_time_sec: float
    warmup_time_sec: float = 0.0
    results: Optional[List[Dict[str, Any]]] = None
    logs: List[str] = []
    status: str = "success"

class DatasetInfoResponse(BaseModel):
    row_count: int
    column_count: int
    columns: List[Dict[str, str]]
    preview: List[Dict[str, Any]]
    source: str = "synthetic"

class UploadResponse(BaseModel):
    row_count: int
    column_count: int
    columns: List[str]
    message: str

class DatasetLoadRequest(BaseModel):
    key: str

class DatasetLoadResponse(BaseModel):
    row_count: int
    column_count: int
    message: str

# ── Platform detection ───────────────────────────────────────────────────────

GPU_KEYWORDS = [
    "classif", "predict", "train", "model", "fit",
    "ml", "machine learning", "risk", "gpu",
]

def _detect_platform(query: str) -> str:
    q = query.lower()
    for kw in GPU_KEYWORDS:
        if kw in q:
            return "gpu"
    return "cpu"

# ── Dataset endpoints ────────────────────────────────────────────────────────

@router.get("/api/dataset/info", response_model=DatasetInfoResponse)
def dataset_info():
    try:
        df = get_dataframe()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    preview = df.head(10)
    def safe_val(v):
        if isinstance(v, (pd.Timestamp, pd.Period)):
            return str(v)
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if pd.isna(v):
            return None
        return v

    preview_rows = [
        {col: safe_val(row[col]) for col in df.columns}
        for row in preview.to_dict("records")
    ]

    columns = [{"name": col, "dtype": str(df[col].dtype)} for col in df.columns]

    source = get_current_source()

    return DatasetInfoResponse(
        row_count=len(df),
        column_count=len(df.columns),
        columns=columns,
        preview=preview_rows,
        source=source,
    )


@router.get("/api/datasets")
def list_available_datasets():
    return list_datasets()


@router.post("/api/dataset/load", response_model=DatasetLoadResponse)
def load_dataset(request: DatasetLoadRequest):
    try:
        df = load_external_dataset(request.key)
        return DatasetLoadResponse(
            row_count=len(df),
            column_count=len(df.columns),
            message=f"Loaded {len(df):,} rows with {len(df.columns)} columns.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/dataset/upload", response_model=UploadResponse)
async def upload_dataset(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    try:
        content = await file.read()
        df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {e}")

    from app.data.bigquery import _set_dataframe
    _set_dataframe(df)

    return UploadResponse(
        row_count=len(df),
        column_count=len(df.columns),
        columns=list(df.columns),
        message=f"Loaded {len(df):,} rows with {len(df.columns)} columns.",
    )

# ── Analyze endpoint (auto-select platform) ──────────────────────────────────

def _execute_locally(code: str, mode: str) -> dict:
    logs = [f"Mode: {mode.upper()} (local fallback)"]
    logs.append("Attempting local execution...")

    if not os.path.exists(PARQUET_FILE_PATH):
        return {"execution_time_sec": 0.0, "warmup_time_sec": 0.0, "results": [], "logs": logs + ["Parquet not found."]}

    try:
        df = pd.read_parquet(PARQUET_FILE_PATH)
        logs.append(f"Data loaded: {len(df)} rows")

        warmup_t0 = time.perf_counter()
        time.sleep(0.01)
        warmup_time = time.perf_counter() - warmup_t0

        result = None
        exec_t0 = time.perf_counter()
        try:
            exec(code, {"df": df, "np": np})
        except Exception as exc:
            exec_time = time.perf_counter() - exec_t0
            logs.append(f"Execution error: {type(exc).__name__}: {exc}")
            return {"execution_time_sec": exec_time, "warmup_time_sec": warmup_time, "results": [], "logs": logs}

        exec_time = time.perf_counter() - exec_t0
        logs.append(f"Execution completed in {exec_time:.3f}s")

        if result is None:
            results = []
        elif hasattr(result, "to_pandas"):
            results = result.to_pandas().head(20).to_dict("records")
        elif hasattr(result, "to_dict"):
            results = result.head(20).to_dict("records")
        elif isinstance(result, list):
            results = result[:20]
        else:
            results = [{"output": str(result)}]

        def _json_fallback(o):
            if hasattr(o, "item"): return o.item()
            if hasattr(o, "isoformat"): return o.isoformat()
            return str(o)

        results = json.loads(json.dumps(results, default=_json_fallback))
        logs.append("Results serialised successfully.")
        return {"execution_time_sec": exec_time, "warmup_time_sec": warmup_time, "results": results, "logs": logs}

    except Exception as exc:
        logs.append(f"Local execution error: {type(exc).__name__}: {exc}")
        return {"execution_time_sec": 0.0, "warmup_time_sec": 0.0, "results": [], "logs": logs}


MOCK_RESULTS = {
    "predict risk_label": [
        {"risk_label": 1, "pred_risk": 0.97, "store_id": "S042", "region": "APAC", "revenue": 8920.0},
        {"risk_label": 1, "pred_risk": 0.94, "store_id": "S107", "region": "EMEA", "revenue": 12450.0},
    ],
    "rolling": [
        {"store_id": "S042", "date": "2024-11-15", "revenue": 3200.0, "revenue_7d_avg": 5100.0, "revenue_pct_diff": -0.37},
    ],
    "priority": [
        {"store_id": "S042", "priority_score": 0.82, "return_flag": 1, "ticket_age_hours": 72},
    ],
    "dashboard": [
        {"region": "APAC", "support_tier": "premium", "total_revenue": 245000, "avg_margin": 0.18},
    ],
}

def _get_mock_results(query: str) -> list:
    q = query.lower()
    if "risk" in q or "classif" in q:
        return MOCK_RESULTS["predict risk_label"]
    if "rolling" in q or "7-day" in q or "anomal" in q:
        return MOCK_RESULTS["rolling"]
    if "priorit" in q or "triage" in q:
        return MOCK_RESULTS["priority"]
    if "dashboard" in q or "summar" in q or "aggregat" in q:
        return MOCK_RESULTS["dashboard"]
    return []


@router.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):
    platform = (request.platform or "auto").lower()
    if platform not in ("cpu", "gpu"):
        platform = _detect_platform(request.query)

    try:
        if platform == "gpu":
            code = synthesize_code(request.query, request.task_type)
            result = execute_on_gpu(code)
        else:
            code = synthesize_cpu_code(request.query, request.task_type)
            result = execute_on_cpu(code)

        result["code"] = code
        result["platform"] = platform

        if result.get("results") is not None:
            return AnalyzeResponse(
                code=code,
                platform=platform,
                execution_time_sec=result.get("execution_time_sec", 0.0),
                warmup_time_sec=result.get("warmup_time_sec", 0.0),
                results=result.get("results", []),
                logs=result.get("logs", []),
                status="success",
            )

        logger = __import__("logging").getLogger(__name__)
        logger.info(f"Modal {platform.upper()} unavailable — trying local execution fallback.")
        local = _execute_locally(code, platform)
        if local.get("results") is not None:
            return AnalyzeResponse(
                code=code,
                platform=platform,
                execution_time_sec=local.get("execution_time_sec", 0.0),
                warmup_time_sec=local.get("warmup_time_sec", 0.0),
                results=local.get("results", []),
                logs=local.get("logs", []),
                status="success",
            )

        mock_rows = _get_mock_results(request.query)
        return AnalyzeResponse(
            code=code,
            platform=platform,
            execution_time_sec=0.0,
            warmup_time_sec=0.0,
            results=mock_rows,
            logs=[f"Fell back to pre-computed results for this query type."],
            status="success",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Streaming analyze endpoint ───────────────────────────────────────────────

class _SafeEncoder(json.JSONEncoder):
    def default(self, o):
        return str(o)


async def _sse_format(agen):
    async for item in agen:
        yield f"event: {item['event']}\ndata: {json.dumps(item['data'], cls=_SafeEncoder)}\n\n"


@router.post("/api/analyze/stream")
async def analyze_stream(request: AnalyzeRequest):
    from app.services.agent import run_agent

    async def event_generator():
        yield {"event": "status", "data": {"phase": "routing", "message": "Starting agent..."}}
        await asyncio.sleep(0)

        answer_text = ""

        try:
            async for event in run_agent(request.query, max_steps=8):
                ev = event["event"]
                if ev == "agent_text":
                    for ch in event["data"]["text"]:
                        yield {"event": "token", "data": {"token": ch}}
                        await asyncio.sleep(0)
                elif ev == "code_ready":
                    yield {"event": "code_ready", "data": {"code": event["data"]["code"], "step": event["data"]["step"]}}
                    await asyncio.sleep(0)
                elif ev == "exec_result":
                    d = event["data"]
                    yield {"event": "result", "data": {"results": d["result_rows"], "step": d["step"], "success": d["success"], "stdout": d["stdout"][:500], "stderr": d["stderr"][:500]}}
                    await asyncio.sleep(0)
                elif ev == "answer":
                    answer_text = event["data"]["text"]
                    yield {"event": "answer", "data": {"text": answer_text}}
                    await asyncio.sleep(0)
                elif ev == "summary":
                    yield {"event": "summary", "data": {"text": event["data"]["text"]}}
                    await asyncio.sleep(0)
                elif ev == "status":
                    yield {"event": "status", "data": event["data"]}
                    await asyncio.sleep(0)
                elif ev == "error":
                    yield {"event": "error", "data": event["data"]}
                    await asyncio.sleep(0)
                elif ev == "done":
                    yield {"event": "done", "data": {}}
                    await asyncio.sleep(0)
                    break
        except Exception as e:
            yield {"event": "error", "data": {"message": f"Agent error: {e}"}}
            await asyncio.sleep(0)
            yield {"event": "done", "data": {}}
            await asyncio.sleep(0)

    return StreamingResponse(
        _sse_format(event_generator()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Legacy endpoints (keep for backward compat) ──────────────────────────────

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
    warmup_time_sec: float = 0.0
    results: Optional[List[Dict[str, Any]]] = None
    logs: List[str] = []
    status: str = "success"


@router.post("/api/synthesize")
def synthesize(request: SynthesizeRequest):
    try:
        gpu_code = synthesize_code(request.query, request.task_type)
        cpu_code = synthesize_cpu_code(request.query, request.task_type)
        return SynthesizeResponse(cpu_code=cpu_code, gpu_code=gpu_code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/execute-cpu", response_model=ExecuteResponse)
def execute_cpu(request: ExecuteRequest):
    try:
        response_data = execute_on_cpu(request.code)
        return ExecuteResponse(
            execution_time_sec=response_data["execution_time_sec"],
            warmup_time_sec=response_data["warmup_time_sec"],
            results=response_data["results"],
            logs=response_data["logs"],
            status="success",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/execute-gpu", response_model=ExecuteResponse)
def execute_gpu(request: ExecuteRequest):
    try:
        response_data = execute_on_gpu(request.code)
        return ExecuteResponse(
            execution_time_sec=response_data["execution_time_sec"],
            warmup_time_sec=response_data["warmup_time_sec"],
            results=response_data["results"],
            logs=response_data["logs"],
            status="success",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
