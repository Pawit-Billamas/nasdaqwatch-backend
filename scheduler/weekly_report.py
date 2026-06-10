"""
scheduler/weekly_report.py
--------------------------
APScheduler configuration for the automated weekly report job.

The job runs every Sunday at 08:00 Bangkok time (Asia/Bangkok, UTC+7).
It reuses the same report generation logic exposed by the
``/api/reports/generate`` endpoint so that manual and scheduled
reports are always identical.
"""

import json
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ai.summarizer import analyze_watchlist_for_weekly
from db.database import get_db
from scraper.yahoo import get_stock_info, get_stock_news

logger = logging.getLogger(__name__)


def _run_weekly_report_job() -> None:
    """
    Scheduled job body: generate and persist a weekly report.

    This function is called automatically by APScheduler every Sunday
    at 08:00 Asia/Bangkok.  It mirrors the logic in
    ``routers/reports.py::generate_report`` so the output is identical
    whether triggered by the scheduler or the REST endpoint.
    """
    logger.info("[Scheduler] Starting weekly report generation …")

    try:
        # ---- Collect watchlist tickers ----
        with get_db() as conn:
            rows = conn.execute(
                "SELECT ticker FROM watchlist ORDER BY added_at ASC"
            ).fetchall()

        stocks_data = []
        for row in rows:
            ticker = row["ticker"]
            info = get_stock_info(ticker)
            news = get_stock_news(ticker)
            stocks_data.append(
                {
                    "ticker":       ticker,
                    "price_change": info.get("change_pct", 0.0) or 0.0,
                    "news":         news[:5],
                }
            )

        # ---- Generate AI report ----
        report = analyze_watchlist_for_weekly(stocks_data)

        now = datetime.utcnow()
        week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        week_end = now.strftime("%Y-%m-%d")

        # ---- Persist to DB ----
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO weekly_reports (week_start, week_end, report_json)
                VALUES (?, ?, ?)
                """,
                (week_start, week_end, json.dumps(report, ensure_ascii=False)),
            )

        logger.info("[Scheduler] Weekly report saved for %s → %s", week_start, week_end)

    except Exception as exc:
        logger.error("[Scheduler] Weekly report job failed: %s", exc)


def start_scheduler(app=None) -> BackgroundScheduler:
    """
    Create, configure and start the background APScheduler instance.

    The scheduler is attached to ``app.state.scheduler`` so FastAPI's
    shutdown event can gracefully stop it.

    Parameters
    ----------
    app : fastapi.FastAPI | None
        The FastAPI application instance.  Pass ``None`` for standalone use.

    Returns
    -------
    BackgroundScheduler
        The running scheduler instance.
    """
    scheduler = BackgroundScheduler(timezone="Asia/Bangkok")

    # Run every Sunday (day_of_week=6) at 08:00 Bangkok time
    scheduler.add_job(
        _run_weekly_report_job,
        trigger=CronTrigger(
            day_of_week="sun",
            hour=8,
            minute=0,
            timezone="Asia/Bangkok",
        ),
        id="weekly_report",
        name="Weekly NASDAQ Report (Sunday 08:00 Bangkok)",
        replace_existing=True,
        misfire_grace_time=3600,  # allow up to 1 hour late start
    )

    scheduler.start()
    logger.info(
        "[Scheduler] Started. Weekly report job scheduled for Sunday 08:00 Asia/Bangkok."
    )

    if app is not None:
        app.state.scheduler = scheduler

    return scheduler
