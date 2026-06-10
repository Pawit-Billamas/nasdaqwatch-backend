"""
main.py
-------
FastAPI application entry point for the NASDAQ Stock News Dashboard backend.

Start the server with:
    uvicorn main:app --reload --port 8000

Or using the convenience batch file:
    run.bat
"""

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables from .env before any other imports that
# may read them (e.g. scraper.newsapi, ai.summarizer).
load_dotenv()

from db.database import init_db
from routers import news, reports, stocks, watchlist
from scheduler.weekly_report import start_scheduler

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application lifespan (replaces deprecated on_event handlers)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage startup and shutdown logic.

    On startup:
      - Initialise the SQLite database (create tables if absent).
      - Start the APScheduler background scheduler.

    On shutdown:
      - Gracefully stop the scheduler.
    """
    # --- Startup ---
    logger.info("=== NASDAQ Stock News Backend starting up ===")
    init_db()
    start_scheduler(app)
    logger.info("=== Backend ready. Listening on http://0.0.0.0:8000 ===")

    yield  # application runs here

    # --- Shutdown ---
    logger.info("=== Backend shutting down ===")
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


# ---------------------------------------------------------------------------
# FastAPI application instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="NASDAQ Stock News Dashboard API",
    description=(
        "Backend API providing stock data, news aggregation, "
        "AI-powered summaries (Thai language), watchlist management "
        "and automated weekly reports for NASDAQ-listed stocks."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS — allow all origins for development and Cloudflare proxy usage.
# Tighten origins list in production.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(stocks.router)
app.include_router(news.router)
app.include_router(watchlist.router)
app.include_router(reports.router)


# ---------------------------------------------------------------------------
# Health-check endpoint
# ---------------------------------------------------------------------------
@app.get("/", tags=["Health"], summary="Health check")
async def root() -> dict[str, str]:
    """
    Simple health-check endpoint.

    Returns HTTP 200 with a status payload so load-balancers and
    monitoring tools can verify the service is alive.
    """
    return {"status": "ok", "version": "1.0.0"}
