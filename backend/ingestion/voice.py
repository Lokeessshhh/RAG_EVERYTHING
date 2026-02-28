"""
Voice RAG Ingester
==================
Transcribes audio/voice recordings using the SpeechRecognition library
(Google Web Speech API) — no Whisper, no local AI model required.

Supports:
- Languages: English (en-US, en-IN) and Hindi (hi-IN)
- Input formats: WAV, MP3, OGG, FLAC, M4A, WEBM, MP4 (audio)
- Input types: uploaded files OR raw audio bytes from browser recorder

Pipeline:
1. Validate audio file (format, size)
2. Convert to WAV 16kHz mono (required by SpeechRecognition)
3. Split into segments (Google STT has 60s limit per request)
4. Transcribe each segment (EN + HI in parallel attempts)
5. NFC normalize (fixes Hindi matras)
6. Chunk transcript for embedding
"""

import io
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
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    print("[WARN] SpeechRecognition not installed — voice ingestion unavailable.")

try:
    import av as _av
    AV_AVAILABLE = True
except ImportError:
    AV_AVAILABLE = False
    print("[WARN] PyAV not installed — only WAV files supported. Run: pip install av")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SUPPORTED_AUDIO_FORMATS = {
    ".wav", ".mp3", ".ogg", ".flac", ".m4a",
    ".webm", ".mp4", ".aac", ".opus", ".weba",
}
MAX_AUDIO_SIZE_BYTES = 100 * 1024 * 1024   # 100 MB
SEGMENT_DURATION_MS  = 55_000              # 55 seconds (Google STT limit is 60s)
SEGMENT_OVERLAP_MS   = 2_000              # 2s overlap between segments
SAMPLE_RATE          = 16_000             # 16kHz — required by Google STT
TARGET_CHANNELS      = 1                  # Mono

# Google Speech API language codes
LANG_EN_US = "en-US"
LANG_EN_IN = "en-IN"    # Indian English accent
LANG_HI_IN = "hi-IN"    # Hindi (India)

# Transcription retry settings
MAX_RETRIES = 3
RETRY_PAUSE_S = 1.0


class VoiceIngester(BaseIngester):
    """
    Ingest voice/audio recordings for RAG.

    Uses Google Web Speech API via SpeechRecognition library.
    No local model required — internet connection needed.

    Detects language automatically:
    - Tries English first, then Hindi
    - Uses the result with more recognized words
    - Falls back to Hindi-only if English produces garbage
    """

    def __init__(self, language: str = "auto"):
        """
        language: "auto" | "en" | "hi" | "en+hi"
        """
        self.language = language
        cfg = CHUNKING.get("voice", {"size": 400, "overlap": 60})
        self.chunk_size = cfg["size"]
        self.overlap = cfg["overlap"]

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def ingest(self, source_path: str) -> List[Chunk]:
        """
        Ingest an audio file. source_path = absolute path to audio file.
        """
        if not SR_AVAILABLE:
            raise RuntimeError(
                "SpeechRecognition library not installed. "
                "Run: pip install SpeechRecognition"
            )

        path = Path(source_path)
        error = self._validate_audio(path)
        if error:
            raise ValueError(f"Audio validation failed: {error}")

        print(f"[Voice] Ingesting: {path.name} ({path.stat().st_size // 1024} KB)")

        # Convert to WAV segments
        segments_wav = self._load_and_segment(path)
        if not segments_wav:
            raise ValueError("Could not load or segment the audio file.")

        print(f"[Voice] Audio split into {len(segments_wav)} segment(s).")

        # Transcribe each segment
        transcript_parts: List[str] = []
        for idx, wav_bytes in enumerate(segments_wav):
            text = self._transcribe_segment(wav_bytes, idx + 1, len(segments_wav))
            if text:
                transcript_parts.append(text)

        if not transcript_parts:
            raise ValueError(
                "No speech could be recognized from the audio. "
                "Ensure the audio is clear and in English or Hindi."
            )

        # Join segments with natural punctuation
        full_transcript = " ".join(transcript_parts)
        full_transcript = unicodedata.normalize("NFC", full_transcript)
        full_transcript = self._clean_transcript(full_transcript)

        print(f"[Voice] Transcript: {len(full_transcript)} chars, {len(full_transcript.split())} words.")

        # Build chunks
        chunks = self._transcript_to_chunks(full_transcript, source_name=path.name)
        print(f"[Voice] Created {len(chunks)} chunks from '{path.name}'")
        return chunks

    # ------------------------------------------------------------------
    # Ingest from raw bytes (for browser MediaRecorder uploads)
    # ------------------------------------------------------------------

    def ingest_bytes(
        self,
        audio_bytes: bytes,
        filename: str = "voice_recording.webm",
        language: Optional[str] = None,
    ) -> List[Chunk]:
        """
        Ingest audio from raw bytes (e.g., browser MediaRecorder output).
        Writes to a temp file then delegates to ingest().
        """
        import tempfile, shutil
        ext = Path(filename).suffix.lower() or ".webm"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            return self.ingest(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def ingest_transcript(
        self,
        transcript: str,
        source_name: str = "voice_recording",
    ) -> List[Chunk]:
        """
        Ingest a plain-text transcript (e.g. from browser Web Speech API).
        No audio file, no ffmpeg, no pydub needed.
        """
        if not transcript or not transcript.strip():
            raise ValueError("Transcript is empty — nothing to ingest.")

        text = unicodedata.normalize("NFC", transcript.strip())
        text = self._clean_transcript(text)

        print(f"[Voice] Transcript ingested: {len(text)} chars, {len(text.split())} words.")
        chunks = self._transcript_to_chunks(text, source_name=source_name)
        print(f"[Voice] Created {len(chunks)} chunks from '{source_name}'")
        return chunks

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_audio(self, path: Path) -> Optional[str]:
        if not path.exists():
            return f"File not found: {path}"

        ext = path.suffix.lower()
        if ext not in SUPPORTED_AUDIO_FORMATS:
            return (
                f"Unsupported format '{ext}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_AUDIO_FORMATS))}"
            )

        size = path.stat().st_size
        if size == 0:
            return "Audio file is empty."
        if size > MAX_AUDIO_SIZE_BYTES:
            return f"File too large ({size // 1024 // 1024} MB). Max 100 MB."

        if not AV_AVAILABLE and ext != ".wav":
            return (
                f"PyAV not installed — only .wav files supported without it. "
                "Run: pip install av"
            )
        return None

    # ------------------------------------------------------------------
    # Audio loading + segmentation (PyAV — no system ffmpeg needed)
    # ------------------------------------------------------------------

    def _load_and_segment(self, path: Path) -> List[bytes]:
        """
        Decode any audio format using PyAV (bundles its own FFmpeg),
        resample to 16kHz mono, split into 55s WAV segments.
        Returns list of WAV byte strings ready for Google STT.
        """
        import wave, audioop, struct

        if not AV_AVAILABLE:
            # Fallback: raw WAV read only
            with open(path, "rb") as f:
                return [f.read()]

        try:
            import av
            container = av.open(str(path))
            audio_stream = next(s for s in container.streams if s.type == "audio")

            # Decode all frames → raw PCM s16 at 16kHz mono
            resampler = av.AudioResampler(
                format="s16",
                layout="mono",
                rate=SAMPLE_RATE,
            )

            all_samples = bytearray()
            for frame in container.decode(audio_stream):
                resampled = resampler.resample(frame)
                for rf in resampled:
                    all_samples.extend(bytes(rf.planes[0]))

            # Flush resampler
            for rf in resampler.resample(None):
                all_samples.extend(bytes(rf.planes[0]))

            container.close()

        except Exception as e:
            print(f"[Voice] PyAV decode error: {e}")
            return []

        if not all_samples:
            print("[Voice] PyAV: no audio samples decoded.")
            return []

        # Split into segments of SEGMENT_DURATION_MS ms (55s)
        bytes_per_ms = SAMPLE_RATE * 2 // 1000   # s16 = 2 bytes/sample, 16000 samples/sec
        segment_bytes = SEGMENT_DURATION_MS * bytes_per_ms
        overlap_bytes = SEGMENT_OVERLAP_MS * bytes_per_ms

        segments: List[bytes] = []
        start = 0
        total = len(all_samples)

        while start < total:
            end = min(start + segment_bytes, total)
            chunk_pcm = bytes(all_samples[start:end])
            wav_bytes = self._pcm_to_wav(chunk_pcm, SAMPLE_RATE)
            segments.append(wav_bytes)
            if end >= total:
                break
            start += segment_bytes - overlap_bytes

        print(f"[Voice] Decoded {total // (SAMPLE_RATE * 2):.1f}s audio → {len(segments)} segment(s)")
        return segments

    def _pcm_to_wav(self, pcm_bytes: bytes, sample_rate: int) -> bytes:
        """Wrap raw s16 mono PCM bytes into a proper WAV container."""
        import wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)   # s16 = 2 bytes
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def _transcribe_segment(
        self, wav_bytes: bytes, seg_num: int, total: int
    ) -> str:
        """
        Transcribe a single WAV segment using Google Web Speech API.
        Tries English and Hindi; returns the best result.
        """
        recognizer = sr.Recognizer()

        # Load WAV bytes into AudioData
        wav_file = io.BytesIO(wav_bytes)
        try:
            with sr.AudioFile(wav_file) as source:
                # Adjust for ambient noise (helps with quality)
                recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio_data = recognizer.record(source)
        except Exception as e:
            print(f"[Voice] Segment {seg_num}/{total}: AudioFile load error: {e}")
            return ""

        # Determine which languages to try
        if self.language == "en":
            langs_to_try = [LANG_EN_IN, LANG_EN_US]
        elif self.language == "hi":
            langs_to_try = [LANG_HI_IN]
        else:
            # auto or en+hi: try both, pick best
            langs_to_try = [LANG_EN_IN, LANG_HI_IN, LANG_EN_US]

        results: List[Tuple[str, int]] = []   # (text, word_count)

        for lang in langs_to_try:
            text = self._try_google_stt(recognizer, audio_data, lang, seg_num, total)
            if text:
                word_count = len(text.split())
                results.append((text, word_count))

        if not results:
            print(f"[Voice] Segment {seg_num}/{total}: No recognition result.")
            return ""

        # Pick result with most words (more complete transcription)
        best_text = max(results, key=lambda x: x[1])[0]
        print(f"[Voice] Segment {seg_num}/{total}: '{best_text[:80]}...' ({len(best_text.split())} words)")
        return best_text

    def _try_google_stt(
        self,
        recognizer: "sr.Recognizer",
        audio_data: "sr.AudioData",
        language: str,
        seg_num: int,
        total: int,
    ) -> str:
        """
        Attempt Google STT for a given language with retries.
        Returns transcribed text or empty string on failure.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                text = recognizer.recognize_google(
                    audio_data,
                    language=language,
                    show_all=False,
                )
                if text:
                    return text.strip()
            except sr.UnknownValueError:
                # Audio not recognizable in this language — not an error
                return ""
            except sr.RequestError as e:
                if attempt < MAX_RETRIES:
                    import time
                    time.sleep(RETRY_PAUSE_S * attempt)
                else:
                    print(f"[Voice] Google STT request error (lang={language}, seg={seg_num}/{total}): {e}")
                    return ""
            except Exception as e:
                print(f"[Voice] Unexpected STT error (lang={language}): {e}")
                return ""
        return ""

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    def _clean_transcript(self, text: str) -> str:
        """Clean up raw transcript text."""
        # Remove multiple spaces
        text = re.sub(r" {2,}", " ", text)
        # Remove multiple newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Capitalize first letter of sentences (English)
        # (Don't do this for Hindi as it doesn't have capitalization)
        text = text.strip()
        return text

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def _transcript_to_chunks(self, transcript: str, source_name: str) -> List[Chunk]:
        """Split transcript into overlapping chunks for embedding."""
        # Add a header for context
        header = f"Voice Recording Transcript: {source_name}\n\n"
        text = header + transcript

        # If the whole transcript fits in one chunk, just return it as-is
        if len(text) <= self.chunk_size:
            return [Chunk(
                text=text.strip(),
                source_type="voice",
                source_name=source_name,
                metadata={
                    "chunk_index": 0,
                    "ingested_at": self._get_timestamp(),
                    "language": self.language,
                    "transcription_engine": "google_web_speech",
                },
            )]

        chunks: List[Chunk] = []
        start = 0
        chunk_idx = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end]

            # Try to break at a natural sentence boundary
            if end < len(text):
                for boundary in [". ", "! ", "? ", "\n", ", "]:
                    last = chunk_text.rfind(boundary)
                    if last > self.chunk_size // 2:
                        chunk_text = chunk_text[:last + len(boundary)]
                        break

            chunk_text = chunk_text.strip()
            if len(chunk_text) >= 20:
                chunks.append(Chunk(
                    text=chunk_text,
                    source_type="voice",
                    source_name=source_name,
                    metadata={
                        "chunk_index": chunk_idx,
                        "ingested_at": self._get_timestamp(),
                        "language": self.language,
                        "transcription_engine": "google_web_speech",
                    },
                ))
                chunk_idx += 1

            # Advance by chunk_size minus overlap (never less than 1)
            advance = max(self.chunk_size - self.overlap, 1)
            start += advance

            if chunk_idx > 500:
                break

        return chunks