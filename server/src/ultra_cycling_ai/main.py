"""FastAPI application entry point."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ultra_cycling_ai.api.routes import router
from ultra_cycling_ai.db.engine import close_db, init_db
from ultra_cycling_ai.tools.registry import build_default_registry
from ultra_cycling_ai.agent.runner import set_registry

_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Starting ultra-cycling-ai backend …")

    # Initialise database.
    await init_db()
    logger.info("Database ready")

    # Build tool registry and wire it into the agent runner.
    registry = build_default_registry()
    set_registry(registry)
    logger.info("Tool registry ready: %s", registry.tool_names)

    yield

    # Shutdown.
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Ultra-Cycling AI",
    description="AI-powered ultra-endurance cycling assistant — cloud agent backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
