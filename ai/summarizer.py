"""
ai/summarizer.py
----------------
Google Gemini-powered news summarisation and watchlist analysis.

All outputs are bilingual: key investor insight is delivered in Thai,
which is the target audience for this dashboard.

If GEMINI_API_KEY is not configured the functions return structured
placeholder data so the rest of the application continues to work.
"""

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
_MODEL_NAME: str = "gemini-1.5-flash"


def _get_model():
    """
    Lazily initialise and return a Gemini GenerativeModel instance.

    Returns
    -------
    google.generativeai.GenerativeModel | None
        Configured model, or None if the key is absent / import fails.
    """
    if not _GEMINI_API_KEY or _GEMINI_API_KEY == "your_gemini_api_key_here":
        logger.warning(
            "GEMINI_API_KEY is not configured. "
            "AI summaries will return placeholder data."
        )
        return None

    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=_GEMINI_API_KEY)
        return genai.GenerativeModel(_MODEL_NAME)
    except Exception as exc:
        logger.error("Failed to initialise Gemini model: %s", exc)
        return None


def _parse_json_response(text: str) -> dict[str, Any]:
    """
    Extract the first JSON object from a Gemini response string.

    Gemini sometimes wraps JSON in markdown code fences; this helper
    strips them before parsing.

    Parameters
    ----------
    text : str
        Raw text returned by the model.

    Returns
    -------
    dict
        Parsed JSON dict, or an empty dict on failure.
    """
    try:
        # Strip markdown code fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        return json.loads(cleaned)
    except Exception as exc:
        logger.error("Failed to parse Gemini JSON response: %s\nRaw: %s", exc, text[:500])
        return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarize_news(
    ticker: str,
    company_name: str,
    news_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Generate a structured AI summary of recent news for a stock.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol (e.g. 'AAPL').
    company_name : str
        Human-readable company name.
    news_items : list[dict]
        List of news dicts, each with at minimum 'title' and
        optionally 'description'.

    Returns
    -------
    dict
        Keys:
          - bullet_points (list[str]): 3-5 key takeaways in Thai.
          - overall_sentiment (str): 'bullish' | 'neutral' | 'bearish'.
          - key_themes (list[str]): English topic labels.
          - long_term_impact (str): Thai assessment for long-term investors.
          - thai_summary (str): 2-3 sentence Thai overview.
    """
    # --- Placeholder when no API key ---
    _placeholder: dict[str, Any] = {
        "bullet_points": [
            f"ไม่มีข้อมูล API สำหรับ {ticker}",
            "กรุณาตั้งค่า GEMINI_API_KEY ใน .env",
        ],
        "overall_sentiment": "neutral",
        "key_themes": ["data unavailable"],
        "long_term_impact": "ไม่สามารถวิเคราะห์ได้เนื่องจากไม่มี API key",
        "thai_summary": f"ไม่พบ API key สำหรับ Gemini กรุณาตั้งค่า GEMINI_API_KEY ใน .env เพื่อรับการวิเคราะห์สำหรับ {ticker}",
    }

    model = _get_model()
    if model is None:
        return _placeholder

    if not news_items:
        return {
            **_placeholder,
            "thai_summary": f"ไม่มีข่าวล่าสุดสำหรับ {ticker} ({company_name})",
            "bullet_points": [f"ไม่พบข่าวสำหรับ {ticker} ในช่วงเวลานี้"],
        }

    # Build a concise news digest for the prompt (keep under token limit)
    news_digest = "\n".join(
        f"- {item.get('title', '')} | {item.get('description', '')[:200]}"
        for item in news_items[:15]
    )

    prompt = f"""
You are a financial analyst assistant. Analyse the following recent news about {company_name} ({ticker}).

NEWS:
{news_digest}

Respond ONLY with a valid JSON object (no markdown fences, no extra text) with this exact structure:
{{
  "bullet_points": ["<Thai point 1>", "<Thai point 2>", "<Thai point 3>"],
  "overall_sentiment": "<bullish|neutral|bearish>",
  "key_themes": ["<English theme 1>", "<English theme 2>"],
  "long_term_impact": "<2-3 sentences in Thai for long-term investors>",
  "thai_summary": "<2-3 sentences Thai summary of the news>"
}}

Rules:
- bullet_points must be 3-5 items, each in Thai language.
- overall_sentiment must be exactly one of: bullish, neutral, bearish.
- key_themes must be in English and reflect the main topics.
- long_term_impact must be in Thai.
- thai_summary must be in Thai.
""".strip()

    try:
        response = model.generate_content(prompt)
        data = _parse_json_response(response.text)
        if not data:
            return _placeholder

        # Validate / fill missing keys
        return {
            "bullet_points":     data.get("bullet_points", _placeholder["bullet_points"]),
            "overall_sentiment": data.get("overall_sentiment", "neutral"),
            "key_themes":        data.get("key_themes", []),
            "long_term_impact":  data.get("long_term_impact", ""),
            "thai_summary":      data.get("thai_summary", ""),
        }

    except Exception as exc:
        logger.error("summarize_news(%s) Gemini call failed: %s", ticker, exc)
        return _placeholder


def analyze_watchlist_for_weekly(
    stocks_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Generate a weekly portfolio analysis for all watchlist stocks.

    Parameters
    ----------
    stocks_data : list[dict]
        Each element should contain at minimum:
          - ticker (str)
          - price_change (float, weekly % change)
          - news (list[dict], recent news items)

    Returns
    -------
    dict
        Keys:
          - top_picks (list[str]): recommended tickers for the week.
          - watch_list_summary (str): Thai overview of the watchlist.
          - market_outlook (str): Thai market outlook paragraph.
    """
    _placeholder: dict[str, Any] = {
        "top_picks": [],
        "watch_list_summary": "กรุณาตั้งค่า GEMINI_API_KEY เพื่อรับการวิเคราะห์รายสัปดาห์",
        "market_outlook": "ไม่สามารถวิเคราะห์ตลาดได้เนื่องจากไม่มี API key",
    }

    model = _get_model()
    if model is None:
        return _placeholder

    if not stocks_data:
        return {
            "top_picks": [],
            "watch_list_summary": "ไม่มีหุ้นใน watchlist",
            "market_outlook": "กรุณาเพิ่มหุ้นลงใน watchlist ก่อนทำการวิเคราะห์",
        }

    # Build a compact stock digest
    stock_digest_parts: list[str] = []
    for s in stocks_data:
        ticker = s.get("ticker", "N/A")
        change = s.get("price_change", 0.0)
        headlines = "; ".join(
            item.get("title", "") for item in (s.get("news") or [])[:3]
        )
        stock_digest_parts.append(
            f"{ticker}: {change:+.2f}% this week. Headlines: {headlines}"
        )

    stock_digest = "\n".join(stock_digest_parts)

    prompt = f"""
You are a Thai stock market analyst. Review the following watchlist performance for the past week and provide insights in Thai.

WATCHLIST PERFORMANCE:
{stock_digest}

Respond ONLY with a valid JSON object (no markdown fences) with this structure:
{{
  "top_picks": ["<TICKER1>", "<TICKER2>"],
  "watch_list_summary": "<2-3 sentences Thai overview of all watchlist stocks>",
  "market_outlook": "<2-3 sentences Thai market outlook paragraph>"
}}

Rules:
- top_picks: list of 1-3 ticker symbols that look most promising this week.
- watch_list_summary: must be in Thai.
- market_outlook: must be in Thai.
""".strip()

    try:
        response = model.generate_content(prompt)
        data = _parse_json_response(response.text)
        if not data:
            return _placeholder

        return {
            "top_picks":          data.get("top_picks", []),
            "watch_list_summary": data.get("watch_list_summary", ""),
            "market_outlook":     data.get("market_outlook", ""),
        }

    except Exception as exc:
        logger.error("analyze_watchlist_for_weekly() Gemini call failed: %s", exc)
        return _placeholder
