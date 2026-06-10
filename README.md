# EPWIKI

명일방주: 엔드필드 정보를 저장, 확인, 조합 시뮬레이션까지 카테고리별 단일 화면에서 다루기 위한 React 프론트엔드 프로젝트입니다.

## 실행

PowerShell 실행 정책 때문에 `npm`이 막히는 환경에서는 `npm.cmd`를 사용합니다.

```bash
npm.cmd install
npm.cmd run dev
```

## 현재 구성

- `src/domain`: 오퍼레이터, 무기, 장비, 피해 계산, 위기 협약 제약 타입
- `src/data`: 실제 데이터 적재 전 화면 검증용 샘플 카탈로그
- `src/features/operators`: 오퍼레이터 기본 정보 화면
- `src/features/damage-calculator`: 빌드 선택 UI와 임시 피해량 계산 모델
- `src/features/crisis-contract`: 위기 협약 제약 선택 및 검증 UI
- `src/app/navigation.ts`: 우측 상단 카테고리 전환 메뉴 정의
- `src/data/game/operator-categories.json`: 나무위키 기준 오퍼레이터 카테고리 축과 한국어 표시명
- `src/data/game/operator.schema.json`: 오퍼레이터 JSON 입력 스키마
- `src/data/game/operators.seed.json`: 조사 기반 오퍼레이터 seed 데이터. 2026-06-09 기준 출시/플레이 가능 범위 28개 레코드와 스킬/재능/잠재/스탯 진행치 포함
- `src/data/game/weapon-categories.json`: 나무위키 기준 무기 카테고리 축과 육성/기질 규칙
- `src/data/game/weapon/essence-categories.json`: 무기 고유 효과 앞 대분류인 기질 카테고리
- `src/data/game/weapon/essence-categories.schema.json`: 기질 카테고리 JSON 입력 스키마
- `src/data/game/weapon/option-categories.json`: 중복 무기 옵션 카테고리와 Lv.1~Lv.9 수치
- `src/data/game/weapon/option-categories.schema.json`: 무기 옵션 카테고리 JSON 입력 스키마
- `src/data/game/weapon.schema.json`: 무기 JSON 입력 스키마
- `src/data/game/weapons.seed.json`: 나무위키 기반 무기 seed 데이터. 2026-06-10 기준 71개 레코드와 레어도/타입/획득 그룹/기본 공격력/옵션 카테고리 참조 포함
- `docs/operator-data-model.md`: 오퍼레이터가 가져야 할 항목과 검증 플로우
- `docs/weapon-data-model.md`: 무기가 가져야 할 항목과 검증 플로우
- `docs/project-plan.md`: 데이터 모델과 다음 구현 순서 구상안

## 개발 원칙

- 실제 게임 데이터는 출처, 패치 버전, 검증 상태를 함께 저장합니다.
- 계산식은 UI와 분리된 순수 함수로 유지해 테스트와 공식 교체가 쉽도록 합니다.
- 위기 협약 제약은 점수, 선행 조건, 충돌 조건을 데이터로 표현합니다.
- 샘플 데이터는 placeholder이며, 실제 수치로 오해되지 않게 검증 상태를 표시합니다.
