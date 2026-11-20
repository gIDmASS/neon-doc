@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
call "%USERPROFILE%\miniconda3\Scripts\activate.bat" reportgen
cd /d "%~dp0"
echo Собираю NEON.DOC-mac.zip в папку Загрузки (программа + твои данные)...
python tools\pack_mac.py %*
echo.
echo Перенеси NEON.DOC-mac.zip на Mac (AirDrop, флешка, облако) и открой «МАК — КАК УСТАНОВИТЬ.txt» внутри.
pause
