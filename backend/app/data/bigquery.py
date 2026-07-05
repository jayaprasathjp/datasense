import os
import pandas as pd
from google.cloud import bigquery
import logging

logger = logging.getLogger(__name__)

# Global DataFrame to hold the BigQuery data for CPU execution
global_df: pd.DataFrame | None = None

# Path to store the parquet file for E2B upload
PARQUET_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data.parquet")

def fetch_ecommerce_data() -> None:
    """
    Fetches the ecommerce data from BigQuery and stores it in the global DataFrame.
    Also exports the DataFrame to a local Parquet file for efficient sandbox uploading.
    """
    global global_df
    
    if global_df is not None:
        logger.info("Data already loaded.")
        return

    logger.info("Initializing BigQuery client and fetching data (this may take a moment)...")
    
    # Assumes google application credentials are set in environment
    client = bigquery.Client()
    
    query = """
    SELECT 
        id, 
        order_id, 
        user_id, 
        product_id, 
        sale_price, 
        created_at, 
        status 
    FROM `bigquery-public-data.thelook_ecommerce.order_items`,
    UNNEST(GENERATE_ARRAY(1, 100))
    WHERE status NOT IN ('Cancelled', 'Returned') 
    LIMIT 10000000
    """
    
    # Run the query and convert to a pandas DataFrame
    job_config = bigquery.QueryJobConfig(use_query_cache=True)
    query_job = client.query(query, job_config=job_config)
    
    global_df = query_job.to_dataframe()
    logger.info(f"Successfully loaded {len(global_df)} rows into global CPU DataFrame.")
    
    # Export to Parquet for E2B Sandbox
    logger.info(f"Exporting DataFrame to {PARQUET_FILE_PATH} for Sandbox transfer...")
    global_df.to_parquet(PARQUET_FILE_PATH, engine="pyarrow")
    logger.info("Export complete.")

def get_dataframe() -> pd.DataFrame:
    """Returns the globally loaded DataFrame."""
    global global_df
    if global_df is None:
        raise ValueError("DataFrame not initialized. Did you call fetch_ecommerce_data()?")
    return global_df
