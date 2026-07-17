#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
수급 쌍끌이 레이더 — 데이터 수집 (로컬 실행용, pykrx 필요: pip install pykrx)

최근 N거래일의 기관/외국인 순매수(전종목, KOSPI+KOSDAQ)와
후보 종목의 시세·재무·52주 범위를 수집해 data/data.json 으로 저장한다.

사용: python fetch_data.py [--days 4] [--top 30]
"""
import argparse, json, datetime, sys, os

def _load_env():
    """같은 폴더의 .env를 환경변수로 로드 (pykrx가 import 시점에 KRX_ID/KRX_PW를 읽으므로 import보다 먼저 실행)"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

# pykrx는 import 시점에 KRX 로그인을 시도한다. KRX는 해외 IP를 차단하므로
# GitHub Actions 등에서는 여기서 예외가 난다 → 네이버 우회 수집으로 자동 전환.
PYKRX_ERR = None
try:
    from pykrx import stock
except Exception as e:  # ImportError뿐 아니라 로그인 실패(JSONDecodeError 등)도 잡는다
    PYKRX_ERR = f"{type(e).__name__}: {e}"

EOK = 100_000_000  # 억원

def trading_dates(n):
    """최근 n거래일 (YYYYMMDD 리스트, 과거→최신)

    당일 장중~마감 직후(≈18시 이전)엔 투자자 순매수 데이터가 아직 확정되지 않아
    후보 0종목의 빈 결과가 나오고, 이게 기존 정상 데이터를 덮어써 버린다.
    그래서 '오늘'이 최신 거래일인데 아직 18시 전이면 오늘을 빼고 직전 거래일까지만 쓴다.
    (예약 실행은 19:05/19:45라 18시 이후 → 오늘 데이터를 정상 사용)
    """
    end = stock.get_nearest_business_day_in_a_week()
    start = (datetime.datetime.strptime(end, "%Y%m%d") - datetime.timedelta(days=n * 3 + 15)).strftime("%Y%m%d")
    idx = [d.strftime("%Y%m%d") for d in stock.get_index_ohlcv(start, end, "1001").index]  # 코스피 지수 거래일
    now = datetime.datetime.now()
    if idx and idx[-1] == now.strftime("%Y%m%d") and now.hour < 18:
        print(f"  ⚠ 당일({idx[-1]}) 수급 데이터 미확정(현재 {now.hour}시) → 직전 거래일 기준으로 조회")
        idx = idx[:-1]
    return idx[-n:]

def net_buy(date, market, investor):
    """해당일 투자자 순매수 (종목코드 → (종목명, 순매수 억원))"""
    df = stock.get_market_net_purchases_of_equities(date, date, market, investor)
    return {code: (row["종목명"], round(row["순매수거래대금"] / EOK, 1)) for code, row in df.iterrows()}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=4)
    ap.add_argument("--top", type=int, default=30, help="기관 순매수 상위 N을 후보 풀로")
    ap.add_argument("--naver", action="store_true", help="KRX 대신 네이버 우회 수집 강제 (테스트용)")
    args = ap.parse_args()

    if args.naver or PYKRX_ERR or os.environ.get("NAVER_FALLBACK"):
        if PYKRX_ERR:
            print(f"pykrx 사용 불가({PYKRX_ERR[:120]})")
        import collect_naver
        collect_naver.collect(args.days, args.top)
        return

    try:
        collect_krx(args)
    except Exception as e:
        print(f"KRX 수집 실패({type(e).__name__}: {e}) → 네이버 우회 수집으로 전환")
        import collect_naver
        collect_naver.collect(args.days, args.top)

def collect_krx(args):
    dates = trading_dates(args.days)
    latest = dates[-1]
    print(f"거래일: {dates}")

    flows = {}  # date -> code -> {"name","fx","inst"}
    for d in dates:
        day = {}
        for mkt in ("KOSPI", "KOSDAQ"):
            inst = net_buy(d, mkt, "기관합계")
            frgn = net_buy(d, mkt, "외국인")
            for code in set(inst) | set(frgn):
                nm = (inst.get(code) or frgn.get(code))[0]
                day[code] = {"name": nm, "mkt": mkt,
                             "fx": frgn.get(code, (nm, 0.0))[1],
                             "inst": inst.get(code, (nm, 0.0))[1]}
        flows[d] = day
        print(f"  {d}: {len(day)}종목")

    # 후보: ① 최신일 기관 순매수 상위 N 중 외국인도 순매수  ② 최신일 외국인 상위 N 중 기관도 순매수
    day = flows[latest]
    top_inst = sorted(day.items(), key=lambda kv: -kv[1]["inst"])[:args.top]
    top_fx = sorted(day.items(), key=lambda kv: -kv[1]["fx"])[:args.top]
    cands = {c for c, v in top_inst if v["fx"] > 0 and v["inst"] > 0} | \
            {c for c, v in top_fx if v["fx"] > 0 and v["inst"] > 0}
    print(f"당일 쌍끌이 후보: {len(cands)}종목")

    # ③ 누적 쌍끌이: 4일 합계 양쪽 + 최신일 기관 상위
    for c, v in top_inst:
        fx_sum = sum(flows[d].get(c, {}).get("fx", 0) for d in dates)
        in_sum = sum(flows[d].get(c, {}).get("inst", 0) for d in dates)
        if fx_sum > 0 and in_sum > 0:
            cands.add(c)

    y1 = (datetime.datetime.strptime(latest, "%Y%m%d") - datetime.timedelta(days=365)).strftime("%Y%m%d")
    fund = {}
    for mkt in ("KOSPI", "KOSDAQ"):
        f = stock.get_market_fundamental(latest, market=mkt)
        cap = stock.get_market_cap(latest, market=mkt)
        for c in cands:
            if c in f.index:
                fund[c] = dict(per=float(f.loc[c, "PER"]) or None, pbr=float(f.loc[c, "PBR"]) or None,
                               div=float(f.loc[c, "DIV"]) or None, eps=float(f.loc[c, "EPS"]),
                               cap=round(float(cap.loc[c, "시가총액"]) / 1e12, 1))

    stocks = []
    for c in sorted(cands):
        o = stock.get_market_ohlcv(y1, latest, c)
        if o.empty: continue
        px = int(o["종가"].iloc[-1]); prev = int(o["종가"].iloc[-2]) if len(o) > 1 else px
        info = day.get(c) or {}
        fdata = {d[4:6] + "-" + d[6:]: [flows[d][c]["fx"], flows[d][c]["inst"]] for d in dates if c in flows[d]}
        stocks.append(dict(
            name=info.get("name") or stock.get_market_ticker_name(c), code=c, mkt=info.get("mkt", "KOSPI"),
            flows=fdata, price=px, chg=round((px / prev - 1) * 100, 2),
            w52l=int(o["저가"].min()), w52h=int(o["고가"].max()),
            **fund.get(c, dict(per=None, pbr=None, div=None, eps=None, cap=0.0)),
            warn=None, why="", strategy=""))

    out = dict(base_date=f"{latest[:4]}-{latest[4:6]}-{latest[6:]}",
               quote_time=f"{latest[:4]}-{latest[4:6]}-{latest[6:]} 종가",
               flow_dates=[d[4:6] + "-" + d[6:] for d in dates], stocks=stocks)
    os.makedirs("data", exist_ok=True)
    json.dump(out, open("data/data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"data/data.json 저장 — 후보 {len(stocks)}종목. 다음: python score.py")

if __name__ == "__main__":
    main()
