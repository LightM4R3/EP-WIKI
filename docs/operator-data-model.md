# 오퍼레이터 JSON 데이터 모델

## 조사 기준

2026-06-09 기준 공개 웹 자료를 바탕으로 오퍼레이터가 가져야 할 항목을 정리했다. 나무위키 문서는 장비와 무기 획득 시스템 구조를 파악하는 데 사용했고, 오퍼레이터 개별 수치와 스킬 구조는 perlica.moe, Icy Veins, 한국어 정리 글을 대조했다.

주의할 점은 소스별 최신성이 다르다는 것이다. 예를 들어 일부 영문 목록은 23명, 다른 목록은 27명 또는 29명으로 표시된다. 따라서 EPWIKI 데이터는 항상 `game.version`, `lastReviewedAt`, `sourceRefs`, `verification.status`를 함께 저장한다.

## 현재 seed 범위

`src/data/game/operator/operators.seed.json`은 2026-06-12 기준 28개 오퍼레이터 레코드를 포함한다.

- perlica.moe 현재 목록은 29개 오퍼레이터 레코드를 노출하지만, `Camille`은 2026-06-09 시점에서 추후 배너로 표시되어 출시 seed에서 제외했다.
- `Endministrator`는 perlica.moe에서 남/여 변형이 `endministrator-a`, `endministrator-b`로 분리되어 있어 현재 seed도 두 레코드로 보존했다.
- 28명 전원은 perlica.moe 상세 페이지 기준으로 기본 공격, 전투 스킬, 콤보 스킬, 궁극기, 재능, 패시브, 잠재, 공업/기지 스킬, 기본 스탯, 레벨당 성장치를 포함한다.
- 자동 추출 데이터이므로 `verification.status`는 우선 `needs_review`로 유지한다. 한국어 표기, 정식 번역, 세부 수치 검수 이후 `verified`로 올린다.
- `schemaVersion: 0.3.0`부터 스킬, 재능, 잠재, 패시브, 기지 스킬에는 `sourceText`, `effectRows`, `calculationRows`를 추가한다. 스킬에는 별도로 `totalDamageRows`를 둔다.

## 한국어 원칙

EPWIKI의 기본 언어는 한국어다. 오퍼레이터 이름과 화면 표시명은 `names.ko` 및 `nameKo`를 우선 사용한다.

다만 현재 공개 웹 출처에서는 오퍼레이터 목록과 프로필 한국어명은 확인되지만, 모든 스킬/재능/잠재의 인게임 한국어 원문은 한 번에 확인되지 않는다. 따라서 전투 텍스트에는 다음 상태를 명시한다.

- `localizationStatus.primaryLanguage`: 항상 `ko`
- `nameKoStatus`: 한국어 명칭 검수 상태
- `textKoStatus`: 한국어 원문 검수 상태
- `sourceText.status`: 원문이 한국어인지, 영문 원천을 임시 보존한 것인지 표시

한국어 원문이 확인되지 않은 항목은 영문 텍스트를 임의 번역하지 않고 `needs_translation`으로 남긴다. 이는 계산식과 출처 검수를 섞지 않기 위한 규칙이다.

## 오퍼레이터 기본 항목

오퍼레이터 1명은 다음 큰 묶음을 가진다.

- `id`: 앱 내부에서 쓰는 영문 kebab-case 고유 id
- `names`: 한국어, 영어, 일본어, 중국어, 별칭
- `rarity`: 4성, 5성, 6성 등급
- `availability`: 출시일, 출시 버전, 획득 경로, 한정 여부
- `profile`: 클래스, 속성, 무기 타입, 전용 무기, 진영, 종족, 생일, CV, 태그
- `combat`: 주 능력치, 보조 능력치, 레벨별 스탯, 기본 스탯/성장치, 핵심 메커니즘, 스킬, 재능, 패시브, 잠재, 공업/기지 스킬, 정예화 재료
- `build`: 추천 무기, 추천 장비 세트, 시너지 오퍼레이터
- `media`: 초상화, 전신 이미지, 공식 영상, 오퍼레이터 스토리 링크
- `sourceRefs`: 이 오퍼레이터 데이터가 참조한 출처 id 목록
- `verification`: placeholder, needs_review, verified 중 하나

## 공통 분류값

현재 확인한 공통 분류값은 아래와 같다.

- 클래스: `Guard`, `Defender`, `Striker`, `Supporter`, `Caster`, `Vanguard`
- 속성: `Physical`, `Heat`, `Electric`, `Cryo`, `Nature`
- 무기 타입: `Sword`, `Greatsword`, `Polearm`, `Handcannon`, `Arts Unit`
- 능력치: `strength`, `agility`, `intellect`, `will`, `hp`, `attack`, `defense`, `critRate`

앱 UI에는 한국어 표시명을 따로 매핑하고, 저장 데이터에는 영문 enum을 유지한다. 이렇게 해야 계산식과 필터가 언어 변경의 영향을 받지 않는다.

`combat.stats`는 현재 1/20/40/60/80/90 레벨 스냅샷을 저장한다. `combat.statProgression`에는 원본 `base`와 `growthPerLevel`을 함께 저장해, 이후 계산기에서 임의 레벨 값을 직접 계산할 수 있게 한다.

## 카테고리 축

나무위키 `명일방주: 엔드필드/오퍼레이터` 문서 기준으로 오퍼레이터 필터 축은 `src/data/game/operator/categories.json`에 분리한다.

- `rarity`: 4★, 5★, 6★
- `stats`: 생명력, 공격력, 방어력, 힘, 민첩, 지능, 의지, 치명타 확률, 치명타 피해, 오리지늄 아츠 강도
- `element`: 물리, 냉기, 열기, 자연, 전기
- `class`: 뱅가드, 가드, 디펜더, 서포터, 캐스터, 스트라이커
- `weapon`: 한손검, 양손검, 장병기, 권총, 아츠 유닛
- `equipment`: 장비 데이터셋과 연결되는 장비 축

오퍼레이터 seed는 계산과 소스 대조를 위해 `Guard`, `Nature`, `Arts Unit` 같은 영문 enum을 유지하고, 화면은 카테고리 사전의 `labelKo`를 우선 사용한다.

## 스킬 항목

스킬은 한 배열로 관리하되 `type`으로 구분한다.

- `basic_attack`: 일반 공격, 낙하 공격, 처형 공격, 막타 계수
- `battle_skill`: 배틀 스킬, 비용, 스택 생성/소모, 주요 계수
- `combo_skill`: 연계 스킬, 발동 조건, 쿨다운, 연계 효과
- `ultimate`: 궁극기, 에너지 비용, 지속 시간, 강화 효과
- `passive`: 별도 패시브가 존재할 경우

스킬 원문은 출처마다 번역과 버전 차이가 생길 수 있으므로, JSON에는 정리된 `description`, 짧은 `summary`, 줄 단위 `effects`, `damageType`, `icon`, 추출 가능한 `multipliers`를 함께 저장한다.

추가로 계산기/RAG를 위해 아래 row를 둔다.

- `sourceText`: 원문 보존 영역. 한국어 원문이 있으면 `ko`, 영문 원천이 있으면 `en`을 저장한다.
- `effectRows`: 텍스트에서 직접 추출한 효과 단위. 예: `공격력 +8%`, `10초`, `최대 5스택`.
- `calculationRows`: 조건이 충족되었을 때 계산기에 적용할 최종 효과. 예: 최대 5스택 기준 `공격력 +40%`.
- `totalDamageRows`: 스킬의 총합 피해량 계산용 row. 현재는 타격 수와 피해 타입만 확인된 항목이 많아 `formulaStatus: "needs_multiplier_data"`로 둔다.

예를 들어 진천우의 재능 `칼날 베기`는 원문과 계산 row를 분리해 저장한다.

- 원문: `스킬이 적에게 명중할 때마다 공격력 +8%, 10초 동안 지속, 해당 효과는 최대 5스택까지 중첩됩니다.`
- 효과 row: `공격력 +8%`, `durationSeconds: 10`, `maxStacks: 5`
- 계산 row: 조건 충족 및 최대 중첩 기준 `공격력 +40%`

## 재능과 잠재

재능과 잠재는 둘 다 `progressionEffect` 형태로 저장한다.

- `talents`: 정예화 또는 레벨에 따라 열리는 고유 효과. 레벨별 효과가 있는 경우 `levels` 배열에 각 설명을 보존한다.
- `passives`: 잠금 해제 단계별 능력치 패시브
- `potentials`: 중복 획득 또는 잠재 능력 등급에 따라 열리는 효과
- `baseSkills`: 제조/공업/시설 배치 효과

이 구조는 추후 피해 계산기가 특정 잠재 등급만 활성화하거나, 공업 계산기가 기지 스킬만 읽는 방식으로 확장하기 쉽다.

`progressionEffect`에도 스킬과 동일하게 `sourceText`, `effectRows`, `calculationRows`를 둔다. 레벨별 재능 효과가 있는 경우 `levels[]` 안에도 같은 row를 둔다. 이렇게 해야 “재능 1레벨 효과”와 “최종 재능 효과”를 계산기에서 분리해서 읽을 수 있다.

## 장비와 무기 연결

나무위키 장비 문서 기준으로 장비는 최소한 아래 항목을 가진다.

- 장비 이름
- 레어도
- 레벨
- 유형: 방어구, 글러브, 부품
- 방어력
- 보조 스탯 1, 보조 스탯 2
- 특성 스탯과 수치
- 설명과 보조 설명
- 세트 효과

오퍼레이터 JSON에는 장비 전체 데이터를 직접 넣지 않고 `recommendedGear`에 세트와 슬롯 추천만 넣는다. 장비 상세 정보는 나중에 별도 `gear.seed.json`으로 분리한다.

무기도 마찬가지로 오퍼레이터에는 전용 무기와 추천 무기 id만 저장하고, 무기 레벨/기질/획득 경로/정가 구매 여부는 별도 무기 JSON으로 분리한다.

## 검증 플로우

1. 새 오퍼레이터가 나오면 `operators.seed.json`에 `verification.status: "placeholder"`로 추가한다.
2. 공식 또는 DB에서 기본 프로필과 스탯을 확인하면 `needs_review`로 올린다.
3. 한국어 스킬/재능/잠재 원문을 인게임 또는 공식 한국어 출처에서 확인하면 `sourceText.status`를 `verified`로 올린다.
4. 효과 row와 계산 row가 원문과 일치하면 각 row의 `sourceStatus`를 `verified`로 올린다.
5. 스킬, 재능, 잠재, 재료, 장비 추천을 2개 이상 출처로 대조하면 오퍼레이터의 `verification.status`를 `verified`로 올린다.
6. 패치가 바뀌면 기존 항목을 덮어쓰지 말고 `reviewedAt`, `sourceRefs`, `notes`를 갱신한다.
