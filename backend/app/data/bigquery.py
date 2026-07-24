import os
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants (matching notebook Section C)
# ─────────────────────────────────────────────────────────────────────────────
N_ROWS = 1_000_000
N_STORES, N_PRODUCTS, N_USERS, N_REGIONS = 250, 2000, 50_000, 8

# Global DataFrame
global_df: pd.DataFrame | None = None
_current_source: str = ""

# Parquet path — one level above this file's directory (i.e. backend/app/data.parquet)
PARQUET_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data.parquet"
)


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic data generator — exact copy of notebook Section C make_transactions
# ─────────────────────────────────────────────────────────────────────────────

def make_transactions(n: int, seed: int = 42) -> pd.DataFrame:
    """Generate a synthetic retail transactions DataFrame with n rows."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "txn_id"            : np.arange(n, dtype=np.int64),
        "date"              : (
            pd.Timestamp("2024-01-01")
            + pd.to_timedelta(rng.integers(0, 365 * 24 * 3600, n), unit="s")
        ).floor("D"),
        "store_id"          : rng.integers(0, N_STORES,   n, dtype=np.int32),
        "product_id"        : rng.integers(0, N_PRODUCTS, n, dtype=np.int32),
        "user_id"           : rng.integers(0, N_USERS,    n, dtype=np.int32),
        "region"            : rng.integers(0, N_REGIONS,  n, dtype=np.int8),
        "qty"               : rng.integers(1, 10,         n, dtype=np.int16),
        "price"             : rng.gamma(2.0, 20.0,        n).round(2),
        "discount_pct"      : rng.uniform(0, 0.35,        n).round(3),
        "return_flag"       : (rng.random(n) < 0.05).astype(np.int8),
        "support_tier"      : rng.integers(1, 5,          n, dtype=np.int8),
        "inventory"         : rng.integers(0, 5000,       n, dtype=np.int32),
        "days_since_restock": rng.integers(0, 60,         n, dtype=np.int16),
        "session_minutes"   : rng.gamma(3.0, 5.0,         n).round(2),
        "ticket_age_hours"  : rng.gamma(2.0, 8.0,         n).round(2),
        "sentiment"         : rng.normal(0, 1,             n).round(3),
        "feat_1"            : rng.normal(0, 1,             n).round(4),
        "feat_2"            : rng.normal(0, 1,             n).round(4),
        "feat_3"            : rng.normal(0, 1,             n).round(4),
        "feat_4"            : rng.normal(0, 1,             n).round(4),
    })
    df["revenue"]      = (df["qty"] * df["price"] * (1 - df["discount_pct"])).round(2)
    df["margin"]       = (df["revenue"] * rng.uniform(0.12, 0.42, n)).round(2)
    df["risk_score"]   = (
        0.45 * df["return_flag"].astype(float)
        + 0.20 * (df["ticket_age_hours"] / (df["ticket_age_hours"].max() + 1e-9))
        + 0.20 * (1 - np.clip(df["sentiment"], -2, 2) / 2)
        + 0.15 * (df["days_since_restock"] / (df["days_since_restock"].max() + 1e-9))
    )
    df["risk_label"]   = (df["risk_score"] > df["risk_score"].quantile(0.75)).astype(np.int8)
    df["target_flag"]  = df["risk_label"]
    df["target_value"] = df["risk_score"]
    return df


# ─────────────────────────────────────────────────────────────────────────────
# BigQuery loader with synthetic fallback — mirrors notebook load_bigquery_or_synthetic
# ─────────────────────────────────────────────────────────────────────────────

def load_bigquery_or_synthetic(n_rows: int) -> pd.DataFrame:
    """
    Tries to fetch from BigQuery (thelook_ecommerce).
    If BigQuery is unavailable or credentials are missing, falls back to
    make_transactions() — exactly as the notebook does in Section C.
    """
    logger.info("Attempting to connect to BigQuery for thelook_ecommerce dataset...")
    try:
        from google.cloud import bigquery

        client = bigquery.Client()
        query = f"""
        SELECT
            id as txn_id,
            user_id,
            product_id,
            created_at as date,
            sale_price as price,
            status
        FROM `bigquery-public-data.thelook_ecommerce.order_items`
        WHERE created_at IS NOT NULL
        LIMIT {n_rows}
        """
        df = client.query(query).to_dataframe()
        logger.info(f"Loaded {len(df):,} rows from BigQuery thelook_ecommerce.")

        rng = np.random.default_rng(42)
        n = len(df)

        # Map real columns
        df["date"]  = pd.to_datetime(df["date"]).dt.tz_localize(None).fillna(pd.Timestamp("2024-01-01"))
        df["price"] = df["price"].astype(float).fillna(50.0).round(2)

        # Synthesise missing columns to match the full schema
        df["store_id"]           = rng.integers(0, N_STORES,   n, dtype=np.int32)
        df["region"]             = rng.integers(0, N_REGIONS,  n, dtype=np.int8)
        df["qty"]                = rng.integers(1, 10,         n, dtype=np.int16)
        df["discount_pct"]       = rng.uniform(0, 0.35,        n).round(3)
        df["return_flag"]        = (df["status"] == "Returned").astype(np.int8)
        df["support_tier"]       = rng.integers(1, 5,          n, dtype=np.int8)
        df["sentiment"]          = rng.normal(0, 1,             n).round(3)
        df["ticket_age_hours"]   = rng.gamma(2.0, 8.0,         n).round(2)
        df["days_since_restock"] = rng.integers(0, 60,         n, dtype=np.int16)
        df["feat_1"]             = rng.normal(0, 1,             n).round(4)
        df["feat_2"]             = rng.normal(0, 1,             n).round(4)
        df["feat_3"]             = rng.normal(0, 1,             n).round(4)
        df["feat_4"]             = rng.normal(0, 1,             n).round(4)

        df["revenue"]    = (df["qty"] * df["price"] * (1 - df["discount_pct"])).round(2)
        df["margin"]     = (df["revenue"] * 0.30).round(2)
        df["risk_score"] = (
            0.45 * df["return_flag"].astype(float)
            + 0.20 * (df["ticket_age_hours"] / (df["ticket_age_hours"].max() + 1e-9))
            + 0.20 * (1 - np.clip(df["sentiment"], -2, 2) / 2)
            + 0.15 * (df["days_since_restock"] / (df["days_since_restock"].max() + 1e-9))
        )
        df["risk_label"]  = (df["risk_score"] > df["risk_score"].quantile(0.75)).astype(np.int8)
        df["target_flag"] = df["risk_label"]
        df["target_value"]= df["risk_score"]

        # Select final columns matching make_transactions schema
        df = df[[
            "store_id", "product_id", "date", "region",
            "qty", "price", "discount_pct", "return_flag", "support_tier",
            "sentiment", "ticket_age_hours", "days_since_restock",
            "feat_1", "feat_2", "feat_3", "feat_4",
            "revenue", "margin", "risk_score", "risk_label",
            "target_flag", "target_value",
        ]].reset_index(drop=True)

        before = len(df)
        df = df.dropna().reset_index(drop=True)
        if before - len(df) > 0:
            logger.info(f"Dropped {before - len(df):,} rows with NaN values.")
        logger.info(f"Final BigQuery df: {len(df):,} rows × {len(df.columns)} cols")
        return df

    except Exception as e:
        logger.warning(f"BigQuery unavailable ({e}). Falling back to synthetic data generator...")
        return make_transactions(n_rows)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def _build_schema(df: pd.DataFrame) -> str:
    """Build a schema description string from a DataFrame."""
    lines = [f"Columns available in `df` ({len(df):,} rows, {len(df.columns)} cols):"]
    for col in df.columns:
        dtype = df[col].dtype
        samples = df[col].dropna().iloc[:3].tolist()
        sample_str = ", ".join(repr(s) if isinstance(s, str) else str(s) for s in samples)
        lines.append(f"  - {col}: {dtype}  (e.g. {sample_str})")
    return "\n".join(lines)


def _set_dataframe(df: pd.DataFrame, source: str = "synthetic") -> None:
    """Replace the global DataFrame (used by CSV upload or dataset loading)."""
    global global_df, DATASET_SCHEMA, _current_source
    global_df = df
    _current_source = source
    DATASET_SCHEMA = _build_schema(df)
    logger.info(f"DataFrame replaced: {len(df):,} rows × {len(df.columns)} cols (source: {source})")


def load_external_dataset(dataset_key: str) -> pd.DataFrame:
    """Download and load a dataset from the registry, replacing global_df."""
    from app.data.datasets import load_dataset as _dl
    df = _dl(dataset_key)
    _set_dataframe(df, source=dataset_key)

    df.to_parquet(PARQUET_FILE_PATH, engine="pyarrow")
    logger.info(f"Parquet updated at {PARQUET_FILE_PATH}")

    return df


def fetch_ecommerce_data() -> None:
    """
    Loads data (BigQuery or synthetic fallback) into global_df and writes
    a Parquet file at PARQUET_FILE_PATH for Modal Sandbox upload.
    """
    global global_df, DATASET_SCHEMA, _current_source

    if global_df is not None:
        logger.info("Data already loaded.")
        return

    logger.info(f"Loading {N_ROWS:,}-row dataset (BigQuery or synthetic fallback)...")
    global_df = load_bigquery_or_synthetic(N_ROWS)
    _current_source = "thelook_ecommerce" if "user_id" in global_df.columns else "synthetic"
    DATASET_SCHEMA = _build_schema(global_df)
    logger.info(f"Dataset ready: {global_df.shape[0]:,} rows × {global_df.shape[1]} cols")

    logger.info(f"Writing Parquet to {PARQUET_FILE_PATH} for Modal Sandbox transfer...")
    global_df.to_parquet(PARQUET_FILE_PATH, engine="pyarrow")
    logger.info("Parquet export complete.")


def get_dataframe() -> pd.DataFrame:
    """Returns the globally loaded DataFrame."""
    global global_df
    if global_df is None:
        raise ValueError("DataFrame not initialized. Did you call fetch_ecommerce_data()?")
    return global_df


def get_current_source() -> str:
    """Returns the name of the currently loaded dataset source."""
    return _current_source


DATASET_SCHEMA = "No dataset loaded yet."
