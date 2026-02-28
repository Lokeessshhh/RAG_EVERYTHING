from typing import Dict, List
from contextlib import asynccontextmanager

import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from backend.routers import ingest_router, chat_router
from backend.core.vector_store import VectorStore
from backend.core.request_counter import get_embedding_stats
from backend.core.upstash_redis import UpstashRedis
from backend.core.cache import cache_get_or_set
from backend.core.rate_limit import rate_limit_ip

# Load environment variables
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup."""
    print("[DEBUG] Starting up RAG Everything API...", flush=True)
    # Create Zilliz collections on startup
    VectorStore()
    print("[DEBUG] VectorStore initialized", flush=True)
    yield


app = FastAPI(
    title="RAG Everything API",
    description="Production-ready RAG application API",
    version="1.0.0",
    lifespan=lifespan
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    import sys
    print(f"[MIDDLEWARE] Incoming request: {request.method} {request.url}", flush=True, file=sys.stdout)
    sys.stdout.flush()
    response = await call_next(request)
    print(f"[MIDDLEWARE] Response status: {response.status_code}", flush=True, file=sys.stdout)
    sys.stdout.flush()
    return response

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # must be False when allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(ingest_router, prefix="/api")
app.include_router(chat_router, prefix="/api")


# Library endpoints
class SourceItem(BaseModel):
    name: str
    type: str
    chunks: int
    ingested_at: str


class LibraryResponse(BaseModel):
    sources: Dict[str, List[SourceItem]]


vector_store = VectorStore()
redis = UpstashRedis()


@app.get("/api/library", response_model=LibraryResponse)
async def get_library():
    """Get all ingested sources grouped by source type."""
    async def _fetch():
        sources_raw = vector_store.get_all_sources()

        sources: Dict[str, List[SourceItem]] = {}
        for source_type, items in sources_raw.items():
            sources[source_type] = []
            for item in items:
                chunk_count = vector_store.get_chunk_count(item["name"])
                sources[source_type].append(
                    SourceItem(
                        name=item["name"],
                        type=item["type"],
                        chunks=chunk_count,
                        ingested_at=item.get("ingested_at", "unknown"),
                    )
                )

        return {"sources": {k: [s.model_dump() for s in v] for k, v in sources.items()}}

    data = await cache_get_or_set(
        redis=redis,
        key="api:library",
        fetch=_fetch,
        ttl_seconds=60,
    )
    return LibraryResponse(**data)


@app.get("/api/test-rate-limit")
async def test_rate_limit(request: Request):
    await rate_limit_ip(
        redis=redis,
        ip=request.client.host if request.client else "unknown",
        limit=30,
        window_seconds=60,
    )
    return {"status": "ok"}


@app.delete("/api/library")
async def delete_source(source_name: str):
    """Delete all vectors for a given source."""
    vector_store.delete_source(source_name)
    await redis.delete("api:library")
    return {"message": f"Deleted source: {source_name}"}


@app.get("/api/test")
async def test_endpoint():
    import sys
    print("[DEBUG] Test endpoint called!", flush=True, file=sys.stdout)
    sys.stdout.flush()
    print("TEST LOG: Backend test endpoint executed", flush=True, file=sys.stdout)
    sys.stdout.flush()
    return {"status": "ok", "message": "Backend is responding"}


@app.get("/api/stats")
async def get_stats():
    """Get daily embedding statistics."""
    return get_embedding_stats()


@app.post("/api/reset-collections")
async def reset_collections():
    """Drop and recreate collections with correct dimensions."""
    from pymilvus import MilvusClient
    import os
    from backend.config import VECTOR_DB
     
    client = MilvusClient(
        uri=os.getenv("ZILLIZ_URI"),
        token=os.getenv("ZILLIZ_TOKEN")
    )
 
    dimensions = VECTOR_DB["dimensions"]
     
    for collection in ["rag_documents", "rag_conversations"]:
        if client.has_collection(collection):
            client.drop_collection(collection)
        client.create_collection(
            collection_name=collection,
            dimension=dimensions,
            metric_type="COSINE",
            id_type="str",
            auto_id=True,
            max_length=65535
        )
     
    return {"message": f"Collections reset with {dimensions} dimensions"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
