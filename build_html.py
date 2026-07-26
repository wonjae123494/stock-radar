#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data/recommendations.json → data/index.html (자체완결형 대시보드)"""
import json, datetime

D = json.load(open("data/recommendations.json", encoding="utf-8"))
S = D["stocks"]
FD = D["flow_dates"]
NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
BANNER = D.get("market_note", "")  # 시장 상황 한 줄 (뉴스 분석 시 data.json에 market_note로 기입)
if D.get("source") == "naver":
    BANNER = (BANNER + " " if BANNER else "") + "(클라우드 자동판 — 과거 일자 수급 금액은 네이버 수량×종가 기반 추정치)"

def won(n): return f"{n:,}"

def flow_svg(s):
    W, H, PAD_T, PAD_B = 300, 132, 26, 20
    vals = []
    for d in FD:
        v = s["flows"].get(d)
        a, b = (v[0], v[1]) if v else (None, None)
        vals.append((d, a, b))
    mx = max([abs(x) for _, a, b in vals for x in (a, b) if x is not None] + [100])
    zero_y = PAD_T + (H - PAD_T - PAD_B) / 2
    scale = (H - PAD_T - PAD_B) / (2 * mx)
    gw = W / len(FD)
    bars = []
    for i, (d, a, b) in enumerate(vals):
        cx = gw * i + gw / 2
        for j, (v, cls, nm) in enumerate([(a, "fx", "외국인"), (b, "inst", "기관")]):
            x = cx - 15 + j * 16
            if v is None:
                bars.append(f'<text x="{x+7}" y="{zero_y-4}" class="miss" text-anchor="middle">·</text>')
                continue
            h = max(2, abs(v) * scale)
            y = zero_y - h if v >= 0 else zero_y + 2
            lab_y = y - 3 if v >= 0 else y + h + 9
            bars.append(
                f'<g class="bar"><title>{d} {nm} {"+" if v>=0 else ""}{v:g}억</title>'
                f'<rect x="{x:.1f}" y="{y:.1f}" width="14" height="{h:.1f}" rx="3" class="{cls}{" neg" if v<0 else ""}"/>'
                f'<text x="{x+7:.1f}" y="{lab_y:.1f}" text-anchor="middle" class="val">{v:+,.0f}</text></g>')
        bars.append(f'<text x="{cx:.1f}" y="{H-4}" text-anchor="middle" class="ax">{d.lstrip("0")}</text>')
    return (f'<svg viewBox="0 0 {W} {H}" class="flow" role="img" aria-label="최근 {len(FD)}거래일 외국인·기관 순매수(억원)">'
            f'<line x1="0" y1="{zero_y}" x2="{W}" y2="{zero_y}" class="base"/>{"".join(bars)}</svg>')

def band_svg(s):
    W, H = 300, 46
    x0, x1 = 8, W - 8
    mx = x0 + (x1 - x0) * s["pos"] / 100
    return (f'<svg viewBox="0 0 {W} {H}" class="band" role="img" aria-label="52주 범위 내 위치 {s["pos"]}%">'
            f'<line x1="{x0}" y1="18" x2="{x1}" y2="18" class="track"/>'
            f'<line x1="{x0}" y1="18" x2="{mx:.1f}" y2="18" class="fill"/>'
            f'<circle cx="{mx:.1f}" cy="18" r="6" class="dot"/>'
            f'<text x="{mx:.1f}" y="9" text-anchor="middle" class="pos">{s["pos"]}%</text>'
            f'<text x="{x0}" y="40" class="ax">최저 {won(s["w52l"])}</text>'
            f'<text x="{x1}" y="40" text-anchor="end" class="ax">최고 {won(s["w52h"])}</text></svg>')

def gauge(s):
    t = s["score_total"]
    R, C = 26, 2 * 3.14159 * 26
    off = C * (1 - t / 100)
    cls = "g-hi" if t >= 70 else ("g-md" if t >= 55 else "g-lo")
    return (f'<svg viewBox="0 0 64 64" class="gauge {cls}"><circle cx="32" cy="32" r="{R}" class="g-bg"/>'
            f'<circle cx="32" cy="32" r="{R}" class="g-fg" stroke-dasharray="{C:.1f}" stroke-dashoffset="{off:.1f}" transform="rotate(-90 32 32)"/>'
            f'<text x="32" y="30" text-anchor="middle" class="g-num">{t:.0f}</text>'
            f'<text x="32" y="43" text-anchor="middle" class="g-lab">/100</text></svg>')

def breakdown(s):
    p = s["score_parts"]
    rows = [("수급 규모", p["size"], 25), ("수급 지속성", p["persist"], 25), ("당일 쌍끌이", p["today"], 20),
            ("우량주", p["quality"], 20), ("과열 리스크", p["risk"], 10)]
    return "".join(f'<div class="bd-row"><span class="bd-n">{nm}</span>'
                   f'<span class="bd-t"><span class="bd-f" style="width:{v/mx*100:.0f}%"></span></span>'
                   f'<span class="bd-v">{v:g}/{mx}</span></div>' for nm, v, mx in rows)

def badges(s):
    b = []
    if s.get("divergence"):
        b.append('<span class="bdg bdg-warn">📉 점수↑ 주가↓</span>')
    v = s["flows"].get(FD[-1])
    if v and v[0] is not None and v[1] is not None and v[0] > 0 and v[1] > 0:
        b.append('<span class="bdg bdg-red">당일 쌍끌이</span>')
    if s["both_days"] >= 2:
        b.append('<span class="bdg bdg-blue">연속 수급</span>')
    if s.get("per") and s["per"] < 10:
        b.append('<span class="bdg bdg-green">저PER</span>')
    if (s.get("div") or 0) >= 3:
        b.append('<span class="bdg bdg-green">고배당</span>')
    if not s.get("per"):
        b.append('<span class="bdg bdg-crit">⚠ 적자기업</span>')
    if s.get("warn"):
        b.append(f'<span class="bdg bdg-warn">⚠ {s["warn"]}</span>')
    return "".join(b)

def metric(label, val):
    return f'<div class="m"><div class="m-l">{label}</div><div class="m-v">{val}</div></div>'

def drop_block(s):
    """점수는 높은데 주가가 하락 중인 종목의 원인 분석 리포트"""
    if not s.get("divergence"):
        return ""
    txt = s.get("drop_why") or "원인 분석 대기 — 다음 갱신 때 작성됩니다."
    return (f'<div class="drop"><b>📉 점수는 높은데 주가는 하락 — 왜?</b>'
            f'<p>{txt}</p></div>')

cards = ""
for s in S:
    chg = s["chg"]
    chg_cls = "up" if chg > 0 else ("dn" if chg < 0 else "")
    per = f'{s["per"]:.1f}배' if s.get("per") else "적자(N/A)"
    div = f'{s["div"]:.2f}%' if s.get("div") else "—"
    pbr = f'{s["pbr"]:.1f}배' if s.get("pbr") else "—"
    ref = ' card-ref' if not s.get("per") else ""
    cards += f"""
<article class="card{ref}" id="s-{s["code"]}">
 <header class="c-head">
   <div class="rank">{s["rank"]}</div>
   <div class="c-title"><h2>{s["name"]} <span class="code">{s["code"]} · {s["mkt"]}</span></h2>
     <div class="bdgs">{badges(s)}</div></div>
   {gauge(s)}
 </header>
 <div class="c-price"><span class="p">{won(s["price"])}원</span><span class="c {chg_cls}">{chg:+.2f}%</span><span class="asof">{D["quote_time"]}</span></div>
 <div class="metrics">{metric("PER", per)}{metric("PBR", pbr)}{metric("배당수익률", div)}{metric("시가총액", f'{s["cap"]:.1f}조' if s.get("cap") else "—")}{metric(f"{len(FD)}일 순매수 합", f'{s["total_flow"]:+,}억')}{metric("쌍끌이 일수", f'{s["both_days"]}/{s["days"]}일')}</div>
 <div class="viz2">
   <div><div class="viz-t">기관·외국인 순매수 (억원)</div>{flow_svg(s)}</div>
   <div><div class="viz-t">52주 가격 밴드</div>{band_svg(s)}
     <div class="viz-t" style="margin-top:10px">점수 구성</div><div class="bd">{breakdown(s)}</div></div>
 </div>
 <div class="imgs"><img loading="lazy" alt="{s["name"]} 일중 차트" src="https://ssl.pstatic.net/imgfinance/chart/item/area/day/{s["code"]}.png" onerror="this.parentElement.style.display='none'">
   <img loading="lazy" alt="{s["name"]} 3개월 차트" src="https://ssl.pstatic.net/imgfinance/chart/item/candle/month/{s["code"]}.png" onerror="this.style.display='none'"></div>
 <div class="why"><b>왜 수급이 몰렸나</b><p>{s["why"]}</p></div>
 {drop_block(s)}
 <div class="strat"><b>매수 전략 메모</b><p>{s["strategy"]}</p></div>
</article>"""

rows = ""
for s in S:
    v = s["flows"].get(FD[-1]) or (None, None)
    fx = f'{v[0]:+,.0f}' if v[0] is not None else "·"
    inst = f'{v[1]:+,.0f}' if v[1] is not None else "·"
    rows += (f'<tr><td>{s["rank"]}</td><td>{s["name"]}</td><td>{s["code"]}</td><td class="num">{won(s["price"])}</td>'
             f'<td class="num">{fx}</td><td class="num">{inst}</td><td class="num">{s["total_flow"]:+,}</td>'
             f'<td class="num">{s.get("per") or "—"}</td><td class="num">{s.get("div") or "—"}</td>'
             f'<td class="num">{s["pos"]}%</td><td class="num"><b>{s["score_total"]}</b></td></tr>')

banner_html = f'<div class="banner"><b>시장 상황</b> — {BANNER}</div>' if BANNER else ""

R = D.get("regime")
regime_html = ""
if R:
    cls = {"위험": "rg-danger", "주의": "rg-caution", "정상": "rg-normal"}.get(R["label"], "rg-normal")
    reasons = " · ".join(R.get("reasons") or [])
    regime_html = (f'<div class="regime {cls}"><div class="rg-top">{R["emoji"]} 시장 레짐 '
                   f'<b>{R["label"]}</b> — 신규 진입 권고 노출 <b>{R["exposure"]}%</b></div>'
                   f'{f"<div class=rg-why>{reasons}</div>" if reasons else ""}'
                   f'<div class="rg-note">지수 5일수익·20일선·변동성 기반 기계적 신호이며, '
                   f'종목 점수와 무관한 참고 정보입니다(투자 권유 아님).</div></div>')

toc_items = "".join(
    f'<a class="toc-i{" toc-ref" if not s.get("per") else ""}" href="#s-{s["code"]}">'
    f'<span class="toc-r">{s["rank"]}</span>{s["name"]}'
    f'{"<span class=toc-w>⚠</span>" if (s.get("warn") or not s.get("per")) else ""}'
    f'{"<span class=toc-w>📉</span>" if s.get("divergence") else ""}'
    f'<span class="toc-s">{s["score_total"]:.0f}점</span></a>' for s in S)
toc_html = (f'<nav class="toc"><details open><summary>📑 목차 · 기준일 <b>{D["base_date"]}</b> · 후보 {len(S)}종목 <span class="toc-hint">(종목을 누르면 바로 이동)</span></summary>'
            f'<div class="toc-grid">{toc_items}'
            f'<a class="toc-i" href="#summary"><span class="toc-r">📋</span>전체 요약표<span class="toc-s">표</span></a></div></details></nav>')

html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>수급 쌍끌이 레이더 — 저평가 우량주 매수 후보</title>
<style>
:root{{--surface:#fcfcfb;--page:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--base:#c3c2b7;
--border:rgba(11,11,11,.10);--fx:#1baf7a;--inst:#2a78d6;--red:#e34948;--up:#c62b2b;--dn:#1c5cab;
--good:#006300;--warn:#b97500;--crit:#d03b3b;--chip:#f0efec}}
@media(prefers-color-scheme:dark){{:root{{--surface:#1a1a19;--page:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
--grid:#2c2c2a;--base:#383835;--border:rgba(255,255,255,.10);--fx:#199e70;--inst:#3987e5;--red:#e66767;
--up:#ff7b7b;--dn:#6da7ec;--good:#0ca30c;--warn:#fab219;--crit:#e66767;--chip:#262624}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--page);color:var(--ink);
font:15px/1.55 system-ui,-apple-system,"Segoe UI","Malgun Gothic",sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:28px 18px 60px}}
h1{{font-size:24px;margin:0 0 4px}}.sub{{color:var(--ink2);margin:0 0 14px}}
.banner{{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--red);
border-radius:10px;padding:12px 16px;margin:14px 0;color:var(--ink2)}}
.banner b{{color:var(--ink)}}
.regime{{border-radius:10px;padding:12px 16px;margin:14px 0;border:1px solid var(--border)}}
.regime .rg-top{{font-size:15px;color:var(--ink)}}
.regime .rg-why{{margin-top:3px;font-size:13px;color:var(--ink2)}}
.regime .rg-note{{margin-top:5px;font-size:11.5px;color:var(--muted)}}
.rg-danger{{background:color-mix(in srgb,var(--red) 12%,var(--surface));border-left:4px solid var(--red)}}
.rg-caution{{background:color-mix(in srgb,var(--warn) 12%,var(--surface));border-left:4px solid var(--warn)}}
.rg-normal{{background:color-mix(in srgb,var(--good) 10%,var(--surface));border-left:4px solid var(--good)}}
.steps{{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 26px}}
.step{{background:var(--surface);border:1px solid var(--border);border-radius:999px;padding:6px 14px;font-size:13px;color:var(--ink2)}}
.step b{{color:var(--ink)}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px;margin:0 0 22px}}
.card-ref{{opacity:.92;border-style:dashed}}
.c-head{{display:flex;gap:14px;align-items:flex-start}}
.rank{{font-size:22px;font-weight:800;color:var(--muted);min-width:30px;line-height:1.2;padding-top:2px}}
.c-title{{flex:1}}.c-title h2{{margin:0;font-size:19px}}.code{{font-size:13px;font-weight:400;color:var(--muted)}}
.bdgs{{margin-top:6px;display:flex;flex-wrap:wrap;gap:6px}}
.bdg{{font-size:11.5px;padding:2.5px 9px;border-radius:999px;background:var(--chip);color:var(--ink2)}}
.bdg-red{{background:color-mix(in srgb,var(--red) 14%,var(--surface));color:var(--red);font-weight:700}}
.bdg-blue{{background:color-mix(in srgb,var(--inst) 14%,var(--surface));color:var(--inst);font-weight:700}}
.bdg-green{{background:color-mix(in srgb,var(--good) 12%,var(--surface));color:var(--good);font-weight:700}}
.bdg-warn{{background:color-mix(in srgb,var(--warn) 14%,var(--surface));color:var(--warn);font-weight:700}}
.bdg-crit{{background:color-mix(in srgb,var(--crit) 14%,var(--surface));color:var(--crit);font-weight:700}}
.gauge{{width:64px;height:64px;flex:none}}
.g-bg{{fill:none;stroke:var(--grid);stroke-width:6}}
.g-fg{{fill:none;stroke-width:6;stroke-linecap:round}}
.g-hi .g-fg{{stroke:var(--good)}}.g-md .g-fg{{stroke:var(--inst)}}.g-lo .g-fg{{stroke:var(--muted)}}
.g-num{{font-size:17px;font-weight:800;fill:var(--ink)}}.g-lab{{font-size:9px;fill:var(--muted)}}
.c-price{{margin:10px 0 2px;display:flex;align-items:baseline;gap:10px}}
.c-price .p{{font-size:21px;font-weight:800}}.c-price .c{{font-weight:700}}
.up{{color:var(--up)}}.dn{{color:var(--dn)}}.asof{{font-size:12px;color:var(--muted)}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(96px,1fr));gap:8px;margin:12px 0}}
.m{{background:var(--chip);border-radius:8px;padding:7px 10px}}
.m-l{{font-size:11px;color:var(--muted)}}.m-v{{font-weight:700;font-variant-numeric:tabular-nums}}
.viz2{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:8px 0}}
@media(max-width:640px){{.viz2{{grid-template-columns:1fr}}}}
.viz-t{{font-size:12px;color:var(--muted);margin-bottom:4px}}
svg.flow{{width:100%;height:auto}}svg.flow .base{{stroke:var(--base);stroke-width:1}}
svg.flow .fx{{fill:var(--fx)}}svg.flow .inst{{fill:var(--inst)}}svg.flow .neg{{opacity:.55}}
svg.flow .val{{font-size:8.5px;fill:var(--ink2);font-variant-numeric:tabular-nums}}
svg.flow .ax{{font-size:9px;fill:var(--muted)}}svg.flow .miss{{font-size:14px;fill:var(--muted)}}
svg.band{{width:100%;height:auto}}svg.band .track{{stroke:var(--grid);stroke-width:6;stroke-linecap:round}}
svg.band .fill{{stroke:var(--inst);stroke-width:6;stroke-linecap:round;opacity:.5}}
svg.band .dot{{fill:var(--inst);stroke:var(--surface);stroke-width:2}}
svg.band .pos{{font-size:10px;font-weight:700;fill:var(--ink)}}svg.band .ax{{font-size:9.5px;fill:var(--muted)}}
.legend{{display:flex;gap:14px;font-size:12px;color:var(--ink2);margin:2px 0 18px;flex-wrap:wrap}}
.sw{{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}}
.bd-row{{display:flex;align-items:center;gap:8px;margin:3px 0}}
.bd-n{{font-size:11.5px;color:var(--ink2);width:74px;flex:none}}
.bd-t{{flex:1;height:7px;background:var(--chip);border-radius:99px;overflow:hidden}}
.bd-f{{display:block;height:100%;background:var(--inst);border-radius:99px}}
.bd-v{{font-size:11px;color:var(--muted);width:46px;text-align:right;font-variant-numeric:tabular-nums}}
.imgs{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}}
@media(max-width:640px){{.imgs{{grid-template-columns:1fr}}}}
.imgs img{{width:100%;border-radius:8px;border:1px solid var(--border);background:#fff}}
.why,.strat{{margin:10px 0 0;font-size:14px}}
.why b,.strat b{{font-size:12.5px;color:var(--muted);display:block;margin-bottom:2px}}
.why p,.strat p{{margin:0}}
.strat{{background:var(--chip);border-radius:8px;padding:10px 12px}}
.drop{{margin:10px 0 0;font-size:14px;background:color-mix(in srgb,var(--warn) 8%,var(--surface));
border:1px solid color-mix(in srgb,var(--warn) 35%,transparent);border-radius:8px;padding:10px 12px}}
.drop b{{font-size:12.5px;color:var(--warn);display:block;margin-bottom:2px}}
.drop p{{margin:0}}
table{{width:100%;border-collapse:collapse;background:var(--surface);border:1px solid var(--border);
border-radius:12px;overflow:hidden;font-size:13px;margin:10px 0 20px}}
th,td{{padding:8px 10px;text-align:left;border-bottom:1px solid var(--grid)}}
th{{color:var(--muted);font-size:12px;font-weight:600}}
td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums}}
tr:last-child td{{border-bottom:none}}
h3{{margin:30px 0 6px}}
.foot{{margin-top:30px;padding-top:16px;border-top:1px solid var(--grid);color:var(--muted);font-size:12.5px}}
.foot a{{color:var(--ink2)}}
.disc{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 16px;margin:24px 0 0;color:var(--ink2);font-size:13px}}
html{{scroll-behavior:smooth}}
.card,h3{{scroll-margin-top:14px}}
.toc{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:4px 16px;margin:0 0 18px}}
.toc summary{{cursor:pointer;font-weight:600;padding:10px 0;font-size:14.5px}}
.toc-hint{{font-weight:400;font-size:12px;color:var(--muted)}}
.toc-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(158px,1fr));gap:6px;padding:2px 0 12px}}
.toc-i{{display:flex;align-items:center;gap:7px;padding:7px 10px;border-radius:8px;background:var(--chip);color:var(--ink);text-decoration:none;font-size:13px;font-weight:600}}
.toc-i:hover{{background:color-mix(in srgb,var(--inst) 14%,var(--chip))}}
.toc-ref{{opacity:.75}}
.toc-r{{color:var(--muted);font-weight:700;min-width:17px;font-variant-numeric:tabular-nums}}
.toc-w{{color:var(--warn)}}
.toc-s{{margin-left:auto;color:var(--ink2);font-weight:400;font-variant-numeric:tabular-nums;font-size:12px}}
.top-btn{{position:fixed;right:16px;bottom:16px;background:var(--surface);border:1px solid var(--border);border-radius:999px;padding:9px 15px;font-size:13px;font-weight:600;color:var(--ink);text-decoration:none;box-shadow:0 2px 12px rgba(0,0,0,.18);z-index:9}}
</style></head><body><div class="wrap" id="top">
<h1>📡 수급 쌍끌이 레이더 <span class="code">{D["base_date"]}</span></h1>
<p class="sub">기관 순매수 상위 → 외국인 동시 순매수 → 뉴스·공시 분석 → 매수 후보 &nbsp;|&nbsp; 수급 기준일 <b>{D["base_date"]}</b> · 시세 {D["quote_time"]} · 생성 {NOW}</p>
{regime_html}
{banner_html}
{toc_html}
<div class="steps"><span class="step"><b>1</b> 기관 순매수 상위</span><span class="step"><b>2</b> 외국인 동시 순매수</span><span class="step"><b>3</b> 연속성·강도·우량주 필터</span><span class="step"><b>4</b> 뉴스 분석 → 매수 전략</span></div>
<div class="legend"><span><span class="sw" style="background:var(--fx)"></span>외국인 순매수</span><span><span class="sw" style="background:var(--inst)"></span>기관 순매수</span><span>· = 데이터 없음</span><span>반투명 = 순매도</span></div>
{cards}
<h3 id="summary">전체 요약표</h3>
<table><thead><tr><th>순위</th><th>종목</th><th>코드</th><th class="num">현재가</th><th class="num">당일 외인(억)</th><th class="num">당일 기관(억)</th><th class="num">{len(FD)}일 합(억)</th><th class="num">PER</th><th class="num">배당%</th><th class="num">52주 위치</th><th class="num">점수</th></tr></thead>
<tbody>{rows}</tbody></table>
<div class="disc">⚠️ <b>투자 유의</b> — 본 페이지는 공개 데이터를 기반으로 한 <b>참고 자료</b>이며 투자 권유가 아닙니다. 주식 투자는 원금 손실 위험이 있으며 최종 판단과 책임은 투자자 본인에게 있습니다. 적자기업 등 우량주 필터 미통과 종목은 추천이 아닌 참고로만 표시됩니다.</div>
<div class="foot">데이터: KRX(pykrx) 또는 AWAKEPLUS·한국투자증권·주달·Google Finance · 차트 이미지: 네이버금융 · 점수 모델: 수급규모25+지속성25+당일쌍끌이20+우량주20+과열리스크10<br>
수급 쌍끌이 레이더 · 종목추천2 프로젝트</div>
<a class="top-btn" href="#top">▲ 목차</a>
</div></body></html>"""

import os, shutil
open("data/index.html", "w", encoding="utf-8").write(html)
os.makedirs("data/archive", exist_ok=True)
open(f"data/archive/index-{D['base_date']}.html", "w", encoding="utf-8").write(html)
# 성과 평가(stock-radar-evaluator)용 일별 추천 스냅샷
shutil.copyfile("data/recommendations.json", f"data/archive/recommendations-{D['base_date']}.json")
print("data/index.html 저장:", len(html), "bytes", f'(archive/index-{D["base_date"]}.html + recommendations 스냅샷 포함)')
