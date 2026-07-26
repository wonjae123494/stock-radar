#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
홈 허브 페이지 생성 → data/home.html

두 섹션:
  1) 📅 일자별 분석 — data/archive/index-*.html 을 날짜순으로 나열(최신 먼저),
     각 날짜의 레짐·대표 추천을 요약해 해당 대시보드로 링크.
  2) 🔍 주기적 점검 리포트 — data/feedback.md(주간 평가·가설 이력)를 렌더링.

build_html.py(매일)와 evaluate.py(매주)가 끝에서 build()를 호출해 자동 갱신한다.
※ home.html의 일자별 링크는 archive/*.html 상대경로다 → data/ 폴더에서 함께 열거나
   GitHub Pages처럼 파일이 같이 있는 곳에서 봐야 링크가 동작한다(텔레그램 단일 첨부로는 X).
"""
import glob, html, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))


def _daily_rows():
    rows = []
    for p in glob.glob(os.path.join(HERE, "data", "archive", "index-*.html")):
        m = re.search(r"index-(\d{4}-\d{2}-\d{2})\.html$", os.path.basename(p))
        if not m:
            continue
        date = m.group(1)
        rec_p = os.path.join(HERE, "data", "archive", f"recommendations-{date}.json")
        regime, picks = None, []
        if os.path.exists(rec_p):
            try:
                d = json.load(open(rec_p, encoding="utf-8"))
                regime = d.get("regime")
                picks = [f'{s["name"]}({s["score_total"]:.0f})'
                         for s in sorted(d.get("stocks", []), key=lambda x: x.get("rank", 99))[:3]]
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        rows.append((date, regime, picks, f"archive/index-{date}.html"))
    rows.sort(key=lambda r: r[0], reverse=True)
    return rows


def _md_to_html(md):
    """feedback.md 라이트 렌더 (제목/굵게/구분선/주석)"""
    out = []
    for line in md.splitlines():
        s = line.rstrip()
        if s.strip().startswith("<!--"):
            continue
        if s.startswith("## "):
            out.append(f'<h3>{html.escape(s[3:])}</h3>')
        elif s.startswith("### "):
            out.append(f'<h4>{html.escape(s[4:])}</h4>')
        elif s.strip() == "---":
            out.append('<hr>')
        elif not s.strip():
            out.append('<div class="sp"></div>')
        else:
            esc = html.escape(s)
            esc = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)
            out.append(f'<div class="ln">{esc}</div>')
    return "\n".join(out)


def build():
    rows = _daily_rows()
    fb_path = os.path.join(HERE, "data", "feedback.md")
    fb = open(fb_path, encoding="utf-8").read() if os.path.exists(fb_path) else "_아직 점검 리포트가 없습니다._"

    daily = ""
    for date, regime, picks, link in rows:
        if regime:
            rg = f'<span class="rg rg-{regime["label"]}">{regime["emoji"]} {regime["label"]} {regime["exposure"]}%</span>'
        else:
            rg = '<span class="rg">-</span>'
        pk = " · ".join(html.escape(p) for p in picks) if picks else "-"
        daily += (f'<a class="row" href="{link}"><span class="d">{date}</span>{rg}'
                  f'<span class="pk">{pk}</span><span class="go">열기 ›</span></a>')
    if not daily:
        daily = '<div class="empty">아직 저장된 일자별 분석이 없습니다.</div>'

    latest = rows[0][0] if rows else "-"
    page = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>수급 쌍끌이 레이더 — 홈</title>
<style>
:root{{--surface:#fcfcfb;--page:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8880;--border:rgba(11,11,11,.10);
--chip:#f0efec;--red:#e34948;--warn:#b97500;--good:#006300;--acc:#2a78d6}}
@media(prefers-color-scheme:dark){{:root{{--surface:#1a1a19;--page:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#8a8880;
--border:rgba(255,255,255,.10);--chip:#262624;--red:#e66767;--warn:#fab219;--good:#0ca30c;--acc:#3987e5}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--page);color:var(--ink);
font:15px/1.55 system-ui,-apple-system,"Segoe UI","Malgun Gothic",sans-serif}}
.wrap{{max-width:920px;margin:0 auto;padding:28px 18px 60px}}
h1{{font-size:24px;margin:0 0 2px}}.sub{{color:var(--ink2);margin:0 0 20px;font-size:13px}}
h2{{font-size:17px;margin:28px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--border)}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden}}
.row{{display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid var(--border);
text-decoration:none;color:var(--ink)}}
.row:last-child{{border-bottom:none}}.row:hover{{background:var(--chip)}}
.d{{font-weight:700;font-variant-numeric:tabular-nums;min-width:96px}}
.rg{{font-size:12px;padding:2px 8px;border-radius:999px;background:var(--chip);color:var(--ink2);white-space:nowrap}}
.rg-위험{{background:color-mix(in srgb,var(--red) 16%,var(--surface));color:var(--red);font-weight:700}}
.rg-주의{{background:color-mix(in srgb,var(--warn) 16%,var(--surface));color:var(--warn);font-weight:700}}
.rg-정상{{background:color-mix(in srgb,var(--good) 14%,var(--surface));color:var(--good);font-weight:700}}
.pk{{flex:1;color:var(--ink2);font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.go{{color:var(--acc);font-size:13px;white-space:nowrap}}
.empty{{padding:20px;color:var(--muted)}}
.report{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:8px 18px}}
.report h3{{font-size:15px;margin:16px 0 4px}}.report h4{{font-size:13.5px;margin:12px 0 2px;color:var(--ink2)}}
.report .ln{{font-size:13.5px;color:var(--ink2);font-variant-numeric:tabular-nums}}
.report .sp{{height:8px}}.report hr{{border:none;border-top:1px solid var(--border);margin:14px 0}}
.report b{{color:var(--ink)}}
.disc{{margin-top:26px;padding:12px 16px;background:var(--surface);border:1px solid var(--border);
border-radius:10px;color:var(--ink2);font-size:12.5px}}
</style></head><body><div class="wrap">
<h1>📡 수급 쌍끌이 레이더 — 홈</h1>
<p class="sub">최신 기준일 {latest} · 일자별 분석 {len(rows)}건 · 자동 갱신</p>

<h2>📅 일자별 분석</h2>
<div class="card">{daily}</div>

<h2>🔍 주기적 점검 리포트</h2>
<div class="report">{_md_to_html(fb)}</div>

<div class="disc">⚠️ 정보 요약 도구이며 투자 권유가 아닙니다. 모의 평가는 수수료·슬리피지 미반영이며,
투자 판단·책임은 본인에게 있습니다. 일자별 링크는 같은 폴더의 archive 파일을 참조합니다.</div>
</div></body></html>"""

    with open(os.path.join(HERE, "data", "home.html"), "w", encoding="utf-8") as f:
        f.write(page)
    return len(rows)


if __name__ == "__main__":
    n = build()
    print(f"data/home.html 저장 — 일자별 {n}건")
