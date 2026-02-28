import os
import json
from typing import Any, Optional, List

import httpx


class UpstashRedisError(RuntimeError):
    pass


class UpstashRedis:
    def __init__(self):
        self.rest_url: Optional[str] = None
        self.rest_token: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    def _refresh_config(self) -> None:
        if not self.rest_url:
            self.rest_url = os.getenv("UPSTASH_REDIS_REST_URL")
        if not self.rest_token:
            self.rest_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

    def is_configured(self) -> bool:
        self._refresh_config()
        return bool(self.rest_url and self.rest_token)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def command(self, args: List[Any]) -> Any:
        if not self.is_configured():
            raise UpstashRedisError("Upstash Redis is not configured")

        client = self._get_client()
        resp = await client.post(
            self.rest_url,
            headers={"Authorization": f"Bearer {self.rest_token}"},
            content=json.dumps(args),
        )
        resp.raise_for_status()
        payload = resp.json()

        if isinstance(payload, dict) and payload.get("error"):
            raise UpstashRedisError(str(payload.get("error")))

        if isinstance(payload, dict) and "result" in payload:
            return payload.get("result")

        return payload

    async def get(self, key: str) -> Optional[str]:
        res = await self.command(["GET", key])
        return res

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        raw = json.dumps(value)
        await self.command(["SET", key, raw, "EX", int(ttl_seconds)])

    async def incr(self, key: str) -> int:
        res = await self.command(["INCR", key])
        return int(res)

    async def expire(self, key: str, ttl_seconds: int) -> None:
        await self.command(["EXPIRE", key, int(ttl_seconds)])

    async def delete(self, key: str) -> None:
        await self.command(["DEL", key])
