#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
수급 레이더 — Windows 작업 스케줄러용 폴백 실행기 (평일 19:45)

Claude Code 예약 작업(19:05)은 앱이 켜져 있어야만 실행된다. 앱이 꺼져 있어 발송이
누락되는 것을 막기 위해, 이 스크립트를 Windows 작업 스케줄러에 등록해 매일 저녁 한 번 더 돌린다.

중복 발송 방지:
  - data/last_sent.txt 에 '오늘 날짜'가 이미 적혀 있으면(= 오늘 이미 발송됨) 아무것도 안 하고 종료.
    (send_telegram.py 가 발송 성공 시 이 파일을 갱신한다. 예약 작업이 먼저 돌았으면 여기서 스킵.)
휴장일/미확정 방지:
  - fetch→score 후 recommendations.json 의 base_date 가 '오늘'이 아니면(휴장일 등) 발송하지 않는다.

사용: python run_fallback.py   (보통 run_fallback.bat 이 호출)
"""
import os, sys, json, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
PY = sys.executable
TODAY = datetime.date.today().strftime("%Y-%m-%d")


def run(script):
    subprocess.run([PY, script], check=True)


def main():
    # 0) GitHub Actions(19:40)가 먼저 발송했을 수 있으니 최신 마커를 당겨온다 (로컬 실행일 때만)
    if not os.environ.get("GITHUB_ACTIONS") and os.path.isdir(os.path.join(HERE, ".git")):
        subprocess.run(["git", "pull", "--ff-only"], check=False, capture_output=True, timeout=60)

    # 1) 오늘 이미 발송됐으면 스킵 (Claude Code 예약이 먼저 돌았거나 이전 폴백)
    #    --force: 테스트용 — 중복 방지를 무시하고 강제 실행
    sent_marker = os.path.join(HERE, "data", "last_sent.txt")
    if "--force" in sys.argv:
        print("--force: 중복 발송 방지 무시하고 진행")
    elif os.path.exists(sent_marker):
        try:
            if open(sent_marker, encoding="utf-8").read().strip() == TODAY:
                print(f"오늘({TODAY}) 이미 발송됨 — 폴백 스킵")
                return 0
        except OSError:
            pass

    # 2) 데이터 수집 + 점수화
    run("fetch_data.py")
    run("score.py")

    # 3) 휴장일/당일 미확정이면 발송 안 함 (base_date 가 오늘이 아니면 스킵)
    d = json.load(open(os.path.join(HERE, "data", "recommendations.json"), encoding="utf-8"))
    if d.get("base_date") != TODAY:
        print(f"휴장일 또는 당일 데이터 미확정(base_date={d.get('base_date')}, 오늘={TODAY}) — 발송 스킵")
        return 0

    # 4) 대시보드 생성 + 발송 (뉴스 분석 없는 기본 버전)
    run("build_html.py")
    run("send_telegram.py")
    print("폴백 발송 완료")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        print(f"폴백 파이프라인 실패: {e}")
        try:
            subprocess.run([PY, "send_telegram.py", "--error"], check=False)
        except Exception:
            pass
        sys.exit(1)
