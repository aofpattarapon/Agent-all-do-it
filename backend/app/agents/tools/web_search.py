"""Web search tool for agents.

Uses a free DuckDuckGo HTML endpoint scraped via httpx. No API key required.
Best-effort and graceful on failure — returns an empty list when anything
goes wrong rather than raising.
"""

import html
import logging
import re

import httpx

logger = logging.getLogger(__name__)

_DDG_HTML_URL = "https://duckduckgo.com/html/"
_USER_AGENT = "Mozilla/5.0 (compatible; PixelDreamAgent/1.0)"

# DuckDuckGo HTML result anchors look like:
#   <a rel="nofollow" class="result__a" href="...">Title</a>
_RESULT_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET_RE = re.compile(
    r'<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    """Strip HTML tags and unescape entities."""
    return html.unescape(_TAG_RE.sub("", text)).strip()


def _extract_real_url(url: str) -> str:
    """DuckDuckGo wraps result URLs in a redirect (/l/?uddg=...). Unwrap it."""
    match = re.search(r"[?&]uddg=([^&]+)", url)
    if match:
        from urllib.parse import unquote

        return unquote(match.group(1))
    if url.startswith("//"):
        return f"https:{url}"
    return url


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web via DuckDuckGo HTML.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return.

    Returns:
        A list of dicts with ``title``, ``url`` and ``snippet`` keys.
        Returns an empty list on any failure.
    """
    if not query or not query.strip():
        return []

    try:
        async with httpx.AsyncClient(
            timeout=10.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        ) as client:
            response = await client.post(_DDG_HTML_URL, data={"q": query})
            response.raise_for_status()
            body = response.text
    except Exception as exc:
        logger.warning("web_search failed for query %r: %s", query, exc)
        return []

    results: list[dict] = []
    snippets = _SNIPPET_RE.findall(body)
    for idx, match in enumerate(_RESULT_RE.finditer(body)):
        if len(results) >= max_results:
            break
        title = _clean(match.group("title"))
        url = _extract_real_url(match.group("url"))
        snippet = _clean(snippets[idx]) if idx < len(snippets) else ""
        if not title or not url:
            continue
        results.append({"title": title, "url": url, "snippet": snippet})

    return results
