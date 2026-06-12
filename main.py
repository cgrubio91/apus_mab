"""
MAPUS Core Engine & API — Entry Point
Delegates to Clean Architecture application in src/
"""

import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger("mapus")

# Backward compatibility: tests import `from main import app`
from src.presentation.main import app

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 10000))
    log.info("Starting MAPUS server on port %d", port)

    uvicorn.run(
        "src.presentation.main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENV", "").lower() == "development",
    )
