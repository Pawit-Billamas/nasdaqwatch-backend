"""
routers/alerts.py
-----------------
CRUD for alert rules and alert events.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.database import db_cursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


class RuleCreate(BaseModel):
    ticker: str
    kind: str
    target: float | None = None
    enabled: bool = True


class RuleToggle(BaseModel):
    enabled: bool


@router.get("/rules")
async def get_rules() -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute("SELECT id, ticker, kind, target::FLOAT AS target, enabled, created_at FROM alert_rules ORDER BY created_at DESC")
        rows = cur.fetchall()
    return [
        {
            "id": r["id"],
            "ticker": r["ticker"],
            "kind": r["kind"],
            "target": r["target"],
            "enabled": r["enabled"],
            "created_at": str(r["created_at"]),
        }
        for r in rows
    ]


@router.post("/rules", status_code=201)
async def create_rule(body: RuleCreate) -> dict[str, Any]:
    ticker = body.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")
    valid_kinds = {"price_above", "price_below", "pct_move", "news", "ai_digest"}
    if body.kind not in valid_kinds:
        raise HTTPException(status_code=400, detail=f"kind must be one of {valid_kinds}")
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO alert_rules (ticker, kind, target, enabled) VALUES (%s, %s, %s, %s) RETURNING id, created_at",
            (ticker, body.kind, body.target, body.enabled)
        )
        row = cur.fetchone()
    return {"id": row["id"], "ticker": ticker, "kind": body.kind, "target": body.target, "enabled": body.enabled, "created_at": str(row["created_at"])}


@router.patch("/rules/{rule_id}")
async def toggle_rule(rule_id: int, body: RuleToggle) -> dict[str, Any]:
    with db_cursor() as cur:
        cur.execute("UPDATE alert_rules SET enabled=%s WHERE id=%s RETURNING id", (body.enabled, rule_id))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"id": rule_id, "enabled": body.enabled}


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: int) -> None:
    with db_cursor() as cur:
        cur.execute("DELETE FROM alert_rules WHERE id=%s", (rule_id,))


@router.get("/events")
async def get_events(limit: int = 50) -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, rule_id, ticker, message, triggered_at, is_read FROM alert_events ORDER BY triggered_at DESC LIMIT %s",
            (limit,)
        )
        rows = cur.fetchall()
    return [
        {
            "id": r["id"],
            "rule_id": r["rule_id"],
            "ticker": r["ticker"],
            "message": r["message"],
            "triggered_at": str(r["triggered_at"]),
            "is_read": r["is_read"],
        }
        for r in rows
    ]


@router.patch("/events/{event_id}/read")
async def mark_read(event_id: int) -> dict[str, Any]:
    with db_cursor() as cur:
        cur.execute("UPDATE alert_events SET is_read=TRUE WHERE id=%s RETURNING id", (event_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"id": event_id, "is_read": True}
