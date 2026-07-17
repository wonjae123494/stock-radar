#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
수급 쌍끌이 레이더 — 네이버 금융 우회 수집 (KRX 차단 환경용: GitHub Actions 등 해외 IP)

pykrx(KRX)와 동일한 data/data.json 스키마를 만든다. 차이점:
  - 당일 순매수 '금액'은 네이버 매매상위 iframe의 정확한 값(백만원)을 사용
  - 과거 3일 이력은 종목별 일별 순매매량(주) × 그날 종가로 '추정'한 억원
  - 시장경보(warn) 정보 없음 → None

데이터원 (모두 해외 IP 접근 가능):
  - finance.naver.com/sise/sise_deal_rank_iframe.naver : 당일 기관/외국인 순매수 상위 40 (금액)
  - finance.naver.com/item/frgn.naver?code=            : 종목별 일별 기관/외인 순매매량 + 종가
  - m.stock.naver.com/api/stock/{code}/basic, /integration : 시세·PER·PBR·배당·52주·시총
"""
import io, json, os, re, sys, time, datetime

import requests

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas가 필요합니다: pip install pandas lxml")

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
     "Referer": "https://finance.naver.com/"}
SLEEP = 0.2  # 네이버 부하 방지


def _get(url, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, headers=H, timeout=15)
            r.raise_for_status()
            return r
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1 + i)


def _num(s):
    """'121,400' / '20.61배' / '0.65%' / '12,372원' → float, 실패 시 None"""
    if s is None:
        return None
    m = re.search(r"-?[\d,]+(?:\.\d+)?", str(s))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _cap_jo(s):
    """'1,490조 8,010억' / '9,850억' → 조 단위 float"""
    if not s:
        return 0.0
    jo = re.search(r"([\d,]+)\s*조", s)
    eok = re.search(r"([\d,]+)\s*억", s)
    v = (float(jo.group(1).replace(",", "")) if jo else 0.0) \
        + (float(eok.group(1).replace(",", "")) / 10000 if eok else 0.0)
    return round(v, 1)


def top_buy_list(sosok, investor_gubun):
    """당일 순매수 상위 (금액 억원). returns {code: (name, 금액억)}"""
    u = (f"https://finance.naver.com/sise/sise_deal_rank_iframe.naver"
         f"?sosok={sosok}&investor_gubun={investor_gubun}&type=buy")
    r = _get(u)
    r.encoding = "euc-kr"
    t = re.sub(r"\s+", " ", r.text)
    rows = re.findall(
        r"code=(\w{6})[^>]*title='([^']+)'[^<]*</a></p></td>"
        r" <td class=\"number\">(-?[\d,]+)</td> <td class=\"number\">(-?[\d,]+)</td>", t)
    out = {}
    for code, name, _qty, amt_mn in rows:
        amt = _num(amt_mn)
        if amt is not None:
            out[code] = (name, round(amt / 100, 1))  # 백만원 → 억원
    return out


def daily_flows(code):
    """종목별 최근 일별: {YYYYMMDD: {"close", "chg", "fx_eok", "inst_eok"}} (금액은 수량×종가 추정)"""
    r = _get(f"https://finance.naver.com/item/frgn.naver?code={code}")
    r.encoding = "euc-kr"
    try:
        tables = pd.read_html(io.StringIO(r.text))
    except ValueError:
        return {}
    df = None
    for t in tables:
        cols = ["".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in t.columns]
        if any("날짜" in c for c in cols) and any("순매매량" in c for c in cols):
            t.columns = cols
            df = t
            break
    if df is None:
        return {}
    date_c = next(c for c in df.columns if "날짜" in c)
    close_c = next(c for c in df.columns if "종가" in c)
    chg_c = next(c for c in df.columns if "등락률" in c)
    inst_c = next(c for c in df.columns if "기관" in c)
    fx_c = next(c for c in df.columns if "외국인" in c and "순매매량" in c)
    out = {}
    for _, row in df.iterrows():
        d = str(row[date_c])
        if not re.match(r"\d{4}\.\d{2}\.\d{2}", d):
            continue
        ymd = d.replace(".", "")
        close = _num(row[close_c])
        if close is None:
            continue
        inst_q, fx_q = _num(row[inst_c]) or 0.0, _num(row[fx_c]) or 0.0
        out[ymd] = {"close": close, "chg": _num(row[chg_c]) or 0.0,
                    "fx_eok": round(fx_q * close / 1e8, 1),
                    "inst_eok": round(inst_q * close / 1e8, 1)}
    return out


def stock_info(code):
    """basic+integration API → dict 또는 None(ETF/ETN/조회불가는 제외)"""
    try:
        b = _get(f"https://m.stock.naver.com/api/stock/{code}/basic").json()
        if b.get("stockEndType") != "stock":
            return None
        time.sleep(SLEEP)
        g = _get(f"https://m.stock.naver.com/api/stock/{code}/integration").json()
    except Exception:
        return None
    info = {i.get("code"): i.get("value") for i in g.get("totalInfos", [])}
    per, pbr = _num(info.get("per")), _num(info.get("pbr"))
    div, eps = _num(info.get("dividendYieldRatio")), _num(info.get("eps"))
    return dict(
        name=b.get("stockName") or code,
        mkt="KOSDAQ" if str(b.get("sosok")) == "1" else "KOSPI",
        price=int(_num(b.get("closePrice")) or 0),
        chg=round(_num(b.get("fluctuationsRatio")) or 0.0, 2),
        w52l=int(_num(info.get("lowPriceOf52Weeks")) or 0),
        w52h=int(_num(info.get("highPriceOf52Weeks")) or 0),
        per=per if per else None, pbr=pbr if pbr else None,
        div=div if div else None, eps=eps,
        cap=_cap_jo(info.get("marketValue")))


def collect(days=4, top=30):
    print("네이버 금융 우회 수집 시작 (KRX 미사용)")

    # 0) 거래일: 삼성전자 일별 표에서 추출 (18시 이전이면 당일 제외 — 데이터 미확정)
    samsung = daily_flows("005930")
    if not samsung:
        sys.exit("네이버 일별 데이터 조회 실패 — 잠시 후 재시도 필요")
    all_dates = sorted(samsung)
    now = datetime.datetime.now()
    if all_dates and all_dates[-1] == now.strftime("%Y%m%d") and now.hour < 18:
        print(f"  ⚠ 당일({all_dates[-1]}) 데이터 미확정(현재 {now.hour}시) → 직전 거래일 기준")
        all_dates = all_dates[:-1]
    dates = all_dates[-days:]
    latest = dates[-1]
    print(f"거래일: {dates}")

    # 1) 당일 순매수 상위 (KOSPI=01, KOSDAQ=02 / 기관=1000, 외국인=9000)
    day_inst, day_fx = {}, {}
    for sosok in ("01", "02"):
        day_inst.update(top_buy_list(sosok, "1000")); time.sleep(SLEEP)
        day_fx.update(top_buy_list(sosok, "9000")); time.sleep(SLEEP)
    print(f"당일 상위: 기관 {len(day_inst)}종목, 외국인 {len(day_fx)}종목")

    top_inst = sorted(day_inst.items(), key=lambda kv: -kv[1][1])[:top * 2]  # KOSPI+KOSDAQ 합산이므로 2배
    top_fx = sorted(day_fx.items(), key=lambda kv: -kv[1][1])[:top * 2]

    # 2) 상위 종목들의 일별 이력 → 쌍끌이 판정
    pool = {c for c, _ in top_inst} | {c for c, _ in top_fx}
    hist = {}
    for c in sorted(pool):
        hist[c] = daily_flows(c)
        time.sleep(SLEEP)

    def flow_at(c, d):
        h = hist.get(c, {}).get(d)
        if not h:
            return None, None
        fx = day_fx[c][1] if (d == latest and c in day_fx) else h["fx_eok"]
        inst = day_inst[c][1] if (d == latest and c in day_inst) else h["inst_eok"]
        return fx, inst

    cands = set()
    for c in pool:
        fx, inst = flow_at(c, latest)
        if fx and inst and fx > 0 and inst > 0:          # ①② 당일 쌍끌이
            cands.add(c)
    print(f"당일 쌍끌이 후보: {len(cands)}종목")
    for c, _ in top_inst:                                 # ③ 4일 누적 쌍끌이
        pairs = [flow_at(c, d) for d in dates]
        fx_sum = sum(p[0] or 0 for p in pairs)
        in_sum = sum(p[1] or 0 for p in pairs)
        if fx_sum > 0 and in_sum > 0:
            cands.add(c)

    # 3) 종목 정보 + 조립 (ETF/ETN은 stock_info에서 걸러짐)
    stocks = []
    for c in sorted(cands):
        info = stock_info(c)
        time.sleep(SLEEP)
        if not info or not info["price"] or not info["w52h"]:
            continue
        fdata = {}
        for d in dates:
            fx, inst = flow_at(c, d)
            if fx is not None:
                fdata[d[4:6] + "-" + d[6:]] = [fx, inst]
        if not fdata:
            continue
        stocks.append(dict(name=info["name"], code=c, mkt=info["mkt"], flows=fdata,
                           price=info["price"], chg=info["chg"], w52l=info["w52l"], w52h=info["w52h"],
                           per=info["per"], pbr=info["pbr"], div=info["div"], eps=info["eps"],
                           cap=info["cap"], warn=None, why="", strategy=""))

    out = dict(base_date=f"{latest[:4]}-{latest[4:6]}-{latest[6:]}",
               quote_time=f"{latest[:4]}-{latest[4:6]}-{latest[6:]} 종가",
               flow_dates=[d[4:6] + "-" + d[6:] for d in dates],
               market_note="", stocks=stocks,
               source="naver")  # 과거 이력 금액은 수량×종가 추정치
    os.makedirs("data", exist_ok=True)
    json.dump(out, open("data/data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"data/data.json 저장 — 후보 {len(stocks)}종목 (네이버 기반). 다음: python score.py")


if __name__ == "__main__":
    collect()
