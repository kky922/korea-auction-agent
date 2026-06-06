# 자동화 90% 운영 가이드

## 목표 운영 방식
- 경매 스케줄에 맞춰 자동 실행
- 유리한 후보를 자동 shortlist
- 투자자는 `APPROVE` 또는 `PASS`만 결정
- `APPROVE` 시 follow-up 자동 생성

## 1) 자동실행 명령
```bash
python3 <project-root>/src/auto_run.py
```

실행 순서:
1. `input_adapter.py`
2. `pipeline.py`
3. `feedback_loop.py`
4. `property_analysis.py`
5. `decision_engine.py`

## 2) 어디를 보면 되는가
- 추천 후보 inbox: `results/decision_inbox/latest_actions.json`
- 의사결정 입력 파일: `data/decisions/pending_decisions.json`
- 물건 분석카드 요약: `results/analysis_cards/latest_analysis_summary.json`
- 개별 물건 분석카드: `results/analysis_cards/<candidate_id>.md`
- 후속 액션: `results/followups/latest_followup.md`
- 전체 자동 실행 로그: `logs/auto_run.log`

## 3) 투자자 의사결정 방식
`data/decisions/pending_decisions.json`에서 각 후보의 `decision` 값을 입력:
- `APPROVE`: 진행
- `PASS`: 제외
- `PENDING`: 보류

입력 후 아래를 다시 실행:
```bash
python3 <project-root>/src/decision_engine.py
```

그러면 `results/followups/latest_followup.md`가 갱신된다.

## 4) 지역 우선순위 정책
- 우선 지역(기본): 대구 및 인근 (`대구`, `경산`, `칠곡`, `성주`, `영천`, `구미`)
- 모니터 지역: `서울`
- 설정 파일: `config/user_preferences.json`

## 5) 스케줄 운영
- 권장: 평일 오전/저녁 2회 실행
- 스케줄 참고 파일: `config/automation_schedule.json`
- cron 또는 launchd에 `scripts/run_auto_schedule.sh` 등록

## 6) 텔레그램 알림 설정
- 환경변수(예: 쉘 프로파일/launchd env)에 아래 값 설정:
  - `AUCTION_TELEGRAM_BOT_TOKEN`
  - `AUCTION_TELEGRAM_CHAT_ID`
- 알림 정책:
  - 자동 실행 완료 후 결과 갱신 요약 알림
  - 매일 09:00(KST) 일일 요약 1회
  - 실행 실패 즉시 알림은 발송하지 않음

수동 테스트:
```bash
# 일반 실행 + 결과 갱신 알림
python3 <project-root>/src/auto_run.py

# 일일 요약 강제 발송(중복 방지 무시)
python3 <project-root>/src/auto_run.py --daily-summary --force-daily-summary
```

운영 상태 파일:
- 일일 요약 중복 방지 상태: `logs/telegram_daily_state.json`
