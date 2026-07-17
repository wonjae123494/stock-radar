#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
수급 레이더 — Windows 작업 스케줄러용 폴백 실행기 (평일 14:35)

발송 순서: 14:00 Claude Code 예약(뉴스 분석 포함 풍부판, 앱 켜진 날만) → 14:20 GitHub Actions
(PC 무관, 기본판) → 14:35 이 폴백. 먼저 성공한 쪽이 마커를 남기면 뒤 순서는 스킵한다.
14시대 실행은 장중이라 수급 데이터가 미확정 → fetch가 자동으로 '전일 종가' 기준일을 잡는다.

중복 발송 방지 (휴장일 처리 겸용):
  - fetch→score 후 recommendations.json 의 base_date 가 data/last_sent.txt 내용과 같으면
    이미 발송된 기준일이므로 종료. (send_telegram.py 가 발송 성공 시 base_date 를 기록한다.
    휴장일엔 base_date 가 직전 거래일 그대로라 자연히 스킵된다.)

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
    # 0) 다른 실행 주체(GitHub Actions 등)가 먼저 발송했을 수 있으니 최신 마커를 당겨온다 (로컬 실행일 때만)
    if not os.environ.get("GITHUB_ACTIONS") and os.path.isdir(os.path.join(HERE, ".git")):
        subprocess.run(["git", "pull", "--ff-only"], check=False, capture_output=True, timeout=60)

    # 1) 데이터 수집 + 점수화
    #    (14시 실행 체제: 장중이므로 fetch가 자동으로 '전일 종가' 기준일을 잡는다)
    run("fetch_data.py")
    run("score.py")

    # 2) 이 기준일 데이터가 이미 발송됐으면 스킵 — 중복 방지 + 휴장일 처리를 겸함
    #    (휴장일엔 base_date가 직전 거래일 그대로라 마커와 같아져 자연히 스킵된다)
    #    --force: 테스트용 — 중복 방지를 무시하고 강제 발송
    d = json.load(open(os.path.join(HERE, "data", "recommendations.json"), encoding="utf-8"))
    base = d.get("base_date")
    sent_marker = os.path.join(HERE, "data", "last_sent.txt")
    if "--force" in sys.argv:
        print("--force: 중복 발송 방지 무시하고 진행")
    elif os.path.exists(sent_marker):
        try:
            if open(sent_marker, encoding="utf-8").read().strip() == base:
                print(f"기준일 {base} 데이터는 이미 발송됨 — 스킵")
                return 0
        except OSError:
            pass

    # 3) 대시보드 생성 + 발송 (뉴스 분석 없는 기본 버전)
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
