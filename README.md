# Korea Auction Agent

한국 법원 부동산 경매 후보를 보수적인 기준으로 계산하고 검토 순서를 만드는
학습용 분석 파이프라인입니다. 자동 입찰은 수행하지 않으며 최종 판단은 사용자가 합니다.

## 기능

- 예상 총비용, 기대 수익, 최대 입찰가 계산
- 권리관계·수익률·준비 상태에 따른 `APPROVED`, `HOLD`, `REJECT` 게이트
- 선호 지역과 검토 이력을 반영한 후보 우선순위
- 분석 카드, 결정 목록, 후속 조치 리포트 생성
- 선택적 공공데이터·등기·Telegram 연동

## 설치

```bash
git clone https://github.com/kky922/korea-auction-agent.git
cd korea-auction-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 설정

샘플 실행에는 API 키가 필요하지 않습니다. 지역과 검토 기준은
`config/user_preferences.json`, 판정 기준은 `policy/decision_gates.json`에서 설정합니다.

외부 연동을 사용할 때만 `.env`에 `PUBLIC_DATA_API_KEY`, `IROS_API_KEY`,
`AUCTION_TELEGRAM_BOT_TOKEN`, `AUCTION_TELEGRAM_CHAT_ID`를 추가합니다.

## 실행

```bash
# 저장소에 포함된 가상 후보 데이터 분석
python3 src/pipeline.py data/candidates/sample_candidates.json

# 결과 확인
cat data/reports/latest_run_report.json

# 웹 대시보드
streamlit run ui/dashboard.py
```

생성 파일은 `data/reports/`와 `results/`에 저장되며 Git에서 제외됩니다.

## 테스트

```bash
pytest -q
```

## 주의사항

이 프로젝트는 학습용 투자 판단 보조 도구이며 투자·법률·세무 자문이 아닙니다.
실제 입찰 전 등기, 임차인, 배당, 현장 상태와 자금 계획을 전문가와 직접 확인하세요.

## 라이선스

MIT
