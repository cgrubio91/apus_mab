"""
Presentation: HTTP Middleware (Rate Limiter + Logging)
"""

import time
import logging
from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger("mapus")

_rate_store: dict[str, list[float]] = {}


def _check_rate(key: str, max_req: int, window: float) -> bool:
    now = time.time()
    cutoff = now - window
    vals = _rate_store.get(key, [])
    vals = [t for t in vals if t > cutoff]
    if len(vals) >= max_req:
        return False
    vals.append(now)
    _rate_store[key] = vals
    return True


async def log_and_rate_limit(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    if request.url.path == "/api/chat-assistant":
        if not _check_rate(f"chat:{ip}", 30, 60):
            return JSONResponse(status_code=429, content={"detail": "Demasiadas solicitudes. Espera un momento."})
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    log.info("%s %s → %s (%.2fs)", request.method, request.url.path, response.status_code, elapsed)
    return response
