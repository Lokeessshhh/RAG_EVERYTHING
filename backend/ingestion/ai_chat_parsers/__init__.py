"""
AI Chat Parsers Module
======================
Parsers for extracting conversations from AI chat share links.

Supported platforms:
- ChatGPT (chatgpt.com, chat.openai.com)
- Gemini (gemini.google.com)
- Claude (claude.ai)
- Grok (grok.com)
- Perplexity (perplexity.ai)

Each parser takes raw HTML and outputs a list of messages:
    [{role: "user" | "assistant", text: str}, ...]
"""

import os
import json
import subprocess
import tempfile
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse


# Platform detection based on domain
PLATFORM_DOMAINS = {
    "chatgpt": ["chatgpt.com", "chat.openai.com"],
    "gemini": ["gemini.google.com"],
    "claude": ["claude.ai"],
    "grok": ["grok.com"],
    "perplexity": ["perplexity.ai"],
}

# Parser script paths (relative to this module)
PARSER_SCRIPTS = {
    "chatgpt": "parse_chatgpt.js",
    "gemini": "parse_gemini.js",
    "claude": "parse_claude.js",
    "grok": "parse_grok.js",
    "perplexity": "parse_perplexity.js",
}


def detect_platform(url: str) -> Optional[str]:
    """
    Detect which AI platform a URL belongs to based on its domain.
    
    Args:
        url: The share URL to detect
        
    Returns:
        Platform name ("chatgpt", "gemini", "claude", "grok", "perplexity") or None
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove www. prefix if present
        if domain.startswith("www."):
            domain = domain[4:]
        
        for platform, domains in PLATFORM_DOMAINS.items():
            if domain in domains:
                return platform
        
        return None
    except Exception:
        return None


def get_parser_script(platform: str) -> Optional[str]:
    """Get the path to the parser script for a platform."""
    script_name = PARSER_SCRIPTS.get(platform)
    if not script_name:
        return None
    
    # Get the directory where this module is located
    module_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(module_dir, script_name)
    
    if os.path.exists(script_path):
        return script_path
    return None


async def fetch_html(url: str) -> Optional[str]:
    """
    Fetch HTML content from a URL.
    Uses crawl4ai (JS rendering) if available, falls back to httpx.
    
    Args:
        url: URL to fetch
        
    Returns:
        Raw HTML string or None if failed
    """
    import asyncio
    
    # Try crawl4ai with proper Windows handling (run sync in thread pool)
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
        
        print(f"[AI Chat Parser] Fetching with crawl4ai: {url}")
        
        # Run crawler in a separate process to avoid Windows asyncio issues
        loop = asyncio.get_event_loop()
        
        async def _crawl():
            browser_cfg = BrowserConfig(headless=True, verbose=False)
            run_cfg = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                wait_for_images=False,
                delay_before_return_html=5.0,
            )
            async with AsyncWebCrawler(config=browser_cfg) as crawler:
                result = await crawler.arun(url=url, config=run_cfg)
                return result
        
        # Use subprocess-friendly approach on Windows
        import sys
        if sys.platform == 'win32':
            # On Windows, create a new event loop in a thread
            import concurrent.futures
            import asyncio as aio
            
            def run_in_new_loop():
                new_loop = aio.new_event_loop()
                aio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(_crawl())
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = await loop.run_in_executor(pool, run_in_new_loop)
        else:
            result = await _crawl()
        
        if result and result.success:
            return result.html or ""
        else:
            error_msg = result.error_message if result else "Unknown error"
            print(f"[AI Chat Parser] crawl4ai failed: {error_msg}")
            
    except Exception as e:
        print(f"[AI Chat Parser] crawl4ai unavailable/failed ({e}). Falling back to httpx...")
    
    # Fallback to httpx with better headers
    import httpx
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }
    
    print(f"[AI Chat Parser] Fetching with httpx: {url}")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        try:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"[AI Chat Parser] httpx failed: {e}")
            return None


def run_js_parser(script_path: str, html: str) -> List[Dict[str, str]]:
    """
    Run a Node.js parser script on HTML content.
    
    Args:
        script_path: Path to the .js parser script
        html: Raw HTML content
        
    Returns:
        List of messages: [{"role": "user"|"assistant", "text": str}, ...]
    """
    # Write HTML to a temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        temp_html_path = f.name
    
    try:
        # Run the parser script
        result = subprocess.run(
            ["node", script_path, temp_html_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        
        if result.returncode != 0:
            print(f"[AI Chat Parser] Parser failed: {result.stderr}")
            return []
        
        # Parse JSON directly from stdout
        stdout = result.stdout.strip()
        if not stdout:
            print("[AI Chat Parser] Empty stdout from parser")
            return []
        
        # Try to parse as JSON
        try:
            messages = json.loads(stdout)
            return messages
        except json.JSONDecodeError as e:
            print(f"[AI Chat Parser] Failed to parse JSON: {e}")
            print(f"[AI Chat Parser] stdout preview: {stdout[:200]}")
            return []
        
    except subprocess.TimeoutExpired:
        print("[AI Chat Parser] Parser timed out")
        return []
    except Exception as e:
        print(f"[AI Chat Parser] Error running parser: {e}")
        return []
    finally:
        # Clean up temp file
        try:
            os.unlink(temp_html_path)
        except Exception:
            pass


async def parse_ai_chat(url: str) -> Tuple[Optional[str], List[Dict[str, str]]]:
    """
    Parse an AI chat conversation from a share URL.
    
    Detects the platform, fetches HTML, and runs the appropriate parser.
    
    Args:
        url: The share URL
        
    Returns:
        Tuple of (platform_name, messages) or (None, []) if failed
    """
    # Detect platform
    platform = detect_platform(url)
    if not platform:
        print(f"[AI Chat Parser] Unknown platform for URL: {url}")
        return None, []
    
    print(f"[AI Chat Parser] Detected platform: {platform}")
    
    # Get parser script
    script_path = get_parser_script(platform)
    if not script_path:
        print(f"[AI Chat Parser] No parser script found for platform: {platform}")
        return platform, []
    
    # Fetch HTML
    html = await fetch_html(url)
    if not html:
        print(f"[AI Chat Parser] Failed to fetch HTML from: {url}")
        return platform, []
    
    print(f"[AI Chat Parser] Fetched HTML: {len(html)} chars")
    
    # Run parser
    messages = run_js_parser(script_path, html)
    
    if messages:
        print(f"[AI Chat Parser] Parsed {len(messages)} messages from {platform}")
    else:
        print(f"[AI Chat Parser] No messages extracted from {platform}")
    
    return platform, messages


def messages_to_text(messages: List[Dict[str, str]], context_window: int = 2) -> str:
    """
    Convert parsed messages to a single text block for embedding.
    
    Each message includes context from previous messages for better retrieval.
    
    Markdown format:
        ## 👤 User (Turn 1)
        <user text>
        
        ## 🤖 Assistant (Turn 2)
        <assistant text>
    """
    if not messages:
        return ""
    
    lines = []
    
    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        text = msg.get("text", "")
        
        # Include context from previous messages
        context_parts = []
        start_idx = max(0, i - context_window)
        if start_idx < i:
            context_parts.append("**Previous context:**")
            for j in range(start_idx, i):
                prev_role = messages[j].get("role", "unknown")
                prev_text = messages[j].get("text", "")
                prev_label = "User" if prev_role == "user" else "Assistant"
                # Truncate long context
                if len(prev_text) > 300:
                    prev_text = prev_text[:300] + "..."
                context_parts.append(f"> **{prev_label}:** {prev_text}")
            context_parts.append("")
        
        if role == "user":
            lines.append(f"## 👤 User (Turn {i + 1})\n\n" + "\n".join(context_parts) + text)
        else:
            lines.append(f"## 🤖 Assistant (Turn {i + 1})\n\n" + "\n".join(context_parts) + text)
    
    return "\n\n---\n\n".join(lines)
