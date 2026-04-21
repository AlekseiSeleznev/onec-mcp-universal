from __future__ import annotations

import time
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import JSONResponse

from .api_token import request_needs_api_token


@dataclass
class _Bucket:
    window_started_at: int
    count: int


class _FixedWindowLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}

    def reset(self) -> None:
        self._buckets = {}

    def allow(self, key: str, limit_per_minute: int) -> tuple[bool, int]:
        now = int(time.time())
        window = now // 60
        bucket = self._buckets.get(key)
        if bucket is None or bucket.window_started_at != window:
            self._buckets[key] = _Bucket(window_started_at=window, count=1)
            return True, 0
        if bucket.count >= limit_per_minute:
            retry_after = max(1, 60 - (now % 60))
            return False, retry_after
        bucket.count += 1
        return True, 0


def build_rate_limit_guard(
    *,
    enabled: bool,
    read_rpm: int,
    mutating_rpm: int,
    mutating_actions: set[str],
):
    class _RateLimitGuard:
        def __init__(self) -> None:
            self._limiter = _FixedWindowLimiter()

        def reset(self) -> None:
            self._limiter.reset()

        async def __call__(self, request: Request, call_next):
            if not enabled:
                return await call_next(request)

            path = request.url.path
            if path == "/health" or path == "/mcp" or path.startswith("/mcp/"):
                return await call_next(request)

            if not (
                path == "/dashboard"
                or path.startswith("/dashboard/")
                or path.startswith("/api/")
            ):
                return await call_next(request)

            is_mutating = request_needs_api_token(
                request,
                mutating_actions=mutating_actions,
            )
            route_family = "mutating" if is_mutating else "read"
            limit = mutating_rpm if is_mutating else read_rpm
            client_ip = request.client.host if request.client and request.client.host else "unknown"
            allowed, retry_after = self._limiter.allow(f"{client_ip}:{route_family}", max(1, limit))
            if allowed:
                return await call_next(request)

            return JSONResponse(
                {
                    "ok": False,
                    "error": "Rate limit exceeded.",
                    "route_family": route_family,
                    "retry_after": retry_after,
                },
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

    return _RateLimitGuard()
