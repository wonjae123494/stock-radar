# 📡 수급 쌍끌이 레이더

기관·외국인이 **동시에 순매수**한 한국 주식을 매일 선별해 점수화하고,
매수 후보 대시보드(`data/index.html`)를 만드는 도구입니다.

## 빠른 시작

```bash
pip install pykrx
python fetch_data.py    # KRX에서 수급·시세·재무 수집
python score.py         # 점수화·순위
python build_html.py    # 대시보드 생성 → data/index.html
```

`data/index.html`을 브라우저로 열면 됩니다. 뉴스 분석까지 포함한 완전한 갱신은
Claude Code에서 "대시보드 업데이트해줘"라고 하면 `CLAUDE.md`의 절차대로 수행됩니다.

## 선별 프로세스

1. 기관 순매수 상위 확인
2. 외국인 동시 순매수 체크 (쌍끌이)
3. 연속성·강도·우량주 필터 + 뉴스·공시 분석
4. 매수 후보 정리 (점수 100점 만점, 상세 기준은 CLAUDE.md)

## 구성

| 파일 | 역할 |
|---|---|
| `fetch_data.py` | pykrx로 최근 4거래일 기관/외국인 순매수 + 시세·재무·52주 수집 |
| `score.py` | 점수 모델 적용, 순위화 |
| `build_html.py` | 자체완결형 HTML 대시보드 생성 (다크모드 지원) |
| `data/news.json` | (선택) 종목별 뉴스 분석 — Claude가 작성 |
| `CLAUDE.md` | Claude Code 작업 지침 |

> ⚠️ 본 도구의 출력은 투자 참고 자료이며 투자 권유가 아닙니다.
> 투자의 최종 판단과 책임은 투자자 본인에게 있습니다.
