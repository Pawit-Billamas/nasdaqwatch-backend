"""
routers/calendar.py
-------------------
GET /api/calendar
Returns weekly earnings/dividend/economic events using yfinance.
"""

import logging
from datetime import date, timedelta
from typing import Any

import yfinance as yf
from fastapi import APIRouter, Query

from db.database import db_cursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/calendar", tags=["Calendar"])

# Macro economic events (static — updated periodically)
MACRO_EVENTS: list[dict[str, str]] = [
    {"weekday": "2", "detail": "FOMC Meeting"},
    {"weekday": "3", "detail": "CPI Release"},
    {"weekday": "4", "detail": "GDP Estimate"},
    {"weekday": "1", "detail": "Jobs Report"},
]


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _get_earnings_week(tickers: list[str], week_start: date) -> dict[str, list[dict]]:
    """Fetch earnings dates for tickers and bucket by weekday."""
    week_end = week_start + timedelta(days=4)
    buckets: dict[str, list[dict]] = {str(week_start + timedelta(i)): [] for i in range(5)}

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            cal = stock.calendar
            if cal is None:
                continue
            ed = None
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date") or cal.get("earningsDate")
                if isinstance(ed, list) and ed:
                    ed = ed[0]
            elif hasattr(cal, "columns") and "Earnings Date" in cal.columns:
                ed = cal["Earnings Date"].iloc[0]
            if ed is None:
                continue
            # Normalize to date
            if hasattr(ed, 'date'):
                ed = ed.date()
            elif isinstance(ed, str):
                ed = date.fromisoformat(ed[:10])
            if week_start <= ed <= week_end:
                key = str(ed)
                if key in buckets:
                    buckets[key].append({"ticker": ticker, "kind": "earnings", "detail": f"{ticker} Earnings"})
        except Exception as exc:
            logger.debug("Calendar fetch failed for %s: %s", ticker, exc)

    return buckets


def _get_dividend_events(tickers: list[str], week_start: date) -> dict[str, list[dict]]:
    """Fetch ex-dividend dates for tickers and bucket by weekday."""
    week_end = week_start + timedelta(days=4)
    buckets: dict[str, list[dict]] = {}

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.fast_info
            ex_div = getattr(info, 'last_ex_dividend_date', None)
            if ex_div is None:
                continue
            if hasattr(ex_div, 'date'):
                ex_div = ex_div.date()
            elif isinstance(ex_div, str):
                ex_div = date.fromisoformat(str(ex_div)[:10])
            if week_start <= ex_div <= week_end:
                key = str(ex_div)
                if key not in buckets:
                    buckets[key] = []
                buckets[key].append({"ticker": ticker, "kind": "dividend", "detail": f"{ticker} Ex-Dividend"})
        except Exception:
            pass

    return buckets


def _build_week(week_start: date, watchlist_tickers: list[str]) -> dict[str, Any]:
    week_end = week_start + timedelta(days=4)

    # Earnings + dividends from yfinance
    earnings_buckets = _get_earnings_week(watchlist_tickers, week_start)
    dividend_buckets = _get_dividend_events(watchlist_tickers, week_start)

    days = []
    for i in range(5):
        d = week_start + timedelta(i)
        ds = str(d)
        events: list[dict] = []
        events.extend(earnings_buckets.get(ds, []))
        events.extend(dividend_buckets.get(ds, []))
        # Static macro events by day index (0=Mon)
        for macro in MACRO_EVENTS:
            if macro["weekday"] == str(i):
                events.append({"ticker": "MACRO", "kind": "economic", "detail": macro["detail"]})
        days.append({"date": ds, "events": events})

    return {
        "week_start": str(week_start),
        "week_end": str(week_end),
        "days": days,
    }


@router.get("")
async def get_calendar(weeks: int = Query(default=3, ge=1, le=6)) -> list[dict[str, Any]]:
    """Return N weeks of earnings/dividend/economic events."""
    # Get watchlist tickers to fetch calendar events for
    try:
        with db_cursor() as cur:
            cur.execute("SELECT ticker FROM watchlist ORDER BY added_at")
            rows = cur.fetchall()
        watchlist_tickers = [r["ticker"] for r in rows]
    except Exception:
        watchlist_tickers = []

    today = date.today()
    current_monday = _monday(today)
    result = []
    for w in range(weeks):
        week_start = current_monday + timedelta(weeks=w)
        result.append(_build_week(week_start, watchlist_tickers))

    return result
