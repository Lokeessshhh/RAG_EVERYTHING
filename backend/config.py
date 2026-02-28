EMBEDDING = {
    "model": "jina-embeddings-v5-text-small",
    "task_doc": "retrieval.passage",
    "task_query": "retrieval.query",
    "batch_size": 50,
    "dimensions": 1024
}

CHUNKING = {
    "text":    {"size": 600,  "overlap": 80},
    "pdf":     {"size": 700,  "overlap": 100},
    "csv":     {"size": None, "overlap": 0},
    "code":    {"size": 800,  "overlap": 0},
    "chat":    {"size": None, "overlap": 0},
    "github":  {"size": 800,  "overlap": 0},
    "youtube": {"size": 200,  "overlap": 30},
    "website": {"size": 800,  "overlap": 100},
    "image":   {"size": 800,  "overlap": 100},
    "voice":   {"size": 400,  "overlap": 60},
}

RETRIEVAL = {
    "top_k_search": 50,
    "top_k_rerank": 10,
    # Voyage rerank-2 scores are in [-inf, +inf] with higher = more relevant.
    # Typical relevant results score > -2.0, irrelevant < -5.0.
    # Setting threshold to -5.0 means we only drop truly irrelevant results.
    # The "always return top 3" fallback in retriever.py also guards against
    # empty context for any threshold value.
    "score_threshold": -5.0
}

VECTOR_DB = {
    "collection_docs":  "rag_documents",
    "collection_chats": "rag_conversations",
    "distance": "cosine",
    "dimensions": 1024
}

LLM = {
    "max_tokens": 1024,
    "temperature": 0.2,
    "stream": True
}

# AI Parser settings for Groq Llama model
# Rate limits: 30 RPM, 1K TPM, 30K TPD, 500K TPM (monthly)
AI_PARSER = {
    "model": "meta-llama/llama-4-scout-17b-16e-instruct",
    "max_tokens": 1024,
    "temperature": 0.2,
    "rpm_limit": 30,       # requests per minute
    "tpm_limit": 30000,    # tokens per minute
    "tpd_limit": 500000,    # tokens per day
    "enabled": True,       # set False to disable AI parsing
}

SOURCES = {
    "github_clone_dir": "./tmp/repos",
    "upload_dir": "./tmp/uploads",
    "max_file_size_mb": 50
}
