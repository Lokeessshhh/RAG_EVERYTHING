import os
import json
from datetime import datetime
from typing import Dict

COUNTER_FILE = "./tmp/request_counter.json"


def _ensure_dir():
    os.makedirs(os.path.dirname(COUNTER_FILE), exist_ok=True)


def _load_counter() -> Dict:
    _ensure_dir()
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "r") as f:
            data = json.load(f)
            if "embedding_requests" not in data:
                data["embedding_requests"] = 0
            if "embedding_chunks" not in data:
                data["embedding_chunks"] = 0
            if "embedding_tokens_remaining" not in data:
                data["embedding_tokens_remaining"] = None
            if "embedding_tokens_used" not in data:
                data["embedding_tokens_used"] = 0
            if "date" not in data:
                data["date"] = ""
            return data
    return {"date": "", "embedding_requests": 0, "embedding_chunks": 0, "embedding_tokens_remaining": 100000, "embedding_tokens_used": 0}


def _save_counter(data: Dict):
    _ensure_dir()
    with open(COUNTER_FILE, "w") as f:
        json.dump(data, f)


def get_today_date() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def increment_embedding_count(requests_count: int = 1, chunks_count: int = 0):
    """Increment embedding stats.

    requests_count: number of embedding API calls made
    chunks_count: number of texts embedded across those calls
    """
    counter = _load_counter()
    today = get_today_date()
    
    # Reset if new day
    if counter["date"] != today:
        counter = {"date": today, "embedding_requests": 0, "embedding_chunks": 0, "embedding_tokens_remaining": None}
    
    counter["embedding_requests"] += requests_count
    counter["embedding_chunks"] += chunks_count
    _save_counter(counter)


def set_embedding_tokens_remaining(tokens_remaining: int):
    """Set the last-seen remaining token budget for embeddings (from provider rate-limit headers)."""
    counter = _load_counter()
    today = get_today_date()

    if counter["date"] != today:
        counter = {"date": today, "embedding_requests": 0, "embedding_chunks": 0, "embedding_tokens_remaining": None}

    counter["embedding_tokens_remaining"] = tokens_remaining
    _save_counter(counter)


def get_embedding_stats() -> Dict:
    """Get today's embedding statistics."""
    counter = _load_counter()
    today = get_today_date()
    
    # Reset if new day
    if counter["date"] != today:
        return {"date": today, "embedding_requests": 0, "embedding_chunks": 0, "embedding_tokens_remaining": None}
    
    return counter
