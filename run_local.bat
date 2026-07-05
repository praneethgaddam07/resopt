@echo off
REM Run locally on Windows. Stateless + bring-your-own-key: enter your AI key in the browser.
cd /d "%~dp0"

if not exist ".venv\" (
  echo Creating virtual environment...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q --disable-pip-version-check -r requirements.txt

echo.
echo  Open http://localhost:8000  (enter your Anthropic / OpenAI / Gemini key in the page)
echo.
uvicorn app.main:app --host 0.0.0.0 --port 8000
