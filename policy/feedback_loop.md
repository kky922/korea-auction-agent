# 피드백 루프 운영 규칙

## 목적
실행 결과를 학습과 정책 파라미터에 반영해 다음 회차 품질을 높인다.

## 입력
- 파이프라인 실행 리포트: `data/reports/latest_run_report.json`
- 후보별 실패 사유 코드 목록

## 처리 규칙
- 실패 사유를 집계해 상위 원인을 추출한다.
- 반복되는 실패 원인에 대응하는 정책 패치를 생성한다.
- 학습 강화 주제를 생성해 CoachAgent에게 전달한다.

## 출력
- 정책 패치 파일: `policy/strategy_patch_latest.json`
- 주간 복기 문서: `results/weekly_reviews/latest_review.md`

## 운영 리듬
- 주간 1회 정기 실행
- 실전 입찰 실패 직후 비정기 실행

## 책임 분리
- PostMortemAgent: 실패 원인 분석
- CoachAgent: 학습 과제 반영
- ValuationAgent/RightsRiskAgent: 패치 사항 반영 검토
