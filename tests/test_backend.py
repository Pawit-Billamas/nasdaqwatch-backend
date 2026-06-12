"""
tests/test_backend.py
---------------------
Automated tests for NasdaqWatch backend.
Run with: python -m pytest tests/ -v
"""

import json
import os
import sys

import pytest

# Make sure the backend root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# 1. Sentiment scorer tests (no network, no API key needed)
# ---------------------------------------------------------------------------

class TestSentimentScorer:
    """score_news_sentiment — fast keyword-based scorer."""

    def setup_method(self):
        from ai.summarizer import score_news_sentiment
        self.score = score_news_sentiment

    def test_bullish_keyword(self):
        result = self.score("Apple stock surges to record high", "Revenue beat expectations")
        assert result == "bullish", f"Expected bullish, got {result}"

    def test_bearish_keyword(self):
        result = self.score("Intel shares plunge after massive layoffs", "Company misses earnings")
        assert result == "bearish", f"Expected bearish, got {result}"

    def test_neutral_mixed(self):
        result = self.score("NVIDIA reports quarterly results", "Mixed signals from the market")
        assert result in ("neutral", "bullish", "bearish")

    def test_empty_input(self):
        result = self.score("", "")
        assert result == "neutral"

    def test_returns_valid_value(self):
        for title in ["stock gains momentum", "market crashes hard", "steady trading day"]:
            result = self.score(title, "")
            assert result in ("bullish", "neutral", "bearish"), f"Invalid: {result}"


# ---------------------------------------------------------------------------
# 2. Yahoo scraper tests (network required, graceful if offline)
# ---------------------------------------------------------------------------

class TestYahooScraper:
    """get_stock_info and get_stock_news from yfinance."""

    def setup_method(self):
        from scraper.yahoo import get_stock_info, get_stock_news, search_stocks
        self.get_info = get_stock_info
        self.get_news = get_stock_news
        self.search = search_stocks

    def test_get_stock_info_returns_dict(self):
        result = self.get_info("AAPL")
        assert isinstance(result, dict), "Should return dict"
        assert "ticker" in result
        assert result["ticker"] == "AAPL"

    def test_get_stock_info_has_price_or_error(self):
        result = self.get_info("AAPL")
        # Either has a real price OR an error key
        assert "price" in result or "error" in result

    def test_get_stock_info_invalid_ticker(self):
        result = self.get_info("XYZXYZXYZ999")
        assert isinstance(result, dict)
        # Should NOT raise, just return error dict or None price
        assert result.get("ticker") == "XYZXYZXYZ999"

    def test_get_stock_news_returns_list(self):
        result = self.get_news("MSFT")
        assert isinstance(result, list), "Should return list"

    def test_get_stock_news_item_structure(self):
        result = self.get_news("NVDA")
        if result:
            item = result[0]
            assert "title" in item
            assert "url" in item

    def test_search_stocks_basic(self):
        result = self.search("apple")
        assert isinstance(result, list)
        tickers = [s["ticker"] for s in result]
        assert "AAPL" in tickers

    def test_search_stocks_case_insensitive(self):
        lower = self.search("nvidia")
        upper = self.search("NVIDIA")
        assert len(lower) == len(upper)

    def test_search_stocks_empty_returns_list(self):
        result = self.search("")
        assert isinstance(result, list)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# 3. Gemini API key test
# ---------------------------------------------------------------------------

class TestGeminiKey:
    """Check that the Gemini API key works and model is accessible."""

    def test_api_key_is_set(self):
        key = os.getenv("GEMINI_API_KEY", "").strip()
        assert key, "GEMINI_API_KEY env var is not set!"
        assert key != "your_gemini_api_key_here", "GEMINI_API_KEY is still the placeholder!"
        assert key.startswith("AIza"), f"API key looks wrong: {key[:8]}..."

    def test_gemini_model_responds(self):
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            pytest.skip("GEMINI_API_KEY not set")

        import google.generativeai as genai
        genai.configure(api_key=key)

        errors = []
        model_obj = None
        for model_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-latest"]:
            try:
                m = genai.GenerativeModel(model_name)
                resp = m.generate_content("Reply with exactly: OK")
                if resp and resp.text:
                    model_obj = model_name
                    break
            except Exception as e:
                errors.append(f"{model_name}: {e}")

        assert model_obj is not None, f"No Gemini model worked. Errors: {errors}"
        print(f"\n✅ Working Gemini model: {model_obj}")

    def test_summarizer_returns_valid_structure(self):
        from ai.summarizer import summarize_news
        result = summarize_news(
            ticker="AAPL",
            company_name="Apple Inc.",
            news_items=[
                {"title": "Apple reports record revenue", "description": "Apple beat all expectations"},
                {"title": "iPhone sales surge globally", "description": "Strong demand in Asia"},
            ],
        )
        assert isinstance(result, dict)
        assert "overall_sentiment" in result
        assert result["overall_sentiment"] in ("bullish", "neutral", "bearish")
        assert "bullet_points" in result
        assert isinstance(result["bullet_points"], list)
        assert "thai_summary" in result
        print(f"\n✅ Summary sentiment: {result['overall_sentiment']}")
        print(f"   Thai summary: {result['thai_summary'][:80]}...")


# ---------------------------------------------------------------------------
# 4. Database tests
# ---------------------------------------------------------------------------

class TestDatabase:
    """Database connection and schema."""

    def test_db_connects(self):
        from db.database import get_db
        with get_db() as conn:
            result = conn.execute("SELECT 1").fetchone()
            assert result[0] == 1

    def test_watchlist_table_exists(self):
        from db.database import get_db
        with get_db() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t[0] for t in tables]
            assert "watchlist" in table_names, f"Tables found: {table_names}"

    def test_news_cache_table_exists(self):
        from db.database import get_db
        with get_db() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t[0] for t in tables]
            assert "news_cache" in table_names, f"Tables found: {table_names}"


# ---------------------------------------------------------------------------
# 5. FastAPI endpoint integration tests
# ---------------------------------------------------------------------------

class TestAPIEndpoints:
    """FastAPI app endpoint integration tests using TestClient."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        from fastapi.testclient import TestClient
        from main import app
        self.client = TestClient(app)

    def test_root_health_check(self):
        r = self.client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"

    def test_watchlist_get(self):
        r = self.client.get("/api/watchlist/")
        assert r.status_code in (200, 307)  # 307 = redirect to /api/watchlist/

    def test_stocks_search(self):
        r = self.client.get("/api/stocks/search?q=apple")
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_market_news_has_sentiment(self):
        r = self.client.get("/api/news/market")
        assert r.status_code == 200
        data = r.json()
        assert "articles" in data
        assert "market_sentiment" in data
        assert data["market_sentiment"] in ("bullish", "neutral", "bearish")
        if data["articles"]:
            article = data["articles"][0]
            assert "sentiment" in article, "Each article should have a sentiment field"
            assert article["sentiment"] in ("bullish", "neutral", "bearish")

    def test_stock_news_has_sentiment(self):
        r = self.client.get("/api/news/AAPL")
        assert r.status_code == 200
        data = r.json()
        assert "articles" in data
        if data["articles"]:
            article = data["articles"][0]
            assert "sentiment" in article

    def test_weekly_report_404_when_empty(self):
        # Fresh DB may have no report — should return 404 not 500
        r = self.client.get("/api/reports/weekly")
        assert r.status_code in (200, 404)

    def test_stock_info_structure(self):
        r = self.client.get("/api/stocks/MSFT")
        assert r.status_code == 200
        data = r.json()
        assert "ticker" in data
        assert data["ticker"] == "MSFT"
