import os
from typing import List
import pandas as pd
from langchain_text_splitters import RecursiveCharacterTextSplitter
from backend.ingestion.base import BaseIngester, Chunk
from backend.config import CHUNKING

_MAX_CHUNK_CHARS = 800  # hard cap for any single CSV chunk


class CSVIngester(BaseIngester):
    def __init__(self):
        self.chunk_size = CHUNKING["csv"]["size"]
        self.overlap = CHUNKING["csv"]["overlap"]
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=_MAX_CHUNK_CHARS,
            chunk_overlap=0,
            separators=["\n", ", ", " "]
        )

    def ingest(self, source_path: str) -> List[Chunk]:
        """Ingest CSV files - each row is one chunk."""
        chunks = []
        filename = os.path.basename(source_path)
        table_name = os.path.splitext(filename)[0]
        
        df = pd.read_csv(source_path)
        
        # If too many columns, drop ID/hash columns
        if len(df.columns) > 20:
            columns_to_drop = []
            for col in df.columns:
                col_lower = col.lower()
                if any(x in col_lower for x in ["id", "hash", "uuid", "_id"]):
                    if df[col].dtype == "object" or "int" in str(df[col].dtype):
                        columns_to_drop.append(col)
            
            if columns_to_drop:
                df = df.drop(columns=columns_to_drop)
        
        column_names = list(df.columns)
        
        # Process rows
        batch_rows = []
        batch_texts = []
        
        for idx, row in df.iterrows():
            row_text = self._format_row(row, column_names)
            
            # If row text is short, batch with other rows
            if len(row_text) < 50:
                batch_rows.append((idx, row_text))
                batch_texts.append(row_text)
                
                # When we have 5-10 short rows, combine them
                if len(batch_rows) >= 7:
                    combined_text = "\n".join(batch_texts)
                    chunks.extend(self._make_chunks(combined_text, filename, table_name, column_names, [r[0] for r in batch_rows]))
                    batch_rows = []
                    batch_texts = []
            else:
                # Flush any pending batch
                if batch_rows:
                    combined_text = "\n".join(batch_texts)
                    chunks.extend(self._make_chunks(combined_text, filename, table_name, column_names, [r[0] for r in batch_rows]))
                    batch_rows = []
                    batch_texts = []
                
                # Create individual chunk for this row
                chunks.extend(self._make_chunks(row_text, filename, table_name, column_names, idx))
        
        # Handle remaining batch
        if batch_rows:
            combined_text = "\n".join(batch_texts)
            chunks.extend(self._make_chunks(combined_text, filename, table_name, column_names, [r[0] for r in batch_rows]))
        
        return chunks

    def _make_chunks(self, text: str, filename: str, table_name: str, column_names: list, row_index) -> List[Chunk]:
        """Create chunks from text, splitting if over size cap."""
        texts = self._splitter.split_text(text) if len(text) > _MAX_CHUNK_CHARS else [text]
        return [
            Chunk(
                text=t,
                source_type="csv",
                source_name=filename,
                metadata={
                    "filename": filename,
                    "table_name": table_name,
                    "row_index": row_index,
                    "column_names": column_names,
                    "ingested_at": self._get_timestamp()
                }
            )
            for t in texts if t.strip()
        ]

    def _format_row(self, row, column_names: List[str]) -> str:
        """Format a row as 'ColumnName: Value, ColumnName: Value, ...'"""
        parts = []
        for col in column_names:
            value = row[col]
            if pd.isna(value):
                value = ""
            parts.append(f"{col}: {value}")
        
        return ", ".join(parts)
