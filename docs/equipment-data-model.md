# 장비 JSON 데이터 모델

## 조사 기준

2026-06-10 기준 나무위키 `명일방주: 엔드필드/장비` 문서를 1차 출처로 삼아 장비 개요, 세트 효과, 장비별 방어력/옵션/단조 수치를 정리했다.

현재 seed는 장비 164개, 세트 장비 종류 18개, 옵션 카테고리 154개를 포함한다. 원문에서 일부 옵션명이 숨김 처리되거나 값만 노출된 항목은 `미확인` 옵션으로 남기고 `needs_review` 상태를 부여했다.

## 파일 구성

- `src/data/game/equipment/categories.json`: 장비 공통 분류. 부위, 그룹, 희귀도, 단조 규칙, 장비 부품 카테고리를 가진다.
- `src/data/game/equipment/set-categories.json`: 세트 장비 종류와 3세트 효과를 가진다.
- `src/data/game/equipment/option-categories.json`: 장비 옵션과 단조 단계별 수치를 가진다.
- `src/data/game/equipment/equipment.seed.json`: 실제 장비 목록이다. 각 장비는 세트와 옵션 카테고리를 참조한다.
- `src/data/game/equipment/*.schema.json`: 위 JSON의 입력 형태를 검증하기 위한 JSON Schema다.

## 장비 기본 항목

장비 1개는 다음 항목을 가진다.

- `id`: 내부에서 사용하는 안정적인 장비 id
- `names.ko`: 한국어 장비명
- `group`: `set` 또는 `single`
- `setCategoryId`: 세트 장비일 경우 `set-categories.json`의 세트 id, 단일 장비는 `null`
- `setOrder`: 같은 세트 안에서의 원문 등장 순서
- `level`: 원문 장비 레벨
- `rarity`: 별 개수 기준 희귀도
- `partId`: `armor`, `gloves`, `kit`
- `defense`: 방어력 표기값
- `options`: 1옵션, 2옵션, 3옵션의 `option-categories.json` 참조
- `forgeable`: Lv.70 5성 장비라 단조 대상인지 여부
- `crafting`: 장비 부품 소모 정보 자리. 현재 원문에서 소모 부품량을 확인할 수 없어 placeholder로 둔다.

## 세트 카테고리

세트 장비는 같은 세트 장비 3개 이상 착용 시 효과가 발동된다. 원문 기준 부품은 같은 장비 2개를 착용해도 세트 효과 계산에 포함될 수 있으므로 `duplicateKitCounts: true`로 표현한다.

세트 카테고리는 다음 항목을 가진다.

- `nameKo`: 세트 이름
- `levelBand`: 원문 레벨 구간
- `piecesRequired`: 현재 3으로 고정
- `effectKo`: 3세트 효과 원문 요약
- `verification`: 출처 검수 상태

## 옵션과 단조

장비 옵션은 무기 옵션과 다르게 `부위 + 옵션 슬롯 + 옵션명 + 기본값 + 단조값` 단위로 카테고리화한다. 같은 옵션명이라도 방어구, 보호 장갑, 부품에서 단조 증가량이 달라질 수 있기 때문이다.

`forgeStages`는 다음처럼 저장한다.

- `stage: 0`: 기본 단조 0단계 값
- `stage: 1`: 단조 +1 값
- `stage: 2`: 단조 +2 값
- `stage: 3`: 단조 +3 값

`forgeStatus`는 다음 상태를 사용한다.

- `available`: 원문에서 단조 1~3단계 값까지 확인됨
- `not_applicable`: Lv.70 5성 장비가 아니어서 단조 대상이 아님
- `needs_review`: 단조 대상처럼 보이나 원문에서 해당 옵션의 단조 행을 확인하지 못함

## 장비 부품 카테고리

원문에서 장비별 소모 부품 수량은 확인되지 않았으므로, 현재는 다음 장비 부품 카테고리 row만 생성했다.

- 자수정 장비 부품
- 페리움 장비 부품
- 크리스톤 장비 부품
- 식양 장비 부품
- 적동 장비 부품
- 혁동 장비 부품

추후 공식 데이터나 인게임 기록으로 실제 소모량이 확인되면 `equipment.seed.json`의 `crafting.materialPartCategoryId`와 별도 소모량 필드를 채우면 된다.

## 검증 플로우

1. 신규 장비는 `equipment.seed.json`에 추가하고 `verification.status: "needs_review"`로 둔다.
2. 세트 효과는 `set-categories.json`에 먼저 등록하고 장비의 `setCategoryId`로 참조한다.
3. 옵션 수치가 기존 `option-categories.json`과 완전히 같으면 기존 카테고리를 재사용한다.
4. 단조 수치는 같은 옵션명이어도 부위가 다르면 반드시 별도 카테고리로 둔다.
5. 옵션명이 원문에서 확인되지 않는 경우 `statKo: "미확인"`으로 저장하고 notes에 검수 사유를 남긴다.
