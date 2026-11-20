@echo off
chcp 65001 >nul
rem Install NEON.DOC dependencies into conda env "reportgen" (creates it if missing)
call "%USERPROFILE%\miniconda3\Scripts\activate.bat"
call conda env list | findstr /B "reportgen " >nul
if errorlevel 1 call conda create -y -n reportgen python=3.11
call conda activate reportgen
cd /d "%~dp0"
pip install -r requirements.txt
pip install -r requirements-app.txt
echo.
echo === NEON.DOC installed. Run run_app.bat ===
pause
