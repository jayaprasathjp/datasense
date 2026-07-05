# DataSense

An intelligent data analysis platform that generates and executes data science code on both CPU (pandas) and GPU (cuDF/cuML) backends — powered by LLM-based code synthesis and Modal serverless infrastructure.

## Architecture

```
datasense/
├── backend/          # FastAPI backend with Modal sandbox execution
│   ├── app/
│   │   ├── api/          # REST endpoints (synthesize, execute, benchmark)
│   │   ├── core/         # Pydantic config, env settings
│   │   ├── data/         # BigQuery loader + synthetic data fallback
│   │   └── services/     # LLM engine, Modal sandbox executors
│   ├── Dockerfile
│   └── modal_app.py      # Modal vLLM inference endpoint
├── frontend/         # React + Vite UI
└── notebooks/        # Evaluation & benchmark notebooks
```

## Key Features

- **Natural Language → Code**: Describe your analysis in plain English; the LLM generates optimized code
- **Dual Backend Benchmarking**: Run the same analysis on CPU (pandas) and GPU (cuDF) concurrently for performance comparison
- **Synthetic Data Fallback**: No BigQuery credentials? Automatically generates realistic retail transaction data
- **Serverless Sandboxes**: Modal sandboxes ensure isolated, reproducible execution environments

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
