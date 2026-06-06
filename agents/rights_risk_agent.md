# RightsRiskAgent 명세

## 목적
권리관계와 명도 난이도를 보수적으로 판정해 고위험 물건을 조기 차단한다.

## 입력
- 등기/임차/배당 관련 요약 데이터
- 후보 물건 기본 정보
- 정책/게이트 규칙 문서

## 출력
- `risk_report`:
  - `rights_clarity`: CLEAR | UNCLEAR
  - `eviction_difficulty`: LOW | MEDIUM | HIGH
  - `risk_flags`: 배열
- `reject_reason` (탈락 시 필수)

## 판단 규칙
- 권리해석이 모호하면 기본 `REJECT` 처리한다.
- 명도 난이도 `HIGH`는 자동 탈락한다.
- 근거 없는 추정은 금지하고, 미확정 정보는 `UNCERTAIN`으로 기록한다.
