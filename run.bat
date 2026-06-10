@echo off
echo =============================================
echo  NASDAQ Stock News Backend
echo =============================================
echo.
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting FastAPI server on http://localhost:8000
echo Press Ctrl+C to stop.
echo.
uvicorn main:app --reload --port 8000
