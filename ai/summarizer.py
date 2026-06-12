"""
ai/summarizer.py
----------------
Google Gemini AI news summarisation using the new google-genai package.
Uses gemini-2.0-flash-lite for generous free-tier quota.
"""

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _make_client():
    """Create a google-genai client. Returns None if key missing."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        logger.warning("GEMINI_API_KEY not set — AI features disabled.")
        return None, None
    try:
        from google import genai  # type: ignore
        client = genai.Client(api_key=api_key)
        # Try models in order of free-tier quota generosity
        for model in ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash"]:
            return client, model
    except Exception as exc:
        logger.error("Failed to create Gemini client: %s", exc)
        return None, None


def _generate(prompt: str) -> str:
    """Call Gemini and return raw text. Returns '' on any failure."""
    client, model = _make_client()
    if client is None:
        return ""
    try:
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text or ""
    except Exception as exc:
        logger.error("Gemini generate failed (model=%s): %s", model, exc)
        return ""


def _parse_json(text: str) -> dict[str, Any]:
    """Strip markdown fences and parse JSON from Gemini response."""
    try:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            start = 1
            end = len(lines) - 1 if lines[-1].strip().startswith("```") else len(lines)
            cleaned = "\n".join(lines[start:end]).strip()
        return json.loads(cleaned)
    except Exception as exc:
        logger.error("JSON parse failed: %s | raw: %.200s", exc, text)
        return {}


# ---------------------------------------------------------------------------
# Fast local sentiment scorer — no API, instant
# ---------------------------------------------------------------------------

def score_news_sentiment(title: str, description: str) -> str:
    """
    Keyword-based sentiment for one news article.
    Returns 'bullish', 'bearish', or 'neutral'. No API call.
    """
    text = (title + " " + (description or "")).lower()
    bullish = [
        "surge", "soar", "rally", "beat", "record", "growth", "gain",
        "profit", "revenue", "upgrade", "outperform", "bullish", "strong",
        "rise", "up", "higher", "positive", "buy", "partnership", "expansion",
        "breakthrough", "launch", "innovation", "demand", "exceed",
    ]
    bearish = [
        "fall", "drop", "plunge", "miss", "loss", "layoff", "cut", "decline",
        "down", "lower", "bearish", "weak", "sell", "concern", "risk",
        "lawsuit", "fine", "penalty", "recall", "crash", "debt", "default",
        "investigation", "fraud", "warning", "downgrade", "miss",
    ]
    b = sum(1 for w in bullish if w in text)
    r = sum(1 for w in bearish if w in text)
    if b > r + 1:
        return "bullish"
    if r > b + 1:
        return "bearish"
    return "neutral"


# ---------------------------------------------------------------------------
# Public AI functions
# ---------------------------------------------------------------------------

def summarize_news(
    ticker: str,
    company_name: str,
    news_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate structured Thai AI summary of recent stock news."""
    _placeholder: dict[str, Any] = {
        "bullet_points": [
            "ไม่สามารถวิเคราะห์ได้ — Gemini API quota อาจหมด หรือ key ไม่ถูกต้อง",
        ],
        "overall_sentiment": "neutral",
        "key_themes": ["data unavailable"],
        "long_term_impact": "ไม่สามารถวิเคราะห์ได้ในขณะนี้ กรุณาลองใหม่ในภายหลัง",
        "thai_summary": f"ไม่สามารถสรุปข่าวสำหรับ {ticker} ได้ในขณะนี้",
    }

    if not news_items:
        return {
            **_placeholder,
            "thai_summary": f"ไม่มีข่าวล่าสุดสำหรับ {ticker} ({company_name}) ในช่วง 7 วัน",
            "bullet_points": [f"ไม่พบข่าวสำหรับ {ticker}"],
        }

    digest = "\n".join(
        f"- {a.get('title','')}: {(a.get('description') or '')[:120]}"
        for a in news_items[:10]
    )

    prompt = f"""Analyse recent news about {company_name} ({ticker}) for Thai long-term investors.

NEWS:
{digest}

Reply ONLY with valid JSON (no markdown fences):
{{
  "bullet_points": ["<Thai point 1>","<Thai point 2>","<Thai point 3>"],
  "overall_sentiment": "<bullish|neutral|bearish>",
  "key_themes": ["<English theme 1>","<English theme 2>"],
  "long_term_impact": "<2-3 Thai sentences>",
  "thai_summary": "<2-3 Thai sentences>"
}}"""

    raw = _generate(prompt)
    if not raw:
        return _placeholder

    data = _parse_json(raw)
    if not data:
        return _placeholder

    return {
        "bullet_points":     data.get("bullet_points", _placeholder["bullet_points"]),
        "overall_sentiment": data.get("overall_sentiment", "neutral"),
        "key_themes":        data.get("key_themes", []),
        "long_term_impact":  data.get("long_term_impact", ""),
        "thai_summary":      data.get("thai_summary", ""),
    }


def analyze_watchlist_for_weekly(
    stocks_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate weekly Thai portfolio analysis."""
    _placeholder: dict[str, Any] = {
        "top_picks": [],
        "watch_list_summary": "ไม่สามารถวิเคราะห์ได้ — Gemini API quota อาจหมด กรุณาลองใหม่ในวันถัดไป",
        "market_outlook": "ไม่สามารถวิเคราะห์ตลาดได้ในขณะนี้",
    }

    if not stocks_data:
        return {
            "top_picks": [],
            "watch_list_summary": "ไม่มีหุ้นใน watchlist กรุณาเพิ่มหุ้นก่อน",
            "market_outlook": "กรุณาเพิ่มหุ้นลงใน watchlist เพื่อรับการวิเคราะห์รายสัปดาห์",
        }

    digest = "\n".join(
        "{}: {:+.2f}% | {}".format(
            s.get("ticker"), s.get("price_change", 0),
            "; ".join(i.get("title","") for i in (s.get("news") or [])[:2])
        )
        for s in stocks_data
    )

    prompt = f"""You are a Thai stock analyst for NASDAQ long-term investors.

WATCHLIST THIS WEEK:
{digest}

Reply ONLY with valid JSON (no markdown):
{{
  "top_picks": ["<TICKER1>","<TICKER2>"],
  "watch_list_summary": "<2-3 Thai sentences>",
  "market_outlook": "<2-3 Thai sentences>"
}}"""

    raw = _generate(prompt)
    if not raw:
        return _placeholder

    data = _parse_json(raw)
    if not data:
        return _placeholder

    return {
        "top_picks":          data.get("top_picks", []),
        "watch_list_summary": data.get("watch_list_summary", ""),
        "market_outlook":     data.get("market_outlook", ""),
    }
