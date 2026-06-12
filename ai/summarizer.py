"""
ai/summarizer.py
----------------
AI-powered news summarisation using Groq (primary) with Gemini fallback.

Provider priority:
  1. Groq  (free, 14,400 req/day, no credit card) — uses Llama 3.3 70B
  2. Gemini (google-genai) — fallback if GROQ_API_KEY not set

Set GROQ_API_KEY in Render environment for full AI features.
Get a free key at: https://console.groq.com
"""

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def _generate(prompt: str) -> str:
    """
    Call AI model and return raw text response.
    Tries Groq first (free, fast), then Gemini as fallback.
    Returns '' on failure.
    """
    # --- Try Groq first ---
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        text = _groq_generate(prompt, groq_key)
        if text:
            return text
        logger.warning("Groq call failed, trying Gemini fallback...")

    # --- Try Gemini as fallback ---
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key and gemini_key != "your_gemini_api_key_here":
        text = _gemini_generate(prompt, gemini_key)
        if text:
            return text

    logger.error("All AI providers failed. Set GROQ_API_KEY in environment.")
    return ""


def _groq_generate(prompt: str, api_key: str) -> str:
    """Call Groq API. Free tier: 14,400 req/day, no credit card needed."""
    try:
        from groq import Groq  # type: ignore
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1024,
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:
        logger.error("Groq generate failed: %s", exc)
        return ""


def _gemini_generate(prompt: str, api_key: str) -> str:
    """Call Gemini API (google-genai package). Fallback provider."""
    try:
        from google import genai  # type: ignore
        client = genai.Client(api_key=api_key)
        for model in ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash"]:
            try:
                resp = client.models.generate_content(model=model, contents=prompt)
                return resp.text or ""
            except Exception as exc:
                logger.warning("Gemini model %s failed: %s", model, exc)
                continue
        return ""
    except Exception as exc:
        logger.error("Gemini generate failed: %s", exc)
        return ""


def _parse_json(text: str) -> dict[str, Any]:
    """Strip markdown fences and parse JSON."""
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
# Fast local sentiment scorer — no API needed
# ---------------------------------------------------------------------------

def score_news_sentiment(title: str, description: str) -> str:
    """
    Keyword-based sentiment for one news article.
    Returns 'bullish', 'bearish', or 'neutral'. No API call, instant.
    """
    text = (title + " " + (description or "")).lower()
    bullish = [
        "surge", "soar", "rally", "beat", "record", "growth", "gain",
        "profit", "revenue", "upgrade", "outperform", "bullish", "strong",
        "rise", "higher", "positive", "buy", "partnership", "expansion",
        "breakthrough", "launch", "innovation", "demand", "exceed", "boost",
    ]
    bearish = [
        "fall", "drop", "plunge", "miss", "loss", "layoff", "cut", "decline",
        "lower", "bearish", "weak", "sell", "concern", "risk",
        "lawsuit", "fine", "penalty", "recall", "crash", "debt", "default",
        "investigation", "fraud", "warning", "downgrade", "disappoint",
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

_NO_KEY_MSG = (
    "ยังไม่ได้ตั้งค่า AI — "
    "กรุณาเพิ่ม GROQ_API_KEY ใน Render Environment "
    "(รับฟรีที่ console.groq.com)"
)


def summarize_news(
    ticker: str,
    company_name: str,
    news_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate structured Thai AI summary of recent stock news."""
    _placeholder: dict[str, Any] = {
        "bullet_points": [_NO_KEY_MSG],
        "overall_sentiment": "neutral",
        "key_themes": ["data unavailable"],
        "long_term_impact": "กรุณาตั้งค่า GROQ_API_KEY ใน Render เพื่อเปิดใช้งาน AI วิเคราะห์",
        "thai_summary": f"ไม่สามารถสรุปข่าวสำหรับ {ticker} ได้ในขณะนี้",
    }

    if not news_items:
        return {
            **_placeholder,
            "thai_summary": f"ไม่มีข่าวล่าสุดสำหรับ {ticker} ({company_name})",
            "bullet_points": [f"ไม่พบข่าวสำหรับ {ticker} ในช่วง 7 วันที่ผ่านมา"],
        }

    digest = "\n".join(
        f"- {a.get('title', '')}: {(a.get('description') or '')[:120]}"
        for a in news_items[:10]
    )

    prompt = f"""Analyse recent news about {company_name} ({ticker}) for Thai long-term NASDAQ investors.

NEWS:
{digest}

Reply ONLY with valid JSON (no markdown fences, no extra text):
{{
  "bullet_points": ["<Thai key point 1>", "<Thai key point 2>", "<Thai key point 3>"],
  "overall_sentiment": "<bullish|neutral|bearish>",
  "key_themes": ["<English theme 1>", "<English theme 2>"],
  "long_term_impact": "<2-3 Thai sentences about long-term investment impact>",
  "thai_summary": "<2-3 Thai sentence news summary>"
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
    """Generate weekly Thai portfolio analysis for all watchlist stocks."""
    _placeholder: dict[str, Any] = {
        "top_picks": [],
        "watch_list_summary": _NO_KEY_MSG,
        "market_outlook": "กรุณาตั้งค่า GROQ_API_KEY ใน Render เพื่อเปิดใช้งาน AI วิเคราะห์",
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
            "; ".join(i.get("title", "") for i in (s.get("news") or [])[:3])
        )
        for s in stocks_data
    )

    prompt = f"""You are a Thai stock analyst specialising in long-term NASDAQ investing.

WATCHLIST PERFORMANCE THIS WEEK:
{digest}

Reply ONLY with valid JSON (no markdown):
{{
  "top_picks": ["<TICKER1>", "<TICKER2>"],
  "watch_list_summary": "<2-3 Thai sentences overview of all watchlist stocks this week>",
  "market_outlook": "<2-3 Thai sentences market outlook for long-term investors>"
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
