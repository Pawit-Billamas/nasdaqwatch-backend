"""
routers/stocks.py
-----------------
FastAPI router for stock search, individual stock data, and fundamentals.
Prefix: /api/stocks
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from scraper.yahoo import get_stock_info, search_stocks, get_fundamentals

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks", tags=["Stocks"])


# ---------------------------------------------------------------------------
# Helpers: rule-based Good / Bad / Neutral scoring
# ---------------------------------------------------------------------------

def _rate(value: float | None, good_above: float | None = None,
          bad_above: float | None = None, good_below: float | None = None,
          bad_below: float | None = None) -> str:
    """Return 'good', 'bad', or 'neutral' based on threshold rules."""
    if value is None:
        return "neutral"
    if good_above is not None and value >= good_above:
        return "good"
    if bad_below is not None and value <= bad_below:
        return "bad"
    if good_below is not None and value <= good_below:
        return "good"
    if bad_above is not None and value >= bad_above:
        return "bad"
    return "neutral"


def _score_fundamentals(f: dict[str, Any]) -> dict[str, Any]:
    """
    Attach a 'rating' (good|neutral|bad) and Thai 'note' to each metric.
    Ratings are tuned for long-term NASDAQ tech/growth investors.
    """
    def rate_metric(key: str, **kw) -> dict[str, Any]:
        v = f.get(key)
        return {"value": v, "rating": _rate(v, **kw)}

    return {
        # Valuation
        "pe_trailing": {
            **rate_metric("pe_trailing", good_below=25, bad_above=60),
            "label": "P/E (Trailing)",
            "note":  "< 25 ดี, 25-60 ปานกลาง, > 60 แพงมาก",
            "format": "x",
        },
        "pe_forward": {
            **rate_metric("pe_forward", good_below=20, bad_above=50),
            "label": "P/E (Forward)",
            "note":  "< 20 ดี, > 50 แพงเกินไป",
            "format": "x",
        },
        "peg_ratio": {
            **rate_metric("peg_ratio", good_below=1.5, bad_above=3.0),
            "label": "PEG Ratio",
            "note":  "< 1 ดีมาก (undervalued), 1-2 ยุติธรรม, > 3 แพงเกินการเติบโต",
            "format": "x",
        },
        "price_to_sales": {
            **rate_metric("price_to_sales", good_below=5, bad_above=20),
            "label": "Price/Sales",
            "note":  "< 5 สมเหตุสมผล, > 20 แพงมาก",
            "format": "x",
        },
        "price_to_book": {
            **rate_metric("price_to_book", good_below=3, bad_above=15),
            "label": "Price/Book",
            "note":  "< 3 ดี, > 15 แพงมาก",
            "format": "x",
        },

        # Profitability
        "gross_margin": {
            **rate_metric("gross_margin", good_above=50, bad_below=20),
            "label": "Gross Margin",
            "note":  "> 50% ดีมาก (บ่งบอก pricing power), < 20% กดดัน",
            "format": "%",
        },
        "operating_margin": {
            **rate_metric("operating_margin", good_above=20, bad_below=0),
            "label": "Operating Margin",
            "note":  "> 20% ดี, ติดลบ = ยังไม่ทำกำไรจากการดำเนินงาน",
            "format": "%",
        },
        "profit_margin": {
            **rate_metric("profit_margin", good_above=15, bad_below=0),
            "label": "Net Profit Margin",
            "note":  "> 15% ดีมาก, ติดลบ = ขาดทุน",
            "format": "%",
        },
        "roe": {
            **rate_metric("roe", good_above=15, bad_below=0),
            "label": "Return on Equity (ROE)",
            "note":  "> 15% ดี (บริษัทสร้างผลตอบแทนจากทุนได้ดี), ติดลบ = ขาดทุน",
            "format": "%",
        },
        "roa": {
            **rate_metric("roa", good_above=5, bad_below=0),
            "label": "Return on Assets (ROA)",
            "note":  "> 5% ดี, ติดลบ = ขาดทุน",
            "format": "%",
        },

        # Growth
        "revenue_growth": {
            **rate_metric("revenue_growth", good_above=10, bad_below=-5),
            "label": "Revenue Growth (YoY)",
            "note":  "> 10% ดี, ติดลบ = รายได้หดตัว",
            "format": "%",
        },
        "earnings_growth": {
            **rate_metric("earnings_growth", good_above=10, bad_below=-10),
            "label": "Earnings Growth (YoY)",
            "note":  "> 10% ดี, ติดลบ = กำไรหดตัว",
            "format": "%",
        },

        # Cash flow
        "free_cash_flow": {
            "value": f.get("free_cash_flow"),
            "rating": "good" if (f.get("free_cash_flow") or 0) > 0 else "bad",
            "label": "Free Cash Flow",
            "note":  "บวก = บริษัทสร้างเงินสดได้ ดีมาก, ลบ = เผาเงิน",
            "format": "$large",
        },
        "operating_cash": {
            "value": f.get("operating_cash"),
            "rating": "good" if (f.get("operating_cash") or 0) > 0 else "bad",
            "label": "Operating Cash Flow",
            "note":  "บวก = กระแสเงินสดจากการดำเนินงานดี",
            "format": "$large",
        },

        # Balance sheet
        "debt_to_equity": {
            **rate_metric("debt_to_equity", good_below=50, bad_above=200),
            "label": "Debt/Equity",
            "note":  "< 50 (0.5x) หนี้น้อยมาก, 50-200 ปานกลาง, > 200 หนี้สูง",
            "format": "raw",
        },
        "current_ratio": {
            **rate_metric("current_ratio", good_above=1.5, bad_below=1.0),
            "label": "Current Ratio",
            "note":  "> 1.5 ดี (สภาพคล่องดี), < 1.0 เสี่ยง",
            "format": "x",
        },
        "total_cash": {
            "value": f.get("total_cash"),
            "rating": "good" if (f.get("total_cash") or 0) > 0 else "neutral",
            "label": "เงินสดในมือ",
            "note":  "ยิ่งมากยิ่งดี บ่งบอกความแข็งแกร่งทางการเงิน",
            "format": "$large",
        },

        # EPS
        "eps_trailing": {
            "value": f.get("eps_trailing"),
            "rating": "good" if (f.get("eps_trailing") or 0) > 0 else "bad",
            "label": "EPS (Trailing 12M)",
            "note":  "กำไรต่อหุ้น บวก = ทำกำไร, ลบ = ขาดทุน",
            "format": "$",
        },
        "eps_forward": {
            "value": f.get("eps_forward"),
            "rating": "good" if (f.get("eps_forward") or 0) > 0 else "bad",
            "label": "EPS (Forward Est.)",
            "note":  "กำไรต่อหุ้นที่นักวิเคราะห์คาดการณ์",
            "format": "$",
        },

        # Dividend
        "dividend_yield": {
            **rate_metric("dividend_yield", good_above=1.5),
            "label": "Dividend Yield",
            "note":  "สำหรับ growth stocks ส่วนใหญ่ไม่จ่าย dividend ถือว่าปกติ",
            "format": "%",
        },
    }


def _overall_verdict(scored: dict[str, Any]) -> dict[str, Any]:
    """Count good/bad/neutral and produce an overall summary."""
    counts = {"good": 0, "bad": 0, "neutral": 0}
    for m in scored.values():
        counts[m.get("rating", "neutral")] += 1

    total = counts["good"] + counts["bad"] + counts["neutral"]
    if total == 0:
        return {"verdict": "neutral", "score": 50, "summary": "ไม่มีข้อมูลเพียงพอ"}

    score = round((counts["good"] / total) * 100)
    bad_pct = counts["bad"] / total

    if score >= 65:
        verdict = "strong"
        summary = f"ปัจจัยพื้นฐานแข็งแกร่ง {counts['good']}/{total} ตัวชี้วัดผ่านเกณฑ์ดี"
    elif score >= 45 and bad_pct < 0.35:
        verdict = "fair"
        summary = f"ปัจจัยพื้นฐานพอใช้ได้ มีทั้งจุดแข็งและจุดที่ต้องระวัง"
    elif bad_pct >= 0.4:
        verdict = "weak"
        summary = f"มีความเสี่ยงสูง {counts['bad']}/{total} ตัวชี้วัดต่ำกว่าเกณฑ์"
    else:
        verdict = "mixed"
        summary = f"สัญญาณผสม ดี {counts['good']} · ปานกลาง {counts['neutral']} · แย่ {counts['bad']}"

    return {
        "verdict": verdict,
        "score": score,
        "good_count": counts["good"],
        "bad_count": counts["bad"],
        "neutral_count": counts["neutral"],
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/search", summary="Search stocks by ticker or company name")
async def search(
    q: str = Query(..., min_length=1, description="Ticker symbol or company name fragment"),
) -> dict[str, Any]:
    try:
        results = search_stocks(q)
        return {"query": q, "results": results, "count": len(results)}
    except Exception as exc:
        logger.error("search(%s) failed: %s", q, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{ticker}/fundamentals", summary="Get financial fundamentals with Good/Bad ratings")
async def get_stock_fundamentals(ticker: str) -> dict[str, Any]:
    """
    Retrieve ~25 financial metrics for a stock with rule-based
    Good / Neutral / Bad ratings tuned for long-term investors.

    Returns:
    - raw: raw fundamentals dict
    - metrics: scored dict with value + rating + label + note per metric
    - verdict: overall assessment (strong / fair / mixed / weak)
    """
    try:
        upper = ticker.upper()
        raw = get_fundamentals(upper)

        if "error" in raw:
            raise HTTPException(status_code=404, detail=raw["error"])

        scored = _score_fundamentals(raw)
        verdict = _overall_verdict(scored)

        return {
            "ticker":  upper,
            "name":    raw.get("name", upper),
            "sector":  raw.get("sector"),
            "industry":raw.get("industry"),
            "next_earnings": raw.get("next_earnings"),
            "total_revenue": raw.get("total_revenue"),
            "employee_count": raw.get("employee_count"),
            "metrics": scored,
            "verdict": verdict,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_stock_fundamentals(%s) failed: %s", ticker, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{ticker}", summary="Get current stock price and info")
async def get_stock(ticker: str) -> dict[str, Any]:
    try:
        data = get_stock_info(ticker.upper())
        if "error" in data and data.get("price") is None:
            raise HTTPException(
                status_code=404,
                detail=f"Ticker '{ticker.upper()}' not found or data unavailable.",
            )
        return data
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_stock(%s) failed: %s", ticker, exc)
        raise HTTPException(status_code=500, detail=str(exc))
