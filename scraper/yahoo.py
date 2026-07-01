"""
scraper/yahoo.py
----------------
Wrappers around the yfinance library for stock data and news retrieval,
plus a local-list-based ticker search utility.
"""

import logging
from datetime import datetime
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Popular NASDAQ / US-listed stock universe used for the search function.
# Extend this list freely; it is filtered client-side so no API key is needed.
# ---------------------------------------------------------------------------
POPULAR_STOCKS: list[dict[str, str]] = [
    {"ticker": "AAPL",  "name": "Apple Inc."},
    {"ticker": "MSFT",  "name": "Microsoft Corporation"},
    {"ticker": "NVDA",  "name": "NVIDIA Corporation"},
    {"ticker": "GOOGL", "name": "Alphabet Inc. Class A"},
    {"ticker": "GOOG",  "name": "Alphabet Inc. Class C"},
    {"ticker": "AMZN",  "name": "Amazon.com Inc."},
    {"ticker": "META",  "name": "Meta Platforms Inc."},
    {"ticker": "TSLA",  "name": "Tesla Inc."},
    {"ticker": "AMD",   "name": "Advanced Micro Devices Inc."},
    {"ticker": "INTC",  "name": "Intel Corporation"},
    {"ticker": "QCOM",  "name": "Qualcomm Inc."},
    {"ticker": "AVGO",  "name": "Broadcom Inc."},
    {"ticker": "ADBE",  "name": "Adobe Inc."},
    {"ticker": "CRM",   "name": "Salesforce Inc."},
    {"ticker": "NFLX",  "name": "Netflix Inc."},
    {"ticker": "PYPL",  "name": "PayPal Holdings Inc."},
    {"ticker": "MU",    "name": "Micron Technology Inc."},
    {"ticker": "LRCX",  "name": "Lam Research Corporation"},
    {"ticker": "AMAT",  "name": "Applied Materials Inc."},
    {"ticker": "KLAC",  "name": "KLA Corporation"},
    {"ticker": "MRVL",  "name": "Marvell Technology Inc."},
    {"ticker": "PANW",  "name": "Palo Alto Networks Inc."},
    {"ticker": "CRWD",  "name": "CrowdStrike Holdings Inc."},
    {"ticker": "ZS",    "name": "Zscaler Inc."},
    {"ticker": "DDOG",  "name": "Datadog Inc."},
    {"ticker": "SNOW",  "name": "Snowflake Inc."},
    {"ticker": "PLTR",  "name": "Palantir Technologies Inc."},
    {"ticker": "ABNB",  "name": "Airbnb Inc."},
    {"ticker": "UBER",  "name": "Uber Technologies Inc."},
    {"ticker": "LYFT",  "name": "Lyft Inc."},
    {"ticker": "COIN",  "name": "Coinbase Global Inc."},
    {"ticker": "HOOD",  "name": "Robinhood Markets Inc."},
    {"ticker": "SOFI",  "name": "SoFi Technologies Inc."},
    {"ticker": "RBLX",  "name": "Roblox Corporation"},
    {"ticker": "U",     "name": "Unity Software Inc."},
    {"ticker": "TTWO",  "name": "Take-Two Interactive Software Inc."},
    {"ticker": "EA",    "name": "Electronic Arts Inc."},
    {"ticker": "ATVI",  "name": "Activision Blizzard Inc."},
    {"ticker": "DOCU",  "name": "DocuSign Inc."},
    {"ticker": "ZM",    "name": "Zoom Video Communications Inc."},
    {"ticker": "OKTA",  "name": "Okta Inc."},
    {"ticker": "NET",   "name": "Cloudflare Inc."},
    {"ticker": "FSLY",  "name": "Fastly Inc."},
    {"ticker": "TWLO",  "name": "Twilio Inc."},
    {"ticker": "SHOP",  "name": "Shopify Inc."},
    {"ticker": "SQ",    "name": "Block Inc."},
    {"ticker": "ROKU",  "name": "Roku Inc."},
    {"ticker": "SPOT",  "name": "Spotify Technology SA"},
    {"ticker": "PINS",  "name": "Pinterest Inc."},
    {"ticker": "SNAP",  "name": "Snap Inc."},
    {"ticker": "DBX",   "name": "Dropbox Inc."},
    {"ticker": "BOX",   "name": "Box Inc."},
    {"ticker": "WDAY",  "name": "Workday Inc."},
    {"ticker": "NOW",   "name": "ServiceNow Inc."},
    {"ticker": "TEAM",  "name": "Atlassian Corporation"},
    {"ticker": "ZEN",   "name": "Zendesk Inc."},
    {"ticker": "HUBS",  "name": "HubSpot Inc."},
    {"ticker": "BILL",  "name": "Bill.com Holdings Inc."},
    {"ticker": "MNDY",  "name": "monday.com Ltd."},
    {"ticker": "GTLB",  "name": "GitLab Inc."},
    {"ticker": "PATH",  "name": "UiPath Inc."},
    {"ticker": "SMAR",  "name": "Smartsheet Inc."},
    {"ticker": "MDB",   "name": "MongoDB Inc."},
    {"ticker": "ESTC",  "name": "Elastic NV"},
    {"ticker": "DOMO",  "name": "Domo Inc."},
    {"ticker": "SUMO",  "name": "Sumo Logic Inc."},
    {"ticker": "SPLK",  "name": "Splunk Inc."},
    {"ticker": "VEEV",  "name": "Veeva Systems Inc."},
    {"ticker": "APPN",  "name": "Appian Corporation"},
    {"ticker": "ALTR",  "name": "Altair Engineering Inc."},
    {"ticker": "NCNO",  "name": "nCino Inc."},
    {"ticker": "DSGX",  "name": "The Descartes Systems Group Inc."},
    {"ticker": "AFRM",  "name": "Affirm Holdings Inc."},
    {"ticker": "UPST",  "name": "Upstart Holdings Inc."},
    {"ticker": "BNPL",  "name": "Sezzle Inc."},
    {"ticker": "OPEN",  "name": "Opendoor Technologies Inc."},
    {"ticker": "CVNA",  "name": "Carvana Co."},
    {"ticker": "VROOM", "name": "Vroom Inc."},
    {"ticker": "ANGI",  "name": "Angi Inc."},
    {"ticker": "IAC",   "name": "IAC Inc."},
    {"ticker": "MTCH",  "name": "Match Group Inc."},
    {"ticker": "BMBL",  "name": "Bumble Inc."},
    {"ticker": "DASH",  "name": "DoorDash Inc."},
    {"ticker": "CART",  "name": "Instacart (Maplebear Inc.)"},
    {"ticker": "ARM",   "name": "Arm Holdings plc"},
    {"ticker": "SMCI",  "name": "Super Micro Computer Inc."},
    {"ticker": "DELL",  "name": "Dell Technologies Inc."},
    {"ticker": "HPQ",   "name": "HP Inc."},
    {"ticker": "HPE",   "name": "Hewlett Packard Enterprise Co."},
    {"ticker": "CSCO",  "name": "Cisco Systems Inc."},
    {"ticker": "ORCL",  "name": "Oracle Corporation"},
    {"ticker": "IBM",   "name": "International Business Machines Corp."},
    {"ticker": "ACN",   "name": "Accenture plc"},
    {"ticker": "INTU",  "name": "Intuit Inc."},
    {"ticker": "ANSS",  "name": "ANSYS Inc."},
    {"ticker": "CDNS",  "name": "Cadence Design Systems Inc."},
    {"ticker": "SNPS",  "name": "Synopsys Inc."},
    {"ticker": "MCHP",  "name": "Microchip Technology Inc."},
    {"ticker": "ON",    "name": "ON Semiconductor Corporation"},
    {"ticker": "SWKS",  "name": "Skyworks Solutions Inc."},
    {"ticker": "QRVO",  "name": "Qorvo Inc."},
    {"ticker": "TXN",   "name": "Texas Instruments Inc."},
    {"ticker": "ADI",   "name": "Analog Devices Inc."},
    {"ticker": "MXIM",  "name": "Maxim Integrated Products Inc."},
    {"ticker": "XLNX",  "name": "Xilinx Inc."},
    {"ticker": "IDXX",  "name": "IDEXX Laboratories Inc."},
    {"ticker": "ILMN",  "name": "Illumina Inc."},
    {"ticker": "VRTX",  "name": "Vertex Pharmaceuticals Inc."},
    {"ticker": "REGN",  "name": "Regeneron Pharmaceuticals Inc."},
    {"ticker": "BIIB",  "name": "Biogen Inc."},
    {"ticker": "GILD",  "name": "Gilead Sciences Inc."},
    {"ticker": "AMGN",  "name": "Amgen Inc."},
    {"ticker": "ISRG",  "name": "Intuitive Surgical Inc."},
    {"ticker": "ALGN",  "name": "Align Technology Inc."},
    {"ticker": "DXCM",  "name": "DexCom Inc."},
    {"ticker": "PODD",  "name": "Insulet Corporation"},
    {"ticker": "NTRA",  "name": "Natera Inc."},
    {"ticker": "GH",    "name": "Guardant Health Inc."},
    {"ticker": "NVAX",  "name": "Novavax Inc."},
    {"ticker": "MRNA",  "name": "Moderna Inc."},
    {"ticker": "BNTX",  "name": "BioNTech SE"},
    {"ticker": "CRSP",  "name": "CRISPR Therapeutics AG"},
    {"ticker": "EDIT",  "name": "Editas Medicine Inc."},
    {"ticker": "NTLA",  "name": "Intellia Therapeutics Inc."},
]


# ---------------------------------------------------------------------------
# In-memory metadata cache: name / sector / pe_ratio from FMP profile.
# Avoids calling yfinance .info (which is rate-limited) on every request.
# TTL: 6 hours — metadata rarely changes during the trading day.
# ---------------------------------------------------------------------------
import time as _time

_META_CACHE: dict[str, dict] = {}   # ticker -> {name, sector, pe_ratio, expires}
_META_TTL = 6 * 3600                # seconds


def _get_meta(upper: str) -> dict[str, Any]:
    """Return cached metadata or fetch from FMP profile (then yfinance as last resort)."""
    cached = _META_CACHE.get(upper)
    if cached and cached['expires'] > _time.time():
        return cached

    meta: dict[str, Any] = {'name': upper, 'sector': None, 'pe_ratio': None}

    # Try FMP profile first (free, not rate-limited)
    try:
        import os, requests as _req
        key = os.getenv('FMP_API_KEY', '')
        if key:
            r = _req.get(
                f'https://financialmodelingprep.com/api/v3/profile/{upper}',
                params={'apikey': key}, timeout=6,
            )
            if r.status_code == 200:
                data = r.json()
                if data:
                    p = data[0]
                    meta['name']   = p.get('companyName') or upper
                    meta['sector'] = p.get('sector')
                    # FMP profile has pe from ratios endpoint; skip to keep calls low
                    _META_CACHE[upper] = {**meta, 'expires': _time.time() + _META_TTL}
                    return meta
    except Exception as exc:
        logger.debug("FMP profile fetch failed for %s: %s", upper, exc)

    # Last resort: yfinance .info (may be rate-limited)
    try:
        import yfinance as _yf
        info = _yf.Ticker(upper).info or {}
        meta['name']     = info.get('longName') or info.get('shortName') or upper
        meta['sector']   = info.get('sector')
        meta['pe_ratio'] = info.get('trailingPE')
    except Exception as info_exc:
        logger.warning("get_stock_info(%s) .info failed (non-fatal): %s", upper, info_exc)

    _META_CACHE[upper] = {**meta, 'expires': _time.time() + _META_TTL}
    return meta


def get_stock_info(ticker: str) -> dict[str, Any]:
    """
    Fetch current price and metadata for a ticker.
    Price: yfinance fast_info (lightweight, not rate-limited).
    Metadata (name/sector): FMP profile cache → yfinance .info fallback.
    """
    upper = ticker.upper()
    try:
        stock = yf.Ticker(upper)
        fast  = stock.fast_info

        price:        float | None = getattr(fast, 'last_price', None)
        prev_close:   float | None = getattr(fast, 'previous_close', None)
        week_52_high: float | None = getattr(fast, 'year_high', None)
        week_52_low:  float | None = getattr(fast, 'year_low', None)
        market_cap:   float | None = getattr(fast, 'market_cap', None)
        volume:       float | None = getattr(fast, 'three_month_average_volume', None)

        change:     float = round(float(price or 0) - float(prev_close or 0), 4) if price and prev_close else 0.0
        change_pct: float = round((change / float(prev_close)) * 100, 2) if prev_close else 0.0

        if price is None:
            raise ValueError(f"No price data returned by yfinance for {upper}")

        meta = _get_meta(upper)

        return {
            'ticker':       upper,
            'name':         meta['name'],
            'price':        round(float(price), 4),
            'change':       change,
            'change_pct':   change_pct,
            'market_cap':   market_cap,
            'sector':       meta['sector'],
            'pe_ratio':     meta['pe_ratio'],
            'week_52_high': week_52_high,
            'week_52_low':  week_52_low,
            'volume':       volume,
        }

    except Exception as exc:
        logger.error("get_stock_info(%s) failed: %s", upper, exc)
        return {
            'ticker':     upper,
            'error':      str(exc),
            'price':      None,
            'change':     None,
            'change_pct': None,
        }


def get_fundamentals(ticker: str) -> dict[str, Any]:
    """
    Fetch fundamentals — tries FMP first (more reliable on Render),
    falls back to yfinance if FMP key is missing or call fails.

    Returns key metrics for long-term investors:
    - Profitability: gross margin, operating margin, net margin, ROE, ROA
    - Valuation: P/E, forward P/E, PEG, P/S, P/B
    - Growth: revenue growth, earnings growth YoY
    - Cash Flow: free cash flow, operating cash flow
    - Balance Sheet: debt/equity, current ratio, cash on hand
    - Earnings: trailing EPS, forward EPS, next earnings date
    """
    upper = ticker.upper()

    # Try FMP first — it's reliable on Render's IPs
    try:
        from scraper.fmp import get_fundamentals_fmp, FMP_API_KEY
        if FMP_API_KEY:
            result = get_fundamentals_fmp(upper)
            if "error" not in result:
                logger.info("get_fundamentals(%s): served from FMP", upper)
                return result
            logger.warning("FMP returned error for %s, falling back to yfinance: %s", upper, result.get("error"))
    except Exception as fmp_exc:
        logger.warning("FMP call failed for %s, falling back to yfinance: %s", upper, fmp_exc)

    try:
        stock = yf.Ticker(upper)
        info = stock.info or {}

        # ---------- Helper: safe float ----------
        def _f(key: str) -> float | None:
            v = info.get(key)
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        def _pct(key: str) -> float | None:
            v = _f(key)
            return round(v * 100, 2) if v is not None else None

        # ---------- Earnings dates ----------
        try:
            cal = stock.calendar
            next_earnings = None
            if cal is not None:
                # Newer yfinance returns dict with 'Earnings Date' key as list
                if isinstance(cal, dict):
                    ed = cal.get('Earnings Date') or cal.get('earningsDate')
                    if ed:
                        next_earnings = str(ed[0]) if isinstance(ed, list) else str(ed)
                elif hasattr(cal, 'columns') and 'Earnings Date' in cal.columns:
                    next_earnings = str(cal['Earnings Date'].iloc[0])
        except Exception:
            next_earnings = None

        # ---------- Assemble ----------
        return {
            "ticker": upper,
            "name":   info.get("longName") or info.get("shortName") or upper,

            # Valuation
            "pe_trailing":      _f("trailingPE"),
            "pe_forward":       _f("forwardPE"),
            "peg_ratio":        _f("pegRatio"),
            "price_to_sales":   _f("priceToSalesTrailing12Months"),
            "price_to_book":    _f("priceToBook"),

            # Profitability (as %)
            "gross_margin":     _pct("grossMargins"),
            "operating_margin": _pct("operatingMargins"),
            "profit_margin":    _pct("profitMargins"),
            "roe":              _pct("returnOnEquity"),
            "roa":              _pct("returnOnAssets"),

            # Growth (as %)
            "revenue_growth":   _pct("revenueGrowth"),
            "earnings_growth":  _pct("earningsGrowth"),

            # Cash flow (raw dollars)
            "free_cash_flow":   _f("freeCashflow"),
            "operating_cash":   _f("operatingCashflow"),

            # Balance sheet
            "total_debt":       _f("totalDebt"),
            "total_cash":       _f("totalCash"),
            "debt_to_equity":   _f("debtToEquity"),
            "current_ratio":    _f("currentRatio"),
            "quick_ratio":      _f("quickRatio"),

            # Per-share
            "eps_trailing":     _f("trailingEps"),
            "eps_forward":      _f("forwardEps"),

            # Revenue
            "total_revenue":    _f("totalRevenue"),
            "revenue_per_share":_f("revenuePerShare"),

            # Dividends
            "dividend_yield":   _pct("dividendYield"),
            "payout_ratio":     _pct("payoutRatio"),

            # Meta
            "sector":           info.get("sector"),
            "industry":         info.get("industry"),
            "employee_count":   info.get("fullTimeEmployees"),
            "next_earnings":    next_earnings,
            "fiscal_year_end":  info.get("fiscalYearEnd"),
        }

    except Exception as exc:
        logger.error("get_fundamentals(%s) failed: %s", upper, exc)
        return {"ticker": upper, "error": str(exc)}


def get_stock_news(ticker: str) -> list[dict[str, Any]]:
    """
    Retrieve recent news articles for a ticker from yfinance.

    Parameters
    ----------
    ticker : str
        The stock ticker symbol.

    Returns
    -------
    list[dict]
        Each item has keys: title, description, url, source, published_at.
        Returns an empty list on failure.
    """
    try:
        stock = yf.Ticker(ticker.upper())
        raw_news = stock.news or []
        result: list[dict[str, Any]] = []

        for item in raw_news:
            # yfinance news structure changed over versions; handle both
            content = item.get("content", item)

            # Extract publication timestamp
            pub_ts = (
                content.get("pubDate")
                or content.get("provider_publish_time")
                or item.get("providerPublishTime")
            )
            if isinstance(pub_ts, int):
                pub_ts = datetime.utcfromtimestamp(pub_ts).isoformat()

            # Extract source name
            provider = content.get("provider", {})
            source_name = (
                provider.get("displayName")
                if isinstance(provider, dict)
                else content.get("source", "Yahoo Finance")
            )

            # Extract thumbnail / image URL
            thumbnail = content.get("thumbnail") or {}
            resolutions = thumbnail.get("resolutions", []) if isinstance(thumbnail, dict) else []
            image_url = resolutions[0].get("url") if resolutions else None

            result.append(
                {
                    "title":        content.get("title") or item.get("title", ""),
                    "description":  content.get("summary") or content.get("description", ""),
                    "url":          content.get("canonicalUrl", {}).get("url")
                                    if isinstance(content.get("canonicalUrl"), dict)
                                    else content.get("link") or item.get("link", ""),
                    "source":       source_name or "Yahoo Finance",
                    "published_at": pub_ts or "",
                    "image_url":    image_url,
                }
            )

        return result

    except Exception as exc:
        logger.error("get_stock_news(%s) failed: %s", ticker, exc)
        return []


import requests

def search_stocks(query: str) -> list[dict[str, str]]:
    """
    Search using Yahoo Finance API directly for full market coverage,
    and fallback to local list if it fails.
    """
    if not query or len(query.strip()) == 0:
        return POPULAR_STOCKS[:20]

    q = query.strip()
    matches: list[dict[str, str]] = []

    # 1. Try Yahoo Finance live search API
    try:
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        params = {'q': q, 'quotesCount': 15, 'newsCount': 0}
        resp = requests.get(url, headers=headers, params=params, timeout=5)
        if resp.status_code == 200:
            quotes = resp.json().get('quotes', [])
            for quote in quotes:
                # We only want equities and ETFs, no mutual funds or crypto if they are weird
                if quote.get('quoteType') in ('EQUITY', 'ETF', 'MUTUALFUND'):
                    matches.append({
                        "ticker": quote.get("symbol", ""),
                        "name": quote.get("shortname") or quote.get("longname") or quote.get("symbol", "")
                    })
            if matches:
                return matches
    except Exception as exc:
        logger.warning("Yahoo API search failed, falling back to local list: %s", exc)

    # 2. Fallback to local POPULAR_STOCKS list
    qu = q.upper()
    for stock in POPULAR_STOCKS:
        if qu in stock["ticker"].upper() or qu in stock["name"].upper():
            matches.append(stock)
        if len(matches) >= 20:
            break

    if matches:
        matches.sort(key=lambda s: (0 if s["ticker"].startswith(qu) else 1, s["ticker"]))

    return matches
