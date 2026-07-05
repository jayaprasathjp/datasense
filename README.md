# DataSense

An intelligent data analysis platform that generates and executes data science code on both CPU (pandas) and GPU (cuDF/cuML) backends — powered by LLM-based code synthesis and Modal serverless infrastructure.

## Architecture

```
datasense/
├── backend/              # FastAPI backend with Modal sandbox execution
│   ├── app/
│   │   ├── api/              # REST endpoints (synthesize, execute, benchmark)
│   │   ├── core/             # Pydantic config, env settings
│   │   ├── data/             # BigQuery loader + synthetic data fallback
│   │   └── services/         # LLM engine, Modal sandbox executors
│   ├── Dockerfile
│   └── modal_app.py          # Modal vLLM inference endpoint
├── frontend/             # React + Vite UI
└── test/                 # R&D artifacts from hackathon
    ├── notebooks/            # Benchmark & evaluation notebooks
    ├── reports/              # HTML reports (day 1 results, presentation, plan)
    ├── benchmarks/           # CSV benchmark data
    ├── visuals/              # Performance charts & speedup graphs
    └── final_decision_notes.txt
```

## Key Features

- **Natural Language → Code**: Describe your analysis in plain English; the LLM generates optimized code
- **Dual Backend Benchmarking**: Run the same analysis on CPU (pandas) and GPU (cuDF) concurrently for performance comparison
- **Synthetic Data Fallback**: No BigQuery credentials? Automatically generates realistic retail transaction data
- **Serverless Sandboxes**: Modal sandboxes ensure isolated, reproducible execution environments
- **Autonomous Self-Healing**: LLM-generated code errors are caught and fed back for automatic correction

## R&D Results

Built for the **NVIDIA Track (Problem Statement 2)** — Gen AI Academy APAC Hackathon. The core thesis: *LLM-generated data science code must execute on GPU to deliver interactive UX.*

### The 213× "Killer Metric"

On the **Risk Modeling** task (Random Forest classification on 181K real ecommerce transactions):

| Backend | Execution Time | Speedup |
|---------|---------------|---------|
| CPU (pandas + sklearn) | **81.04s** | 1× |
| GPU (cuDF + cuML) | **0.38s** | **213×** |

CPU execution alone makes conversational data science unusable — GPU acceleration is essential.

### Raw GPU Sweep (100K – 20M rows)

| Operation | Best Scale | CPU (Max) | GPU (Max) | Max Speedup |
|-----------|-----------|-----------|-----------|-------------|
| Time-series alerting (rolling window) | 20M rows | 23.17s | 0.39s | **58.9×** |
| Dashboard joins (merge) | 20M rows | 6.73s | 0.17s | **39.8×** |
| Data wrangling (sort) | 20M rows | 9.50s | 0.45s | **21.1×** |
| BI dashboards (groupby agg) | 1M rows | 0.14s | 0.01s | **18.4×** |
| Risk scoring (RF fit) | 5M rows | 174.83s | 11.13s | **15.7×** |

### LLM-in-the-Loop Benchmark (real BigQuery data, 181K rows)

| Task | CPU | GPU | Speedup |
|------|-----|-----|---------|
| Dashboard Summary | 0.03s | 0.21s | GPU overhead at small scale |
| Priority Ranking | 0.04s | 0.63s | Sub-second both |
| Rolling Alert | 0.10s | 0.13s | Equivalent |
| **Risk Model (RF)** | **81.04s** | **0.38s** | **213×** |

### Autonomous Self-Debugging

The DataSense LLM model hallucinated syntax errors during testing. A custom recovery loop caught exceptions, formulated targeted feedback, and re-prompted the LLM for fixes — achieving full recovery on attempts 2–3.

### Decision: Risk/Priority Scoring + Time-Series Alerting

Based on consistent >15× GPU speedups, the final product focused on two verticals:
- **Risk/Priority Scoring** — cuML Random Forest trains 30× faster, enabling real-time triage
- **Time-Series Alerting** — 58.9× cuDF rolling windows let dashboards refresh in <1s vs 60s

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
```

Configure environment variables in `backend/.env`:

```
GEMINI_API_KEY=your_key
MODAL_TOKEN_ID=your_modal_token_id
MODAL_TOKEN_SECRET=your_modal_token_secret
MODAL_URL=your_modal_endpoint_url
MODAL_API_KEY=your_modal_api_key
```

Run the server:

```bash
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```
