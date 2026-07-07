import time
import logging
from collections import OrderedDict
from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger("mapus")

MAX_ENTRIES = 10000


class RateStore:
    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._store: OrderedDict[str, list[float]] = OrderedDict()
        self._max_entries = max_entries

    def check(self, key: str, max_req: int, window: float) -> bool:
        now = time.time()
        cutoff = now - window
        vals = self._store.get(key, [])
        vals = [t for t in vals if t > cutoff]
        if len(vals) >= max_req:
            return False
        vals.append(now)
        self._store[key] = vals
        self._evict_if_needed()
        return True

    def _evict_if_needed(self):
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)

    def cleanup_expired(self, window: float = 3600):
        now = time.time()
        cutoff = now - window
        stale = [k for k, v in self._store.items() if v and max(v) < cutoff]
        for k in stale:
            del self._store[k]


_rate_store = RateStore()

# Límites por IP: (clave, máx solicitudes, ventana en segundos).
# Los endpoints que consumen IA (chat, extracción, análisis) tienen límites
# más estrictos porque cada llamada cuesta cuota de Gemini.
_RATE_RULES: list[tuple[str, str, int, float]] = [
    ("/chat-assistant", "chat", 30, 60),
    ("/extract-file", "extract", 10, 60),
    ("/extract-file-async", "extract", 10, 60),
    ("/save-extracted", "save", 20, 60),
    ("/analisis-apu/upload", "analisis", 10, 60),
]


def _match_rate_rule(path: str) -> tuple[str, int, float] | None:
    for suffix, bucket, max_req, window in _RATE_RULES:
        if path.endswith(suffix):
            return bucket, max_req, window
    if path.endswith("/analizar") and "/analisis-apu/" in path:
        return "analisis", 10, 60
    return None


async def log_and_rate_limit(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    if request.method == "POST":
        rule = _match_rate_rule(request.url.path)
        if rule:
            bucket, max_req, window = rule
            if not _rate_store.check(f"{bucket}:{ip}", max_req, window):
                return JSONResponse(status_code=429, content={"detail": "Demasiadas solicitudes. Espera un momento."})
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    log.info("%s %s → %s (%.2fs)", request.method, request.url.path, response.status_code, elapsed)
    return response
