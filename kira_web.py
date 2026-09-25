"""
KIRA Web Access Module — Search and browse the internet.

Provides web search and page reading capabilities with intelligent caching
to minimize redundant network requests and improve response times.

Uses:
- DuckDuckGo for web search (free, no API key)
- Requests + BeautifulSoup for page fetching

Shared knowledge (Supabase):
- Learned web research is ALWAYS stored locally first (kira_memory.db).
- Non-personal web research is ALSO shared to Supabase best-effort so
  several KIRA instances can reuse it.
- Personal data (conversations, names, preferences, tasks, private notes)
  never leaves the local database and is never passed to Supabase.
"""

import re
import hashlib
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

# Import caching
try:
    from kira_cache import web_cache
    CACHE_ENABLED = True
except ImportError:
    CACHE_ENABLED = False

# Shared knowledge base (Supabase) — non-personal web research only.
try:
    import kira_shared_memory
    SHARED_KNOWLEDGE_AVAILABLE = True
except ImportError:
    kira_shared_memory = None
    SHARED_KNOWLEDGE_AVAILABLE = False

try:
    from duckduckgo_search import DDGS
    DUCKDUCKGO_AVAILABLE = True
except ImportError:
    DUCKDUCKGO_AVAILABLE = False
    print("[WARNING] duckduckgo-search not installed. Install with: pip install duckduckgo-search")


def shared_knowledge_available() -> bool:
    """True when the Supabase shared knowledge base is configured and usable."""
    return bool(
        SHARED_KNOWLEDGE_AVAILABLE
        and kira_shared_memory is not None
        and kira_shared_memory.is_enabled()
    )


def _share_to_supabase(
    kind: str,
    topic: str,
    title: str,
    content: str,
    source_url: str = "",
    tags=None,
) -> bool:
    """
    Best-effort publish of learned web knowledge to the shared Supabase store.

    PRIVACY: only generic, non-personal web knowledge may be shared here.
    Conversations, names, preferences, tasks and private notes stay local
    (kira_memory.db) and must never be passed to this function. The shared
    memory module additionally refuses payloads that look personal.

    Returns True when the entry was shared, False otherwise. Failures are
    silent (logged) — local memory is always saved regardless.
    """
    if not shared_knowledge_available():
        return False

    try:
        shared = kira_shared_memory.save_shared_knowledge(
            kind=kind,
            topic=topic,
            content=content,
            title=title,
            source_url=source_url,
            tags=tags,
        )

        if shared:
            print(f"[KIRA WEB] Shared web knowledge to Supabase: [{kind}] {topic}")

        return bool(shared)

    except Exception as exc:
        print(f"[KIRA WEB] Supabase share skipped: {exc}")
        return False


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
    
    # Check cache first
    if CACHE_ENABLED:
        cache_key = f"search:{hashlib.md5(query.encode()).hexdigest()}:{num_results}"
        cached_result = web_cache.get(cache_key)
        if cached_result is not None:
            print(f"[KIRA WEB] Cache hit for search: {query}")
            return cached_result
    
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
        
        # Cache the results
        if CACHE_ENABLED:
            web_cache.set(cache_key, formatted, ttl=3600)  # 1 hour TTL
        
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
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return {"error": "Invalid URL"}
        
        # Check cache first
        if CACHE_ENABLED:
            cache_key = f"webpage:{hashlib.md5(url.encode()).hexdigest()}"
            cached_result = web_cache.get(cache_key)
            if cached_result is not None:
                print(f"[KIRA WEB] Cache hit for webpage: {url}")
                return cached_result
        
        print(f"[KIRA WEB] Fetching: {url}")
        
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
        
        result = {
            "title": title,
            "url": url,
            "content": text
        }
        
        # Cache the result
        if CACHE_ENABLED:
            web_cache.set(cache_key, result, ttl=3600)  # 1 hour TTL
        
        return result
        
    except requests.exceptions.Timeout:
        return {"error": "Request timed out"}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}
    except Exception as e:
        print(f"[KIRA WEB] Fetch error: {e}")
        return {"error": str(e)}


def search_and_summarize(query: str, store_memory: bool = False) -> str:
    """
    Search the web and return a formatted summary of results.
    
    Args:
        query: Search query
        store_memory: If True, store key information in KIRA's memory
    
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
    
    # Store in memory if requested
    if store_memory:
        try:
            import kira_memory
            # Create a concise memory entry
            memory_key = query.lower().replace(" ", "_")[:50]  # Limit key length
            memory_content = f"Web search results for '{query}': " + "; ".join([
                f"{r['title']} - {r['snippet'][:100]}" for r in results[:2]
            ])
            
            kira_memory.save_memory("web_knowledge", memory_key, memory_content)
            summary_parts.append("\n💾 I've saved this information to my memory for future reference.")
            print(f"[KIRA WEB] Stored search results in memory: {memory_key}")

            # 2. Also share this NON-personal web research to Supabase
            #    (best-effort; the local save above is never affected).
            if _share_to_supabase(
                kind="web_research",
                topic=memory_key,
                title=f"Web search results for '{query}'",
                content=memory_content,
                source_url=results[0].get("url", "") if results else "",
                tags=["web_search"],
            ):
                summary_parts.append(
                    "🌐 I've also shared this web research to the shared knowledge base."
                )
        except Exception as e:
            print(f"[KIRA WEB] Failed to store memory: {e}")
    
    return "\n".join(summary_parts)


def learn_from_url(url: str) -> str:
    """
    Fetch a web page and store key information in KIRA's memory.
    
    Args:
        url: URL to learn from
    
    Returns:
        Status message
    """
    try:
        import kira_memory
        
        # Fetch the page
        page_data = fetch_webpage(url, max_length=5000)
        
        if "error" in page_data:
            return f"I couldn't read that page: {page_data['error']}"
        
        # Extract key information
        title = page_data.get("title", "Untitled")
        content = page_data.get("content", "")
        
        # Create a summary (first 500 chars)
        summary = content[:500].strip()
        if len(content) > 500:
            summary += "..."
        
        # Store in memory
        memory_key = url.replace("https://", "").replace("http://", "").replace("/", "_")[:50]
        memory_content = f"Learned from {title} ({url}): {summary}"
        
        kira_memory.save_memory("web_knowledge", memory_key, memory_content)
        
        print(f"[KIRA WEB] Learned from {url} and stored in memory")

        # 2. Also share this NON-personal web knowledge to Supabase
        #    (best-effort; the local save above is never affected).
        shared = _share_to_supabase(
            kind="web_page",
            topic=memory_key,
            title=title,
            content=memory_content,
            source_url=url,
            tags=["web_page"],
        )

        if shared:
            return (
                f"I've read and memorized the content from '{title}'. I'll remember "
                "this for future conversations and shared it with the shared knowledge base."
            )

        return f"I've read and memorized the content from '{title}'. I'll remember this for future conversations."
        
    except Exception as e:
        print(f"[KIRA WEB] Learn from URL error: {e}")
        return f"I encountered an error while trying to learn from that page: {str(e)}"


def search_and_learn(query: str) -> str:
    """
    Search the web and automatically store key information in memory.
    
    Args:
        query: Search query
    
    Returns:
        Formatted string with search results and memory confirmation
    """
    return search_and_summarize(query, store_memory=True)


def search_shared_knowledge(query: str, limit: int = 5) -> str:
    """
    Search the shared (Supabase) knowledge base and return a text summary.

    This only READS shared knowledge — personal data such as conversations,
    names, preferences, tasks and private notes never leaves local memory.

    Args:
        query: Search query
        limit: Maximum number of shared entries to return

    Returns:
        Formatted string with shared results, or an explanatory message.
    """
    if not shared_knowledge_available():
        return (
            "The shared knowledge base is not configured. Add SUPABASE_URL and "
            "SUPABASE_ANON_KEY to your .env file (see .env.example)."
        )

    results = kira_shared_memory.search_shared_knowledge(query, limit=limit)

    if not results:
        return f"I found nothing in the shared knowledge base about '{query}'."

    lines = [f"Shared knowledge about '{query}':\n"]

    for index, item in enumerate(results, 1):
        topic = str(item.get("topic", "")).replace("_", " ").strip() or "entry"
        title = str(item.get("title", "")).strip()
        content = str(item.get("content", "")).strip()[:400]
        source_url = str(item.get("source_url", "")).strip()

        lines.append(f"{index}. **{title or topic}**")
        lines.append(f"   {content}")
        if source_url:
            lines.append(f"   Source: {source_url}")
        lines.append("")

    return "\n".join(lines)


def share_project_knowledge(topic: str, content: str, title: str = "", tags=None) -> str:
    """
    Share NON-personal project knowledge with the shared knowledge base.

    Personal notes must stay local (kira_memory.db). The shared memory module
    refuses payloads that look personal.

    Returns a status message.
    """
    if not shared_knowledge_available():
        return (
            "The shared knowledge base is not configured, so I kept this local. "
            "Add SUPABASE_URL and SUPABASE_ANON_KEY to your .env file to share it."
        )

    if _share_to_supabase(
        kind="project_knowledge",
        topic=topic,
        title=title or topic,
        content=content,
        tags=tags or ["project"],
    ):
        return f"I've shared that project knowledge about '{topic}' with the shared knowledge base."

    return (
        "I couldn't share that — it may look personal or private. "
        "I kept it in local memory instead."
    )
