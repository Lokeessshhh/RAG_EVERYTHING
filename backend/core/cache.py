import json
import hashlib
import os
from typing import Any, Awaitable, Callable

from backend.core.upstash_redis import UpstashRedis


DEFAULT_TTL_SECONDS = 3600


def make_cache_key(prefix: str, raw: str) -> str:
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


async def cache_get_or_set(
    *,
    redis: UpstashRedis,
    key: str,
    fetch: Callable[[], Awaitable[Any]],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    enabled: bool = True,
) -> Any:
    debug = os.getenv("CACHE_DEBUG") == "1"
    if not enabled or not redis.is_configured():
        if debug:
            print("[CACHE] bypass")
        return await fetch()

    try:
        cached = await redis.get(key)
        if cached is not None:
            if debug:
                print("[CACHE] hit")
            return json.loads(cached)
        if debug:
            print("[CACHE] miss")
    except Exception:
        if debug:
            print("[CACHE] error")
        return await fetch()

    data = await fetch()

    try:
        await redis.set_json(key, data, ttl_seconds=ttl_seconds)
    except Exception:
        pass

    return data
