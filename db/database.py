"""
db/database.py
--------------
PostgreSQL database setup using psycopg2.
Connects to Neon (serverless PostgreSQL) via DATABASE_URL env var.

Provides table initialisation and a connection factory that returns
dict-like rows (via RealDictCursor) — keeping the same interface
the routers already use.
"""

import logging
import os
from contextlib import contextmanager
from typing import Generator

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_DATABASE_URL: str = os.getenv("DATABASE_URL", "")


def get_db() -> psycopg2.extensions.connection:
    """
    Return a new psycopg2 connection to Neon PostgreSQL.
    Rows are returned as RealDictRow (accessible by column name,
    identical to SQLite's row_factory=sqlite3.Row behaviour).

    The caller is responsible for committing and closing
    (use as a context manager via `with get_db() as conn:`).
    """
    if not _DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Add it to Render environment variables."
        )
    conn = psycopg2.connect(
        _DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor,
        connect_timeout=10,
    )
    return conn


@contextmanager
def db_cursor() -> Generator:
    """
    Context manager that yields a cursor and auto-commits or rolls back.

    Usage:
        with db_cursor() as cur:
            cur.execute("SELECT ...")
            rows = cur.fetchall()
    """
    conn = get_db()
    try:
        with conn:          # psycopg2: `with conn` handles COMMIT / ROLLBACK
            with conn.cursor() as cur:
                yield cur
    finally:
        conn.close()


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
    logger.info("Initialising PostgreSQL database via Neon...")

    sql = """
        -- ----------------------------------------------------------------
        -- watchlist: user-saved NASDAQ tickers
        -- ----------------------------------------------------------------
        CREATE TABLE IF NOT EXISTS watchlist (
            id         SERIAL       PRIMARY KEY,
            ticker     TEXT         UNIQUE NOT NULL,
            added_at   TIMESTAMPTZ  DEFAULT NOW()
        );

        -- ----------------------------------------------------------------
        -- news_cache: fetched news articles (from yfinance / NewsAPI)
        -- ----------------------------------------------------------------
        CREATE TABLE IF NOT EXISTS news_cache (
            id           SERIAL       PRIMARY KEY,
            ticker       TEXT         NOT NULL,
            title        TEXT,
            description  TEXT,
            url          TEXT,
            source       TEXT,
            published_at TEXT,
            sentiment    TEXT,
            summary      TEXT,
            cached_at    TIMESTAMPTZ  DEFAULT NOW()
        );

        -- ----------------------------------------------------------------
        -- weekly_reports: AI-generated weekly analysis blobs
        -- ----------------------------------------------------------------
        CREATE TABLE IF NOT EXISTS weekly_reports (
            id          SERIAL       PRIMARY KEY,
            week_start  TEXT         NOT NULL,
            week_end    TEXT         NOT NULL,
            report_json TEXT         NOT NULL,
            created_at  TIMESTAMPTZ  DEFAULT NOW()
        );

        -- ----------------------------------------------------------------
        -- portfolio_holdings: user portfolio positions
        -- ----------------------------------------------------------------
        CREATE TABLE IF NOT EXISTS portfolio_holdings (
            id         SERIAL       PRIMARY KEY,
            ticker     TEXT         NOT NULL,
            shares     NUMERIC      NOT NULL CHECK (shares > 0),
            avg_cost   NUMERIC      NOT NULL CHECK (avg_cost > 0),
            added_at   TIMESTAMPTZ  DEFAULT NOW()
        );

        -- ----------------------------------------------------------------
        -- alert_rules: price / news / AI alert conditions
        -- ----------------------------------------------------------------
        CREATE TABLE IF NOT EXISTS alert_rules (
            id         SERIAL       PRIMARY KEY,
            ticker     TEXT         NOT NULL,
            kind       TEXT         NOT NULL,
            target     NUMERIC,
            enabled    BOOLEAN      DEFAULT TRUE,
            created_at TIMESTAMPTZ  DEFAULT NOW()
        );

        -- ----------------------------------------------------------------
        -- alert_events: triggered alert instances
        -- ----------------------------------------------------------------
        CREATE TABLE IF NOT EXISTS alert_events (
            id           SERIAL       PRIMARY KEY,
            rule_id      INTEGER      REFERENCES alert_rules(id) ON DELETE CASCADE,
            ticker       TEXT         NOT NULL,
            message      TEXT         NOT NULL,
            triggered_at TIMESTAMPTZ  DEFAULT NOW(),
            is_read      BOOLEAN      DEFAULT FALSE
        );
    """

    with db_cursor() as cur:
        cur.execute(sql)

    logger.info("PostgreSQL tables ready.")
