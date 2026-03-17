"""
Browserless Client
==================
Cloud-based browser automation for scraping JS-rendered pages.

API Docs: https://www.browserless.io/docs/
"""

import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import httpx

# Browserless API configuration
BROWSERLESS_API_URL = "https://chrome.browserless.io"
BROWSERLESS_API_KEY = "2UACALckmhXD2j416821b260bb85ab3145cb713ef3809865e"


@dataclass
class ScrapeResult:
    """Result from a Browserless scrape operation."""
    success: bool
    html: str
    markdown: str = ""
    title: str = ""
    url: str = ""
    error_message: str = ""


class BrowserlessClient:
    """
    Async client for Browserless.io API.
    
    Provides methods for:
    - Scraping pages with JS rendering (content endpoint)
    - Taking screenshots
    - Generating PDFs
    """
    
    def __init__(
        self,
        api_key: str = BROWSERLESS_API_KEY,
        base_url: str = BROWSERLESS_API_URL,
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
    
    def _get_url(self, endpoint: str) -> str:
        """Build full URL with API token."""
        return f"{self.base_url}{endpoint}?token={self.api_key}"
    
    async def scrape(
        self,
        url: str,
        wait_for: Optional[str] = None,
        wait_timeout: int = 30000,
        user_agent: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ScrapeResult:
        """
        Scrape a URL and return rendered HTML.
        
        Args:
            url: Target URL to scrape
            wait_for: CSS selector to wait for before returning
            wait_timeout: Max wait time in ms
            user_agent: Custom user agent
            headers: Additional request headers
            
        Returns:
            ScrapeResult with html, title, and status
        """
        endpoint = "/content"
        
        payload: Dict[str, Any] = {
            "url": url,
        }
        
        # waitForSelector must be an object with selector property
        if wait_for:
            payload["waitForSelector"] = {
                "selector": wait_for,
                "timeout": wait_timeout or 30000,
            }
        elif wait_timeout:
            payload["waitForTimeout"] = wait_timeout
        if user_agent:
            payload["userAgent"] = user_agent
        if headers:
            payload["headers"] = headers
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self._get_url(endpoint),
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                
                if response.status_code == 200:
                    html = response.text
                    # Extract title from HTML
                    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
                    title = title_match.group(1).strip() if title_match else url
                    
                    return ScrapeResult(
                        success=True,
                        html=html,
                        title=title,
                        url=url,
                    )
                else:
                    return ScrapeResult(
                        success=False,
                        html="",
                        url=url,
                        error_message=f"HTTP {response.status_code}: {response.text[:200]}",
                    )
                    
        except Exception as e:
            return ScrapeResult(
                success=False,
                html="",
                url=url,
                error_message=str(e),
            )
    
    async def scrape_markdown(
        self,
        url: str,
        wait_for: Optional[str] = None,
        wait_timeout: int = 30000,
        exclude_selectors: Optional[List[str]] = None,
    ) -> ScrapeResult:
        """
        Scrape a URL and return content converted to markdown-like text.
        
        Fetches HTML and cleans it client-side (removing nav, footer, etc.)
        """
        # Use content endpoint and strip HTML client-side
        result = await self.scrape(
            url=url,
            wait_for=wait_for,
            wait_timeout=wait_timeout,
        )
        
        if result.success and result.html:
            # Convert HTML to clean text (with exclusions)
            clean_text = self._html_to_clean_text(result.html, exclude_selectors)
            result.markdown = clean_text
        
        return result
    
    def _html_to_clean_text(self, html: str, extra_exclude: Optional[List[str]] = None) -> str:
        """Convert HTML to clean, readable text, removing noise elements."""
        import re
        
        text = html
        
        # Default elements to remove (nav, footer, etc.)
        exclude_tags = ["script", "style", "nav", "footer", "header", "aside",
                       "noscript", "iframe", "svg", "form", "button"]
        
        # Remove excluded tags
        for tag in exclude_tags:
            text = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", text, flags=re.I | re.S)
        
        # Remove extra selectors if provided (class/ID based)
        # Note: Complex CSS selectors are handled by the cleaning pipeline in website.py
        
        
        # Remove all remaining HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        
        # Decode HTML entities
        import html as html_module
        text = html_module.unescape(text)
        
        # Clean whitespace
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n\s*\n", "\n\n", text)
        
        return text.strip()
    
    async def screenshot(
        self,
        url: str,
        full_page: bool = True,
        format: str = "png",
    ) -> Optional[bytes]:
        """
        Take a screenshot of a URL.
        
        Returns:
            Image bytes or None on failure
        """
        endpoint = "/screenshot"
        
        payload = {
            "url": url,
            "options": {
                "fullPage": full_page,
                "type": format,
            },
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self._get_url(endpoint),
                    json=payload,
                )
                
                if response.status_code == 200:
                    return response.content
                return None
        except Exception:
            return None


# Singleton client instance
_client: Optional[BrowserlessClient] = None


def get_browserless_client() -> BrowserlessClient:
    """Get or create the Browserless client singleton."""
    global _client
    if _client is None:
        _client = BrowserlessClient()
    return _client


async def fetch_html_browserless(url: str, wait_seconds: int = 5) -> Optional[str]:
    """
    Convenience function to fetch HTML from a URL using Browserless.
    
    Args:
        url: URL to fetch
        wait_seconds: Seconds to wait for JS to render
        
    Returns:
        HTML string or None if failed
    """
    client = get_browserless_client()
    result = await client.scrape(
        url=url,
        wait_timeout=wait_seconds * 1000,
    )
    
    if result.success:
        return result.html
    else:
        print(f"[Browserless] Failed to fetch {url}: {result.error_message}")
        return None


async def fetch_clean_text_browserless(url: str, wait_seconds: int = 5) -> Optional[str]:
    """
    Convenience function to fetch clean text from a URL using Browserless.
    
    Args:
        url: URL to fetch
        wait_seconds: Seconds to wait for JS to render
        
    Returns:
        Clean text string or None if failed
    """
    client = get_browserless_client()
    result = await client.scrape_markdown(
        url=url,
        wait_timeout=wait_seconds * 1000,
    )
    
    if result.success:
        return result.markdown or result.html
    else:
        print(f"[Browserless] Failed to fetch {url}: {result.error_message}")
        return None
