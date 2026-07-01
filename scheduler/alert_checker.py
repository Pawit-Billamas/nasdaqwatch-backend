"""
scheduler/alert_checker.py
--------------------------
Background job that checks enabled alert rules every 10 minutes
and fires alert_events when conditions are met.
"""

import logging
from datetime import datetime, timedelta

from db.database import db_cursor
from scraper.yahoo import get_stock_info

logger = logging.getLogger(__name__)

_LAST_TRIGGERED: dict[str, datetime] = {}  # rule_id -> last trigger time (debounce)
_DEBOUNCE_HOURS = 4


def _debounced(rule_id: int) -> bool:
    """Return True if the rule fired too recently (debounce)."""
    key = str(rule_id)
    last = _LAST_TRIGGERED.get(key)
    if last and (datetime.utcnow() - last) < timedelta(hours=_DEBOUNCE_HOURS):
        return True
    return False


def _fire_event(rule_id: int, ticker: str, message: str) -> None:
    try:
        with db_cursor() as cur:
            cur.execute(
                "INSERT INTO alert_events (rule_id, ticker, message) VALUES (%s, %s, %s)",
                (rule_id, ticker, message)
            )
        _LAST_TRIGGERED[str(rule_id)] = datetime.utcnow()
        logger.info("Alert fired: rule_id=%s ticker=%s: %s", rule_id, ticker, message)
    except Exception as exc:
        logger.error("Failed to insert alert_event: %s", exc)


def check_alerts() -> None:
    """Main job: fetch enabled rules and evaluate conditions."""
    logger.info("Alert checker running...")
    try:
        with db_cursor() as cur:
            cur.execute(
                "SELECT id, ticker, kind, target::FLOAT AS target FROM alert_rules WHERE enabled=TRUE"
            )
            rules = cur.fetchall()
    except Exception as exc:
        logger.error("Failed to fetch alert rules: %s", exc)
        return

    if not rules:
        return

    # Group rules by ticker to avoid duplicate yfinance calls
    ticker_rules: dict[str, list] = {}
    for r in rules:
        ticker_rules.setdefault(r["ticker"], []).append(r)

    for ticker, trules in ticker_rules.items():
        try:
            info = get_stock_info(ticker)
        except Exception as exc:
            logger.warning("Could not fetch price for %s: %s", ticker, exc)
            continue

        price = float(info.get("price") or 0)
        change_pct = float(info.get("change_pct") or 0)
        if price == 0:
            continue

        for r in trules:
            rid = r["id"]
            kind = r["kind"]
            target = r["target"]

            if _debounced(rid):
                continue

            if kind == "price_above" and target is not None and price >= target:
                _fire_event(rid, ticker, f"{ticker} reached ${price:.2f} (above ${target:.2f})")

            elif kind == "price_below" and target is not None and price <= target:
                _fire_event(rid, ticker, f"{ticker} dropped to ${price:.2f} (below ${target:.2f})")

            elif kind == "pct_move" and target is not None and abs(change_pct) >= target:
                direction = "up" if change_pct >= 0 else "down"
                _fire_event(rid, ticker, f"{ticker} moved {change_pct:+.1f}% today ({direction} ≥ {target:.1f}%)")

    logger.info("Alert checker done. Checked %d tickers.", len(ticker_rules))
