# 웹 대시보드 실행 가이드

## 1) Streamlit 설치
```bash
python3 -m pip install streamlit
```

## 2) 대시보드 실행
```bash
streamlit run <project-root>/ui/dashboard.py
```

## 3) 주요 기능
- `전체 자동 실행` 버튼: `auto_run.py` 실행
- `결정 반영 후 Follow-up 갱신` 버튼: `decision_engine.py` 실행
- shortlist 후보별:
  - 상태/수익률/최대입찰가 확인
  - 분석카드 열람
  - `APPROVE` / `PASS` / `PENDING` 결정 저장
- 하단에서 최신 follow-up 문서 확인
