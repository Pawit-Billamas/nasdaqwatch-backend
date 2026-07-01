"""
routers/portfolio.py
--------------------
CRUD for portfolio holdings, enriched with live prices from yfinance.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.database import db_cursor
from scraper.yahoo import get_stock_info

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])


class HoldingCreate(BaseModel):
    ticker: str
    shares: float
    avg_cost: float


class HoldingUpdate(BaseModel):
    shares: float
    avg_cost: float


@router.get("")
async def get_portfolio() -> dict[str, Any]:
    """Return all holdings enriched with live price data."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, ticker, shares::FLOAT AS shares, avg_cost::FLOAT AS avg_cost, added_at FROM portfolio_holdings ORDER BY added_at"
        )
        rows = cur.fetchall()

    if not rows:
        return {
            "total_value": 0, "day_change": 0, "day_change_pct": 0,
            "total_gain": 0, "total_gain_pct": 0, "holdings": []
        }

    holdings: list[dict[str, Any]] = []
    total_value = 0.0
    total_cost = 0.0
    total_day_change = 0.0

    for row in rows:
        ticker = row["ticker"]
        shares = float(row["shares"])
        avg_cost = float(row["avg_cost"])
        try:
            info = get_stock_info(ticker)
            price = float(info.get("price") or 0)
            change_pct = float(info.get("change_pct") or 0)
            name = info.get("name", ticker)
        except Exception:
            price = avg_cost
            change_pct = 0.0
            name = ticker

        value = price * shares
        cost_basis = avg_cost * shares
        gain = value - cost_basis
        gain_pct = (gain / cost_basis * 100) if cost_basis > 0 else 0.0
        prev_price = price / (1 + change_pct / 100) if change_pct != -100 else price
        day_change_this = (price - prev_price) * shares

        total_value += value
        total_cost += cost_basis
        total_day_change += day_change_this

        holdings.append({
            "id": row["id"],
            "ticker": ticker,
            "name": name,
            "shares": shares,
            "avg_cost": avg_cost,
            "price": round(price, 4),
            "change_pct": round(change_pct, 2),
            "value": round(value, 2),
            "gain": round(gain, 2),
            "gain_pct": round(gain_pct, 2),
            "weight_pct": 0.0,  # filled below
            "added_at": str(row["added_at"]),
        })

    total_gain = total_value - total_cost
    total_gain_pct = (total_gain / total_cost * 100) if total_cost > 0 else 0.0
    day_change_pct = (total_day_change / (total_value - total_day_change) * 100) if (total_value - total_day_change) > 0 else 0.0

    for h in holdings:
        h["weight_pct"] = round(h["value"] / total_value * 100, 2) if total_value > 0 else 0.0

    return {
        "total_value": round(total_value, 2),
        "day_change": round(total_day_change, 2),
        "day_change_pct": round(day_change_pct, 2),
        "total_gain": round(total_gain, 2),
        "total_gain_pct": round(total_gain_pct, 2),
        "holdings": holdings,
    }


@router.post("", status_code=201)
async def add_holding(body: HoldingCreate) -> dict[str, Any]:
    ticker = body.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO portfolio_holdings (ticker, shares, avg_cost) VALUES (%s, %s, %s) RETURNING id",
            (ticker, body.shares, body.avg_cost)
        )
        row = cur.fetchone()
    return {"id": row["id"], "ticker": ticker, "shares": body.shares, "avg_cost": body.avg_cost}


@router.put("/{holding_id}")
async def update_holding(holding_id: int, body: HoldingUpdate) -> dict[str, Any]:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE portfolio_holdings SET shares=%s, avg_cost=%s WHERE id=%s RETURNING id",
            (body.shares, body.avg_cost, holding_id)
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Holding not found")
    return {"id": holding_id, "shares": body.shares, "avg_cost": body.avg_cost}


@router.delete("/{holding_id}", status_code=204)
async def delete_holding(holding_id: int) -> None:
    with db_cursor() as cur:
        cur.execute("DELETE FROM portfolio_holdings WHERE id=%s", (holding_id,))
