@echo off
chcp 65001 >nul
rem One-time setup: conda env "reportgen" (Python 3.11) + packages
call "%USERPROFILE%\miniconda3\Scripts\activate.bat"
call conda create -y -n reportgen python=3.11
call conda activate reportgen
pip install -r "%~dp0requirements.txt"
echo.
echo Done. Next: run_plan.bat
pause
