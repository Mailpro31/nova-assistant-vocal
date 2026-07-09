@echo off
rem ===========================================================================
rem  Nova — construit l'installateur complet Nova-Setup.exe en une commande.
rem  1) build.bat  -> dossier PyInstaller dist\Nova\
rem  2) Inno Setup -> dist\Nova-Setup.exe (assistant + raccourcis + desinstall.)
rem
rem  Prerequis : venv prete (pip install -r requirements.txt pyinstaller)
rem              + Inno Setup 6 installe (https://jrsoftware.org/isdl.php)
rem ===========================================================================
setlocal
cd /d "%~dp0"

echo [1/2] Compilation PyInstaller...
set NOVA_NOPAUSE=1
call build.bat
if errorlevel 1 goto :err
if not exist "dist\Nova\Nova.exe" (
  echo ERREUR : dist\Nova\Nova.exe introuvable, build.bat a echoue.
  goto :err
)

echo.
echo [2/2] Compilation de l'installateur (Inno Setup)...
rem Cherche iscc.exe (compilateur Inno Setup) aux emplacements habituels.
set "ISCC="
for %%P in (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  "%ProgramFiles%\Inno Setup 6\ISCC.exe"
) do if exist "%%~P" set "ISCC=%%~P"
if not defined ISCC (
  where iscc >nul 2>nul && for /f "delims=" %%I in ('where iscc') do set "ISCC=%%I"
)
if not defined ISCC (
  echo ERREUR : Inno Setup introuvable. Installe-le depuis
  echo          https://jrsoftware.org/isdl.php puis relance ce script.
  goto :err
)

"%ISCC%" "installer\nova.iss"
if errorlevel 1 goto :err

echo.
echo ============================================================
echo  Termine ! Installateur : dist\Nova-Setup.exe
echo ============================================================
pause
exit /b 0

:err
echo.
echo Echec de la construction.
pause
exit /b 1
