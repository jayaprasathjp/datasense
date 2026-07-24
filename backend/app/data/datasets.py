import logging
import os
import pandas as pd

logger = logging.getLogger(__name__)

DATASETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets")

DATASET_REGISTRY = {
    "uci_online_retail_ii": {
        "label": "UCI Online Retail II",
        "description": "~1M retail transactions (UK, 2009–2011). CC BY 4.0",
        "url": "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip",
        "size": "43.5 MB",
        "rows": "~1,067,371",
        "columns": 8,
        "file_type": "xlsx",
        "archive_file": "online_retail_II.xlsx",
    },
    "ecommerce_sales_2024_2025": {
        "label": "E-Commerce Sales 2024–2025",
        "description": "5k synthetic sales records with categories, regions, profit. CC0",
        "url": "https://raw.githubusercontent.com/shazlanamirul8/E-Commerce-Sales-Data-Power-BI-/main/Ecommerce_Sales_Data_2024_2025.csv",
        "size": "555 KB",
        "rows": "5,000",
        "columns": 14,
        "file_type": "csv",
    },
    "infoveave_retail_daily_sales": {
        "label": "Infoveave Retail Daily Sales",
        "description": "1k daily POS transactions across 20 stores, 5 regions",
        "url": "https://infoveave.com/sample-datasets/retail-daily-sales.csv",
        "size": "134 KB",
        "rows": "1,000",
        "columns": 9,
        "file_type": "csv",
    },
    "montgomery_county_sales": {
        "label": "Montgomery County Sales",
        "description": "319k retail sales records (Maryland, USA, open data)",
        "url": "https://data.montgomerycountymd.gov/api/views/v76h-r7br/rows.csv?accessType=DOWNLOAD",
        "size": "28.5 MB",
        "rows": "319,028",
        "columns": 9,
        "file_type": "csv",
    },
}


def dataset_local_path(dataset_key: str) -> str:
    info = DATASET_REGISTRY[dataset_key]
    ext = info.get("file_type", "csv")
    return os.path.join(DATASETS_DIR, f"{dataset_key}.csv")


def _http_get(url: str) -> bytes:
    import requests
    headers = {"User-Agent": "DataSense/1.0 (Windows NT 10.0; Win64; x64)"}
    r = requests.get(url, headers=headers, timeout=180)
    r.raise_for_status()
    return r.content


def download_dataset(dataset_key: str) -> str:
    import zipfile
    import io

    info = DATASET_REGISTRY[dataset_key]
    url = info["url"]
    local_path = dataset_local_path(dataset_key)

    if os.path.exists(local_path):
        logger.info(f"Dataset already cached: {local_path}")
        return local_path

    os.makedirs(DATASETS_DIR, exist_ok=True)

    file_type = info.get("file_type", "csv")

    if url.endswith(".zip"):
        logger.info(f"Downloading zip archive: {url}")
        data = _http_get(url)
        zip_data = io.BytesIO(data)
        with zipfile.ZipFile(zip_data) as zf:
            archive_file = info.get("archive_file")
            if archive_file:
                with zf.open(archive_file) as f:
                    if file_type == "xlsx":
                        df = pd.read_excel(f, engine="openpyxl")
                    else:
                        df = pd.read_csv(f)
            else:
                csv_files = [n for n in zf.namelist() if n.endswith(".csv")]
                if csv_files:
                    with zf.open(csv_files[0]) as f:
                        df = pd.read_csv(f)
                else:
                    raise ValueError("No CSV found in zip archive")
    elif url.endswith(".xlsx"):
        logger.info(f"Downloading xlsx: {url}")
        data = _http_get(url)
        df = pd.read_excel(io.BytesIO(data), engine="openpyxl")
    else:
        logger.info(f"Downloading CSV: {url}")
        data = _http_get(url)
        df = pd.read_csv(io.BytesIO(data))

    df.to_csv(local_path, index=False)
    logger.info(f"Saved {len(df):,} rows to {local_path}")
    return local_path


def load_dataset(dataset_key: str) -> pd.DataFrame:
    path = download_dataset(dataset_key)
    df = pd.read_csv(path)
    logger.info(f"Loaded {len(df):,} rows × {len(df.columns)} cols from {dataset_key}")
    return df


def list_datasets() -> list[dict]:
    result = []
    for key, info in DATASET_REGISTRY.items():
        entry = {"key": key, **info}
        path = dataset_local_path(key)
        entry["cached"] = os.path.exists(path)
        result.append(entry)
    return result
