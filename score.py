#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
수급 쌍끌이 레이더 — 점수화
data/data.json (+ 선택: data/news.json) → data/recommendations.json

점수(100) = 수급규모25 + 지속성25 + 당일쌍끌이20 + 우량주20 + 과열리스크10
"""
import json, os

D = json.load(open("data/data.json", encoding="utf-8"))
NEWS = json.load(open("data/news.json", encoding="utf-8")) if os.path.exists("data/news.json") else {}
FD = D["flow_dates"]
LATEST = FD[-1]

def score(s):
    f = {k: tuple(v) for k, v in s["flows"].items()}
    total = sum((a or 0) + (b or 0) for a, b in f.values())
    s1 = 25 * min(1.0, max(0, total) / 1800)                      # 수급 규모
    days = len(f)
    both = sum(1 for a, b in f.values() if (a or 0) > 0 and (b or 0) > 0)
    s2 = 10 * days / len(FD) + 15 * both / len(FD)                # 지속성
    a, b = f.get(LATEST, (None, None))
    if a is not None and b is not None and a > 0 and b > 0: s3 = 20   # 당일 쌍끌이
    elif (b or 0) > 0 and a is None: s3 = 10
    elif (b or 0) > 0: s3 = 5
    else: s3 = 0
    s4 = (10 if s.get("per") else 0) + (5 if (s.get("cap") or 0) >= 10 else 0) \
         + (5 if (s.get("div") or 0) >= 0.5 else 0)               # 우량주
    pos = (s["price"] - s["w52l"]) / max(1, s["w52h"] - s["w52l"])
    s5 = 10 if pos < 0.70 else (5 if pos < 0.85 else 0)           # 과열 리스크
    if s.get("warn") and "투자경고" in s["warn"]: s5 = 0
    parts = dict(size=round(s1, 1), persist=round(s2, 1), today=s3, quality=s4, risk=s5)
    return round(s1 + s2 + s3 + s4 + s5, 1), parts, dict(total_flow=round(total), both_days=both,
                                                         days=days, pos=round(pos * 100))

out = []
for s in D["stocks"]:
    n = NEWS.get(s["code"], {})
    s["why"] = n.get("why") or s.get("why") or "(뉴스 분석 미작성 — CLAUDE.md의 뉴스 분석 단계 수행)"
    s["strategy"] = n.get("strategy") or s.get("strategy") or "분할 매수 원칙. 상세 전략은 뉴스 분석 후 작성."
    s["warn"] = n.get("warn", s.get("warn"))
    s["drop_why"] = n.get("drop_why") or None
    if not s.get("per") and s["warn"] is None:
        s["warn"] = None  # 적자 배지는 build_html에서 자동
    t, parts, extra = score(s)
    s.update(score_total=t, score_parts=parts, **extra)
    s["divergence"] = t >= 70 and (s.get("chg") or 0) < 0  # 점수 높은데 당일 주가 하락 → 괴리 리포트 대상
    out.append(s)

out.sort(key=lambda x: -x["score_total"])
for i, s in enumerate(out, 1):
    s["rank"] = i

D["stocks"] = out

# 시장 레짐 판정 (종목 점수와 무관 — 비중 권고·경고용 참고 신호). 실패해도 파이프라인은 계속.
try:
    import regime
    D["regime"] = regime.assess()
except Exception as e:
    print(f"(경고) 레짐 판정 실패 — 무시하고 계속: {e}")
    D["regime"] = None

json.dump(D, open("data/recommendations.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for s in out:
    print(f'{s["rank"]:2d}. {s["name"]:10s} {s["score_total"]:5.1f}점  52주위치 {s["pos"]}%  4일합 {s["total_flow"]:+,}억')
div_miss = [s for s in out if s.get("divergence") and not s.get("drop_why")]
if div_miss:
    print("📉 점수·주가 괴리 종목(news.json에 drop_why 원인 분석 작성 필요):",
          ", ".join(f'{s["name"]}({s["code"]})' for s in div_miss))
print("data/recommendations.json 저장. 다음: python build_html.py")
