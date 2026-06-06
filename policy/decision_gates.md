# 의사결정 게이트 정의

## Gate 1: 예산 적합성
- 조건
  - `total_cost` <= 30,000,000
  - `reserve_cash` >= 3,000,000
- 실패 시 처리
  - 상태: `REJECT`
  - 사유코드: `BUDGET_EXCEEDED` 또는 `RESERVE_TOO_LOW`

## Gate 2: 권리관계 단순성
- 조건
  - 말소기준권리 이후 권리 정리가 명확함
  - 대항력/우선변제 관련 불확실성 없음
  - 명도 난이도 `LOW` 또는 `MEDIUM`
- 실패 시 처리
  - 상태: `REJECT`
  - 사유코드: `RIGHTS_UNCLEAR` 또는 `EVICTION_RISK_HIGH`

## Gate 3: 수익 안전마진
- 조건
  - `expected_margin_rate` >= 0.12
  - `max_bid` 산정값 존재
- 실패 시 처리
  - 상태: `REJECT`
  - 사유코드: `MARGIN_TOO_LOW`

## Gate 4: 실행 가능성
- 조건
  - 현장조사 완료
  - 서류 점검 완료
  - 자금조달 계획 확정
- 실패 시 처리
  - 상태: `HOLD`
  - 사유코드: `CHECKLIST_INCOMPLETE`

## 판정 우선순위
1. 권리/법적 리스크 차단
2. 예산 제한 준수
3. 수익성 검증
4. 실행 체크리스트 검증

## 최종 상태
- `APPROVED`: 4개 게이트 모두 통과
- `HOLD`: 실행 게이트만 미완료
- `REJECT`: 1~3번 게이트 중 하나라도 실패
