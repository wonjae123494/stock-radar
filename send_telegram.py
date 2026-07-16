#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
수급 쌍끌이 레이더 — 텔레그램 발송
config.json 의 bot_token / chat_id 로 요약 메시지 + 대시보드 HTML 파일을 보낸다.

사용:
  python send_telegram.py            # 요약 + index.html 발송
  python send_telegram.py --error   # 파이프라인 실패 알림만 발송
설정(config.json):
  { "bot_token": "123456:ABC-...", "chat_id": "123456789" }
"""
import json, sys, os, datetime

try:
    import requests
except ImportError:
    sys.exit("requests가 필요합니다: pip install requests")

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "config.json")

if not os.path.exists(CFG):
    sys.exit("config.json이 없습니다. config.example.json을 복사해 bot_token/chat_id를 채우세요.")
cfg = json.load(open(CFG, encoding="utf-8"))
TOKEN, CHAT = cfg["bot_token"], cfg["chat_id"]
API = f"https://api.telegram.org/bot{TOKEN}"


def send_text(text):
    r = requests.post(f"{API}/sendMessage", data={
        "chat_id": CHAT, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": True}, timeout=30)
    r.raise_for_status()
    return r.json()


def send_file(path, caption=""):
    with open(path, "rb") as f:
        r = requests.post(f"{API}/sendDocument",
                          data={"chat_id": CHAT, "caption": caption},
                          files={"document": (os.path.basename(path), f, "text/html")}, timeout=120)
    r.raise_for_status()
    return r.json()


def main():
    today = datetime.date.today().strftime("%Y-%m-%d")
    if "--error" in sys.argv:
        send_text(f"⚠️ <b>수급 레이더 {today}</b>\n자동 갱신 실패 — logs 폴더 확인 후 클로드 코드에 '오류 고쳐줘'라고 요청하세요.")
        return

    d = json.load(open(os.path.join(HERE, "data", "recommendations.json"), encoding="utf-8"))
    top = d["stocks"][:5]
    lines = [f"📡 <b>수급 쌍끌이 레이더</b> — 기준일 {d['base_date']}"]
    if d.get("market_note"):
        lines.append(f"<i>{d['market_note'][:120]}</i>")
    lines.append("")
    for s in top:
        warn = " ⚠️" if (s.get("warn") or not s.get("per")) else ""
        per = f"PER {s['per']:.1f}" if s.get("per") else "적자"
        lines.append(f"<b>{s['rank']}. {s['name']}</b> {s['score_total']:.0f}점{warn}\n"
                     f"   {s['price']:,}원 · {per} · 4일 수급 {s['total_flow']:+,}억 · 52주 {s['pos']}%")
        if s.get("divergence"):
            note = s.get("drop_why") or "점수 대비 주가 하락 — 원인은 대시보드 참고"
            lines.append(f"   📉 <i>{note[:110]}</i>")
    lines.append("")
    lines.append("전체 순위·차트·매수 전략은 첨부 대시보드 참고")
    lines.append("<i>※ 투자 참고 자료이며 투자 권유가 아닙니다.</i>")
    send_text("\n".join(lines))
    send_file(os.path.join(HERE, "data", "index.html"),
              caption=f"수급 레이더 대시보드 ({d['base_date']}) — 브라우저로 열어보세요")
    # 발송 성공 표식: 같은 날 중복 발송(예약 작업 + Windows 폴백 + GitHub Actions)을 방지하기 위해 기록
    try:
        with open(os.path.join(HERE, "data", "last_sent.txt"), "w", encoding="utf-8") as f:
            f.write(today)
    except OSError:
        pass
    # 로컬에서 발송했으면 마커를 GitHub에도 푸시 → 19:40 GitHub Actions가 보고 스킵
    # (Actions 안에서는 워크플로우가 직접 커밋하므로 여기선 건너뜀. 실패해도 발송은 성공이므로 무시)
    if not os.environ.get("GITHUB_ACTIONS") and os.path.isdir(os.path.join(HERE, ".git")):
        import subprocess
        try:
            subprocess.run(["git", "add", "data/"], cwd=HERE, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"chore: local radar send {today}"],
                           cwd=HERE, check=False, capture_output=True)
            subprocess.run(["git", "pull", "--rebase"], cwd=HERE, check=False, capture_output=True, timeout=60)
            subprocess.run(["git", "push"], cwd=HERE, check=False, capture_output=True, timeout=60)
        except Exception as e:
            print(f"(경고) 발송 마커 git 푸시 실패 — 무시하고 계속: {e}")
    print("텔레그램 발송 완료")


if __name__ == "__main__":
    main()
