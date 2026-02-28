import os
from typing import List, Dict, Any, Optional
from pymilvus import MilvusClient
from backend.config import VECTOR_DB
from backend.ingestion.base import Chunk


class VectorStore:
    def __init__(self):
        self.uri = os.getenv("ZILLIZ_URI")
        self.token = os.getenv("ZILLIZ_TOKEN")
        self.client = MilvusClient(uri=self.uri, token=self.token)
        self.collection_docs = VECTOR_DB["collection_docs"]
        self.collection_chats = VECTOR_DB["collection_chats"]
        self.dimensions = VECTOR_DB["dimensions"]
        self._create_collections()

    def _create_collections(self):
        """Create collections if they don't exist."""
        for collection_name in [self.collection_docs, self.collection_chats]:
            if not self.client.has_collection(collection_name):
                self.client.create_collection(
                    collection_name=collection_name,
                    dimension=self.dimensions,
                    metric_type="COSINE",
                    id_type="str",
                    auto_id=True,
                    max_length=65535
                )
            self.client.load_collection(collection_name)

    def _get_collection(self, source_type: str) -> str:
        """Determine which collection to use based on source type."""
        if source_type == "chat":
            return self.collection_chats
        return self.collection_docs

    def upsert(self, chunks: List[Chunk], embeddings: List[List[float]]):
        """Insert chunks with embeddings into the appropriate collection."""
        if not chunks or not embeddings:
            return

        collection_name = self._get_collection(chunks[0].source_type)

        data = []
        skipped = 0
        for chunk, embedding in zip(chunks, embeddings):
            # Validate text
            if not chunk.text or not chunk.text.strip():
                skipped += 1
                continue
            # Validate embedding dimension
            if not embedding or len(embedding) != self.dimensions:
                print(f"[WARN] Skipping chunk with wrong embedding dim: {len(embedding) if embedding else 0} (expected {self.dimensions})")
                skipped += 1
                continue
            # Validate no NaN/Inf in embedding
            if any(v != v or v == float('inf') or v == float('-inf') for v in embedding):
                print(f"[WARN] Skipping chunk with NaN/Inf in embedding")
                skipped += 1
                continue
            data.append({
                "vector": embedding,
                "text": chunk.text[:32000],        # Milvus varchar cap
                "source_type": chunk.source_type,
                "source_name": chunk.source_name[:512],
                "metadata": chunk.metadata if isinstance(chunk.metadata, dict) else {},
            })

        if skipped:
            print(f"[WARN] upsert: skipped {skipped} invalid chunks out of {len(chunks)}")

        if not data:
            print("[WARN] upsert: no valid data to insert after validation")
            return

        self.client.insert(collection_name=collection_name, data=data)
        self.client.flush(collection_name=collection_name)
        self.client.load_collection(collection_name)
        print(f"[DEBUG] upsert: inserted {len(data)} chunks into {collection_name}")

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 20,
        source_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors with optional source type filter."""
        results = []

        if len(query_embedding) != self.dimensions:
            print(
                f"[DEBUG] Query embedding dim mismatch: got={len(query_embedding)}, expected={self.dimensions}"
            )
        
        collections_to_search = [self.collection_docs, self.collection_chats]
        
        for collection_name in collections_to_search:
            try:
                self.client.load_collection(collection_name)
                stats = self.client.get_collection_stats(collection_name)
                row_count = stats.get("row_count", 0)
                print(f"[DEBUG] Collection {collection_name} row_count={row_count}")
                
                # Diagnostic: query one row to see stored vector dimension
                if row_count > 0:
                    sample = self.client.query(
                        collection_name=collection_name,
                        filter="",
                        output_fields=["vector", "text", "source_type"],
                        limit=1
                    )
                    if sample and len(sample) > 0:
                        vec = sample[0].get("vector", [])
                        print(f"[DEBUG] Sample vector dim: {len(vec) if isinstance(vec, list) else 'not a list'}")
                        print(f"[DEBUG] Sample source_type: {sample[0].get('source_type')}")
            except Exception as e:
                print(f"[DEBUG] Error getting stats for {collection_name}: {e}")
            
            filter_expr = None
            if source_types and "All" not in source_types:
                allowed = ", ".join([f'"{t}"' for t in source_types])
                filter_expr = f"source_name in [{allowed}]"
            
            print(f"[DEBUG] Query embedding dim: {len(query_embedding)}")
            print(f"[DEBUG] Searching {collection_name} with filter={filter_expr}")
            
            try:
                search_results = self.client.search(
                    collection_name=collection_name,
                    data=[query_embedding],
                    limit=top_k,
                    filter=filter_expr,
                    anns_field="vector",
                    search_params={"metric_type": "COSINE", "params": {"nprobe": 10}},
                    output_fields=["text", "source_type", "source_name", "metadata"]
                )
                
                print(f"[DEBUG] Search on {collection_name} returned: {len(search_results[0]) if search_results else 0} hits")
                
                if search_results and len(search_results) > 0:
                    for hit in search_results[0]:
                        # Milvus search hits expose fields via hit["entity"] or directly on the hit dict
                        entity = hit.get("entity") if isinstance(hit.get("entity"), dict) else {}
                        results.append({
                            "id": hit.get("id"),
                            "score": hit.get("distance", 0),
                            "text": entity.get("text") or hit.get("text", ""),
                            "source_type": entity.get("source_type") or hit.get("source_type", ""),
                            "source_name": entity.get("source_name") or hit.get("source_name", ""),
                            "metadata": entity.get("metadata") or hit.get("metadata", {})
                        })
            except Exception as e:
                print(f"[DEBUG] Search error on {collection_name}: {e}")
        
        # Sort by score and return top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def get_source_files(self, source_name: str) -> List[Dict[str, Any]]:
        """Get list of unique files from a source."""
        files = set()
        
        for collection_name in [self.collection_docs, self.collection_chats]:
            try:
                self.client.load_collection(collection_name)
                # Query all vectors with filter for source_name
                results = self.client.query(
                    collection_name=collection_name,
                    filter=f'source_name == "{source_name}"',
                    output_fields=["metadata"],
                    limit=1000
                )
                
                for hit in results:
                    # Milvus SDK query() returns flat dicts, not {entity: ...}
                    raw_meta = hit.get("metadata") or hit.get("entity", {}).get("metadata", {})
                    if isinstance(raw_meta, dict):
                        metadata = raw_meta
                    else:
                        metadata = {}
                    file_path = metadata.get("file_path", "")
                    if file_path:
                        files.add(file_path)
            except Exception as e:
                print(f"[DEBUG] Error getting files from {collection_name}: {e}")
        
        return [{"file_path": f} for f in sorted(files)]

    def get_all_sources(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all unique sources grouped by source type."""
        sources = {}
        
        for collection_name in [self.collection_docs, self.collection_chats]:
            try:
                # Query all documents to get unique sources
                results = self.client.query(
                    collection_name=collection_name,
                    filter="",
                    output_fields=["source_type", "source_name", "metadata"],
                    limit=10000
                )
                
                # Group by source_name
                seen = set()
                for item in results:
                    # Milvus SDK query() returns flat dicts; handle both flat and entity-wrapped
                    source_name = item.get("source_name") or item.get("entity", {}).get("source_name", "")
                    source_type = item.get("source_type") or item.get("entity", {}).get("source_type", "")
                    raw_meta = item.get("metadata") or item.get("entity", {}).get("metadata", {})
                    metadata = raw_meta if isinstance(raw_meta, dict) else {}
                    
                    if source_name and source_name not in seen:
                        seen.add(source_name)
                        if source_type not in sources:
                            sources[source_type] = []
                        
                        sources[source_type].append({
                            "name": source_name,
                            "type": source_type,
                            "ingested_at": metadata.get("ingested_at", "unknown")
                        })
            except Exception:
                pass
        
        return sources

    def get_chunk_count(self, source_name: str) -> int:
        """Get the number of chunks for a given source using pagination."""
        count = 0
        escaped = source_name.replace('\\', '\\\\').replace('"', '\\"')
        for collection_name in [self.collection_docs, self.collection_chats]:
            try:
                offset = 0
                batch = 16383  # Milvus max query limit
                while True:
                    results = self.client.query(
                        collection_name=collection_name,
                        filter=f'source_name == "{escaped}"',
                        output_fields=["source_name"],
                        limit=batch,
                        offset=offset
                    )
                    count += len(results)
                    if len(results) < batch:
                        break
                    offset += batch
            except Exception:
                pass
        return count

    def has_documents(self) -> bool:
        """Check if any documents exist in the vector store."""
        try:
            stats = self.client.get_collection_stats(self.collection_docs)
            return int(stats.get("row_count", 0)) > 0
        except Exception:
            return False

    def delete_source(self, source_name: str):
        """Delete all vectors for a given source from both collections."""
        escaped = source_name.replace('\\', '\\\\').replace('"', '\\"')
        expr = f'source_name == "{escaped}"'
        for collection_name in [self.collection_docs, self.collection_chats]:
            try:
                self.client.load_collection(collection_name)
                res = self.client.delete(
                    collection_name=collection_name,
                    filter=expr,
                )
                self.client.flush(collection_name=collection_name)
                print(f"[DEBUG] Deleted source_name={source_name} from {collection_name}: {res}")
            except Exception as e:
                print(f"[DEBUG] Error deleting source_name={source_name} from {collection_name}: {e}")
