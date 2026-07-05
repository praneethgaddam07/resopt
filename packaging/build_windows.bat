@echo off
REM Build the Windows desktop app (RESOPT.exe) with PyInstaller. Run on Windows.
REM   packaging\build_windows.bat   ->   dist\RESOPT.exe
cd /d "%~dp0\.."

python -m venv .build-venv
call .build-venv\Scripts\activate.bat
pip install -q --disable-pip-version-check -r requirements-desktop.txt Pillow

python packaging\make_icon.py

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

pyinstaller --noconfirm --windowed --onefile --name "RESOPT" ^
  --icon packaging/assets/icon.ico ^
  --add-data "app/static;app/static" ^
  --add-data "app/workflow/master_taxonomy.json;app/workflow" ^
  --collect-all uvicorn ^
  --collect-all anthropic ^
  --collect-all openai ^
  --collect-all google.generativeai ^
  --collect-all webview ^
  --collect-submodules app ^
  desktop.py

echo.
echo Built: dist\RESOPT.exe
