# 수급 쌍끌이 레이더 — Claude Code 작업 지침

한국 주식(코스피/코스닥)에서 **기관·외국인 동시 순매수(쌍끌이)** 종목을 선별해
`data/index.html` 대시보드를 갱신하는 프로젝트다.

## 갱신 절차 (사용자가 "업데이트해줘"라고 하면)

```bash
pip install pykrx          # 최초 1회
python fetch_data.py       # KRX 수급·시세·재무 수집 → data/data.json
python score.py            # 점수화 → data/recommendations.json
python build_html.py       # 대시보드 → data/index.html
```

그 다음 **뉴스 분석을 직접 수행**한다 (이 단계가 사람 없이 스크립트만으로는 안 되는 부분):

1. `data/recommendations.json` 상위 종목별로 웹에서 "{종목명} 주가 뉴스"를 검색해
   수급이 몰린 이유(실적, 수주, 목표주가, 테마 등)를 파악한다.
2. 시장 전체가 급등/급락했으면 원인을 `data/data.json`의 `market_note` 필드에 한 줄로 기입.
3. `data/news.json`을 작성한다:
   ```json
   { "005930": { "why": "수급이 몰린 이유 2~3문장", "strategy": "매수 전략 메모 1~2문장", "warn": "투자경고종목 지정", "drop_why": "점수 높은데 주가 하락 중인 이유 2~3문장" } }
   ```
   `warn`은 투자경고·거래정지·바이너리 이벤트(FDA 결과 등) 있을 때만. 없으면 생략.
4. **괴리 리포트(`drop_why`)**: `score.py` 출력에 "📉 점수·주가 괴리 종목"으로 표시된 종목
   (점수 70점 이상인데 당일 등락률 마이너스)은, 수급 점수가 높은데도 주가가 왜 떨어지는지
   웹 검색으로 원인을 파악해 `news.json`의 해당 종목에 `drop_why`(2~3문장)로 작성한다.
   전형적 원인: 차익실현 매물, 업종/시장 동반 하락, 개별 악재(공시·소송·실적 미스),
   외인·기관은 사는데 개인/기타 매도가 더 큰 경우 등. 원인을 못 찾으면 "뚜렷한 개별 악재
   미확인 — 시장 동반 조정으로 추정"처럼 확인된 사실만 적는다.
5. `python score.py && python build_html.py` 재실행 → 완성된 `data/index.html` 확인.

## 점수 모델 (100점) — 임의로 바꾸지 말 것 (사용자와 합의된 기준)

| 항목 | 배점 | 규칙 |
|---|---|---|
| 수급 규모 | 25 | 최근 4거래일 외인+기관 순매수 합, 1,800억에서 만점 |
| 수급 지속성 | 25 | 등장일수/4×10 + 쌍끌이일수/4×15 |
| 당일 쌍끌이 | 20 | 양쪽 순매수 20 / 기관만 확인 10 / 기관+·외인 소폭 매도 5 |
| 우량주 | 20 | 흑자 10 + 시총 10조↑ 5 + 배당 0.5%↑ 5 |
| 과열 리스크 | 10 | 52주 위치 70% 미만 10 / 85% 미만 5 / 이상 0. 투자경고종목 0 |

## 원칙

- 적자기업·투자경고종목은 **제외하지 않고** "추천 아닌 참고"(dashed 카드)로 표시한다.
- 대시보드 하단 **투자 유의 고지 문구는 절대 삭제·완화하지 않는다.**
- 점수 모델을 바꾸고 싶다는 요청이 오면 바꾸되, 이 파일의 표도 함께 갱신한다.
- `data/flow_history.json`은 클라우드 자동 갱신(매일 19:05 KST, Cowork 스케줄)과 공유되는
  수급 이력 포맷이다. 로컬에서는 pykrx가 이력을 직접 조회하므로 필수는 아니다.
- pykrx 응답이 비거나 KRX 점검 시간(보통 새벽)이면 잠시 후 재시도.

## 텔레그램 + 매일 자동 실행 (Windows)

구성 파일: `send_telegram.py`(발송), `run_daily.bat`(전체 파이프라인+발송), `config.json`(토큰).

**최초 설정 — 사용자가 "텔레그램 자동화 설정해줘"라고 하면:**

1. `config.json` 확인. 없으면 사용자에게 안내:
   - 텔레그램에서 `@BotFather` 검색 → `/newbot` → 봇 이름 지정 → **토큰** 받기
   - 만든 봇에게 아무 메시지 1개 보내기 → `https://api.telegram.org/bot<토큰>/getUpdates` 열어
     `"chat":{"id":숫자}` 의 **chat_id** 확인
   - 두 값을 `config.example.json` 형식으로 `config.json`에 저장
2. `python send_telegram.py` 로 발송 테스트.
3. 작업 스케줄러 등록 (관리자 권한 불필요):
   ```
   schtasks /Create /F /SC DAILY /ST 19:05 /TN "StockRadar" /TR "\"%CD%\run_daily.bat\""
   ```
   `schtasks /Run /TN "StockRadar"` 으로 즉시 1회 테스트, `schtasks /Query /TN "StockRadar"` 로 확인.
4. 뉴스 분석까지 자동화하려면 `run_daily.bat`의 `claude -p ...` 줄 주석 해제 (수동으로 한 번 검증한 뒤에).

**주의:** `config.json`은 비밀 토큰이므로 git에 커밋하지 말 것(.gitignore 유지). PC가 꺼져 있으면
로컬 자동 실행은 건너뛰어진다 — 클라우드(Cowork) 쪽 19:05 자동 갱신은 별도로 계속 돈다.

## 배경

- 이 프로젝트는 Claude Cowork "종목추천2" 프로젝트에서 생성됐다.
  클라우드 쪽은 네트워크 제약으로 WebFetch 기반 수집(절차: 프로젝트 문서 `claude/종목선별-절차.md`)을 쓰고,
  로컬은 pykrx로 더 정확한 전종목 수급 데이터를 쓴다. 점수 모델은 양쪽이 동일해야 한다.
- `data/` 안의 index.html·recommendations.json은 2026-07-08 클라우드 세션이 만든 초기 산출물이다.
