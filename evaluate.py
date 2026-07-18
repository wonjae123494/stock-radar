#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
수급 쌍끌이 레이더 — 모의 매매 성과 평가

규칙 (사용자 합의 — 임의 변경 금지):
  매수: 추천 base_date의 다음 거래일 종가 (발송일 14시 → 당일 종가 근사)
  매도: 이후 5거래일 내 고가가 매수가×1.03 이상이면 그날 +3.0% 체결,
        미도달 시 5거래일째 종가. 5거래일이 안 지났으면 '진행 중'.
  대상: 각 base_date 추천 상위 5종목 (텔레그램 발송분)

사용:
  python evaluate.py            # 계산 + data/eval_report.txt + data/feedback.md 갱신
  python evaluate.py --send     # 위 + 텔레그램 발송 (오늘 이미 발송했으면 스킵, --force로 무시)

※ 가상 시뮬레이션이며 실제 주문은 하지 않는다. 수수료·세금·슬리피지 미반영.
"""
import datetime, glob, io, json, os, re, subprocess, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

def _load_env():
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

try:
    from pykrx import stock as _krx
except Exception:
    _krx = None  # KRX 차단 환경(GitHub Actions 등) → 네이버 시세로 대체

TARGET = 1.03      # +3% 매도
HOLD_DAYS = 5      # 최대 보유 거래일
TOP_N = 5          # 발송분(상위 5)만 확정 평가

H = {"User-Agent": "Mozilla/5.0 Chrome/126", "Referer": "https://finance.naver.com/"}


def naver_ohlcv(code, need_from):
    """네이버 일별 시세 → {YYYYMMDD: (고가, 종가)}"""
    try:
        import pandas as pd
    except ImportError:
        return {}
    out = {}
    for page in range(1, 8):  # 페이지당 10거래일 → 최대 ~70일
        r = requests.get(f"https://finance.naver.com/item/sise_day.naver?code={code}&page={page}",
                         headers=H, timeout=15)
        r.encoding = "euc-kr"
        try:
            df = pd.read_html(io.StringIO(r.text))[0].dropna()
        except (ValueError, IndexError):
            break
        oldest = None
        for _, row in df.iterrows():
            d = str(row.get("날짜", ""))
            if not re.match(r"\d{4}\.\d{2}\.\d{2}", d):
                continue
            ymd = d.replace(".", "")
            out[ymd] = (float(row["고가"]), float(row["종가"]))
            oldest = ymd
        if oldest is None or oldest < need_from:
            break
        time.sleep(0.2)
    return out


_PX_CACHE = {}

def ohlcv(code, start):
    """start(YYYYMMDD)부터 오늘까지 {YYYYMMDD: (고가, 종가)} — pykrx 우선, 실패 시 네이버"""
    key = (code, start)
    if key in _PX_CACHE:
        return _PX_CACHE[key]
    end = datetime.date.today().strftime("%Y%m%d")
    px = {}
    if _krx is not None:
        try:
            df = _krx.get_market_ohlcv(start, end, code)
            px = {d.strftime("%Y%m%d"): (float(r["고가"]), float(r["종가"])) for d, r in df.iterrows()}
            time.sleep(0.2)
        except Exception:
            px = {}
    if not px:
        px = naver_ohlcv(code, start)
    _PX_CACHE[key] = px
    return px


def load_snapshots():
    """base_date → 추천 데이터. archive 스냅샷 + git 이력 백필."""
    snaps = {}
    for p in sorted(glob.glob("data/archive/recommendations-*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
            snaps[d["base_date"]] = d
        except (json.JSONDecodeError, KeyError):
            continue
    try:
        shas = subprocess.run(["git", "log", "--format=%H", "--", "data/recommendations.json"],
                              capture_output=True, text=True, timeout=60).stdout.split()
        for sha in shas:
            raw = subprocess.run(["git", "show", f"{sha}:data/recommendations.json"],
                                 capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=60)
            if raw.returncode:
                continue
            try:
                d = json.loads(raw.stdout)
                snaps.setdefault(d.get("base_date"), d)
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    snaps.pop(None, None)
    return snaps


def simulate(base_date, s):
    """한 건의 추천을 모의 매매. dict(수익률 등) 또는 status='pending'/'nodata'"""
    bd = base_date.replace("-", "")
    px = ohlcv(s["code"], bd)
    if not px:
        return {"status": "nodata"}
    days = sorted(d for d in px if d > bd)
    if not days:
        # 시세는 있는데 base_date 이후 거래일이 아직 없음 → 매수 대기 (다음 개장일에 매수)
        return {"status": "pending", "elapsed": 0}
    buy_day = days[0]
    buy = px[buy_day][1]
    window = days[1:1 + HOLD_DAYS]
    for i, d in enumerate(window, 1):
        high, close = px[d]
        if high >= buy * TARGET:
            return {"status": "done", "hit": True, "buy": buy, "sell": round(buy * TARGET, 2),
                    "ret": (TARGET - 1) * 100, "hold": i, "buy_day": buy_day}
    if len(window) < HOLD_DAYS:
        return {"status": "pending", "buy": buy, "buy_day": buy_day, "elapsed": len(window)}
    sell = px[window[-1]][1]
    return {"status": "done", "hit": False, "buy": buy, "sell": sell,
            "ret": (sell / buy - 1) * 100, "hold": HOLD_DAYS, "buy_day": buy_day}


def main():
    today = datetime.date.today().strftime("%Y-%m-%d")
    snaps = load_snapshots()
    if not snaps:
        sys.exit("평가할 추천 기록이 없습니다 (data/archive/, git 이력 모두 비어 있음)")

    done, pending, nodata = [], [], []
    for base_date in sorted(snaps):
        for s in snaps[base_date]["stocks"]:
            if s.get("rank", 99) > TOP_N:
                continue
            r = simulate(base_date, s)
            row = dict(base=base_date, name=s["name"], code=s["code"],
                       score=s.get("score_total"), parts=s.get("score_parts", {}), **r)
            {"done": done, "pending": pending, "nodata": nodata}[r["status"]].append(row)

    lines = [f"📊 <b>주간 모의투자 성과 평가</b> — {today}"]
    if done:
        wins = [r for r in done if r["hit"]]
        rets = [r["ret"] for r in done]
        avg = sum(rets) / len(rets)
        best, worst = max(done, key=lambda r: r["ret"]), min(done, key=lambda r: r["ret"])
        lines.append(f"확정 {len(done)}건 · 승률 {len(wins) / len(done) * 100:.0f}%"
                     f" (+3% 도달 {len(wins)}건) · 평균 {avg:+.2f}%")
        lines.append(f"최고 {best['name']} {best['ret']:+.1f}% · 최저 {worst['name']} {worst['ret']:+.1f}%")
        lines.append("")
        for r in sorted(done, key=lambda r: -r["ret"]):
            tag = "달성" if r["hit"] else "기간만료"
            lines.append(f"{r['base'][5:]} {r['name']} {r['ret']:+.1f}% ({r['hold']}일·{tag}·점수{r['score']:.0f})")
        if len(done) >= 8:
            lines.append("")
            keys = ["size", "persist", "today", "quality", "risk"]
            names = {"size": "수급규모", "persist": "지속성", "today": "당일쌍끌이", "quality": "우량주", "risk": "과열리스크"}
            losers = [r for r in done if not r["hit"]]
            diffs = []
            for k in keys:
                w = sum(r["parts"].get(k, 0) for r in wins) / max(1, len(wins))
                l = sum(r["parts"].get(k, 0) for r in losers) / max(1, len(losers))
                diffs.append(f"{names[k]} 승자{w:.1f}/패자{l:.1f}")
            lines.append("<i>점수요소 평균(승/패): " + " · ".join(diffs) + "</i>")
        elif done:
            lines.append("")
            lines.append("<i>표본이 적어(20건 미만) 통계적 의미는 낮습니다.</i>")
    else:
        lines.append("확정된 평가 건이 아직 없습니다.")
    if pending:
        lines.append(f"⏳ 진행 중 {len(pending)}건 — 5거래일이 지나면 다음 평가에서 확정됩니다.")
    if nodata:
        lines.append(f"(시세 조회 실패 {len(nodata)}건 제외)")
    lines.append("")
    lines.append("※ 모의 평가이며 수수료·세금·슬리피지 미반영. 투자 판단·책임은 본인에게 있습니다.")
    report = "\n".join(lines)

    with open("data/eval_report.txt", "w", encoding="utf-8") as f:
        f.write(report)
    # feedback.md에 누적 (최신이 위)
    old = open("data/feedback.md", encoding="utf-8").read() if os.path.exists("data/feedback.md") else ""
    plain = re.sub(r"</?[bi]>", "**", report)
    with open("data/feedback.md", "w", encoding="utf-8") as f:
        f.write(f"## {today} 자동 평가(스크립트)\n\n{plain}\n\n---\n\n{old}")
    print(report.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
    print("\ndata/eval_report.txt · data/feedback.md 저장 완료")

    if "--send" in sys.argv:
        marker = "data/last_eval.txt"
        if "--force" not in sys.argv and os.path.exists(marker) \
                and open(marker, encoding="utf-8").read().strip() == today:
            print("오늘 이미 평가 발송됨 — 스킵")
            return
        subprocess.run([sys.executable, "send_telegram.py", "--textfile", "data/eval_report.txt"], check=True)
        with open(marker, "w", encoding="utf-8") as f:
            f.write(today)
        print("평가 리포트 텔레그램 발송 완료")


if __name__ == "__main__":
    main()
