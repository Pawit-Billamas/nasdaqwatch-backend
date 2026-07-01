"""
routers/compare.py
------------------
GET /api/compare?tickers=AAPL,MSFT,GOOGL
Returns a table of comparable metrics side-by-side.
"""

import logging
from typing import Any

from fastapi import APIRouter, Query

from scraper.yahoo import get_stock_info, get_fundamentals

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/compare", tags=["Compare"])


def _fmt_val(raw: Any, fmt: str) -> str | None:
    """Format a numeric value for display."""
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return str(raw)
    if fmt == "x":
        return f"{v:.1f}x"
    if fmt == "%":
        return f"{v:.1f}%"
    if fmt == "$large":
        if v >= 1e12: return f"${v/1e12:.2f}T"
        if v >= 1e9:  return f"${v/1e9:.1f}B"
        if v >= 1e6:  return f"${v/1e6:.1f}M"
        return f"${v:.0f}"
    if fmt == "$":
        return f"${v:.2f}"
    return f"{v:.2f}"


METRIC_DEFS: list[tuple[str, str, str]] = [
    # (label, key in fundamentals, format)
    ("P/E (Trailing)", "pe_trailing", "x"),
    ("P/E (Forward)", "pe_forward", "x"),
    ("PEG Ratio", "peg_ratio", "x"),
    ("P/S Ratio", "price_to_sales", "x"),
    ("P/B Ratio", "price_to_book", "x"),
    ("Gross Margin", "gross_margin", "%"),
    ("Operating Margin", "operating_margin", "%"),
    ("Net Margin", "profit_margin", "%"),
    ("ROE", "roe", "%"),
    ("ROA", "roa", "%"),
    ("Revenue Growth", "revenue_growth", "%"),
    ("Earnings Growth", "earnings_growth", "%"),
    ("Free Cash Flow", "free_cash_flow", "$large"),
    ("Total Revenue", "total_revenue", "$large"),
    ("Total Debt", "total_debt", "$large"),
    ("Market Cap", None, "$large"),  # from stock info
    ("Debt/Equity", "debt_to_equity", "x"),
    ("Current Ratio", "current_ratio", "x"),
    ("EPS (Trailing)", "eps_trailing", "$"),
    ("EPS (Forward)", "eps_forward", "$"),
    ("Dividend Yield", "dividend_yield", "%"),
]


@router.get("")
async def compare_stocks(tickers: str = Query(..., description="Comma-separated ticker list, 2-4")) -> dict[str, Any]:
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()][:4]
    if len(ticker_list) < 2:
        return {"tickers": [], "columns": [], "rows": []}

    columns = []
    fund_data = []

    for tk in ticker_list:
        try:
            info = get_stock_info(tk)
        except Exception:
            info = {"ticker": tk, "price": 0, "change_pct": 0, "sector": None, "name": tk}
        try:
            fund = get_fundamentals(tk)
        except Exception:
            fund = {}
        fund["_market_cap"] = info.get("market_cap")
        fund_data.append(fund)
        columns.append({
            "ticker": tk,
            "name": info.get("name", tk),
            "price": float(info.get("price") or 0),
            "change_pct": float(info.get("change_pct") or 0),
            "sector": info.get("sector"),
        })

    rows = []
    for label, key, fmt in METRIC_DEFS:
        values = []
        for fund in fund_data:
            if key is None:
                raw = fund.get("_market_cap")
            else:
                raw = fund.get(key)
            values.append(_fmt_val(raw, fmt))
        rows.append({"metric": label, "key": key or "market_cap", "values": values})

    return {"tickers": ticker_list, "columns": columns, "rows": rows}
