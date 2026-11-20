@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
call "%USERPROFILE%\miniconda3\Scripts\activate.bat" reportgen
cd /d "%~dp0"
set TASK=%~1
if "%TASK%"=="" set TASK=tasks\tipup_lr3_benchmark
python -m reportgen.pipeline write "%TASK%"
pause
