"""
Image RAG Ingester
==================
Analyzes images using Google Gemini 1.5 Flash (vision) as primary method,
with pytesseract OCR as parallel/fallback for text extraction.

Supports: JPEG, PNG, GIF, WEBP, BMP, TIFF
Languages: English and Hindi (Devanagari)

Pipeline per image:
1. Validate image (format, size, corruption check)
2. [Parallel] Run Gemini 1.5 Flash vision analysis + pytesseract OCR
3. Merge: Gemini summary/description + OCR text (deduplicated)
4. NFC normalize (fixes Hindi combining chars)
5. Chunk into overlapping segments for embedding
"""

import os
import re
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple

from backend.config import CHUNKING
from backend.ingestion.base import BaseIngester, Chunk

# ---------------------------------------------------------------------------
# Optional dependencies
# ---------------------------------------------------------------------------
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    print("[WARN] google-genai not installed — Gemini vision disabled. Run: pip install google-genai")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[WARN] Pillow not installed — image validation will be limited.")

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    print("[WARN] pytesseract not installed — OCR fallback disabled.")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}
MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024   # 20 MB (Gemini limit)
MAX_IMAGE_DIMENSION = 4096                 # px — resize if larger
GEMINI_MODEL = "gemini-2.5-flash"         # Best current model for vision (Feb 2026)

# Tesseract language codes
TESSERACT_LANG_EN   = "eng"
TESSERACT_LANG_HI   = "hin"
TESSERACT_LANG_BOTH = "eng+hin"

GEMINI_PROMPT = """\
You are an expert document and image analyzer for a RAG (Retrieval-Augmented Generation) system.

Analyze this image thoroughly and produce structured text that will be embedded into a vector database.

Your response MUST include ALL of the following sections that are applicable:

1. **CONTENT DESCRIPTION**: Describe what the image shows in detail (objects, people, scene, layout).
2. **OCR TEXT**: Extract ALL visible text from the image exactly as written. Preserve numbers, dates, names, codes.
   - If text is in Hindi (Devanagari), transcribe it exactly in Devanagari script.
   - If text is in English, transcribe it exactly.
   - If mixed (Hinglish), transcribe both.
3. **KEY INFORMATION**: Bullet-point list of the most important facts, data points, or concepts visible.
4. **DOCUMENT TYPE**: (if applicable) e.g. invoice, chart, diagram, screenshot, photograph, handwritten note.
5. **SUMMARY**: A 2-3 sentence plain-English summary suitable for semantic search.

Be exhaustive. Do not skip any text visible in the image. Format clearly with section headers.
"""


class ImageIngester(BaseIngester):
    """
    Ingest images for RAG using Gemini 1.5 Flash vision + pytesseract OCR.

    Usage:
        ingester = ImageIngester()
        chunks = ingester.ingest("/path/to/image.jpg")
    """

    def __init__(self):
        # Read API key lazily in _analyze_with_gemini so that load_dotenv()
        # in main.py has time to run before we check the env var.
        cfg = CHUNKING.get("image", {"size": 800, "overlap": 100})
        self.chunk_size = cfg["size"]
        self.overlap = cfg["overlap"]

    @property
    def _gemini_api_key(self) -> str:
        """Lazily read GEMINI_API_KEY so load_dotenv() has already run."""
        return os.getenv("GEMINI_API_KEY", "")

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def ingest(self, source_path: str) -> List[Chunk]:
        """
        Ingest an image file and return RAG chunks.
        source_path: absolute path to the image file.
        """
        path = Path(source_path)

        # Validate
        error = self._validate_image(path)
        if error:
            raise ValueError(f"Image validation failed: {error}")

        print(f"[Image] Ingesting: {path.name}")

        # Run Gemini + OCR
        gemini_text = ""
        ocr_text = ""

        gemini_text = self._analyze_with_gemini(path)

        if TESSERACT_AVAILABLE and PIL_AVAILABLE:
            ocr_text = self._extract_ocr(path)

        # Merge results
        combined = self._merge_analyses(gemini_text, ocr_text, path.name)

        if not combined.strip():
            raise ValueError(f"No content could be extracted from image '{path.name}'.")

        print(f"[Image] Extracted {len(combined)} chars from '{path.name}' "
              f"(Gemini: {'yes' if gemini_text else 'no'}, OCR: {'yes' if ocr_text else 'no'})")

        # Build chunks
        chunks = self._text_to_chunks(combined, source_name=path.name)
        print(f"[Image] Created {len(chunks)} chunks from '{path.name}'")
        return chunks

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_image(self, path: Path) -> Optional[str]:
        """Return error string if invalid, None if OK."""
        if not path.exists():
            return f"File not found: {path}"

        ext = path.suffix.lower()
        if ext not in SUPPORTED_FORMATS:
            return f"Unsupported format '{ext}'. Supported: {', '.join(sorted(SUPPORTED_FORMATS))}"

        size = path.stat().st_size
        if size == 0:
            return "File is empty."
        if size > MAX_IMAGE_SIZE_BYTES:
            return f"File too large ({size // 1024 // 1024} MB). Max: 20 MB."

        if PIL_AVAILABLE:
            try:
                with Image.open(path) as img:
                    img.verify()   # raises if corrupt
            except Exception as e:
                return f"Image file is corrupt or unreadable: {e}"

        return None

    # ------------------------------------------------------------------
    # Gemini 1.5 Flash Vision
    # ------------------------------------------------------------------

    def _analyze_with_gemini(self, path: Path) -> str:
        """Analyze image using google-genai SDK (same as working test script)."""
        if not GENAI_AVAILABLE:
            print("[WARN] google-genai not installed — Gemini vision disabled. Run: pip install google-genai")
            return ""
        if not PIL_AVAILABLE:
            print("[WARN] Pillow not installed — cannot open image for Gemini.")
            return ""

        key = self._gemini_api_key
        if not key:
            print("[WARN] GEMINI_API_KEY not set — Gemini vision disabled. Set it in your .env file.")
            return ""

        try:
            client = genai.Client(api_key=key)
            img = Image.open(path)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[GEMINI_PROMPT, img],
            )
            text = response.text.strip() if response.text else ""
            print(f"[Image] Gemini ({GEMINI_MODEL}) extracted {len(text)} chars.")
            return text

        except Exception as e:
            print(f"[Image] Gemini error: {e}")
            return ""

    # ------------------------------------------------------------------
    # pytesseract OCR
    # ------------------------------------------------------------------

    def _extract_ocr(self, path: Path) -> str:
        """Extract text using pytesseract with English + Hindi support."""
        if not TESSERACT_AVAILABLE or not PIL_AVAILABLE:
            return ""

        try:
            with Image.open(path) as img:
                # Convert to RGB (tesseract doesn't handle all modes)
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")

                # Resize if too large (speeds up OCR, avoids memory issues)
                w, h = img.size
                if max(w, h) > MAX_IMAGE_DIMENSION:
                    scale = MAX_IMAGE_DIMENSION / max(w, h)
                    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

                # Try English + Hindi first, fall back to English only
                try:
                    text = pytesseract.image_to_string(img, lang=TESSERACT_LANG_BOTH)
                except pytesseract.TesseractError:
                    try:
                        text = pytesseract.image_to_string(img, lang=TESSERACT_LANG_EN)
                    except Exception:
                        return ""

            text = text.strip()
            print(f"[Image] OCR extracted {len(text)} chars.")
            return text

        except Exception as e:
            print(f"[Image] OCR error: {e}")
            return ""

    # ------------------------------------------------------------------
    # Merge Gemini + OCR results
    # ------------------------------------------------------------------

    def _merge_analyses(self, gemini_text: str, ocr_text: str, filename: str) -> str:
        """
        Merge Gemini vision analysis and OCR text into a single coherent block.
        Deduplicates OCR text that Gemini already captured.
        """
        parts = []

        # Header with filename for context
        parts.append(f"Image: {filename}\n")

        if gemini_text:
            # Normalize unicode
            gemini_text = unicodedata.normalize("NFC", gemini_text)
            parts.append(gemini_text)

        if ocr_text:
            ocr_text = unicodedata.normalize("NFC", ocr_text)
            # Only append OCR if it adds meaningful content not in Gemini output
            if not gemini_text:
                # No Gemini — use OCR as primary
                parts.append(f"\nExtracted Text (OCR):\n{ocr_text}")
            else:
                # Check if OCR has significant unique content (>50 chars not in gemini)
                ocr_unique = self._unique_content(ocr_text, gemini_text, threshold=50)
                if ocr_unique:
                    parts.append(f"\nAdditional OCR Text:\n{ocr_unique}")

        return "\n".join(parts).strip()

    def _unique_content(self, source: str, reference: str, threshold: int = 50) -> str:
        """Return lines from source not found in reference (simple substring check)."""
        ref_lower = reference.lower()
        unique_lines = []
        for line in source.splitlines():
            stripped = line.strip()
            if len(stripped) < 3:
                continue
            # Check if this line already appears in gemini output
            if stripped.lower() not in ref_lower:
                unique_lines.append(line)

        unique_text = "\n".join(unique_lines).strip()
        return unique_text if len(unique_text) >= threshold else ""

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def _text_to_chunks(self, text: str, source_name: str) -> List[Chunk]:
        """Split extracted image text into overlapping chunks."""
        # Clean up excessive whitespace
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        text = re.sub(r" {3,}", "  ", text)
        text = text.strip()

        if len(text) < 50:
            # Very short — return as single chunk
            return [Chunk(
                text=text,
                source_type="image",
                source_name=source_name,
                metadata={"chunk_index": 0, "ingested_at": self._get_timestamp()},
            )]

        chunks: List[Chunk] = []
        start = 0
        chunk_idx = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end]

            # Break at natural boundary
            if end < len(text):
                for boundary in ["\n\n", "\n", ". ", "! ", "? "]:
                    last = chunk_text.rfind(boundary)
                    if last > self.chunk_size // 2:
                        chunk_text = chunk_text[:last + len(boundary)]
                        break

            chunk_text = chunk_text.strip()
            if len(chunk_text) >= 20:
                chunks.append(Chunk(
                    text=chunk_text,
                    source_type="image",
                    source_name=source_name,
                    metadata={
                        "chunk_index": chunk_idx,
                        "ingested_at": self._get_timestamp(),
                        "has_gemini": True,
                        "has_ocr": TESSERACT_AVAILABLE,
                    },
                ))
                chunk_idx += 1

            advance = max(len(chunk_text) - self.overlap, 1)
            start += advance

            if chunk_idx > 500:
                break

        return chunks