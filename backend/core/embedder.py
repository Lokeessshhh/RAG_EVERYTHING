import os
import time
from typing import List, Optional

try:
    import tiktoken
except ModuleNotFoundError:  # pragma: no cover
    tiktoken = None
import httpx

from backend.config import EMBEDDING
from backend.core.request_counter import increment_embedding_count


class Embedder:
    def __init__(self):
        self._api_key = os.getenv("JINA_API_KEY")
        if not self._api_key:
            raise RuntimeError("Missing JINA_API_KEY environment variable")

        self._endpoint = os.getenv("JINA_EMBEDDINGS_URL", "https://api.jina.ai/v1/embeddings")
        self._http = httpx.Client(timeout=httpx.Timeout(60.0, connect=20.0))
        self.model = EMBEDDING["model"]
        self.task_doc = EMBEDDING["task_doc"]
        self.task_query = EMBEDDING["task_query"]
        self.batch_size = EMBEDDING["batch_size"]
        self.dimensions = EMBEDDING["dimensions"]

        self._rpm_limit = int(os.getenv("JINA_EMBED_RPM", "100"))
        self._tpm_limit = int(os.getenv("JINA_EMBED_TPM", "100000"))
        self._window_seconds = 60
        self._window_start = time.time()
        self._window_requests = 0
        self._window_tokens = 0

        self._tokenizer = None
        if tiktoken is not None:
            self._tokenizer = tiktoken.get_encoding(os.getenv("EMBED_TOKENIZER", "cl100k_base"))

    def _estimate_tokens(self, texts: List[str]) -> int:
        # Best effort:
        # - Prefer a real tokenizer (tiktoken) when installed.
        # - Fallback to a conservative heuristic (~4 chars per token).
        if self._tokenizer is None:
            total_chars = sum(len(t or "") for t in texts)
            return max(1, total_chars // 4)

        total = 0
        for t in texts:
            if not t:
                continue
            total += len(self._tokenizer.encode(t))
        return max(1, total)

    def _sleep_with_jitter(self, seconds: float):
        if seconds <= 0:
            return
        time.sleep(seconds + 0.05)

    def _get_retry_after_seconds(self, resp: httpx.Response) -> Optional[float]:
        retry_after = resp.headers.get("retry-after")
        if not retry_after:
            return None
        try:
            return float(retry_after)
        except ValueError:
            return None

    def _wait_for_budget(self, requests_cost: int, tokens_cost: int):
        now = time.time()
        elapsed = now - self._window_start
        if elapsed >= self._window_seconds:
            self._window_start = time.time()
            self._window_requests = 0
            self._window_tokens = 0

        exceeds_rpm = (self._window_requests + requests_cost) > self._rpm_limit
        exceeds_tpm = (self._window_tokens + tokens_cost) > self._tpm_limit

        if not (exceeds_rpm or exceeds_tpm):
            return

        reason = "RPM" if exceeds_rpm else "TPM"
        sleep_for = (self._window_start + self._window_seconds) - now
        if sleep_for > 0:
            print(f"[DEBUG] Rate limit budget reached ({reason}). Sleeping {sleep_for:.2f}s...")
            self._sleep_with_jitter(sleep_for)

        self._window_start = time.time()
        self._window_requests = 0
        self._window_tokens = 0

    def _embed_batch(self, batch: List[str], task: str) -> tuple[List[List[float]], Optional[int]]:
        payload = {
            "model": self.model,
            "input": batch,
            "task": task,
            "dimensions": self.dimensions,
            "truncate": False,
            "embedding_type": "float",
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        attempt = 0
        while True:
            attempt += 1
            resp = self._http.post(self._endpoint, headers=headers, json=payload)

            if resp.status_code == 429:
                retry_after_s = self._get_retry_after_seconds(resp)
                backoff = retry_after_s if retry_after_s is not None else min(60.0, 2.0 ** min(attempt, 5))
                print(f"[ERROR] Jina API 429. Sleeping {backoff:.2f}s before retry...")
                self._sleep_with_jitter(backoff)
                continue

            resp.raise_for_status()

            body = resp.json()
            usage = body.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens")
            print(f"[DEBUG] Jina API usage response: {usage}")
            print(f"[DEBUG] prompt_tokens type: {type(prompt_tokens)}, value: {prompt_tokens}")
            
            # Calculate remaining tokens based on 100000 TPM limit since Jina free tier doesn't send headers
            if isinstance(prompt_tokens, int) and prompt_tokens >= 0:
                print(f"[DEBUG] Token tracking condition met")
                # Track actual tokens used and calculate remaining from 100000 limit
                from backend.core.request_counter import _load_counter, _save_counter, get_today_date
                counter = _load_counter()
                today = get_today_date()
                if counter.get("date") != today:
                    counter = {"date": today, "embedding_requests": 0, "embedding_chunks": 0, "embedding_tokens_used": 0, "embedding_tokens_remaining": 100000}
                if "embedding_tokens_used" not in counter:
                    counter["embedding_tokens_used"] = 0
                counter["embedding_tokens_used"] += prompt_tokens
                # Calculate remaining (100000 is Jina's TPM limit)
                remaining = max(0, 100000 - counter["embedding_tokens_used"])
                counter["embedding_tokens_remaining"] = remaining
                _save_counter(counter)
                print(f"[DEBUG] Tokens used: {counter['embedding_tokens_used']}, Remaining: {remaining}")
            else:
                print(f"[DEBUG] Token tracking skipped - prompt_tokens condition not met")

            data = body.get("data", [])
            embeddings: List[List[float]] = []
            for item in data:
                vec = item.get("embedding")
                if not isinstance(vec, list):
                    raise RuntimeError("Unexpected Jina embeddings response format")
                embeddings.append(vec)
            return embeddings, prompt_tokens

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents in batches."""
        all_embeddings = []

        i = 0
        while i < len(texts):
            batch = texts[i:i + self.batch_size]
            estimated_tokens = self._estimate_tokens(batch)
            print(f"[DEBUG] Batch: {len(batch)} chunks, ~{estimated_tokens} tokens. "
                  f"Usage: {self._window_requests}/{self._rpm_limit} req, "
                  f"{self._window_tokens}/{self._tpm_limit} tokens")

            if estimated_tokens > self._tpm_limit and len(batch) > 1:
                shrink_ratio = max(0.01, self._tpm_limit / float(estimated_tokens))
                new_size = max(1, int(len(batch) * shrink_ratio))
                batch = texts[i:i + new_size]
                estimated_tokens = self._estimate_tokens(batch)
                print(f"[DEBUG] Batch too large for TPM. Shrunk to {len(batch)} chunks.")

            self._wait_for_budget(requests_cost=1, tokens_cost=estimated_tokens)

            # Reserve budget immediately
            self._window_requests += 1
            self._window_tokens += estimated_tokens

            print(f"[DEBUG] Sending batch {i//self.batch_size + 1}: {len(batch)} chunks, ~{estimated_tokens} tokens to Jina API...")

            embeddings, prompt_tokens = self._embed_batch(batch=batch, task=self.task_doc)
            for vec in embeddings:
                all_embeddings.append(vec)

            if isinstance(prompt_tokens, int) and prompt_tokens >= 0:
                self._window_tokens += (prompt_tokens - estimated_tokens)

            increment_embedding_count(requests_count=1, chunks_count=len(batch))

            i += len(batch)

            if i < len(texts):
                print("[DEBUG] Waiting 3s before next batch...")
                self._sleep_with_jitter(3)

        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        """Embed a single query."""
        estimated_tokens = self._estimate_tokens([query])
        self._wait_for_budget(requests_cost=1, tokens_cost=estimated_tokens)

        self._window_requests += 1
        self._window_tokens += estimated_tokens

        embeddings, prompt_tokens = self._embed_batch(batch=[query], task=self.task_query)
        if isinstance(prompt_tokens, int) and prompt_tokens >= 0:
            self._window_tokens += (prompt_tokens - estimated_tokens)

        # Track embedding usage: 1 API request, 1 embedded chunk.
        increment_embedding_count(requests_count=1, chunks_count=1)

        if not embeddings:
            raise RuntimeError("No embedding returned for query")
        return embeddings[0]
