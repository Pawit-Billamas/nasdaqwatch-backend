"""
routers/news.py
---------------
FastAPI router for stock-specific and general market news.
Prefix: /api/news

News items are sourced from both yfinance and NewsAPI, deduplicated by
title, and cached in SQLite.  AI summaries are cached for 6 hours.

IMPORTANT — route ordering:
  /market must be declared BEFORE /{ticker} to avoid FastAPI treating
  the literal string "market" as a ticker parameter.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException

from ai.summarizer import summarize_news, score_news_sentiment
from db.database import get_db
from scraper import newsapi as newsapi_scraper
from scraper import yahoo as yahoo_scraper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/news", tags=["News"])

# How long cached articles are considered fresh (seconds)
_CACHE_TTL_SECONDS = 3600  # 1 hour for articles
_SUMMARY_TTL_HOURS = 6


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

import re

def _deduplicate(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate articles using normalized title and URL as keys."""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[dict[str, Any]] = []
    
    for a in articles:
        url = (a.get("url") or "").strip().lower()
        title = (a.get("title") or "").strip().lower()
        
        # Remove all punctuation and extra whitespace for fuzzy match
        norm_title = re.sub(r'[^\w\s]', '', title)
        norm_title = re.sub(r'\s+', ' ', norm_title).strip()
        
        # Skip if either URL or exact normalized title has been seen
        if (url and url in seen_urls) or (norm_title and norm_title in seen_titles):
            continue
            
        if url:
            seen_urls.add(url)
        if norm_title:
            seen_titles.add(norm_title)
            
        unique.append(a)
    return unique


def _cache_articles(ticker: str, articles: list[dict[str, Any]]) -> None:
    """Persist a list of articles to the news_cache table."""
    try:
        with get_db() as conn:
            for a in articles:
                conn.execute(
                    """
                    INSERT INTO news_cache
                        (ticker, title, description, url, source, published_at, cached_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        ticker.upper(),
                        a.get("title", ""),
                        a.get("description", ""),
                        a.get("url", ""),
                        a.get("source", ""),
                        a.get("published_at", ""),
                    ),
                )
    except Exception as exc:
        logger.error("_cache_articles(%s) failed: %s", ticker, exc)


def _get_cached_articles(ticker: str) -> list[dict[str, Any]]:
    """Return articles from cache that are not older than _CACHE_TTL_SECONDS."""
    try:
        cutoff = (
            datetime.utcnow() - timedelta(seconds=_CACHE_TTL_SECONDS)
        ).strftime("%Y-%m-%d %H:%M:%S")

        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT title, description, url, source, published_at
                FROM   news_cache
                WHERE  ticker = ? AND cached_at >= ?
                ORDER  BY published_at DESC
                LIMIT  40
                """,
                (ticker.upper(), cutoff),
            ).fetchall()

        return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("_get_cached_articles(%s) failed: %s", ticker, exc)
        return []


def _get_cached_summary(ticker: str) -> dict[str, Any] | None:
    """
    Return the most recent cached AI summary if it is less than
    _SUMMARY_TTL_HOURS old, otherwise None.
    """
    try:
        cutoff = (
            datetime.utcnow() - timedelta(hours=_SUMMARY_TTL_HOURS)
        ).strftime("%Y-%m-%d %H:%M:%S")

        with get_db() as conn:
            row = conn.execute(
                """
                SELECT summary FROM news_cache
                WHERE  ticker = ? AND summary IS NOT NULL AND cached_at >= ?
                ORDER  BY cached_at DESC
                LIMIT  1
                """,
                (ticker.upper(), cutoff),
            ).fetchone()

        if row and row["summary"]:
            import json
            return json.loads(row["summary"])
        return None
    except Exception as exc:
        logger.error("_get_cached_summary(%s) failed: %s", ticker, exc)
        return None


def _cache_summary(ticker: str, summary: dict[str, Any]) -> None:
    """Store an AI summary JSON blob into the most recent cache row for ticker."""
    try:
        import json

        with get_db() as conn:
            conn.execute(
                """
                UPDATE news_cache
                SET    summary = ?, cached_at = datetime('now')
                WHERE  id = (
                    SELECT id FROM news_cache
                    WHERE  ticker = ?
                    ORDER  BY cached_at DESC
                    LIMIT  1
                )
                """,
                (json.dumps(summary, ensure_ascii=False), ticker.upper()),
            )
    except Exception as exc:
        logger.error("_cache_summary(%s) failed: %s", ticker, exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/market", summary="General NASDAQ / tech market news")
async def market_news() -> dict[str, Any]:
    """
    Return recent NASDAQ/tech market news with per-article sentiment.
    Each article has a 'sentiment' field: bullish | neutral | bearish.
    Also returns overall market_sentiment summary.
    """
    try:
        newsapi_articles = newsapi_scraper.get_market_news(days=7)
        yf_articles = yahoo_scraper.get_stock_news("QQQ")  # NASDAQ 100 ETF proxy

        combined = _deduplicate(newsapi_articles + yf_articles)

        # Score sentiment for every article (fast local, no API call)
        scored: list[dict[str, Any]] = []
        for a in combined:
            sentiment = score_news_sentiment(
                a.get("title", ""),
                a.get("description", ""),
            )
            scored.append({**a, "sentiment": sentiment})

        # Derive overall market sentiment from article counts
        bull = sum(1 for a in scored if a["sentiment"] == "bullish")
        bear = sum(1 for a in scored if a["sentiment"] == "bearish")
        if bull > bear + 2:
            market_sentiment = "bullish"
        elif bear > bull + 2:
            market_sentiment = "bearish"
        else:
            market_sentiment = "neutral"

        return {
            "source":           "NewsAPI + yfinance",
            "count":            len(scored),
            "market_sentiment": market_sentiment,
            "articles":         scored,
        }
    except Exception as exc:
        logger.error("market_news() failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{ticker}", summary="Get news for a specific ticker")
async def stock_news(ticker: str) -> dict[str, Any]:
    """
    Return recent news for the given ticker with per-article sentiment.
    """
    try:
        upper_ticker = ticker.upper()

        # Try fresh cache first
        cached = _get_cached_articles(upper_ticker)
        if cached:
            # Add sentiment if missing from cache
            scored = [
                {**a, "sentiment": a.get("sentiment") or score_news_sentiment(a.get("title", ""), a.get("description", ""))}
                for a in cached
            ]
            return {"ticker": upper_ticker, "source": "cache", "count": len(scored), "articles": scored}

        # Fetch live data
        yf_articles = yahoo_scraper.get_stock_news(upper_ticker)
        stock_info = yahoo_scraper.get_stock_info(upper_ticker)
        company_name = stock_info.get("name", "")

        newsapi_articles = newsapi_scraper.get_stock_news(
            ticker=upper_ticker, company_name=company_name, days=7,
        )

        combined = _deduplicate(yf_articles + newsapi_articles)

        # Score sentiment for each article
        scored = [
            {**a, "sentiment": score_news_sentiment(a.get("title", ""), a.get("description", ""))}
            for a in combined
        ]

        _cache_articles(upper_ticker, scored)

        return {
            "ticker":   upper_ticker,
            "source":   "yfinance + NewsAPI",
            "count":    len(scored),
            "articles": scored,
        }
    except Exception as exc:
        logger.error("stock_news(%s) failed: %s", ticker, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{ticker}/summary", summary="AI-generated news summary for a ticker")
async def stock_news_summary(ticker: str) -> dict[str, Any]:
    """
    Return a Gemini AI summary of recent news for the given ticker.

    If a valid summary was generated within the last 6 hours it is
    returned from cache; otherwise fresh news is fetched and summarised.
    """
    try:
        upper_ticker = ticker.upper()

        # Return cached summary if fresh enough
        cached_summary = _get_cached_summary(upper_ticker)
        if cached_summary:
            return {
                "ticker":  upper_ticker,
                "source":  "cache",
                "summary": cached_summary,
            }

        # Fetch news to summarise
        yf_articles = yahoo_scraper.get_stock_news(upper_ticker)
        stock_info = yahoo_scraper.get_stock_info(upper_ticker)
        company_name = stock_info.get("name", upper_ticker)

        newsapi_articles = newsapi_scraper.get_stock_news(
            ticker=upper_ticker,
            company_name=company_name,
            days=7,
        )
        combined = _deduplicate(yf_articles + newsapi_articles)

        # Generate summary via Gemini
        summary = summarize_news(
            ticker=upper_ticker,
            company_name=company_name,
            news_items=combined,
        )

        # Persist to cache
        if combined:
            _cache_articles(upper_ticker, combined)
        _cache_summary(upper_ticker, summary)

        return {
            "ticker":  upper_ticker,
            "source":  "gemini-1.5-flash",
            "summary": summary,
        }
    except Exception as exc:
        logger.error("stock_news_summary(%s) failed: %s", ticker, exc)
        raise HTTPException(status_code=500, detail=str(exc))
