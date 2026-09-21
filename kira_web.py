"""
KIRA Web Access Module — Search and browse the internet.

Provides web search and page reading capabilities using:
- DuckDuckGo for web search (free, no API key)
- Requests + BeautifulSoup for page fetching
"""

import re
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

try:
    from duckduckgo_search import DDGS
    DUCKDUCKGO_AVAILABLE = True
except ImportError:
    DUCKDUCKGO_AVAILABLE = False
    print("[WARNING] duckduckgo-search not installed. Install with: pip install duckduckgo-search")


def search_web(query: str, num_results: int = 5) -> list:
    """
    Search the web using DuckDuckGo.
    
    Args:
        query: Search query
        num_results: Number of results to return (default 5)
    
    Returns:
        List of search results with title, url, and snippet
    """
    if not DUCKDUCKGO_AVAILABLE:
        return [{"error": "duckduckgo-search not installed"}]
    
    try:
        print(f"[KIRA WEB] Searching: {query}")
        
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))
        
        # Format results
        formatted = []
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", "")
            })
        
        print(f"[KIRA WEB] Found {len(formatted)} results")
        return formatted
        
    except Exception as e:
        print(f"[KIRA WEB] Search error: {e}")
        return [{"error": str(e)}]


def fetch_webpage(url: str, max_length: int = 3000) -> dict:
    """
    Fetch and extract text content from a web page.
    
    Args:
        url: URL to fetch
        max_length: Maximum characters to extract (default 3000)
    
    Returns:
        Dictionary with title, url, and content
    """
    try:
        print(f"[KIRA WEB] Fetching: {url}")
        
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return {"error": "Invalid URL"}
        
        # Fetch page with timeout
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        
        # Extract text
        text = soup.get_text(separator=" ", strip=True)
        
        # Clean up whitespace
        text = re.sub(r"\s+", " ", text)
        
        # Extract title
        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
        
        # Truncate if too long
        if len(text) > max_length:
            text = text[:max_length] + "..."
        
        print(f"[KIRA WEB] Fetched {len(text)} characters")
        
        return {
            "title": title,
            "url": url,
            "content": text
        }
        
    except requests.exceptions.Timeout:
        return {"error": "Request timed out"}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}
    except Exception as e:
        print(f"[KIRA WEB] Fetch error: {e}")
        return {"error": str(e)}


def search_and_summarize(query: str) -> str:
    """
    Search the web and return a formatted summary of results.
    
    Args:
        query: Search query
    
    Returns:
        Formatted string with search results
    """
    results = search_web(query, num_results=3)
    
    if not results or "error" in results[0]:
        return f"I couldn't search the web: {results[0].get('error', 'Unknown error')}"
    
    # Format results
    summary_parts = [f"Here's what I found for '{query}':\n"]
    
    for i, result in enumerate(results, 1):
        summary_parts.append(f"{i}. **{result['title']}**")
        summary_parts.append(f"   {result['snippet']}")
        summary_parts.append(f"   Source: {result['url']}\n")
    
    return "\n".join(summary_parts)
