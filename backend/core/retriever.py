import os
import re
from typing import List, Dict, Any, Optional
import httpx
from backend.config import RETRIEVAL
from backend.core.embedder import Embedder
from backend.core.vector_store import VectorStore

# Known code/doc file extensions — prevents version numbers like "2.5" being treated as filenames
_CODE_EXTENSIONS = {
    "py", "js", "ts", "tsx", "jsx", "java", "cpp", "c", "h", "hpp",
    "cs", "go", "rb", "rs", "php", "swift", "kt", "scala", "sh", "bash",
    "zsh", "fish", "ps1", "md", "txt", "rst", "yaml", "yml", "json",
    "toml", "ini", "cfg", "env", "html", "css", "scss", "sass", "vue",
    "sql", "graphql", "proto", "xml", "csv", "ipynb", "r", "m", "f90",
}


class Retriever:
    def __init__(self):
        self.embedder = Embedder()
        self.vector_store = VectorStore()
        self.top_k_search = RETRIEVAL["top_k_search"]
        self.top_k_rerank = RETRIEVAL["top_k_rerank"]
        self.score_threshold = RETRIEVAL["score_threshold"]
        self.voyage_api_key = os.getenv("VOYAGE_API_KEY")

    def _extract_filename_from_query(self, query: str) -> Optional[str]:
        """Extract potential filename from query — only real code/doc extensions."""
        for match in re.finditer(r'\b([\w.-]+?)\.(\w{1,10})\b', query):
            ext = match.group(2).lower()
            if ext in _CODE_EXTENSIONS:
                return match.group(0)
        return None

    def _is_metadata_query(self, query: str) -> bool:
        """Detect if query is asking about file metadata (count, list, etc)."""
        query_lower = query.lower()
        metadata_patterns = [
            "how many files",
            "list files",
            "what files",
            "show files",
            "files are there",
            "number of files",
            "count files",
            "which files",
        ]
        return any(p in query_lower for p in metadata_patterns)

    def get_file_listing(self, source_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get file listing for a source."""
        if source_name:
            return self.vector_store.get_source_files(source_name)
        # Get all files from all sources
        all_files = []
        sources = self.vector_store.get_all_sources()
        for source_type, items in sources.items():
            for item in items:
                files = self.vector_store.get_source_files(item["name"])
                all_files.extend(files)
        return all_files

    def search(
        self,
        query: str,
        source_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Search for relevant chunks and rerank them."""
        # Embed query
        query_embedding = self.embedder.embed_query(query)
        
        # Search vector store
        results = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=self.top_k_search,
            source_types=source_types
        )
        
        print(f"[DEBUG] Vector search found {len(results)} results")
        
        # Boost results that match filename in query
        filename = self._extract_filename_from_query(query)
        if filename:
            print(f"[DEBUG] Detected filename in query: {filename}")
            for r in results:
                file_path = r.get("metadata", {}).get("file_path", "")
                if filename in file_path:
                    # Boost score by moving to front
                    r["boosted"] = True
                    print(f"[DEBUG] Boosting result with file: {file_path}")
            # Sort: boosted results first, then by original score
            results.sort(key=lambda x: (not x.get("boosted", False), -x.get("score", 0)))
        
        for r in results[:5]:
            print(f"  - source: {r.get('source_name', '')}, file: {r.get('metadata', {}).get('file_path', 'N/A')}, text: {r.get('text', '')[:60]}...")
        
        if not results:
            return []
        
        # Rerank with Voyage AI
        reranked = self._rerank(query, results)
        
        print(f"[DEBUG] After rerank: {len(reranked)} results")
        for r in reranked[:3]:
            print(f"  - score: {r.get('rerank_score', 0):.3f}, text: {r.get('text', '')[:50]}...")
        
        # Filter by score threshold
        # For Voyage rerank-2: scores are in (-inf, +inf), relevant > -2, irrelevant < -5
        # For fallback cosine sim: scores are in [0, 1], relevant > 0.3
        # The threshold in config is tuned for Voyage; fallback uses its own floor.
        is_fallback = all("rerank_score" in r and r.get("_is_fallback", False) for r in reranked)
        if is_fallback:
            threshold = 0.2  # cosine sim floor for fallback
        else:
            threshold = self.score_threshold
        filtered = [r for r in reranked if r.get("rerank_score", 0) >= threshold]

        print(f"[DEBUG] After threshold filter ({threshold}): {len(filtered)} results")
        if not filtered and reranked:
            best = reranked[0].get("rerank_score", 0)
            print(f"[WARN] All results filtered out! Best score was {best:.4f}, threshold is {threshold}. Returning top 3 anyway.")
            filtered = reranked[:3]  # Always return at least top 3 to prevent empty context
        
        return filtered

    def _rerank(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rerank results using Voyage AI Rerank API. Falls back gracefully on any failure."""
        if not results:
            return []

        # If no Voyage key is configured, skip reranking entirely
        if not self.voyage_api_key:
            print("[WARN] VOYAGE_API_KEY not set — skipping rerank, using vector scores.")
            return self._fallback_rank(results)

        # Build document strings (include file path prefix for code chunks)
        documents = []
        for r in results:
            file_path = r.get("metadata", {}).get("file_path", "")
            text = r.get("text", "")
            if file_path:
                documents.append(f"[File: {file_path}]\n{text}")
            else:
                documents.append(text)

        try:
            response = httpx.post(
                "https://api.voyageai.com/v1/rerank",
                headers={
                    "Authorization": f"Bearer {self.voyage_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "rerank-2",
                    "query": query,
                    "documents": documents,
                    "top_k": self.top_k_rerank,
                },
                timeout=30.0,
            )

            if response.status_code != 200:
                print(f"[WARN] Voyage rerank API error {response.status_code}: {response.text[:200]} — using fallback.")
                return self._fallback_rank(results)

            data = response.json()
            items = data.get("data", [])

            if not items:
                print(f"[WARN] Voyage rerank returned empty data field: {data} — using fallback.")
                return self._fallback_rank(results)

            # Map reranked results back to original results with scores
            reranked_results = []
            for item in items:
                index = item.get("index", 0)
                score = item.get("relevance_score", 0.0)
                if index < len(results):
                    result = results[index].copy()
                    result["rerank_score"] = score
                    reranked_results.append(result)

            print(f"[DEBUG] Voyage rerank returned {len(reranked_results)} results, top score: {reranked_results[0].get('rerank_score', 0):.4f}" if reranked_results else "[DEBUG] Voyage rerank: no mapped results")
            return reranked_results

        except httpx.TimeoutException:
            print("[WARN] Voyage rerank API timed out — using fallback.")
            return self._fallback_rank(results)
        except Exception as e:
            print(f"[WARN] Voyage rerank exception: {type(e).__name__}: {e} — using fallback.")
            return self._fallback_rank(results)

    def _fallback_rank(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fallback: use cosine similarity scores when reranking is unavailable.

        Milvus COSINE metric returns similarity in [0, 1] where 1 = identical.
        We map that directly to rerank_score and tag results with _is_fallback=True
        so the threshold filter in search() uses the cosine-appropriate floor (0.2).
        """
        top = results[:self.top_k_rerank]
        for r in top:
            raw_score = r.get("score", 0.5)
            r["rerank_score"] = max(0.0, min(1.0, float(raw_score)))
            r["_is_fallback"] = True
        # Sort by descending similarity
        top.sort(key=lambda x: x["rerank_score"], reverse=True)
        print(f"[DEBUG] Fallback rank: top score={top[0]['rerank_score']:.4f}" if top else "[DEBUG] Fallback rank: no results")
        return top

    def build_context(self, results: List[Dict[str, Any]]) -> str:
        """Build context string from search results."""
        context_parts = []
        
        for result in results:
            source_name = result.get("source_name", "Unknown")
            source_type = result.get("source_type", "unknown")
            text = result.get("text", "")
            metadata = result.get("metadata", {})
            
            # Build source label
            source_label = f"[Source: {source_name}"
            
            if source_type == "pdf" and "page_number" in metadata:
                source_label += f" | page {metadata['page_number']}"
            elif source_type == "github" and "file_path" in metadata:
                source_label += f" | file: {metadata['file_path']}"
            elif source_type == "code" and "function_name" in metadata:
                source_label += f" | function {metadata['function_name']}"
            elif source_type == "csv" and "row_index" in metadata:
                source_label += f" | row {metadata['row_index']}"
            elif source_type == "chat" and "turn_index" in metadata:
                source_label += f" | turn {metadata['turn_index']}"
            elif source_type == "youtube" and "chunk_index" in metadata:
                source_label += f" | transcript chunk {metadata['chunk_index']}"
                if "video_url" in metadata:
                    source_label += f" | {metadata['video_url']}"
            source_label += "]"
            
            context_parts.append(f"{source_label}\n{text}\n")
        
        return "\n".join(context_parts)
