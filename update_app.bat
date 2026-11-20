@echo off
chcp 65001 >nul
rem Обновление NEON.DOC: доставить новые пакеты (расшифровка по участникам, Excel/PowerPoint, картинки)
call "%USERPROFILE%\miniconda3\Scripts\activate.bat" reportgen
cd /d "%~dp0"
python -m pip install -r requirements-app.txt
echo.
echo === Готово. Закрой старое окно NEON.DOC и запусти run_app.bat ===
pause
