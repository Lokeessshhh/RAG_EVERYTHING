import os
from typing import List
import fitz  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter
from backend.ingestion.base import BaseIngester, Chunk
from backend.config import CHUNKING


class PDFIngester(BaseIngester):
    def __init__(self):
        self.chunk_size = CHUNKING["pdf"]["size"]
        self.overlap = CHUNKING["pdf"]["overlap"]

    def ingest(self, source_path: str) -> List[Chunk]:
        """Ingest PDF files with section-aware chunking."""
        chunks = []
        filename = os.path.basename(source_path)
        
        doc = fitz.open(source_path)
        
        # Extract pages and detect headings
        pages_data = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            
            # Skip pages with minimal content
            if len(text.strip()) < 30:
                continue
            
            # Detect headings by font size
            headings = self._detect_headings(page)
            
            pages_data.append({
                "page_num": page_num + 1,
                "text": text,
                "headings": headings
            })
        
        doc.close()
        
        # Check if we have detected headings
        has_headings = any(p["headings"] for p in pages_data)
        
        if has_headings:
            # Section-aware chunking
            chunks = self._chunk_by_sections(pages_data, filename)
        else:
            # Fallback to recursive splitter
            chunks = self._chunk_by_splitter(pages_data, filename)
        
        return chunks

    def _detect_headings(self, page) -> List[dict]:
        """Detect headings based on font size."""
        headings = []
        
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" not in block:
                continue
            
            for line in block["lines"]:
                for span in line["spans"]:
                    # Heuristic: larger font sizes are headings
                    if span["size"] > 14 and span["text"].strip():
                        headings.append({
                            "text": span["text"].strip(),
                            "size": span["size"],
                            "y": line["bbox"][1]
                        })
        
        # Sort by position
        headings.sort(key=lambda h: h["y"])
        return headings

    def _chunk_by_sections(self, pages_data: List[dict], filename: str) -> List[Chunk]:
        """Chunk text by detected sections."""
        chunks = []
        current_section = "Introduction"
        current_text = []
        
        for page_data in pages_data:
            page_num = page_data["page_num"]
            text = page_data["text"]
            headings = page_data["headings"]
            
            # Split text by headings
            lines = text.split("\n")
            heading_texts = {h["text"] for h in headings}
            
            for line in lines:
                stripped = line.strip()
                
                # Check if this line is a heading
                if stripped in heading_texts:
                    # Save current section if it has content
                    if current_text:
                        section_content = "\n".join(current_text)
                        if len(section_content.strip()) > 50:
                            chunks.extend(self._create_section_chunks(
                                section_content,
                                filename,
                                page_num,
                                current_section
                            ))
                    
                    current_section = stripped
                    current_text = []
                else:
                    current_text.append(line)
        
        # Handle remaining content
        if current_text:
            section_content = "\n".join(current_text)
            if len(section_content.strip()) > 50:
                chunks.extend(self._create_section_chunks(
                    section_content,
                    filename,
                    pages_data[-1]["page_num"] if pages_data else 1,
                    current_section
                ))
        
        return chunks

    def _chunk_by_splitter(self, pages_data: List[dict], filename: str) -> List[Chunk]:
        """Fallback: chunk using RecursiveCharacterTextSplitter."""
        chunks = []
        
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.overlap,
            separators=["\n\n", "\n", ". ", " "]
        )
        
        for page_data in pages_data:
            page_num = page_data["page_num"]
            text = page_data["text"]
            
            split_docs = splitter.create_documents([text])
            
            for i, doc in enumerate(split_docs):
                chunk = Chunk(
                    text=doc.page_content,
                    source_type="pdf",
                    source_name=filename,
                    metadata={
                        "filename": filename,
                        "page_number": page_num,
                        "section_heading": None,
                        "ingested_at": self._get_timestamp(),
                        "chunk_index": i
                    }
                )
                chunks.append(chunk)
        
        return chunks

    def _create_section_chunks(
        self,
        text: str,
        filename: str,
        page_num: int,
        section: str
    ) -> List[Chunk]:
        """Create chunks from a section, splitting if necessary."""
        chunks = []
        
        if len(text) <= self.chunk_size:
            chunk = Chunk(
                text=text,
                source_type="pdf",
                source_name=filename,
                metadata={
                    "filename": filename,
                    "page_number": page_num,
                    "section_heading": section,
                    "ingested_at": self._get_timestamp(),
                    "chunk_index": 0
                }
            )
            chunks.append(chunk)
        else:
            # Split large sections
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.overlap,
                separators=["\n\n", "\n", ". ", " "]
            )
            
            split_docs = splitter.create_documents([text])
            
            for i, doc in enumerate(split_docs):
                chunk = Chunk(
                    text=doc.page_content,
                    source_type="pdf",
                    source_name=filename,
                    metadata={
                        "filename": filename,
                        "page_number": page_num,
                        "section_heading": section,
                        "ingested_at": self._get_timestamp(),
                        "chunk_index": i
                    }
                )
                chunks.append(chunk)
        
        return chunks
