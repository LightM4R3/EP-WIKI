# EP-WIKI Crawler

`wiki.skport.com`의 오퍼레이터, 무기, 장비 데이터를 KR/EN/JP/CN 기준으로 수집하기 위한 독립 Selenium 패키지입니다.

이 디렉터리는 기존 React 앱과 `src/data/game` seed를 직접 수정하지 않습니다. 크롤링 결과는 먼저 `output`에 저장하고, 검증 및 publish 단계는 이후 별도 명령으로 연결합니다.

## 디렉터리

```text
crawler/
├─ config/                         # locale 및 subType별 gameEntryId 타깃
├─ data/
│  ├─ catalog/                     # immutable int ID + stable code 사전
│  ├─ canonical/                   # 검증된 구조화 사실 데이터
│  ├─ localization/                # locale별 SKPort 원문 overlay
│  └─ rag/                         # 임베딩/검색용 역정규화 문서
├─ schemas/                        # canonical/RAG JSON Schema
├─ src/epwiki_crawler/
│  ├─ core/                        # 브라우저, 계약, 저장 공통 코드
│  ├─ operator/                    # 오퍼레이터 수집기
│  ├─ weapon/                      # 무기 수집기
│  └─ gear/                        # 장비 수집기
├─ tests/                          # 브라우저 없이 실행 가능한 구조 테스트
└─ output/                         # 실행 산출물; Git 제외
```

## 로컬 준비

PowerShell 기준:

```powershell
cd crawler
py -m venv .venv
.venv\Scripts\python -m pip install -e .
```

Selenium 4의 Selenium Manager가 로컬 브라우저에 맞는 드라이버를 관리합니다. `plan`은 브라우저 없이 URL을 검증하고, `crawl`은 실제 렌더링 결과를 `output`에 저장합니다.

```powershell
.venv\Scripts\python -m epwiki_crawler domains
.venv\Scripts\python -m epwiki_crawler plan --domain all --locale all
.venv\Scripts\python -m epwiki_crawler crawl --domain all --locale all
.venv\Scripts\python -m unittest discover -s tests
```

## 크롤링 타깃과 실행

### start/end 범위 자동 수집

`--start`와 `--end`는 양 끝을 모두 포함합니다. 범위만 지정하면 각 전역 `gameEntryId`를 한 번만 열고, 렌더된 페이지를 `operator`/`weapon`/`gear`로 자동 분류합니다. 세 카테고리에 속하지 않는 ID는 `skipped`로 처리합니다.

```powershell
# 전역 gameEntryId 1~1000을 한 번씩 조회하고 자동 분류
.venv\Scripts\python -m epwiki_crawler crawl --start 1 --end 1000 --locale ko-KR

# 필요할 때만 특정 카테고리로 제한하여 검증
.venv\Scripts\python -m epwiki_crawler crawl --sub-type-id 2 --start 700 --end 800 --locale all
```

실행 전 URL 목록만 확인할 수도 있습니다.

```powershell
.venv\Scripts\python -m epwiki_crawler plan --start 1 --end 1000 --locale ko-KR
```

존재하지 않는 sparse ID는 `skipped`로 집계하고 다음 번호로 계속 진행합니다. 유효 항목은 도메인별로 다음 섹션만 RAG에 포함합니다.

- 오퍼레이터: 프로필, 성장/정예화, 전투 스킬, 오퍼레이터 재능, 인프라 스킬, 잠재능력
- 무기: 프로필, 레벨 성장, 무기 옵션, 잠재능력
- 장비: 프로필/기초 수치, 단조 옵션, 세트 효과

RAG 청크는 약 2,400자 단위이며, 각 문서에 `subTypeId`, `gameEntryId`, locale, 원본 SHA-256과 raw 파일 참조가 들어갑니다.

### manifest와 개별 ID 수집

기본 타깃은 `config/targets.json`에 `subTypeId`별로 관리합니다. `mainTypeId=1`과 도메인명은 코드가 결정하므로 새 항목을 추가할 때 `gameEntryIds`만 수정합니다.

```json
{
  "targets": [
    { "subTypeId": 1, "gameEntryIds": [25] },
    { "subTypeId": 2, "gameEntryIds": [732] },
    { "subTypeId": 4, "gameEntryIds": [1023] }
  ]
}
```

전체 타깃을 실행하기 전에 생성될 URL을 확인할 수 있습니다.

```powershell
.venv\Scripts\python -m epwiki_crawler plan --locale ko-KR
.venv\Scripts\python -m epwiki_crawler crawl --locale ko-KR
```

manifest를 수정하지 않고 sparse ID를 바로 확인하려면 단일 도메인과 `--entry-id`를 반복 지정합니다.

```powershell
.venv\Scripts\python -m epwiki_crawler plan --domain weapon --locale ko-KR --entry-id 732 --entry-id 900
.venv\Scripts\python -m epwiki_crawler crawl --domain gear --locale en-US --entry-id 1023
```

실행 결과는 데이터 역할별 디렉터리로 분리되고, 파일명에는 ID와 해당 locale의 이름이 함께 들어갑니다.

```text
output/<run-id>/
├─ raw/<locale>/<domain>/<gameEntryId>_<이름>.json
├─ rag/<locale>/<domain>/<gameEntryId>_<이름>.json
├─ errors/<locale>/<domain>/<gameEntryId>.json
├─ progress.json
└─ summary.json
```

긴 범위 실행 중에는 `progress.json`이 매 항목마다 갱신됩니다. 완료되면 `status`가 `completed`로 바뀌고 전체 결과는 `summary.json`에 기록됩니다.

완료된 run의 구조·스키마·raw/RAG 대응·정규화 메타데이터 품질은 다음 명령으로 검사할 수 있습니다.

```powershell
.venv\Scripts\python -m epwiki_crawler.quality output/<run-id>
```

검사 결과는 해당 run의 `quality-report.json`에 저장됩니다.

### 최신 RAG snapshot publish

크롤링과 동시에 프론트 검증용 최신 snapshot을 갱신할 수 있습니다.

```powershell
.venv\Scripts\python -m epwiki_crawler crawl --start 1001 --end 1050 --locale ko-KR --publish
```

완료된 여러 run을 하나의 최신 snapshot으로 병합하려면 `publish` 명령을 사용합니다.

```powershell
.venv\Scripts\python -m epwiki_crawler publish `
  --run-id auto-1-1000-ko-KR `
  --run-id auto-1001-1050-ko-KR-final `
  --locale ko-KR `
  --replace
```

산출물은 `data/rag/published/latest.<locale>.json`과 `manifest.json`입니다. 구조 검사를 통과하지 못한 run은 publish되지 않습니다. canonical 정규화까지 강제하려면 `--require-normalized`를 추가합니다.

예를 들어 탕탕은 `raw/ko-KR/operator/25_탕탕.json`과 `rag/ko-KR/operator/25_탕탕.json`으로 분리됩니다. URL의 `subTypeId`와 실제 전역 `gameEntryId`의 데이터 유형이 다르면 raw/error 파일을 만들지 않고 `skipped`로만 집계합니다.

기본 실행은 필요한 텍스트만 저장합니다. DOM 디버깅이 필요한 경우 `crawl` 명령에 `--save-html`을 추가합니다.

## 확장 규칙

- 사이트 표시명 대신 안정적인 내부 ID 또는 URL ID를 canonical ID로 사용합니다.
- locale은 `ko-KR`, `en-US`, `ja-JP`, `zh-TW`로 통일합니다. SKPort의 중국어 메뉴가 번체이므로 CN 수집 슬롯을 `zh-TW`/`zh-Hant`로 명시합니다.
- `operator`, `weapon`, `gear`는 공통 `DomainCrawler` 계약을 구현합니다.
- selector는 각 도메인의 `selectors.py`에서 관리합니다.
- 크롤링 결과가 기존 `src/data/game` 파일을 직접 덮어쓰지 않도록 합니다.
- 렌더링된 원본 DOM, 챕터 텍스트, 수집 시각과 콘텐츠 SHA-256은 실행 산출물로 보존합니다.

## RAG 데이터 규칙

- 클래스, 속성, 무기 유형, 능력치는 정수 ID로 필터링하되 stable code와 locale label을 함께 보존합니다. 임베딩에는 정수 ID만 넣지 않습니다.
- 정확 목록 질문(예: “민첩이 주요 능력치인 오퍼레이터”)은 `primaryId` 같은 구조 필드로 먼저 필터링하고 RAG 문서는 근거와 설명을 붙이는 데 사용합니다.
- 스킬은 1~12를 `levels` 배열로 저장합니다. 1~9는 `rank`, 10~12는 `mastery`이며 원문 표기(`RANK1`, `마스터리I` 등)를 함께 보존합니다.
- 페이지에서 텍스트로 노출되지 않는 클래스 아이콘은 PNG 바이트 SHA-256을 `classes.json`과 대조합니다. 미등록 해시는 자동 추정하지 않고 `needs_review`로 격리합니다.
- 언어 전환은 `#lang` 메뉴에서 `siteOptionLabel`을 클릭하고 `<html lang>` 및 `xml:lang`이 `config/locales.json`의 `htmlLang`과 일치할 때까지 기다립니다.
- locale DOM에서 최신 KR 수치 행이 빠진 경우 값을 번역으로 추정하지 않습니다. `missing_in_locale_dom`으로 표시하고 stable metric code를 통해 `ko-KR` canonical 값을 fallback합니다.
- 최초 예시는 `data/canonical/operator/tangtang.json`, `data/localization/operator/tangtang.*.json`, `data/rag/operator/tangtang.*.json`입니다.

## SKPort 상세 주소 규칙

- 현재 엔드필드 상세 페이지는 `mainTypeId=1`을 공통으로 사용합니다.
- 도메인은 `subTypeId`로 구분합니다: 오퍼레이터 `1`, 무기 `2`, 장비 `4`.
- `gameEntryId`는 도메인별 연속 번호가 아닌 전체 상세 항목의 sparse ID로 취급합니다.
- URL은 `epwiki_crawler.config.build_detail_url()`로만 생성해 라우팅 숫자를 중복 선언하지 않습니다.

## 무기 RAG 데이터 규칙

- 무기 레벨과 옵션 RANK는 별도 배열입니다. 무기 공격력은 `progression`의 LV.1/20/40/60/80/90, 옵션 수치는 각 `options[].levels`의 RANK 1~9에 저장합니다.
- 여러 무기가 공유하는 옵션 정의는 `weapon-options.json`에 정규화하고, 무기 canonical에는 immutable `optionId`/stable `optionCode`와 해당 무기의 수치만 저장합니다.
- `민첩 증가 · 대`, `공격력 증가 · 대`는 `shared_stat_option`, `방출 · 토벌의 원한`은 `named_weapon_trait`로 구분합니다.
- 최초 예시는 `data/canonical/weapon/rebellion.json`, `data/localization/weapon/rebellion.ko-KR.json`, `data/rag/weapon/rebellion.ko-KR.json`입니다.

## 장비 RAG 데이터 규칙

- 장비 LV와 단조 단계는 서로 다른 축입니다. LV/방어력은 장비 본체에, 옵션 변화는 각 `options[].levels`의 `forgeLevel` 0~3에 저장합니다.
- 1옵션과 3옵션은 필수이고 2옵션은 선택입니다. 2옵션이 없는 장비도 슬롯 번호를 당기지 않고 `[1, 3]`으로 보존합니다.
- 1·2옵션은 `힘/민첩/지능/의지` 중 하나만 허용합니다. 2옵션이 없는 장비의 높은 1옵션 수치는 전체 수집 후 `distribution_check`로 비교합니다.
- 장비 유형, 품질, 옵션, 세트는 각각 `gear-types.json`, `gear-qualities.json`, `gear-options.json`, `gear-sets.json`의 immutable ID와 stable code를 참조합니다.
- 노란색 품질의 단조 가능 규칙은 품질 카탈로그에 두고, 사용자 확인과 페이지 확인을 `eligibilityStatus`로 구분합니다.
- 세트 효과는 개별 장비에 복제하지 않습니다. 장비의 `setId`/`setCode`가 별도 `gear-set` canonical과 RAG 문서를 참조합니다.
- 최초 예시는 `data/canonical/gear/echo_of_ancient_sword_metal_gloves_i.json`과 `data/canonical/gear-set/echo_of_ancient_sword.json`입니다.

탕탕 RAG 문서를 다시 생성하거나 committed 결과와 일치하는지 확인할 수 있습니다.

```powershell
.venv\Scripts\python -m epwiki_crawler.operator.rag_builder
.venv\Scripts\python -m epwiki_crawler.operator.rag_builder --check
.venv\Scripts\python -m epwiki_crawler.weapon.rag_builder
.venv\Scripts\python -m epwiki_crawler.weapon.rag_builder --check
.venv\Scripts\python -m epwiki_crawler.gear.rag_builder
.venv\Scripts\python -m epwiki_crawler.gear.rag_builder --check
```
