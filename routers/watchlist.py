"""
routers/watchlist.py
--------------------
FastAPI router for managing the user's stock watchlist.
Prefix: /api/watchlist

The watchlist is stored in PostgreSQL (Neon) and each GET / also
augments each ticker with its current live price info from yfinance.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.database import db_cursor
from scraper.yahoo import get_stock_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["Watchlist"])


class WatchlistAddRequest(BaseModel):
    ticker: str


@router.get("/", summary="List all watchlist tickers with live price data")
async def get_watchlist() -> list[dict[str, Any]]:
    """
    Return all tickers saved in the watchlist, enriched with current
    price data from yfinance.
    """
    try:
        with db_cursor() as cur:
            cur.execute("SELECT ticker, added_at FROM watchlist ORDER BY added_at DESC")
            rows = cur.fetchall()

        tickers_info: list[dict[str, Any]] = []
        for row in rows:
            ticker = row["ticker"]
            info = get_stock_info(ticker)
            info["added_at"] = str(row["added_at"])
            tickers_info.append(info)

        return tickers_info

    except Exception as exc:
        logger.error("get_watchlist() failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/", summary="Add a ticker to the watchlist (body: {ticker})")
async def add_to_watchlist_body(payload: WatchlistAddRequest) -> dict[str, Any]:
    """Add the given ticker to the watchlist via JSON body {"ticker": "AAPL"}."""
    return await _add_ticker(payload.ticker)


@router.post("/{ticker}", summary="Add a ticker to the watchlist (path param)")
async def add_to_watchlist(ticker: str) -> dict[str, Any]:
    """Add the given ticker via path parameter (alternate form)."""
    return await _add_ticker(ticker)


async def _add_ticker(ticker: str) -> dict[str, Any]:
    """Shared logic to insert a ticker into the watchlist."""
    upper_ticker = ticker.upper()
    try:
        with db_cursor() as cur:
            # Check if already exists
            cur.execute(
                "SELECT id FROM watchlist WHERE ticker = %s", (upper_ticker,)
            )
            existing = cur.fetchone()

            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Ticker '{upper_ticker}' is already in the watchlist.",
                )

            cur.execute(
                "INSERT INTO watchlist (ticker) VALUES (%s)", (upper_ticker,)
            )

        return {"message": f"'{upper_ticker}' added to watchlist.", "ticker": upper_ticker}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("add_to_watchlist(%s) failed: %s", ticker, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{ticker}", summary="Remove a ticker from the watchlist")
async def remove_from_watchlist(ticker: str) -> dict[str, Any]:
    """Remove the given ticker from the watchlist. Returns HTTP 404 if not found."""
    upper_ticker = ticker.upper()
    try:
        with db_cursor() as cur:
            cur.execute(
                "DELETE FROM watchlist WHERE ticker = %s", (upper_ticker,)
            )
            if cur.rowcount == 0:
                raise HTTPException(
                    status_code=404,
                    detail=f"Ticker '{upper_ticker}' was not found in the watchlist.",
                )

        return {"message": f"'{upper_ticker}' removed from watchlist.", "ticker": upper_ticker}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("remove_from_watchlist(%s) failed: %s", ticker, exc)
        raise HTTPException(status_code=500, detail=str(exc))
