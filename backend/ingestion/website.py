"""
Website RAG Ingester
====================
Crawls a full website using Crawl4AI and indexes every page into the vector store.

Strategy:
1. Fetch sitemap.xml / sitemap_index.xml / robots.txt to discover all URLs
2. Crawl each URL using Crawl4AI (async, headless Chromium) to get clean text
3. Aggressively clean all markdown artifacts, HTML tags, URLs, and noise
4. Chunk clean text and return Chunk objects for embedding

Production-level cleaning:
- Strip all markdown syntax (links, images, headers, bold, italic, code fences)
- Strip residual HTML tags and entities
- Strip bare URLs and base64 data
- Remove nav/footer/cookie noise lines
- Deduplicate identical chunks across pages (hash-based)
- Minimum word count enforced per chunk (>= 15 words)
- Unicode NFC normalization
- Smart sentence-boundary chunking with overlap
"""

import asyncio
import hashlib
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Optional, Set, Tuple, Dict, Any
from urllib.parse import urlparse

import httpx

from backend.config import CHUNKING, AI_PARSER
from backend.ingestion.base import BaseIngester, Chunk

# ---------------------------------------------------------------------------
# Optional dependency: crawl4ai
# ---------------------------------------------------------------------------
try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    CRAWL4AI_AVAILABLE = True
except ImportError:
    CRAWL4AI_AVAILABLE = False
    print("[WARN] crawl4ai not installed - falling back to httpx+html2text for website crawling.")

try:
    import html2text
    HTML2TEXT_AVAILABLE = True
except ImportError:
    HTML2TEXT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_PAGES_DEFAULT  = 200
CONCURRENT_CRAWLS  = 5
CRAWL_DELAY_S      = 0.3
REQUEST_TIMEOUT    = 20
MIN_WORDS_PER_CHUNK = 15    # chunks with fewer words are discarded
MIN_CHUNK_CHARS    = 80     # absolute minimum chars

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemap/sitemap.xml",
    "/sitemaps/sitemap.xml",
    "/wp-sitemap.xml",
    "/sitemap.php",
    "/sitemap.txt",
]

SKIP_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".mp4", ".mp3", ".wav", ".zip", ".tar", ".gz", ".exe", ".dmg",
    ".css", ".js", ".mjs", ".woff", ".woff2", ".ttf", ".otf", ".ico",
    ".xml", ".json", ".yaml", ".yml",
}

# Lines matching these patterns are pure noise - discard entirely
_NOISE_LINE_PATTERNS = [
    re.compile(r"^\s*$"),                                          # blank
    re.compile(r"^(home|menu|nav|skip to|toggle|search|close|open|back|next|previous)\b", re.I),
    re.compile(r"^\s*(cookie|accept all|accept cookies|privacy policy|terms of service|copyright|all rights reserved)\s*$", re.I),
    re.compile(r"^\s*[\|\-\*\_\=\#\~]{3,}\s*$"),                 # horizontal rules / dividers
    re.compile(r"^\s*[\|\-\*\_\=\#\~]{3,}\s*$"),                 # horizontal rules / dividers
    re.compile(r"^\s*\[.*?\]\s*$"),                               # lone markdown link labels
    re.compile(r"^https?://\S+$"),                                # bare URLs
    re.compile(r"^\s*!\[.*?\]\(.*?\)\s*$"),                      # standalone markdown images
    re.compile(r"^(\s*[>\*\-\+]\s*){1,3}$"),                    # lone list bullets
    re.compile(r"^\s*\d+\s*$"),                                   # lone numbers (pagination)
]


class WebsiteIngester(BaseIngester):
    """
    Ingest an entire website for RAG.
    Produces clean, embedding-ready text chunks with zero HTML/markdown noise.
    """

    def __init__(
        self,
        max_pages: int = MAX_PAGES_DEFAULT,
        same_domain_only: bool = True,
        include_path_prefix: Optional[str] = None,
        use_ai_parser: bool = True,
    ):
        self.max_pages = max_pages
        self.same_domain_only = same_domain_only
        self.include_path_prefix = include_path_prefix
        cfg = CHUNKING.get("website", {"size": 800, "overlap": 100})
        self.chunk_size = cfg["size"]
        self.overlap = cfg["overlap"]
        self.use_ai_parser = use_ai_parser and AI_PARSER.get("enabled", True)
        self._ai_parser = None

    # ------------------------------------------------------------------
    # Public entry point (sync wrapper required by BaseIngester)
    # ------------------------------------------------------------------

    def ingest(self, source_path: str) -> List[Chunk]:
        url = source_path.strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        import concurrent.futures
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, self._run(url))
                    return future.result()
            else:
                return loop.run_until_complete(self._run(url))
        except RuntimeError:
            return asyncio.run(self._run(url))

    # ------------------------------------------------------------------
    # Async pipeline
    # ------------------------------------------------------------------

    async def _run(self, root_url: str) -> List[Chunk]:
        parsed = urlparse(root_url)
        base_domain = parsed.netloc
        print("[Website] ═══════════════════════════════════════════")
        print(f"[Website] Starting crawl: {root_url}")
        print(f"[Website] Max pages: {self.max_pages} | Domain: {base_domain}")
        print("[Website] ═══════════════════════════════════════════")

        urls = await self._discover_urls(root_url, base_domain)
        print(f"[Website] URL queue ({len(urls)} pages): crawling in order...")
        for i, u in enumerate(urls[:10]):
            print(f"[Website]   [{i+1}] {u}")
        if len(urls) > 10:
            print(f"[Website]   ... and {len(urls) - 10} more")

        if CRAWL4AI_AVAILABLE:
            all_chunks = await self._crawl_with_crawl4ai(urls, root_url)
        else:
            all_chunks = await self._crawl_with_httpx(urls, root_url)

        # Global deduplication across all pages
        before = len(all_chunks)
        all_chunks = self._deduplicate_chunks(all_chunks)
        print("[Website] ───────────────────────────────────────────")
        print(f"[Website] Done! Pages crawled: {len(urls)}")
        print(f"[Website] Chunks before dedup: {before} | After: {len(all_chunks)}")
        print("[Website] ═══════════════════════════════════════════")
        return all_chunks

    # ------------------------------------------------------------------
    # URL discovery
    # ------------------------------------------------------------------

    async def _discover_urls(self, root_url: str, base_domain: str) -> List[str]:
        # Use an ordered dict to preserve insertion order with dedup
        # CRITICAL: root_url is inserted FIRST so max_pages=1 always crawls
        # the exact URL the user entered, not whatever sitemap lists first.
        from collections import OrderedDict
        discovered: "OrderedDict[str, None]" = OrderedDict()

        # Normalize root_url for canonical comparison
        parsed_root = urlparse(root_url)
        root_canonical = f"{parsed_root.scheme}://{parsed_root.netloc}{parsed_root.path}"

        # Step 1: Root URL goes in FIRST — always
        discovered[root_canonical] = None
        print(f"[Website] #1 priority (user URL): {root_canonical}")

        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "RAGBot/1.0 (+https://github.com/rag-everything)"},
        ) as client:
            sitemap_urls_found: List[str] = []

            # Step 2: Try known sitemap paths
            for path in SITEMAP_PATHS:
                sitemap_url = f"{parsed_root.scheme}://{parsed_root.netloc}{path}"
                try:
                    resp = await client.get(sitemap_url)
                    if resp.status_code == 200 and len(resp.text.strip()) > 50:
                        sitemap_urls_found.append(sitemap_url)
                        print(f"[Website] Sitemap found: {sitemap_url}")
                        break
                except Exception:
                    continue

            # Step 3: Fall back to robots.txt
            if not sitemap_urls_found:
                try:
                    robots_url = f"{parsed_root.scheme}://{parsed_root.netloc}/robots.txt"
                    resp = await client.get(robots_url)
                    if resp.status_code == 200:
                        for line in resp.text.splitlines():
                            if line.lower().startswith("sitemap:"):
                                sm_url = line.split(":", 1)[1].strip()
                                sitemap_urls_found.append(sm_url)
                                print(f"[Website] Sitemap from robots.txt: {sm_url}")
                except Exception:
                    pass

            # Step 4: Parse sitemaps — append after root_url
            for sm_url in sitemap_urls_found:
                urls_from_sitemap = await self._parse_sitemap(client, sm_url, base_domain)
                for u in urls_from_sitemap:
                    # Normalize and deduplicate
                    try:
                        p = urlparse(u)
                        canonical = f"{p.scheme}://{p.netloc}{p.path}"
                        if canonical not in discovered:
                            discovered[canonical] = None
                    except Exception:
                        pass

        # Step 5: Filter (preserving order — root_url stays at index 0)
        filtered = self._filter_urls(list(discovered.keys()), base_domain)

        print(f"[Website] Total unique URLs discovered: {len(filtered)}")
        if self.max_pages < len(filtered):
            print(f"[Website] Limiting to first {self.max_pages} pages (root URL is always #1)")

        return filtered[: self.max_pages]

    async def _parse_sitemap(
        self, client: httpx.AsyncClient, sitemap_url: str, base_domain: str, depth: int = 0
    ) -> Set[str]:
        urls: Set[str] = set()
        if depth > 3:
            return urls
        try:
            resp = await client.get(sitemap_url, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return urls
            content = resp.text.strip()

            if sitemap_url.endswith(".txt") or not content.startswith("<"):
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("http"):
                        urls.add(line)
                return urls

            try:
                root = ET.fromstring(content)
            except ET.ParseError:
                return urls

            tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

            if tag == "sitemapindex":
                for sitemap_elem in root.iter("{%s}sitemap" % SITEMAP_NS):
                    loc = sitemap_elem.findtext("{%s}loc" % SITEMAP_NS, "").strip()
                    if loc:
                        child_urls = await self._parse_sitemap(client, loc, base_domain, depth + 1)
                        urls.update(child_urls)
            else:
                for url_elem in root.iter("{%s}url" % SITEMAP_NS):
                    loc = url_elem.findtext("{%s}loc" % SITEMAP_NS, "").strip()
                    if loc:
                        urls.add(loc)
        except Exception as e:
            print(f"[Website] Sitemap parse error {sitemap_url}: {e}")
        return urls

    def _filter_urls(self, urls: List[str], base_domain: str) -> List[str]:
        seen: Set[str] = set()
        result: List[str] = []
        for url in urls:
            try:
                parsed = urlparse(url)
            except Exception:
                continue
            if parsed.scheme not in ("http", "https"):
                continue
            if self.same_domain_only and parsed.netloc != base_domain:
                continue
            if self.include_path_prefix and not parsed.path.startswith(self.include_path_prefix):
                continue
            path_lower = parsed.path.lower()
            if any(path_lower.endswith(ext) for ext in SKIP_EXTENSIONS):
                continue
            canonical = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                canonical += f"?{parsed.query}"
            if canonical in seen:
                continue
            seen.add(canonical)
            result.append(url)
        return result

    # ------------------------------------------------------------------
    # Crawling: Crawl4AI
    # ------------------------------------------------------------------

    async def _crawl_with_crawl4ai(self, urls: List[str], root_url: str) -> List[Chunk]:
        browser_cfg = BrowserConfig(headless=True, verbose=False)
        run_cfg = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            word_count_threshold=20,
            excluded_tags=["nav", "header", "footer", "script", "style", "aside",
                           "form", "button", "noscript", "iframe", "svg"],
            exclude_external_links=True,
            exclude_social_media_links=True,
            process_iframes=False,
            remove_overlay_elements=True,
        )

        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            semaphore = asyncio.Semaphore(CONCURRENT_CRAWLS)
            tasks = [
                self._crawl_one_crawl4ai_raw(
                    crawler,
                    url,
                    run_cfg,
                    semaphore,
                    page_index=i + 1,
                    page_total=len(urls),
                )
                for i, url in enumerate(urls)
            ]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        pages: List[Dict[str, Any]] = []
        for result in raw_results:
            if isinstance(result, dict):
                pages.append(result)
            elif isinstance(result, Exception):
                print(f"[Website] Crawl4AI task error: {result}")

        if self.use_ai_parser:
            return await self._pages_to_chunks_ai(pages, root_url)

        all_chunks: List[Chunk] = []
        for p in pages:
            clean = self._clean_text(p["raw"])
            if not clean:
                continue
            all_chunks.extend(self._text_to_chunks(clean, p["url"], root_url, p["title"]))
        return all_chunks

    async def _crawl_one_crawl4ai_raw(
        self,
        crawler,
        url,
        run_cfg,
        semaphore,
        page_index: int,
        page_total: int,
    ) -> Dict[str, Any]:
        async with semaphore:
            await asyncio.sleep(CRAWL_DELAY_S)
            result = await crawler.arun(url=url, config=run_cfg)
            if not result.success:
                print(f"[Website] ✗ FAILED : {url}")
                print(f"[Website]   Reason  : {result.error_message}")
                return {}
            raw = getattr(result, "fit_markdown", None) or result.markdown or ""
            if not raw.strip():
                print(f"[Website] ✗ EMPTY  : {url} (no content extracted)")
                return {}
            title = (getattr(result, "metadata", None) or {}).get("title", "") or url
            return {"url": url, "title": title, "raw": raw, "page_index": page_index, "page_total": page_total}

    # ------------------------------------------------------------------
    # Crawling: httpx + html2text fallback
    # ------------------------------------------------------------------

    async def _crawl_with_httpx(self, urls: List[str], root_url: str) -> List[Chunk]:
        all_chunks: List[Chunk] = []

        semaphore = asyncio.Semaphore(CONCURRENT_CRAWLS)
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "RAGBot/1.0 (page crawler)"},
        ) as client:
            tasks = [
                self._crawl_one_httpx_raw(
                    client,
                    url,
                    semaphore,
                    page_index=i + 1,
                    page_total=len(urls),
                )
                for i, url in enumerate(urls)
            ]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        pages: List[Dict[str, Any]] = []
        for result in raw_results:
            if isinstance(result, dict):
                pages.append(result)

        if self.use_ai_parser:
            return await self._pages_to_chunks_ai(pages, root_url)

        for p in pages:
            clean = self._clean_text(p["raw"])
            if not clean:
                continue
            all_chunks.extend(self._text_to_chunks(clean, p["url"], root_url, p["title"]))

        return all_chunks

    async def _crawl_one_httpx_raw(
        self,
        client,
        url,
        semaphore,
        page_index: int,
        page_total: int,
    ) -> Dict[str, Any]:
        async with semaphore:
            await asyncio.sleep(CRAWL_DELAY_S)
            resp = await client.get(url)
            if resp.status_code != 200:
                print(f"[Website] ✗ HTTP {resp.status_code}: {url}")
                return {}
            ct = resp.headers.get("content-type", "")
            if "text/html" not in ct and "text/plain" not in ct:
                print(f"[Website] ✗ SKIP (non-HTML content-type: {ct}): {url}")
                return {}
            html = resp.text
            raw = self._html_to_text(html)
            if not raw.strip():
                print(f"[Website] ✗ EMPTY  : {url} (no content extracted)")
                return {}
            title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            title = title_m.group(1).strip() if title_m else url
            return {"url": url, "title": title, "raw": raw, "page_index": page_index, "page_total": page_total}

    async def _pages_to_chunks_ai(self, pages: List[Dict[str, Any]], root_url: str) -> List[Chunk]:
        if not pages:
            return []
        if self._ai_parser is None:
            from backend.core.ai_parser import get_ai_parser
            self._ai_parser = get_ai_parser()

        rpm_limit = int(AI_PARSER.get("rpm_limit", 30))
        tpm_limit = int(AI_PARSER.get("tpm_limit", 30000))
        pages = [p for p in pages if p and p.get("raw")]
        if not pages:
            return []

        estimated = [self._ai_parser.estimate_request_tokens(self._clean_text(p["raw"])) for p in pages]
        all_chunks: List[Chunk] = []
        idx = 0
        total_pages = len(pages)
        while idx < total_pages:
            batch_pages: List[Dict[str, Any]] = []
            batch_sum = 0
            while idx < total_pages and len(batch_pages) < rpm_limit:
                t = estimated[idx]
                if batch_pages and (batch_sum + t) > tpm_limit:
                    break
                if not batch_pages and t > tpm_limit:
                    batch_pages.append(pages[idx])
                    batch_sum += t
                    idx += 1
                    break
                batch_pages.append(pages[idx])
                batch_sum += t
                idx += 1

            tasks = []
            for p in batch_pages:
                basic_clean = self._clean_text(p["raw"])
                tasks.append(
                    asyncio.to_thread(
                        self._ai_parser.parse_content,
                        basic_clean,
                        p.get("url", ""),
                        p.get("page_index"),
                        p.get("page_total"),
                    )
                )

            parsed_results = await asyncio.gather(*tasks, return_exceptions=True)
            for p, parsed in zip(batch_pages, parsed_results):
                url = p["url"]
                title = p["title"]
                if isinstance(parsed, Exception) or not parsed:
                    clean = self._clean_text(p["raw"])
                else:
                    clean = str(parsed)
                if not clean:
                    continue
                chunks = self._text_to_chunks(clean, url, root_url, title)
                word_count = len(clean.split())
                print(f"[Website] ✓ EMBEDDED: {url}")
                print(f"[Website]   Title   : {title[:80]}")
                print(f"[Website]   Words   : {word_count} | Chunks: {len(chunks)}")
                all_chunks.extend(chunks)

        return all_chunks

    def _html_to_text(self, html: str) -> str:
        """Convert raw HTML to plain text with no markdown artifacts."""
        if HTML2TEXT_AVAILABLE:
            h = html2text.HTML2Text()
            h.ignore_links = True        # CRITICAL: no [text](url) noise
            h.ignore_images = True       # no ![alt](src) noise
            h.ignore_emphasis = True     # no **bold** / *italic* noise
            h.ignore_tables = False
            h.body_width = 0
            h.skip_internal_links = True
            return h.handle(html)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&#\d+;", " ", text)
        text = re.sub(r"&[a-z]+;", " ", text)
        return text

    # ------------------------------------------------------------------
    # Content parsing (AI-powered with fallback)
    # ------------------------------------------------------------------

    def _parse_content(self, raw: str, url: str, page_index: int, page_total: int) -> str:
        """
        Parse raw scraped content into clean text.
        Uses AI parser (Groq Llama) when enabled, falls back to regex cleaning.
        """
        # First, always do basic cleaning
        basic_clean = self._clean_text(raw)
        
        if not self.use_ai_parser:
            return basic_clean
        
        # Try AI parsing
        try:
            if self._ai_parser is None:
                from backend.core.ai_parser import get_ai_parser
                self._ai_parser = get_ai_parser()
            
            ai_result = self._ai_parser.parse_content(
                basic_clean,
                url,
                page_index=page_index,
                page_total=page_total,
            )
            if ai_result:
                return ai_result
        except Exception as e:
            print(f"[Website] AI parser error, using fallback: {e}")
        
        # Fallback to basic cleaning
        return basic_clean

    # ------------------------------------------------------------------
    # Text cleaning pipeline (regex-based fallback)
    # ------------------------------------------------------------------

    def _clean_text(self, raw: str) -> str:
        """
        Aggressively clean markdown/HTML output into pure, embedding-ready prose.
        Order matters: each step assumes previous steps have run.
        """
        text = unicodedata.normalize("NFC", raw)

        # 1. Strip base64 embedded data (images in markdown)
        text = re.sub(r"!\[[^\]]*\]\(data:[^)]+\)", "", text)

        # 2. Strip markdown images: ![alt](url) -> alt text only
        text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)

        # 3. Strip markdown links: [text](url) -> text only
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)

        # 4. Strip reference-style links: [text][ref] -> text only
        text = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", text)

        # 5. Strip bare markdown link references: [ref]: url
        text = re.sub(r"^\s*\[[^\]]+\]:\s*https?://\S+.*$", "", text, flags=re.M)

        # 6. Strip markdown headers (## Title -> Title)
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)

        # 7. Strip markdown bold/italic: **text** -> text, *text* -> text
        text = re.sub(r"\*{2,3}([^*]+)\*{2,3}", r"\1", text)
        text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
        text = re.sub(r"_{2,3}([^_]+)_{2,3}", r"\1", text)
        text = re.sub(r"_([^_\n]+)_", r"\1", text)

        # 8. Strip inline code: `code` -> code
        text = re.sub(r"`([^`\n]+)`", r"\1", text)

        # 9. Strip fenced code blocks entirely (they're rarely useful for prose RAG)
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"~~~[\s\S]*?~~~", "", text)

        # 10. Strip markdown horizontal rules
        text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.M)

        # 11. Strip blockquotes: > text -> text
        text = re.sub(r"^>\s*", "", text, flags=re.M)

        # 12. Strip list markers: - item / * item / 1. item -> item
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.M)

        # 13. Strip bare URLs (http://... with no surrounding text context)
        text = re.sub(r"https?://[^\s\)\"\'<>]+", "", text)

        # 14. Strip residual HTML tags (in case crawl4ai leaves some)
        text = re.sub(r"<[^>]{0,200}>", " ", text)

        # 15. Strip HTML entities
        text = re.sub(r"&[a-zA-Z]{2,8};", " ", text)
        text = re.sub(r"&#\d{1,6};", " ", text)

        # 16. Strip excessive punctuation runs (----, ====, ....., ~~~~)
        text = re.sub(r"[=\-~.]{4,}", " ", text)

        # 17. Strip lines that are pure noise
        lines = text.split("\n")
        clean_lines = []
        for line in lines:
            stripped = line.strip()
            if any(p.search(stripped) for p in _NOISE_LINE_PATTERNS):
                continue
            clean_lines.append(stripped)

        text = "\n".join(clean_lines)

        # 18. Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)

        # 19. Fix spacing around punctuation
        text = re.sub(r" {2,}", " ", text)

        return text.strip()

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def _text_to_chunks(
        self, text: str, page_url: str, root_url: str, title: str
    ) -> List[Chunk]:
        """Split clean text into semantically coherent, overlap-based chunks."""
        if len(text) < MIN_CHUNK_CHARS:
            return []

        chunks: List[Chunk] = []
        start = 0
        chunk_idx = 0
        now = datetime.now(timezone.utc).isoformat()

        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end]

            # Prefer natural break points
            if end < len(text):
                for boundary in ["\n\n", "\n", ". ", "! ", "? "]:
                    pos = chunk_text.rfind(boundary)
                    if pos > self.chunk_size // 2:
                        chunk_text = chunk_text[: pos + len(boundary)]
                        break

            chunk_text = chunk_text.strip()

            # Quality gate: must have enough words and chars
            word_count = len(chunk_text.split())
            if word_count >= MIN_WORDS_PER_CHUNK and len(chunk_text) >= MIN_CHUNK_CHARS:
                chunks.append(Chunk(
                    text=chunk_text,
                    source_type="website",
                    source_name=root_url,
                    metadata={
                        "page_url": page_url,
                        "page_title": title[:200],
                        "chunk_index": chunk_idx,
                        "ingested_at": now,
                    },
                ))
                chunk_idx += 1

            advance = max(len(chunk_text) - self.overlap, 1)
            start += advance

            if chunk_idx > 5000:  # per-page safety cap
                break

        return chunks

    # ------------------------------------------------------------------
    # Global deduplication
    # ------------------------------------------------------------------

    def _deduplicate_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """Remove chunks with identical or near-identical text (e.g. shared headers/footers)."""
        seen_hashes: Set[str] = set()
        unique: List[Chunk] = []
        for chunk in chunks:
            # Hash first 300 chars (catches repeated headers/nav that sneak through)
            fingerprint = hashlib.md5(chunk.text[:300].encode("utf-8")).hexdigest()
            if fingerprint not in seen_hashes:
                seen_hashes.add(fingerprint)
                unique.append(chunk)
        removed = len(chunks) - len(unique)
        if removed:
            print(f"[Website] Deduplication removed {removed} duplicate chunks")
        return unique