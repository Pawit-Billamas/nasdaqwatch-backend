"""
db/database.py
--------------
SQLite database setup using Python's built-in sqlite3 module.
Provides table initialisation and a connection factory.
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve the database file path relative to this file's parent directory.
DB_PATH = Path(__file__).resolve().parent.parent / "stock_news.db"


def get_db() -> sqlite3.Connection:
    """
    Return a new SQLite connection with row_factory set so rows behave
    like dictionaries (accessible by column name).

    Returns
    -------
    sqlite3.Connection
        An open database connection. The caller is responsible for
        closing it (preferably via a context manager).
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row          # enables dict-like row access
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrency for FastAPI
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """
    Create all required tables if they do not already exist.

    Tables
    ------
    watchlist
        Stores user-saved ticker symbols.
    news_cache
        Caches fetched news articles along with optional AI metadata.
    weekly_reports
        Stores generated weekly AI analysis reports as JSON blobs.
    """
    logger.info("Initialising database at %s", DB_PATH)
    with get_db() as conn:
        conn.executescript(
            """
            -- ----------------------------------------------------------------
            -- watchlist: user-saved NASDAQ tickers
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS watchlist (
                id         INTEGER  PRIMARY KEY AUTOINCREMENT,
                ticker     TEXT     UNIQUE NOT NULL,
                added_at   DATETIME DEFAULT (datetime('now'))
            );

            -- ----------------------------------------------------------------
            -- news_cache: fetched news articles (from yfinance / NewsAPI)
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS news_cache (
                id           INTEGER  PRIMARY KEY AUTOINCREMENT,
                ticker       TEXT     NOT NULL,
                title        TEXT,
                description  TEXT,
                url          TEXT,
                source       TEXT,
                published_at TEXT,
                sentiment    TEXT,
                summary      TEXT,
                cached_at    DATETIME DEFAULT (datetime('now'))
            );

            -- ----------------------------------------------------------------
            -- weekly_reports: AI-generated weekly analysis blobs
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS weekly_reports (
                id          INTEGER  PRIMARY KEY AUTOINCREMENT,
                week_start  TEXT     NOT NULL,
                week_end    TEXT     NOT NULL,
                report_json TEXT     NOT NULL,
                created_at  DATETIME DEFAULT (datetime('now'))
            );
            """
        )
    logger.info("Database tables ready.")
