"""
KIRA Cache Module - High-performance caching layer.

Provides in-memory caching with TTL (Time To Live) for expensive operations.
Reduces redundant processing and improves response times.
"""

import time
import threading
from typing import Any, Optional, Dict
from collections import OrderedDict


class LRUCache:
    """
    Thread-safe LRU (Least Recently Used) cache with TTL support.
    Automatically evicts old entries when capacity is reached.
    """

    def __init__(self, capacity: int = 1000, default_ttl: int = 3600):
        """
        Initialize cache.

        Args:
            capacity: Maximum number of items to store
            default_ttl: Default time-to-live in seconds (1 hour)
        """
        self.capacity = capacity
        self.default_ttl = default_ttl
        self.cache: OrderedDict = OrderedDict()
        self.expiry: Dict[str, float] = {}
        self.lock = threading.RLock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self.lock:
            if key not in self.cache:
                self.misses += 1
                return None

            # Check expiry
            if key in self.expiry and time.time() > self.expiry[key]:
                self.delete(key)
                self.misses += 1
                return None

            # Move to end (most recently used)
            self.cache.move_to_end(key)
            self.hits += 1
            return self.cache[key]

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        with self.lock:
            # Remove if exists (to update order)
            if key in self.cache:
                self.cache.move_to_end(key)
            else:
                # Evict oldest if at capacity
                if len(self.cache) >= self.capacity:
                    oldest_key = next(iter(self.cache))
                    self.delete(oldest_key)

            self.cache[key] = value

            # Set expiry
            if ttl is not None:
                self.expiry[key] = time.time() + ttl
            elif self.default_ttl > 0:
                self.expiry[key] = time.time() + self.default_ttl

    def delete(self, key: str) -> bool:
        """
        Delete item from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted, False if not found
        """
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                if key in self.expiry:
                    del self.expiry[key]
                return True
            return False

    def clear(self):
        """Clear all cached items."""
        with self.lock:
            self.cache.clear()
            self.expiry.clear()

    def cleanup_expired(self):
        """Remove all expired entries."""
        with self.lock:
            current_time = time.time()
            expired_keys = [
                key for key, expiry_time in self.expiry.items()
                if current_time > expiry_time
            ]
            for key in expired_keys:
                self.delete(key)

    def stats(self) -> dict:
        """Get cache statistics."""
        with self.lock:
            total = self.hits + self.misses
            hit_rate = (self.hits / total * 100) if total > 0 else 0
            return {
                "size": len(self.cache),
                "capacity": self.capacity,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": f"{hit_rate:.2f}%",
            }


# Global cache instances for different purposes
command_cache = LRUCache(capacity=500, default_ttl=300)  # 5 min for commands
web_cache = LRUCache(capacity=200, default_ttl=3600)     # 1 hour for web results
tts_cache = LRUCache(capacity=100, default_ttl=86400)    # 24 hours for TTS
memory_cache = LRUCache(capacity=1000, default_ttl=60)   # 1 min for memory lookups


def cached(cache_instance: LRUCache, key_func=None):
    """
    Decorator for caching function results.

    Args:
        cache_instance: LRUCache instance to use
        key_func: Optional function to generate cache key from args

    Example:
        @cached(web_cache)
        def search_web(query):
            # expensive operation
            return results
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Default: use function name + args
                cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

            # Try cache first
            result = cache_instance.get(cache_key)
            if result is not None:
                return result

            # Compute and cache
            result = func(*args, **kwargs)
            if result is not None:
                cache_instance.set(cache_key, result)

            return result
        return wrapper
    return decorator


# Periodic cleanup task
def start_cache_cleanup_thread(interval: int = 300):
    """
    Start background thread to periodically clean up expired cache entries.

    Args:
        interval: Cleanup interval in seconds (default 5 minutes)
    """
    def cleanup_loop():
        while True:
            time.sleep(interval)
            command_cache.cleanup_expired()
            web_cache.cleanup_expired()
            tts_cache.cleanup_expired()
            memory_cache.cleanup_expired()

    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()
    return thread
