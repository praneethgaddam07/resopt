@echo off
setlocal
echo =================================================
echo RESOPT Native Messaging Host Installer (Windows)
echo =================================================
echo To connect the RESOPT Chrome extension to the desktop app,
echo we need your Extension ID. You can find this by:
echo 1. Opening Chrome and going to chrome://extensions/
echo 2. Finding the RESOPT extension
echo 3. Copying the ID (e.g., abcdefghijklmnopqrstuvwxyz)
echo.
set /p EXT_ID="Enter your Chrome Extension ID: "

if "%EXT_ID%"=="" (
    echo Extension ID is required. Exiting.
    pause
    exit /b 1
)

set HOST_DIR=%LOCALAPPDATA%\resopt
if not exist "%HOST_DIR%" mkdir "%HOST_DIR%"

set WRAPPER_SCRIPT=%HOST_DIR%\resopt-native-host.bat
echo @echo off > "%WRAPPER_SCRIPT%"
echo "%~dp0RESOPT.exe" --native >> "%WRAPPER_SCRIPT%"

set JSON_FILE=%HOST_DIR%\com.praneeth.resopt.json
echo { > "%JSON_FILE%"
echo   "name": "com.praneeth.resopt", >> "%JSON_FILE%"
echo   "description": "RESOPT Native Messaging Host", >> "%JSON_FILE%"
echo   "path": "%WRAPPER_SCRIPT:\=\\%", >> "%JSON_FILE%"
echo   "type": "stdio", >> "%JSON_FILE%"
echo   "allowed_origins": [ >> "%JSON_FILE%"
echo     "chrome-extension://%EXT_ID%/" >> "%JSON_FILE%"
echo   ] >> "%JSON_FILE%"
echo } >> "%JSON_FILE%"

:: Install for Chrome
REG ADD "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.praneeth.resopt" /ve /t REG_SZ /d "%JSON_FILE%" /f >nul

:: Install for Edge
REG ADD "HKCU\Software\Microsoft\Edge\NativeMessagingHosts\com.praneeth.resopt" /ve /t REG_SZ /d "%JSON_FILE%" /f >nul

:: Install for Brave
REG ADD "HKCU\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.praneeth.resopt" /ve /t REG_SZ /d "%JSON_FILE%" /f >nul

echo.
echo =================================================
echo SUCCESS!
echo The extension should now be able to communicate with the RESOPT desktop app.
echo Please restart your browser.
pause
