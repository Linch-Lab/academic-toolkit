@echo off
REM MinerU batch runner — processes a PDF to structured Markdown
REM Usage: run.bat paper.pdf [output_dir]

setlocal
set PAPER=%1
set OUT=%2
if "%OUT%"=="" set OUT=output

set PYTHONPATH=
D:\mineru_py310\Scripts\mineru.exe -p "%PAPER%" -o "%OUT%" -b pipeline

echo.
echo Done: %OUT%\%~n1\auto\%~n1.md
pause
