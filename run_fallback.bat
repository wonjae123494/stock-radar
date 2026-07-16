@echo off
REM ==== Stock Radar 폴백 (평일 19:45, Windows 작업 스케줄러) ====
REM Claude Code 앱이 꺼져 있어 19:05 예약이 누락된 날을 대비한 보조 실행.
REM 오늘 이미 발송됐으면 run_fallback.py 안에서 스스로 스킵한다.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist logs mkdir logs
set LOG=logs\fallback_%date:~0,4%%date:~5,2%%date:~8,2%.log
echo ==== fallback run %date% %time% ==== >> "%LOG%" 2>&1
python run_fallback.py >> "%LOG%" 2>&1
echo exit=%errorlevel% >> "%LOG%"
exit /b %errorlevel%
