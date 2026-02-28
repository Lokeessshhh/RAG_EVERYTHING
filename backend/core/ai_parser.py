"""
AI Parser Module
================
Uses Groq's Llama model to parse raw scraped website data into clean,
structured content before embedding.

Rate Limits for meta-llama/llama-4-scout-17b-16e-instruct:
- 30 RPM (requests per minute)
- 1K TPM (tokens per minute)
- 30K TPD (tokens per day)
- 500K TPM (tokens per month)
"""

import os
import time
import threading
from typing import Optional

from backend.config import AI_PARSER


class AIParser:
    """
    Parse raw scraped content using Groq's Llama model.
    Handles rate limiting with exponential backoff retry.
    """

    def __init__(self):
        self._api_key = os.getenv("GROQ_API_KEY")
        if not self._api_key:
            raise RuntimeError("Missing GROQ_API_KEY environment variable")

        self._model = AI_PARSER["model"]
        self._max_tokens = AI_PARSER["max_tokens"]
        self._temperature = AI_PARSER["temperature"]

        # Rate limits from Groq for meta-llama/llama-4-scout-17b-16e-instruct
        self._rpm_limit = AI_PARSER["rpm_limit"]          # 30 requests per minute
        self._tpm_limit = AI_PARSER["tpm_limit"]          # 1K tokens per minute
        self._tpd_limit = AI_PARSER["tpd_limit"]          # 30K tokens per day

        # Rate limit tracking
        self._window_seconds = 60
        self._window_start = time.time()
        self._window_requests = 0
        self._window_tokens = 0
        self._daily_tokens = 0

        # Initialize Groq client lazily
        self._client = None

        self._budget_lock = threading.Lock()

    def _get_client(self):
        """Lazy initialization of Groq client."""
        if self._client is None:
            try:
                from groq import Groq
                self._client = Groq(api_key=self._api_key)
            except ImportError:
                raise RuntimeError("groq package not installed. Run: pip install groq")
        return self._client

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (roughly 4 chars per token)."""
        return max(1, len(text) // 4)

    def estimate_request_tokens(self, raw_content: str) -> int:
        """Estimate total tokens for a request (prompt/input + completion)."""
        if not raw_content:
            return self._max_tokens
        # Keep consistent with parse_content truncation logic.
        max_input_chars = 6000
        trimmed = raw_content[:max_input_chars]
        input_tokens = self._estimate_tokens(trimmed)
        return input_tokens + self._max_tokens

    def _sleep_with_jitter(self, seconds: float):
        """Sleep with small jitter to avoid thundering herd."""
        if seconds <= 0:
            return
        jitter = 0.05 * (1 + 0.1 * (time.time() % 1))
        time.sleep(seconds + jitter)

    def _wait_for_budget(self, estimated_tokens: int):
        """Wait if we've exceeded rate limits."""
        now = time.time()
        elapsed = now - self._window_start

        # Reset window if 60 seconds passed
        if elapsed >= self._window_seconds:
            self._window_start = time.time()
            self._window_requests = 0
            self._window_tokens = 0

        exceeds_rpm = (self._window_requests + 1) > self._rpm_limit
        exceeds_tpm = (self._window_tokens + estimated_tokens) > self._tpm_limit
        exceeds_tpd = (self._daily_tokens + estimated_tokens) > self._tpd_limit

        if not (exceeds_rpm or exceeds_tpm or exceeds_tpd):
            return

        # Determine wait reason
        if exceeds_tpd:
            wait_reason = "TPD (daily limit)"
            # For daily limit, we can't proceed - raise error
            raise RuntimeError(
                f"Daily token limit ({self._tpd_limit}) exceeded. "
                f"Used: {self._daily_tokens}. Please try again tomorrow."
            )
        else:
            wait_reason = "RPM" if exceeds_rpm else "TPM"
            sleep_for = (self._window_start + self._window_seconds) - now
            if sleep_for > 0:
                print(f"[AI Parser] Rate limit ({wait_reason}). Waiting {sleep_for:.2f}s...")
                self._sleep_with_jitter(sleep_for)

        # Reset window after waiting
        self._window_start = time.time()
        self._window_requests = 0
        self._window_tokens = 0

    def parse_content(
        self,
        raw_content: str,
        page_url: str = "",
        page_index: Optional[int] = None,
        page_total: Optional[int] = None,
    ) -> Optional[str]:
        """
        Parse raw scraped content into clean, structured text using AI.

        Args:
            raw_content: Raw text from web scraping (may contain noise, HTML artifacts, etc.)
            page_url: URL of the page (for context in prompt)

        Returns:
            Cleaned, structured text ready for embedding, or None if parsing fails
        """
        if not raw_content or not raw_content.strip():
            return None

        # Truncate if too long (keep within token limits)
        max_input_chars = 6000  # ~1500 tokens, leaving room for output
        if len(raw_content) > max_input_chars:
            raw_content = raw_content[:max_input_chars] + "\n...[truncated]"

        input_tokens = self._estimate_tokens(raw_content)
        estimated_tokens = input_tokens + self._max_tokens

        if page_index is not None and page_total is not None:
            print(
                f"[AI Parser] Page {page_index}/{page_total} | ~{input_tokens} input tokens + {self._max_tokens} output = ~{estimated_tokens} total"
            )
        else:
            print(f"[AI Parser] ~{input_tokens} input tokens + {self._max_tokens} output = ~{estimated_tokens} total")

        # Check budget + reserve budget (atomic)
        with self._budget_lock:
            try:
                self._wait_for_budget(estimated_tokens)
            except RuntimeError as e:
                print(f"[AI Parser] {e}")
                return None

            self._window_requests += 1
            self._window_tokens += estimated_tokens
            self._daily_tokens += estimated_tokens

        # Build prompt
        prompt = f"""You are a content parser. Your task is to extract and structure the main content from raw web page data.

Rules:
1. Remove ALL navigation, headers, footers, sidebars, ads, cookie notices
2. Remove ALL markdown syntax, HTML tags, URLs, and formatting artifacts
3. Keep ONLY the main article/page content
4. Structure the content with clear paragraphs
5. Preserve important information: titles, headings (as plain text), lists, tables
6. If content is garbage/noise, respond with "NO_VALID_CONTENT"
7. Do NOT add any commentary or explanations - just the cleaned content

Raw content from {page_url}:

{raw_content}

Cleaned content:"""

        client = self._get_client()

        # Retry logic with exponential backoff
        max_retries = 5
        base_backoff = 2.0

        for attempt in range(max_retries):
            try:
                completion = client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self._temperature,
                    max_completion_tokens=self._max_tokens,
                    top_p=1,
                    stream=False,
                )

                result = completion.choices[0].message.content
                if not result or result.strip() == "NO_VALID_CONTENT":
                    return None

                print(f"[AI Parser] ✓ Parsed: {page_url[:60]}...")
                return result.strip()

            except Exception as e:
                error_str = str(e).lower()

                # Check for rate limit errors
                if "429" in error_str or "rate limit" in error_str or "too many requests" in error_str:
                    backoff = base_backoff ** (attempt + 1)
                    print(f"[AI Parser] Rate limited. Backing off {backoff:.1f}s (attempt {attempt + 1}/{max_retries})")
                    self._sleep_with_jitter(backoff)
                    continue

                # Check for token limit errors
                if "token" in error_str and ("limit" in error_str or "exceed" in error_str):
                    print(f"[AI Parser] Token limit exceeded: {e}")
                    # Try with smaller input
                    if len(raw_content) > 3000:
                        return self.parse_content(raw_content[:3000], page_url)
                    return None

                # Other errors - retry once then give up
                if attempt < max_retries - 1:
                    print(f"[AI Parser] Error: {e}. Retrying...")
                    self._sleep_with_jitter(1.0)
                    continue

                print(f"[AI Parser] ✗ Failed after {max_retries} attempts: {e}")
                return None

        return None

    def parse_batch(self, contents: list[tuple[str, str]]) -> list[tuple[str, Optional[str]]]:
        """
        Parse multiple raw contents with rate limiting.

        Args:
            contents: List of (raw_content, page_url) tuples

        Returns:
            List of (page_url, parsed_content or None) tuples
        """
        results = []
        for i, (raw_content, page_url) in enumerate(contents):
            print(f"[AI Parser] Processing {i+1}/{len(contents)}: {page_url[:50]}...")
            parsed = self.parse_content(raw_content, page_url)
            results.append((page_url, parsed))

            # Small delay between requests to stay within RPM
            if i < len(contents) - 1:
                self._sleep_with_jitter(2.5)  # ~24 requests per minute

        return results


# Singleton instance
_ai_parser: Optional[AIParser] = None


def get_ai_parser() -> AIParser:
    """Get or create the AI parser singleton."""
    global _ai_parser
    if _ai_parser is None:
        _ai_parser = AIParser()
    return _ai_parser
