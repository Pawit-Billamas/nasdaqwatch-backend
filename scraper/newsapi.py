"""
scraper/newsapi.py
------------------
Wrappers around the newsapi-python library for fetching stock-specific
and general NASDAQ / technology market news.

If NEWSAPI_KEY is not set in the environment the functions return an
empty list and log a warning — the rest of the application continues
to function using yfinance news only.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")


def _get_client():
    """
    Lazily build a NewsApiClient instance.

    Returns
    -------
    NewsApiClient | None
        Client if a valid key is found, else None.
    """
    if not _NEWSAPI_KEY or _NEWSAPI_KEY == "your_newsapi_key_here":
        logger.warning(
            "NEWSAPI_KEY is not configured. "
            "Set it in .env to enable NewsAPI integration."
        )
        return None

    try:
        from newsapi import NewsApiClient  # type: ignore
        return NewsApiClient(api_key=_NEWSAPI_KEY)
    except Exception as exc:
        logger.error("Failed to initialise NewsApiClient: %s", exc)
        return None


def _format_article(article: dict[str, Any]) -> dict[str, Any]:
    """
    Normalise a raw NewsAPI article dict into the shared article schema.

    Parameters
    ----------
    article : dict
        Raw article as returned by newsapi-python.

    Returns
    -------
    dict
        Normalised dict with keys: title, description, url, source,
        published_at, image_url.
    """
    source = article.get("source", {})
    return {
        "title":        article.get("title", ""),
        "description":  article.get("description", ""),
        "url":          article.get("url", ""),
        "source":       source.get("name", "") if isinstance(source, dict) else str(source),
        "published_at": article.get("publishedAt", ""),
        "image_url":    article.get("urlToImage"),
    }


def get_stock_news(
    ticker: str,
    company_name: str = "",
    days: int = 7,
) -> list[dict[str, Any]]:
    """
    Fetch recent news articles about a specific stock from NewsAPI.

    Builds a query combining the ticker symbol and the company name
    (if provided) to maximise relevant results.

    Parameters
    ----------
    ticker : str
        The stock ticker symbol (e.g. 'AAPL').
    company_name : str, optional
        Human-readable company name to widen the search.
    days : int, optional
        How many days back to search (default 7).

    Returns
    -------
    list[dict]
        Up to 20 normalised article dicts.  Empty list on error or
        missing API key.
    """
    client = _get_client()
    if client is None:
        return []

    try:
        # Build a focused query; company_name is optional
        query_parts = [ticker]
        if company_name:
            # Use the first meaningful word of the company name
            short_name = company_name.split()[0] if " " in company_name else company_name
            query_parts.append(short_name)

        query = " OR ".join(query_parts)
        from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        response = client.get_everything(
            q=query,
            from_param=from_date,
            language="en",
            sort_by="publishedAt",
            page_size=20,
        )

        articles: list[dict[str, Any]] = response.get("articles", [])
        return [_format_article(a) for a in articles]

    except Exception as exc:
        logger.error("NewsAPI get_stock_news(%s) failed: %s", ticker, exc)
        return []


def get_market_news(days: int = 7) -> list[dict[str, Any]]:
    """
    Fetch general NASDAQ / US technology market news from NewsAPI.

    Parameters
    ----------
    days : int, optional
        How many days back to search (default 7).

    Returns
    -------
    list[dict]
        Up to 30 normalised article dicts. Empty list on error or
        missing API key.
    """
    client = _get_client()
    if client is None:
        return []

    try:
        from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        response = client.get_everything(
            q="NASDAQ OR stocks OR technology OR AI OR semiconductor OR earnings",
            from_param=from_date,
            language="en",
            sort_by="publishedAt",
            page_size=50,
        )

        articles: list[dict[str, Any]] = response.get("articles", [])
        return [_format_article(a) for a in articles]

    except Exception as exc:
        logger.error("NewsAPI get_market_news() failed: %s", exc)
        return []
