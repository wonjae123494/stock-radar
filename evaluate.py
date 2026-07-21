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

TARGET = 1.03          # +3% 익절
HOLD_DAYS = 5          # 최대 보유 거래일
TOP_N = 5              # 발송분(상위 5)만 확정 평가
STOPS = [None, 0.02, 0.03, 0.05]   # 손절 민감도 비교 (None=손절 없음=기존 규칙)
COST = 0.25            # 왕복 거래비용(%) 추정: 매도세 0.18 + 수수료·슬리피지
IDX_CODE = {"KOSPI": "1001", "KOSDAQ": "2001"}

H = {"User-Agent": "Mozilla/5.0 Chrome/126", "Referer": "https://finance.naver.com/"}


def naver_ohlcv(code, need_from):
    """네이버 일별 시세 → {YYYYMMDD: (고가, 저가, 종가)}"""
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
            out[ymd] = (float(row["고가"]), float(row["저가"]), float(row["종가"]))
            oldest = ymd
        if oldest is None or oldest < need_from:
            break
        time.sleep(0.2)
    return out


def naver_index(mkt, need_from):
    """네이버 지수 일별 종가 → {YYYYMMDD: 종가}"""
    try:
        import pandas as pd
    except ImportError:
        return {}
    out = {}
    for page in range(1, 8):
        r = requests.get(f"https://finance.naver.com/sise/sise_index_day.naver?code={mkt}&page={page}",
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
            out[ymd] = float(str(row["체결가"]).replace(",", ""))
            oldest = ymd
        if oldest is None or oldest < need_from:
            break
        time.sleep(0.2)
    return out


_IDX_CACHE = {}

def index_close(mkt, start):
    """지수 일별 종가 {YYYYMMDD: close} — pykrx 우선, 실패 시 네이버"""
    key = (mkt, start)
    if key in _IDX_CACHE:
        return _IDX_CACHE[key]
    end = datetime.date.today().strftime("%Y%m%d")
    idx = {}
    if _krx is not None:
        try:
            df = _krx.get_index_ohlcv(start, end, IDX_CODE.get(mkt, "1001"))
            idx = {d.strftime("%Y%m%d"): float(r["종가"]) for d, r in df.iterrows()}
            time.sleep(0.2)
        except Exception:
            idx = {}
    if not idx:
        idx = naver_index("KOSPI" if mkt == "KOSPI" else "KOSDAQ", start)
    _IDX_CACHE[key] = idx
    return idx


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
            px = {d.strftime("%Y%m%d"): (float(r["고가"]), float(r["저가"]), float(r["종가"]))
                  for d, r in df.iterrows()}
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


def simulate(base_date, s, stop=None):
    """한 건의 추천을 모의 매매.

    매수: base_date 다음 거래일 종가. 매도: 이후 HOLD_DAYS 거래일 내
      - stop(예: 0.03)이 주어지면 저가가 매수가×(1-stop) 이하로 닿은 날 손절(그날 익절과 동시
        도달 시 손절 우선 — 위험을 보수적으로 추정), 익절(고가≥매수가×TARGET), 없으면 마지막날 종가.
    반환: dict(status='done', hit=익절도달, exit=사유, ret=수익률%, alpha=시장대비%p, ...)
          또는 status='pending'/'nodata'.
    """
    bd = base_date.replace("-", "")
    px = ohlcv(s["code"], bd)
    if not px:
        return {"status": "nodata"}
    days = sorted(d for d in px if d > bd)
    if not days:
        return {"status": "pending", "elapsed": 0}   # 매수 대기 (다음 개장일)
    buy_day = days[0]
    buy = px[buy_day][1]
    window = days[1:1 + HOLD_DAYS]

    exit_day, exit_ret, exit_kind, hit = None, None, None, False
    for i, d in enumerate(window, 1):
        high, low, close = px[d]
        if stop is not None and low <= buy * (1 - stop):   # 손절 우선(보수적)
            exit_day, exit_ret, exit_kind, hold = d, -stop * 100, "손절", i
            break
        if high >= buy * TARGET:                           # 익절
            exit_day, exit_ret, exit_kind, hit, hold = d, (TARGET - 1) * 100, "익절", True, i
            break
    else:
        if len(window) < HOLD_DAYS:
            return {"status": "pending", "buy": buy, "buy_day": buy_day, "elapsed": len(window)}
        exit_day = window[-1]                               # 시간청산(5일째 종가)
        exit_ret, exit_kind, hold = (px[exit_day][2] / buy - 1) * 100, "기간만료", HOLD_DAYS

    # 알파: 같은 보유구간(buy_day→exit_day) 지수 수익률 대비 초과분
    idx = index_close(s.get("mkt", "KOSPI"), bd)
    alpha = None
    if idx.get(buy_day) and idx.get(exit_day):
        idx_ret = (idx[exit_day] / idx[buy_day] - 1) * 100
        alpha = exit_ret - idx_ret
    return {"status": "done", "hit": hit, "exit": exit_kind, "ret": exit_ret,
            "alpha": alpha, "hold": hold, "buy": buy, "buy_day": buy_day}


def main():
    today = datetime.date.today().strftime("%Y-%m-%d")
    snaps = load_snapshots()
    if not snaps:
        sys.exit("평가할 추천 기록이 없습니다 (data/archive/, git 이력 모두 비어 있음)")

    done, pending, nodata, done_src = [], [], [], []
    for base_date in sorted(snaps):
        for s in snaps[base_date]["stocks"]:
            if s.get("rank", 99) > TOP_N:
                continue
            r = simulate(base_date, s)   # 손절 없음(기존 규칙) = 기본 리포트 기준
            row = dict(base=base_date, name=s["name"], code=s["code"],
                       score=s.get("score_total"), parts=s.get("score_parts", {}), **r)
            {"done": done, "pending": pending, "nodata": nodata}[r["status"]].append(row)
            if r["status"] == "done":
                done_src.append((base_date, s))

    def stat(rows):
        rets = [r["ret"] for r in rows]
        wins = [x for x in rets if x > 0]
        losses = [x for x in rets if x <= 0]
        alphas = [r["alpha"] for r in rows if r.get("alpha") is not None]
        aw = sum(wins) / len(wins) if wins else 0.0
        al = sum(losses) / len(losses) if losses else 0.0
        return dict(n=len(rets), exp=sum(rets) / len(rets) if rets else 0.0,
                    hit=len(wins) / len(rets) if rets else 0.0, aw=aw, al=al,
                    payoff=(aw / abs(al)) if al else float("inf"),
                    alpha=(sum(alphas) / len(alphas)) if alphas else None)

    def fnum(x):
        return "∞" if x == float("inf") else f"{x:.2f}"

    lines = [f"📊 <b>주간 모의투자 성과 평가</b> — {today}"]
    if done:
        st = stat(done)
        lines.append(f"확정 {st['n']}건 · 승률 {st['hit'] * 100:.0f}% · <b>기대값 {st['exp']:+.2f}%/건</b>")
        lines.append(f"평균이익 {st['aw']:+.2f}% / 평균손실 {st['al']:+.2f}% · 손익비 {fnum(st['payoff'])}")
        if st["alpha"] is not None:
            lines.append(f"시장대비(알파) 평균 <b>{st['alpha']:+.2f}%p</b>")
        lines.append(f"<i>비용 허들 왕복 약 {COST}% — 기대값이 이보다 커야 실질 흑자</i>")
        best, worst = max(done, key=lambda r: r["ret"]), min(done, key=lambda r: r["ret"])
        lines.append(f"최고 {best['name']} {best['ret']:+.1f}% · 최저 {worst['name']} {worst['ret']:+.1f}%")
        lines.append("")
        for r in sorted(done, key=lambda r: -r["ret"]):
            a = f"·알파{r['alpha']:+.1f}%p" if r.get("alpha") is not None else ""
            lines.append(f"{r['base'][5:]} {r['name']} {r['ret']:+.1f}% ({r['hold']}일·{r['exit']}{a}·점수{r['score']:.0f})")

        # 손절 민감도: 익절+3%/최대5일 고정, 손절선만 바꿔 기대값 비교
        lines.append("")
        lines.append("<b>손절 민감도</b> (손절선만 변경)")
        for stop in STOPS:
            rows = [simulate(b, s, stop) for b, s in done_src]  # px 캐시라 재조회 비용 없음
            sst = stat([r for r in rows if r["status"] == "done"])
            label = "없음" if stop is None else f"-{stop * 100:.0f}%"
            lines.append(f"손절 {label}: 기대값 {sst['exp']:+.2f}% · 승률 {sst['hit'] * 100:.0f}% · 손익비 {fnum(sst['payoff'])}")

        # 점수요소별 승/패 (표본 8건↑)
        if len(done) >= 8:
            wins = [r for r in done if r["ret"] > 0]
            losers = [r for r in done if r["ret"] <= 0]
            names = {"size": "수급규모", "persist": "지속성", "today": "당일쌍끌이", "quality": "우량주", "risk": "과열리스크"}
            diffs = [f"{nm} 승{sum(r['parts'].get(k, 0) for r in wins) / max(1, len(wins)):.1f}"
                     f"/패{sum(r['parts'].get(k, 0) for r in losers) / max(1, len(losers)):.1f}"
                     for k, nm in names.items()]
            lines.append("")
            lines.append("<i>점수요소 평균(승/패): " + " · ".join(diffs) + "</i>")
        if len(done) < 20:
            lines.append("<i>표본 20건 미만 — 통계적 의미는 낮습니다.</i>")
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
