import hashlib
import json
import os
import re
import logging
from threading import Lock

logger = logging.getLogger(__name__)

# Cache file in the same directory as this script
CACHE_FILE = os.path.join(os.path.dirname(__file__), "llm_cache.json")
_cache_lock = Lock()
_cache_data = None

def _load_cache() -> dict:
    global _cache_data
    if _cache_data is not None:
        return _cache_data
        
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _cache_data = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            _cache_data = {}
    else:
        _cache_data = {}
        
    return _cache_data

def _save_cache():
    if _cache_data is not None:
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(_cache_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

def normalize_query(query: str) -> str:
    """Normalize query by lowercasing and stripping punctuation/whitespace."""
    return re.sub(r'[^a-z0-9]', '', query.lower())

def get_hash(schema: str, query: str) -> str:
    """Create a SHA-256 hash of the normalized query and schema."""
    norm_q = normalize_query(query)
    combined = f"{schema}::{norm_q}"
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()

def get_cached_code(schema: str, query: str, backend: str) -> str | None:
    """Get the cached code for a given schema, query, and backend ('gpu' or 'cpu')."""
    cache_key = get_hash(schema, query)
    
    with _cache_lock:
        cache = _load_cache()
        if cache_key in cache and backend in cache[cache_key]:
            logger.info(f"Cache HIT for query (backend={backend}): {query}")
            return cache[cache_key][backend]
            
    logger.info(f"Cache MISS for query (backend={backend}): {query}")
    return None

def set_cached_code(schema: str, query: str, backend: str, code: str):
    """Save the synthesized code into the cache."""
    cache_key = get_hash(schema, query)
    
    with _cache_lock:
        cache = _load_cache()
        if cache_key not in cache:
            cache[cache_key] = {}
            
        cache[cache_key][backend] = code
        _save_cache()
