import os
import re
import sys
import tempfile
import shutil
from typing import Optional, List as TList
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from backend.core.embedder import Embedder
from backend.core.vector_store import VectorStore
from backend.ingestion import (
    TextIngester,
    PDFIngester,
    CSVIngester,
    CodeIngester,
    ChatExportIngester,
    GitHubRepoIngester,
    YouTubeIngester,
    WebsiteIngester,
    ImageIngester,
    VoiceIngester,
)
from backend.config import SOURCES
from backend.core.upstash_redis import UpstashRedis

router = APIRouter(prefix="/ingest", tags=["ingestion"])

# Initialize components
embedder = Embedder()
vector_store = VectorStore()
_redis = UpstashRedis()


async def _bust_library_cache():
    """Invalidate the library cache so next GET /api/library returns fresh data."""
    try:
        await _redis.delete("api:library")
    except Exception:
        pass


class GitHubRequest(BaseModel):
    url: str


class IngestResponse(BaseModel):
    chunks_created: int
    source_name: str


def get_ingester(source_type: str):
    """Get the appropriate ingester for a source type."""
    ingesters = {
        "text": TextIngester(),
        "pdf": PDFIngester(),
        "csv": CSVIngester(),
        "code": CodeIngester(),
        "chat": ChatExportIngester(),
    }
    return ingesters.get(source_type)


def detect_source_type(filename: str) -> str:
    """Auto-detect source type from filename extension."""
    ext = os.path.splitext(filename)[1].lower()
    
    text_extensions = {".txt", ".md"}
    code_extensions = {".py", ".js", ".ts", ".java", ".go", ".cpp", ".c", ".cs", ".rb", ".php", ".rs"}
    
    if ext in text_extensions:
        return "text"
    elif ext == ".pdf":
        return "pdf"
    elif ext == ".csv":
        return "csv"
    elif ext in code_extensions:
        return "code"
    else:
        return "text"  # Default fallback


@router.post("/upload", response_model=IngestResponse)
async def upload_file(
    files: TList[UploadFile] = File(...),
    source_type: Optional[str] = Form(None)
):
    """Upload and ingest one or more files."""
    upload_dir = SOURCES["upload_dir"]
    os.makedirs(upload_dir, exist_ok=True)

    total_chunks = 0
    last_name = ""

    for file in files:
        st = source_type or detect_source_type(file.filename)
        if st == "code" and file.filename.lower().endswith(".json"):
            st = "chat"

        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, file.filename)

        try:
            with open(temp_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

            ingester = get_ingester(st)
            if not ingester:
                raise HTTPException(status_code=400, detail=f"Unsupported source type: {st}")

            try:
                chunks = ingester.ingest(temp_path)
            except Exception as e:
                raise HTTPException(status_code=422, detail=f"Failed to parse '{file.filename}': {str(e)}")

            if not chunks:
                raise HTTPException(status_code=400, detail=f"No content extracted from '{file.filename}'.")

            texts = [chunk.text for chunk in chunks]
            embeddings = embedder.embed_documents(texts)
            vector_store.upsert(chunks, embeddings)
            total_chunks += len(chunks)
            last_name = file.filename
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    await _bust_library_cache()
    return IngestResponse(chunks_created=total_chunks, source_name=last_name)


@router.post("/github", response_model=IngestResponse)
async def ingest_github(request: GitHubRequest):
    """Ingest a GitHub repository."""
    print(f"[DEBUG] Received GitHub ingest request: {request.url}", flush=True)
    sys.stdout.flush()
    repo_url = request.url
    
    # Validate URL
    if not repo_url.startswith("https://github.com/") and not repo_url.startswith("git@github.com:"):
        print(f"[DEBUG] Invalid GitHub URL: {repo_url}", flush=True)
        sys.stdout.flush()
        raise HTTPException(status_code=400, detail="Invalid GitHub URL")
    
    print("[DEBUG] Valid GitHub URL, starting ingestion...", flush=True)
    sys.stdout.flush()
    
    # Get GitHub ingester
    ingester = GitHubRepoIngester()
    
    # Ingest repository
    chunks = ingester.ingest(repo_url)
    
    if not chunks:
        raise HTTPException(status_code=400, detail="No content could be extracted from the repository. Ensure the repo is public and contains supported file types.")
    
    # Embed chunks in batches
    texts = [chunk.text for chunk in chunks]
    embeddings = embedder.embed_documents(texts)
    
    # Upsert to vector store
    vector_store.upsert(chunks, embeddings)
    await _bust_library_cache()
    
    # Extract repo name for response
    repo_name = repo_url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    
    return IngestResponse(
        chunks_created=len(chunks),
        source_name=repo_name
    )


class WebsiteRequest(BaseModel):
    url: str
    max_pages: int = 2
    include_path_prefix: Optional[str] = None


@router.post("/website", response_model=IngestResponse)
async def ingest_website(request: WebsiteRequest):
    """Crawl an entire website using Crawl4AI + sitemap discovery and ingest all pages."""
    url = request.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Basic URL validation
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid URL — could not determine domain.")

    try:
        ingester = WebsiteIngester(
            max_pages=min(request.max_pages, 500),  # hard cap
            same_domain_only=True,
            include_path_prefix=request.include_path_prefix,
        )
        chunks = ingester.ingest(url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Website crawl failed: {str(e)}")

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail=(
                "No content could be extracted from the website. "
                "The site may require JavaScript rendering, block bots, or have no accessible pages."
            ),
        )

    # Embed and store
    texts = [chunk.text for chunk in chunks]
    embeddings = embedder.embed_documents(texts)
    vector_store.upsert(chunks, embeddings)
    await _bust_library_cache()

    return IngestResponse(chunks_created=len(chunks), source_name=parsed.netloc)


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"
}
SUPPORTED_AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".ogg", ".flac", ".m4a", ".webm", ".mp4", ".aac", ".opus", ".weba"
}


@router.post("/image", response_model=IngestResponse)
async def ingest_image(
    file: UploadFile = File(...),
    language: Optional[str] = Form("auto"),
):
    """
    Ingest an image using Gemini 1.5 Flash vision analysis + pytesseract OCR.
    Supports JPEG, PNG, GIF, WEBP, BMP, TIFF.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in SUPPORTED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image format '{ext}'. Supported: {', '.join(sorted(SUPPORTED_IMAGE_EXTENSIONS))}",
        )

    # Check file size (read up to 21MB)
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large. Max 20 MB.")
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")

    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, file.filename or f"image{ext}")

    try:
        with open(temp_path, "wb") as f:
            f.write(raw)

        ingester = ImageIngester()
        try:
            chunks = ingester.ingest(temp_path)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Image analysis failed: {str(e)}")

        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="No content could be extracted from the image. "
                       "Ensure GEMINI_API_KEY is set and the image contains readable content.",
            )

        texts = [c.text for c in chunks]
        embeddings = embedder.embed_documents(texts)
        vector_store.upsert(chunks, embeddings)
        await _bust_library_cache()

        print(f"[Image] Ingested '{file.filename}': {len(chunks)} chunks embedded.")
        return IngestResponse(chunks_created=len(chunks), source_name=file.filename or "image")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/voice", response_model=IngestResponse)
async def ingest_voice(
    file: UploadFile = File(...),
    language: Optional[str] = Form("auto"),
):
    """
    Transcribe and ingest a voice/audio recording.
    Uses Google Web Speech API (SpeechRecognition library).
    Supports English (en-US, en-IN) and Hindi (hi-IN).
    Accepted formats: WAV, MP3, OGG, FLAC, M4A, WEBM, MP4.
    language param: 'auto' | 'en' | 'hi' | 'en+hi'
    """
    ext = os.path.splitext(file.filename or "")[1].lower()

    # Browsers record as webm/opus — also accept no extension (treat as webm)
    if not ext:
        ext = ".webm"
    if ext not in SUPPORTED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format '{ext}'. "
                   f"Supported: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}",
        )

    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")
    if len(raw) > 100 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Audio file too large. Max 100 MB.")

    # Sanitize language param
    lang = (language or "auto").lower().strip()
    if lang not in ("auto", "en", "hi", "en+hi"):
        lang = "auto"

    temp_dir = tempfile.mkdtemp()
    safe_name = re.sub(r"[^\w.\-]", "_", file.filename or f"voice{ext}")
    temp_path = os.path.join(temp_dir, safe_name)

    try:
        with open(temp_path, "wb") as f:
            f.write(raw)

        ingester = VoiceIngester(language=lang)
        try:
            chunks = ingester.ingest(temp_path)
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Voice transcription failed: {str(e)}")

        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="No speech could be recognized. "
                       "Ensure audio is clear, not silent, and in English or Hindi.",
            )

        texts = [c.text for c in chunks]
        embeddings = embedder.embed_documents(texts)
        vector_store.upsert(chunks, embeddings)

        await _bust_library_cache()
        source_name = safe_name
        transcript_preview = chunks[0].text[:200] if chunks else ""
        print(f"[Voice] Ingested '{safe_name}': {len(chunks)} chunks. Preview: '{transcript_preview}'")
        return IngestResponse(chunks_created=len(chunks), source_name=source_name)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


class VoiceTextRequest(BaseModel):
    transcript: str
    source_name: str = "voice_recording"
    language: str = "auto"


@router.post("/voice-text", response_model=IngestResponse)
async def ingest_voice_text(request: VoiceTextRequest):
    """
    Ingest a voice transcript produced by the browser's Web Speech API.
    No audio file upload needed — just the transcribed text.
    Supports English (en-IN, en-US) and Hindi (hi-IN).
    """
    transcript = (request.transcript or "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript is empty.")
    if len(transcript) > 50_000:
        raise HTTPException(status_code=400, detail="Transcript too long. Max 50,000 characters.")

    source_name = request.source_name or "voice_recording"

    ingester = VoiceIngester(language=request.language)
    try:
        chunks = ingester.ingest_transcript(transcript, source_name=source_name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice ingest failed: {str(e)}")

    if not chunks:
        raise HTTPException(status_code=400, detail="No content could be extracted from the transcript.")

    texts = [c.text for c in chunks]
    embeddings = embedder.embed_documents(texts)
    vector_store.upsert(chunks, embeddings)

    await _bust_library_cache()
    print(f"[Voice] Ingested transcript '{source_name}': {len(chunks)} chunks embedded.")
    return IngestResponse(chunks_created=len(chunks), source_name=source_name)


class YouTubeRequest(BaseModel):
    url: str


@router.post("/youtube", response_model=IngestResponse)
async def ingest_youtube(request: YouTubeRequest):
    """Download a YouTube video, transcribe it with Whisper, and ingest the transcript."""
    url = request.url
    # Basic YouTube URL validation
    if "youtube.com" not in url and "youtu.be" not in url:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    try:
        ingester = YouTubeIngester()
        chunks = ingester.ingest(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not chunks:
        raise HTTPException(status_code=400, detail="No transcript could be extracted from the video")
    texts = [chunk.text for chunk in chunks]
    embeddings = embedder.embed_documents(texts)
    vector_store.upsert(chunks, embeddings)
    await _bust_library_cache()
    source_name = chunks[0].source_name
    return IngestResponse(chunks_created=len(chunks), source_name=source_name)


class TextRequest(BaseModel):
    content: str
    source_name: str


class AIChatRequest(BaseModel):
    url: str


@router.post("/ai-chat", response_model=IngestResponse)
async def ingest_ai_chat(request: AIChatRequest):
    """Ingest an AI chat conversation from a shared URL (ChatGPT, Gemini, Claude, Grok, Perplexity)."""
    print(f"[AI Chat] Received ingestion request: {request.url}", flush=True)
    url = request.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    from urllib.parse import urlparse
    parsed = urlparse(url)
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid URL — could not determine domain.")

    # Import the AI chat parser module
    from backend.ingestion.ai_chat_parsers import (
        parse_ai_chat,
        messages_to_text,
        detect_platform,
    )
    from backend.ingestion.base import Chunk
    import datetime

    # Detect platform first for better error messages
    platform = detect_platform(url)
    if not platform:
        raise HTTPException(
            status_code=400,
            detail="Unknown AI chat platform. Supported: ChatGPT, Gemini, Claude, Grok, Perplexity."
        )
    
    print(f"[AI Chat] Detected platform: {platform}", flush=True)

    # Parse the chat conversation
    try:
        platform, messages = await parse_ai_chat(url)
    except Exception as e:
        print(f"[AI Chat] Parsing failed: {str(e)}", flush=True)
        raise HTTPException(status_code=500, detail=f"Failed to parse chat: {str(e)}")

    if not messages:
        raise HTTPException(
            status_code=400,
            detail=f"No conversation could be extracted from {platform}. The page may require authentication or be unavailable."
        )

    print(f"[AI Chat] Parsed {len(messages)} messages from {platform}", flush=True)

    # Convert messages to text for embedding
    chat_text = messages_to_text(messages)
    if not chat_text:
        raise HTTPException(status_code=400, detail="No text content could be extracted from the conversation.")

    # Create chunks from the conversation
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from backend.config import CHUNKING
    
    chat_config = CHUNKING.get("chat", {})
    chunk_size = chat_config.get("size") or 800
    overlap = chat_config.get("overlap") or 100

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n---\n\n", "\n\n", "\n", ". ", " "]
    )
    
    split_docs = splitter.create_documents([chat_text])
    
    # Use URL path as source name for chat links
    source_name = parsed.path.strip("/").replace("/", "_") or parsed.netloc
    now = datetime.datetime.now().isoformat()
    
    chunks = []
    for i, doc in enumerate(split_docs):
        chunk = Chunk(
            text=doc.page_content,
            source_type="chat",
            source_name=source_name,
            metadata={
                "platform": platform,
                "url": url,
                "turn_count": len(messages),
                "chunk_index": i,
                "ingested_at": now,
            }
        )
        chunks.append(chunk)

    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks could be created from the conversation.")

    # Embed and store
    texts = [chunk.text for chunk in chunks]
    embeddings = embedder.embed_documents(texts)
    vector_store.upsert(chunks, embeddings)

    await _bust_library_cache()
    print(f"[AI Chat] Ingested '{source_name}': {len(chunks)} chunks embedded.", flush=True)
    return IngestResponse(chunks_created=len(chunks), source_name=source_name)


@router.post("/text", response_model=IngestResponse)
async def ingest_text(request: TextRequest):
    """Ingest plain text content directly."""
    content = request.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is empty")
    
    source_name = request.source_name.strip() or "pasted_text"
    
    # Use TextIngester logic but with direct content
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from backend.ingestion.base import Chunk
    import datetime

    # Get chunking config
    from backend.config import CHUNKING
    chunk_size = CHUNKING["text"]["size"]
    overlap = CHUNKING["text"]["overlap"]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " "]
    )
    
    split_docs = splitter.create_documents([content])
    
    chunks = []
    for i, doc in enumerate(split_docs):
        chunk = Chunk(
            text=doc.page_content,
            source_type="text",
            source_name=source_name,
            metadata={
                "filename": source_name,
                "extension": ".txt",
                "ingested_at": datetime.datetime.now().isoformat(),
                "chunk_index": i
            }
        )
        chunks.append(chunk)

    if not chunks:
        raise HTTPException(status_code=400, detail="No content could be processed")

    # Embed and store
    texts = [chunk.text for chunk in chunks]
    embeddings = embedder.embed_documents(texts)
    vector_store.upsert(chunks, embeddings)
    await _bust_library_cache()

    return IngestResponse(chunks_created=len(chunks), source_name=source_name)


@router.post("/audio", response_model=IngestResponse)
async def ingest_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form("auto"),
):
    """Alias for /ingest/voice to match frontend requirements."""
    return await ingest_voice(file, language)
