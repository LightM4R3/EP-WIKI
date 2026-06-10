# 무기 JSON 데이터 모델

## 조사 기준

2026-06-10 기준 나무위키 `명일방주: 엔드필드/무기` 문서와 무기 타입별 하위 문서를 기준으로 무기 분류와 seed 데이터를 정리했다.

현재 `src/data/game/weapons.seed.json`은 71개 무기를 포함한다. 긴 설명/스토리 전문은 저장하지 않고, 계산기와 필터에 먼저 필요한 무기명, 레어도, 타입, 획득 그룹, 기본 공격력, 기질 슬롯의 이름/대상 능력치/레벨별 계수만 구조화했다.

## 파일 구성

- `src/data/game/weapon-categories.json`: 무기 공통 분류 축과 육성 규칙
- `src/data/game/weapon/essence-categories.json`: 무기 고유 효과명 앞에 붙는 기질 대분류
- `src/data/game/weapon/essence-categories.schema.json`: 기질 대분류 JSON Schema
- `src/data/game/weapon/option-categories.json`: 중복되는 무기 옵션/기질 카테고리와 Lv.1~Lv.9 수치
- `src/data/game/weapon/option-categories.schema.json`: 무기 옵션 카테고리 JSON Schema
- `src/data/game/weapon.schema.json`: 무기 seed가 따라야 할 JSON Schema
- `src/data/game/weapons.seed.json`: 나무위키 기반 1차 무기 seed

## 무기 기본 항목

무기 1개는 다음 큰 묶음을 가진다.

- `id`: 앱 내부에서 쓰는 안정적인 고유 id
- `names`: 한국어 무기명과 추후 별칭
- `rarity`: 3성, 4성, 5성, 6성
- `type`: `Sword`, `Greatsword`, `Polearm`, `Handcannon`, `Arts Unit`
- `acquisition`: 무기고 거래소 상시, 무기고 거래소 한정, 프로토콜 통행증, 일반
- `stats.baseAttack`: 기본 공격력
- `traits`: 기질 또는 무기 스킬 슬롯 참조. 3성은 2개, 4성 이상은 3개
- `traits[].slot`: 무기 안에서의 옵션 슬롯
- `traits[].categoryId`: `weapon/option-categories.json`의 `categories[].id`

무기 옵션 카테고리 1개는 다음 항목을 가진다.

- `id`: 무기 seed에서 참조하는 옵션 카테고리 id
- `kind`: `stat` 또는 `weaponSkill`
- `nameKo`: 옵션/기질 이름
- `statKo`: 이 옵션의 대표 적용 능력치 또는 효과
- `essenceCategoryId`: `kind`가 `weaponSkill`일 때만 존재하는 기질 대분류 id
- `range.min/max`: 빠른 표시와 필터에 쓰는 Lv.1/Lv.9 값
- `range.raw`: Lv.1부터 Lv.9까지의 실제 원문 수치 배열. `raw[index]`의 레벨은 `index + 1`

## 기질 대분류

무기 고유 효과는 `고통 · 백야의 별`, `방출 · 사무치는 추위`, `의료 · 탈로스의 눈`처럼 `·` 앞에 대분류를 가진다. 이 대분류는 기질을 무기에 부여하거나 같은 계열의 기질을 매칭할 때 별도 축으로 사용한다.

현재 확인한 대분류는 `essence-categories.json`에 저장한다.

- 분쇄
- 강공
- 고통
- 골절
- 기예
- 방출
- 사기
- 어둠
- 억제
- 의료
- 잔혹
- 추격
- 효율
- 흐름
- `sourceRefs`: 참조한 원천 문서 id
- `verification`: `placeholder`, `needs_review`, `verified` 중 하나

## 카테고리 축

무기 카테고리는 `weapon-categories.json`에 분리한다.

- `rarity`: 3★부터 6★까지. 3성은 기질 슬롯 2개, 4성 이상은 3개
- `type`: 한손검, 양손검, 장병기, 권총, 아츠 유닛
- `skill`: 무기 스킬 슬롯과 레벨 상한
- `growth`: 무기 레벨 상한 20/40/60/80/90
- `potential`: 잠재 능력으로 세 번째 스킬 레벨과 상한 증가
- `essence`: 기질 획득과 스킬 증가치
- `essenceEngraving`: 5성 기질 식각 확률과 냉각제 비용

## 검증 플로우

1. 새 무기가 나오면 `weapons.seed.json`에 `verification.status: "placeholder"`로 추가한다.
2. 나무위키 또는 공식 데이터에서 기본 공격력과 기질 표를 확인하면 `needs_review`로 올린다.
3. 스킬 설명, 레벨별 계수, 잠재/기질 상호작용을 2개 이상 출처로 대조하면 `verified`로 올린다.
4. 실제 피해 계산식에 연결할 때는 `traits[].categoryId`로 옵션 카테고리를 찾고, `category.range.raw[level - 1]`을 우선 사용한다. 문자열 수치를 곱셈에 넣어야 할 때는 별도 정규화 필드나 계산용 수치 필드를 추가한다.
