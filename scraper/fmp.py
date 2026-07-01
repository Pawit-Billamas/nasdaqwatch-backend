"""
scraper/fmp.py
--------------
Financial Modeling Prep (FMP) free-tier API client.
Provides fundamentals data as a drop-in replacement for yfinance .info
when Yahoo Finance rate-limits Render's IPs.

Free tier: 250 calls/day — enough for on-demand fundamentals lookups.
API key is read from FMP_API_KEY environment variable.
"""

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

FMP_API_KEY = os.getenv("FMP_API_KEY", "")
_BASE = "https://financialmodelingprep.com/api/v3"
_TIMEOUT = 8


def _get(path: str, params: dict | None = None) -> Any:
    if not FMP_API_KEY:
        raise RuntimeError("FMP_API_KEY not set")
    p = {"apikey": FMP_API_KEY, **(params or {})}
    r = requests.get(f"{_BASE}{path}", params=p, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_fundamentals_fmp(ticker: str) -> dict[str, Any]:
    """
    Fetch comprehensive fundamentals from FMP free API.
    Returns a dict with the same keys as yahoo.get_fundamentals()
    so the scoring logic in stocks.py works unchanged.
    """
    upper = ticker.upper()

    try:
        # --- Profile (name, sector, industry, mktcap, employees) ---
        profile_list = _get(f"/profile/{upper}")
        profile: dict = profile_list[0] if profile_list else {}

        # --- Key metrics TTM (P/S, P/B, EV metrics, FCF yield…) ---
        metrics_list = _get(f"/key-metrics-ttm/{upper}")
        km: dict = metrics_list[0] if metrics_list else {}

        # --- Ratios TTM (margins, ROE, ROA, current ratio, P/E…) ---
        ratios_list = _get(f"/ratios-ttm/{upper}")
        rt: dict = ratios_list[0] if ratios_list else {}

        # --- Income statement (revenue growth, earnings growth) ---
        income_list = _get(f"/income-statement/{upper}", {"limit": 2, "period": "annual"})
        income_curr: dict = income_list[0] if income_list else {}
        income_prev: dict = income_list[1] if len(income_list) > 1 else {}

        # --- Balance sheet (cash, debt) ---
        balance_list = _get(f"/balance-sheet-statement/{upper}", {"limit": 1, "period": "annual"})
        bs: dict = balance_list[0] if balance_list else {}

        # --- Cash flow statement ---
        cf_list = _get(f"/cash-flow-statement/{upper}", {"limit": 1, "period": "annual"})
        cf: dict = cf_list[0] if cf_list else {}

        # --- Earnings calendar ---
        try:
            earn = _get(f"/historical/earning_calendar/{upper}", {"limit": 1})
            next_earnings = earn[0].get("date") if earn else None
        except Exception:
            next_earnings = None

        # ── Compute YoY growth ──
        def _pct_growth(curr: float | None, prev: float | None) -> float | None:
            if curr is None or prev is None or prev == 0:
                return None
            return round((curr - prev) / abs(prev) * 100, 2)

        rev_curr = income_curr.get("revenue")
        rev_prev = income_prev.get("revenue")
        net_curr = income_curr.get("netIncome")
        net_prev = income_prev.get("netIncome")

        def _f(v: Any) -> float | None:
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        def _pct(v: Any) -> float | None:
            f = _f(v)
            return round(f * 100, 2) if f is not None else None

        return {
            "ticker": upper,
            "name": profile.get("companyName", upper),
            "sector": profile.get("sector"),
            "industry": profile.get("industry"),
            "employee_count": profile.get("fullTimeEmployees"),
            "next_earnings": next_earnings,
            "fiscal_year_end": None,

            # Valuation
            "pe_trailing":    _f(rt.get("peRatioTTM")),
            "pe_forward":     None,  # not in free tier
            "peg_ratio":      _f(km.get("pegRatioTTM")),
            "price_to_sales": _f(rt.get("priceToSalesRatioTTM")),
            "price_to_book":  _f(rt.get("priceToBookRatioTTM")),

            # Profitability (as %)
            "gross_margin":     _pct(rt.get("grossProfitMarginTTM")),
            "operating_margin": _pct(rt.get("operatingProfitMarginTTM")),
            "profit_margin":    _pct(rt.get("netProfitMarginTTM")),
            "roe":              _pct(rt.get("returnOnEquityTTM")),
            "roa":              _pct(rt.get("returnOnAssetsTTM")),

            # Growth (as %)
            "revenue_growth":  _pct_growth(_f(rev_curr), _f(rev_prev)),
            "earnings_growth": _pct_growth(_f(net_curr), _f(net_prev)),

            # Cash flow
            "free_cash_flow":  _f(cf.get("freeCashFlow")),
            "operating_cash":  _f(cf.get("operatingCashFlow")),

            # Balance sheet
            "total_debt":      _f(bs.get("totalDebt")),
            "total_cash":      _f(bs.get("cashAndCashEquivalents")),
            "debt_to_equity":  _f(rt.get("debtEquityRatioTTM")),
            "current_ratio":   _f(rt.get("currentRatioTTM")),
            "quick_ratio":     _f(rt.get("quickRatioTTM")),

            # Per-share
            "eps_trailing":    _f(km.get("netIncomePerShareTTM")),
            "eps_forward":     None,

            # Revenue
            "total_revenue":     _f(rev_curr),
            "revenue_per_share": _f(km.get("revenuePerShareTTM")),

            # Dividends
            "dividend_yield": _pct(rt.get("dividendYieldTTM")),
            "payout_ratio":   _pct(rt.get("payoutRatioTTM")),

            # Market
            "market_cap": _f(profile.get("mktCap")),
        }

    except Exception as exc:
        logger.error("get_fundamentals_fmp(%s) failed: %s", upper, exc)
        return {"ticker": upper, "error": str(exc)}
