from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.api.routes import router
from app.data.bigquery import fetch_ecommerce_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info("Starting up FastAPI server...")
    try:
        # Load BigQuery data into global DataFrame and export Parquet
        # The parquet file will be uploaded into Modal Sandboxes on each execution request
        fetch_ecommerce_data()
    except Exception as e:
        logger.error(f"Failed to fetch initial data: {e}")
        # Not stopping the server here to allow debugging
    yield
    # Shutdown logic
    logger.info("Shutting down FastAPI server...")

app = FastAPI(title="DataSense GPU API", lifespan=lifespan)

# Add CORS middleware for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/")
def root():
    return {"message": "DataSense GPU API is running!"}
