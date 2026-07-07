@echo off
rem Compile Nova en .exe (dossier dist\Nova\)
cd /d "%~dp0"
call .venv\Scripts\activate.bat
pyinstaller --noconfirm --noconsole --onedir --name Nova --icon icon.ico ^
  --collect-all faster_whisper ^
  --collect-all ctranslate2 ^
  --collect-all webview ^
  --collect-all pvporcupine ^
  --hidden-import pystray._win32 ^
  --hidden-import serial ^
  --hidden-import serial.tools.list_ports ^
  --add-data "ui;ui" ^
  --add-data "icon.png;." ^
  app.py
copy /y config.json "dist\Nova\" >nul
copy /y commands.json "dist\Nova\" >nul
if exist notes.json copy /y notes.json "dist\Nova\" >nul
if exist secrets.json copy /y secrets.json "dist\Nova\" >nul
if exist nova.db copy /y nova.db "dist\Nova\" >nul
echo.
echo Termine ! Lance : dist\Nova\Nova.exe
pause
