@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
call "%USERPROFILE%\miniconda3\Scripts\activate.bat" reportgen
cd /d "%~dp0"
start "NEON.DOC server" /min cmd /c "python -m neondoc > neondoc.log 2>&1"
