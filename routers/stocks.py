"""
routers/stocks.py
-----------------
FastAPI router for stock search and individual stock data.
Prefix: /api/stocks
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from scraper.yahoo import get_stock_info, search_stocks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks", tags=["Stocks"])


@router.get("/search", summary="Search stocks by ticker or company name")
async def search(
    q: str = Query(..., min_length=1, description="Ticker symbol or company name fragment"),
) -> dict[str, Any]:
    """
    Search popular NASDAQ stocks whose ticker or name contains *q*.

    Returns up to 20 matching results from the local curated list.
    """
    try:
        results = search_stocks(q)
        return {"query": q, "results": results, "count": len(results)}
    except Exception as exc:
        logger.error("search(%s) failed: %s", q, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{ticker}", summary="Get current stock price and info")
async def get_stock(ticker: str) -> dict[str, Any]:
    """
    Retrieve live price, financials and metadata for a single ticker.

    Returns an error payload (HTTP 200) if yfinance cannot find the
    ticker, so the frontend can display a friendly message.
    """
    try:
        data = get_stock_info(ticker.upper())
        if "error" in data and data.get("price") is None:
            raise HTTPException(
                status_code=404,
                detail=f"Ticker '{ticker.upper()}' not found or data unavailable.",
            )
        return data
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_stock(%s) failed: %s", ticker, exc)
        raise HTTPException(status_code=500, detail=str(exc))
