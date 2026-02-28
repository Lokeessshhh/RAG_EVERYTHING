import os
from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter
from backend.ingestion.base import BaseIngester, Chunk
from backend.config import CHUNKING


class TextIngester(BaseIngester):
    def __init__(self):
        self.chunk_size = CHUNKING["text"]["size"]
        self.overlap = CHUNKING["text"]["overlap"]

    def ingest(self, source_path: str) -> List[Chunk]:
        """Ingest text/markdown files."""
        chunks = []
        
        with open(source_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        filename = os.path.basename(source_path)
        extension = os.path.splitext(source_path)[1].lower()
        
        # Determine source type based on extension
        if extension == ".md":
            source_type = "text"
        else:
            source_type = "text"
        
        # Use RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.overlap,
            separators=["\n\n", "\n", ". ", " "]
        )
        
        split_docs = splitter.create_documents([content])
        
        for i, doc in enumerate(split_docs):
            chunk = Chunk(
                text=doc.page_content,
                source_type=source_type,
                source_name=filename,
                metadata={
                    "filename": filename,
                    "extension": extension,
                    "ingested_at": self._get_timestamp(),
                    "chunk_index": i
                }
            )
            chunks.append(chunk)
        
        return chunks
