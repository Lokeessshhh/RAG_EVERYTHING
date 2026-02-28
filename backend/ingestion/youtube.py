import re
import unicodedata
from datetime import datetime
from typing import List, Optional

from backend.ingestion.base import BaseIngester, Chunk
from backend.config import CHUNKING


def _extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _chunk_transcript(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split transcript text into overlapping chunks by word count."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i:i + chunk_size]
        chunks.append(" ".join(chunk_words))
        if i + chunk_size > len(words):
            break
        i += chunk_size - overlap
    return chunks


def _fetch_transcript(video_id: str):
    """
    Fetch transcript using youtube-transcript-api (v1.x instance API).
    Uses YouTubeTranscriptApi().fetch() directly with language preference.
    Tries in priority order: Hindi → English → any available language.
    Returns (full_text, language_code)
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        raise RuntimeError(
            "youtube-transcript-api is not installed. Run: pip install youtube-transcript-api"
        )

    api = YouTubeTranscriptApi()

    fetched = None
    language_code = "unknown"

    # 1. Try Hindi + English first (preferred for multilingual support)
    try:
        fetched = api.fetch(video_id, languages=["hi", "en", "en-US", "en-GB"])
        language_code = fetched.language_code
    except Exception:
        pass

    # 2. Fall back — fetch whatever language is available
    if fetched is None:
        try:
            fetched = api.fetch(video_id)
            language_code = fetched.language_code
        except Exception as e:
            raise RuntimeError(
                f"Could not fetch transcript for video {video_id}. "
                f"The video may have captions disabled. Error: {e}"
            )

    # Build full text from snippet objects (.text attribute in v1.x)
    parts = []
    for snippet in fetched:
        text = snippet.text if hasattr(snippet, "text") else snippet.get("text", "")
        text = text.replace("\n", " ").strip()
        if text:
            parts.append(text)

    full_text = " ".join(parts)

    # Normalize Unicode to NFC — reattaches combining characters (matras in Devanagari)
    # This fixes garbled Hindi like "दनय" → "दुनिया"
    full_text = unicodedata.normalize("NFC", full_text)

    return full_text, language_code


def _get_video_title(video_id: str) -> str:
    """
    Try to get the video title via yt-dlp (if installed) or fall back to video ID.
    This is optional — transcript fetching does not depend on this.
    """
    try:
        import yt_dlp
        ydl_opts = {"quiet": True, "skip_download": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False
            )
            return info.get("title") or f"youtube_{video_id}"
    except Exception:
        pass

    # Lightweight fallback: scrape page title without downloading
    try:
        import httpx
        resp = httpx.get(
            f"https://www.youtube.com/watch?v={video_id}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10.0,
            follow_redirects=True,
        )
        match = re.search(r"<title>(.+?)</title>", resp.text)
        if match:
            raw = match.group(1).strip()
            # YouTube appends " - YouTube" to every title
            title = re.sub(r"\s*-\s*YouTube\s*$", "", raw, flags=re.IGNORECASE).strip()
            if title:
                return title
    except Exception:
        pass

    return f"youtube_{video_id}"


class YouTubeIngester(BaseIngester):
    """
    Ingests a YouTube video by fetching its transcript/captions via
    youtube-transcript-api (no audio download, no ffmpeg required).

    Supports:
    - Hindi captions (manual or auto-generated)
    - English captions
    - Any other language captions
    - Hinglish (mixed language) queries work because the embedding model is multilingual
    """

    def __init__(self):
        cfg = CHUNKING.get("youtube", {"size": 200, "overlap": 30})
        self.chunk_size = cfg["size"]    # words per chunk
        self.overlap = cfg["overlap"]    # word overlap between chunks

    def ingest(self, source_path: str) -> List[Chunk]:
        """
        source_path is the YouTube URL.
        """
        url = source_path.strip()
        video_id = _extract_video_id(url)
        if not video_id:
            raise ValueError(f"Could not extract video ID from URL: {url}")

        print(f"[YouTube] Fetching transcript for video ID: {video_id}")
        full_text, language_code = _fetch_transcript(video_id)

        if not full_text.strip():
            raise RuntimeError(
                f"Transcript is empty for video {video_id}. "
                "The video may not have captions enabled."
            )

        print(f"[YouTube] Transcript fetched — language: {language_code}, "
              f"length: {len(full_text.split())} words")

        # Fetch title (best-effort, non-blocking on failure)
        try:
            title = _get_video_title(video_id)
        except Exception:
            title = f"youtube_{video_id}"

        print(f"[YouTube] Video title: {title}")

        chunks = self._make_chunks(full_text, url, video_id, title, language_code)
        print(f"[YouTube] Created {len(chunks)} chunks")
        return chunks

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _make_chunks(
        self,
        transcript: str,
        url: str,
        video_id: str,
        source_name: str,
        language_code: str,
    ) -> List[Chunk]:
        """Split transcript into overlapping word-based chunks."""
        raw_chunks = _chunk_transcript(transcript, self.chunk_size, self.overlap)
        ingested_at = datetime.utcnow().isoformat()
        chunks = []
        for idx, chunk_text in enumerate(raw_chunks):
            if not chunk_text.strip():
                continue
            chunks.append(Chunk(
                text=chunk_text,
                source_type="youtube",
                source_name=source_name,
                metadata={
                    "video_url": url,
                    "video_id": video_id,
                    "video_title": source_name,
                    "chunk_index": idx,
                    "language": language_code,
                    "ingested_at": ingested_at,
                }
            ))
        return chunks
