#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
시장 레짐(국면) 판정 — "지금 신규 진입해도 되는 장인가"를 지수 흐름으로 신호화.

종목 선정 점수(score.py)는 절대 건드리지 않는다. 이 모듈은 시장 전체 상태만 보고
'권고 노출(비중) %'와 경고 배너 텍스트를 만든다. (참고 신호이며 투자 권유가 아님.)

판정 근거(지수별 위험 점수 합산, KOSPI·KOSDAQ 중 나쁜 쪽 채택):
  +1  최근 5거래일 수익률 ≤ -4%   / 추가 +1  ≤ -8%   (낙폭)
  +1  종가가 20일 이동평균 아래     (하락추세)
  +1  최근 10일 평균 일간변동 ≥ 3% / 추가 +1  ≥ 4.5%  (변동성·패닉)
  → 3점↑ 위험(노출 0%) · 2점 주의(50%) · 1점↓ 정상(100%)

데이터: pykrx 지수, 실패 시 네이버 지수(해외 IP/GitHub Actions 대비).
"""
import datetime, io, os, re, time

import requests


def _load_env():
    """pykrx 지수 조회에 필요한 KRX 로그인값을 .env에서 로드 (import 전에 실행돼야 함)"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

H = {"User-Agent": "Mozilla/5.0 Chrome/126", "Referer": "https://finance.naver.com/"}
IDX = {"KOSPI": "1001", "KOSDAQ": "2001"}


def _krx_index(code, start, end):
    try:
        from pykrx import stock
        df = stock.get_index_ohlcv(start, end, code)
        return [float(v) for v in df["종가"].tolist()]
    except Exception:
        return []


def _naver_index(mkt, need):
    try:
        import pandas as pd
    except ImportError:
        return []
    closes = {}
    for page in range(1, 5):
        try:
            r = requests.get(f"https://finance.naver.com/sise/sise_index_day.naver?code={mkt}&page={page}",
                             headers=H, timeout=15)
            r.encoding = "euc-kr"
            df = pd.read_html(io.StringIO(r.text))[0].dropna()
        except Exception:
            break
        oldest = None
        for _, row in df.iterrows():
            d = str(row.get("날짜", ""))
            if not re.match(r"\d{4}\.\d{2}\.\d{2}", d):
                continue
            closes[d.replace(".", "")] = float(str(row["체결가"]).replace(",", ""))
            oldest = d
        if oldest is None or len(closes) >= need:
            break
        time.sleep(0.2)
    return [closes[k] for k in sorted(closes)]


def _closes(name):
    """과거→최신 종가 리스트 (약 30거래일)"""
    end = datetime.date.today().strftime("%Y%m%d")
    start = (datetime.date.today() - datetime.timedelta(days=45)).strftime("%Y%m%d")
    c = _krx_index(IDX[name], start, end)
    if len(c) < 21:
        c = _naver_index(name, 25)
    return c


def _score_one(closes):
    """(위험점수, metrics) 또는 None(데이터 부족)"""
    if len(closes) < 6:
        return None
    last = closes[-1]
    ret5 = (last / closes[-6] - 1) * 100
    ma20 = sum(closes[-20:]) / len(closes[-20:])
    daily = [abs(closes[i] / closes[i - 1] - 1) * 100 for i in range(max(1, len(closes) - 10), len(closes))]
    vol = sum(daily) / len(daily) if daily else 0.0
    pts = 0
    if ret5 <= -4: pts += 1
    if ret5 <= -8: pts += 1
    if last < ma20: pts += 1
    if vol >= 3.0: pts += 1
    if vol >= 4.5: pts += 1
    return pts, dict(ret5=round(ret5, 1), vol=round(vol, 1), below_ma=bool(last < ma20))


def assess():
    """레짐 판정 dict 또는 None(판정 불가). score.py가 recommendations.json에 실어 나른다."""
    res = {}
    for nm in ("KOSPI", "KOSDAQ"):
        try:
            res[nm] = _score_one(_closes(nm))
        except Exception:
            res[nm] = None
    scored = [v for v in res.values() if v]
    if not scored:
        return None
    pts = max(v[0] for v in scored)
    label, exposure, emoji = (("위험", 0, "🚨") if pts >= 3 else
                              ("주의", 50, "⚠️") if pts == 2 else
                              ("정상", 100, "🟢"))
    reasons = []
    for nm, v in res.items():
        if not v:
            continue
        m = v[1]
        tag = []
        if m["ret5"] <= -4: tag.append(f"5일 {m['ret5']:+.1f}%")
        if m["below_ma"]: tag.append("20일선 이탈")
        if m["vol"] >= 3.0: tag.append(f"변동성 {m['vol']:.1f}%")
        if tag:
            reasons.append(f"{nm} {'·'.join(tag)}")
    return dict(label=label, exposure=exposure, emoji=emoji, points=pts, reasons=reasons)


if __name__ == "__main__":
    import json
    print(json.dumps(assess(), ensure_ascii=False, indent=1))
