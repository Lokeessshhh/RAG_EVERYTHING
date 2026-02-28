from fastapi import HTTPException

from backend.core.upstash_redis import UpstashRedis


async def rate_limit_ip(
    *,
    redis: UpstashRedis,
    ip: str,
    limit: int,
    window_seconds: int,
    key_prefix: str = "rl:ip",
    enabled: bool = True,
) -> None:
    if not enabled or not redis.is_configured():
        return

    key = f"{key_prefix}:{ip}:{window_seconds}"

    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds)
    except Exception:
        return

    if count > limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
