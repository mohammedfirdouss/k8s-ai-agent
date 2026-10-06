"""Application entry point.

Creates and configures the FastAPI application:
- CORS (origins come from settings, default http://localhost:3000)
- Logging via loguru
- API routes
"""

import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.routes import router as api_router
from app.core.auth import auth_enabled
from app.core.config import settings
from app.services.history import history_enabled


def configure_logging() -> None:
    """Set up loguru as the application logger."""
    logger.remove()  # remove the default handler so we control the format
    logger.add(
        sys.stderr,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
    )


def create_app() -> FastAPI:
    """Application factory: build and return the FastAPI app."""
    configure_logging()

    app = FastAPI(
        title="AI Kubernetes Troubleshooting Agent",
        description="Backend API for AI-assisted Kubernetes troubleshooting.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    logger.info("Application configured. Allowed CORS origins: {}", settings.cors_origins_list)
    if auth_enabled():
        logger.info("Authentication enabled: requests require an InsForge user token")
        if not history_enabled():
            logger.warning("INSFORGE_API_KEY is not set — investigation history will not be saved")
    else:
        logger.warning(
            "INSFORGE_URL is not set — running in local single-user mode with NO authentication. "
            "Do not expose this backend to a network."
        )
    return app


app = create_app()
