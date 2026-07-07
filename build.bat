@echo off
rem Compile Nova v3 (Speechly-lite) en .exe (dossier dist\Nova\)
cd /d "%~dp0"
call .venv\Scripts\activate.bat
pyinstaller --noconfirm --noconsole --onedir --name Nova --icon icon.ico ^
  --collect-all faster_whisper ^
  --collect-all ctranslate2 ^
  --hidden-import pystray._win32 ^
  --add-data "icon.png;." ^
  app.py

rem --- DLLs CUDA (accélération GPU) : copiées à côté de l'exe pour que
rem     CTranslate2 les trouve (cuBLAS + cuDNN, ~1,8 Go). Sans GPU, Nova les
rem     ignore et tourne sur CPU. Absentes si les paquets nvidia-*-cu12 ne sont
rem     pas installés : pip install nvidia-cublas-cu12 nvidia-cuda-runtime-cu12 nvidia-cudnn-cu12
for /d %%D in (.venv\Lib\site-packages\nvidia\*) do if exist "%%D\bin" copy /y "%%D\bin\*.dll" "dist\Nova\" >nul

copy /y config.json "dist\Nova\" >nul
if exist secrets.json copy /y secrets.json "dist\Nova\" >nul
if exist nova.db copy /y nova.db "dist\Nova\" >nul
echo.
echo Termine ! Lance : dist\Nova\Nova.exe
pause
