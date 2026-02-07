"""
Web browsing utility for VOID AI.

Provides web search and page fetching capabilities.
"""

import asyncio
import aiohttp
from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus
import re

import structlog

logger = structlog.get_logger()


class WebBrowser:
    """Web browsing utility for AI agent."""

    def __init__(self, timeout: int = 15):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    async def search_duckduckgo(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """
        Search DuckDuckGo for information.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of search results with title, url, snippet
        """
        try:
            # Use DuckDuckGo HTML search (no API key needed)
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status != 200:
                        logger.warning("duckduckgo_search_failed", status=response.status)
                        return []

                    html = await response.text()

                    # Parse results (simple regex-based parsing)
                    results = []

                    # Find result blocks
                    result_pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>([^<]+)</a>'
                    snippet_pattern = r'<a class="result__snippet"[^>]*>([^<]+(?:<[^>]+>[^<]+)*)</a>'

                    urls = re.findall(result_pattern, html)
                    snippets = re.findall(snippet_pattern, html)

                    for i, (url, title) in enumerate(urls[:max_results]):
                        snippet = snippets[i] if i < len(snippets) else ""
                        # Clean HTML from snippet
                        snippet = re.sub(r'<[^>]+>', '', snippet).strip()

                        results.append({
                            "title": title.strip(),
                            "url": url,
                            "snippet": snippet[:300]
                        })

                    logger.info("duckduckgo_search_complete", query=query, results=len(results))
                    return results

        except Exception as e:
            logger.error("duckduckgo_search_error", error=str(e))
            return []

    async def fetch_url(self, url: str, max_chars: int = 5000) -> Optional[str]:
        """
        Fetch and extract text content from a URL.

        Args:
            url: URL to fetch
            max_chars: Maximum characters to return

        Returns:
            Extracted text content or None
        """
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers=self.headers, allow_redirects=True) as response:
                    if response.status != 200:
                        logger.warning("url_fetch_failed", url=url, status=response.status)
                        return None

                    content_type = response.headers.get("Content-Type", "")
                    if "text/html" not in content_type and "text/plain" not in content_type:
                        logger.warning("url_not_text", url=url, content_type=content_type)
                        return None

                    html = await response.text()

                    # Extract text from HTML
                    text = self._extract_text_from_html(html)

                    if len(text) > max_chars:
                        text = text[:max_chars] + "..."

                    logger.info("url_fetched", url=url, chars=len(text))
                    return text

        except Exception as e:
            logger.error("url_fetch_error", url=url, error=str(e))
            return None

    def _extract_text_from_html(self, html: str) -> str:
        """Extract readable text from HTML."""
        # Remove script and style elements
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<head[^>]*>.*?</head>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)

        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        # Decode HTML entities
        import html as html_lib
        text = html_lib.unescape(text)

        return text

    async def search_and_summarize(self, query: str) -> str:
        """
        Search the web and return a summary of findings.

        Args:
            query: Search query

        Returns:
            Summary of search results
        """
        results = await self.search_duckduckgo(query, max_results=3)

        if not results:
            return f"No search results found for: {query}"

        summary_parts = [f"Search results for '{query}':\n"]

        for i, result in enumerate(results, 1):
            summary_parts.append(
                f"{i}. {result['title']}\n"
                f"   {result['snippet']}\n"
                f"   Source: {result['url'][:60]}...\n"
            )

        return "\n".join(summary_parts)


# Singleton instance
_browser: Optional[WebBrowser] = None


def get_web_browser() -> WebBrowser:
    """Get or create web browser instance."""
    global _browser
    if _browser is None:
        _browser = WebBrowser()
    return _browser


__all__ = ["WebBrowser", "get_web_browser"]
