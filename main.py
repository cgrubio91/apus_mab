"""
MAPUS Core Engine & API — Entry Point
Delegates to Clean Architecture application in src/
"""

import logging

# H10: el logging se configura una sola vez en src/presentation/main.py.
# (logging.basicConfig solo tiene efecto la primera vez; duplicarlo confunde.)
log = logging.getLogger("mapus")

# Backward compatibility: tests import `from main import app`
from src.presentation.main import app

if __name__ == "__main__":
    import uvicorn

    from src.config.settings import settings

    log.info("Starting MAPUS server on port %d", settings.PORT)

    uvicorn.run(
        "src.presentation.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.ENV.lower() == "development",
    )
