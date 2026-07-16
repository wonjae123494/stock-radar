@echo off
REM ==== Stock Radar daily pipeline (19:05 via Task Scheduler) ====
cd /d "%~dp0"
if not exist logs mkdir logs
set LOG=logs\run_%date:~0,4%%date:~5,2%%date:~8,2%.log
echo ==== run %date% %time% ==== >> "%LOG%" 2>&1

python fetch_data.py >> "%LOG%" 2>&1 || goto :fail
python score.py      >> "%LOG%" 2>&1 || goto :fail
python build_html.py >> "%LOG%" 2>&1 || goto :fail

REM (optional) Claude Code news analysis - uncomment after testing manually:
REM claude -p "CLAUDE.md의 뉴스 분석 단계를 수행해 data/news.json을 갱신한 뒤 score.py와 build_html.py를 다시 실행해줘" >> "%LOG%" 2>&1

python send_telegram.py >> "%LOG%" 2>&1 || goto :fail
echo OK >> "%LOG%"
exit /b 0

:fail
echo FAILED >> "%LOG%"
python send_telegram.py --error >> "%LOG%" 2>&1
exit /b 1
