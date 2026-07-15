# Retrieval 전용 RAG corpus

이 디렉터리만 LLM 검색에 사용합니다. `manifest.<locale>.json`은 유일한 ingestion 진입점이며, manifest에 등록되지 않은 JSON은 색인 대상이 아닙니다.

## 문서 원칙

- 문서 하나는 프로필, 스킬 하나, 무기 옵션 하나, 단조 표 하나처럼 하나의 의미 단위만 가집니다.
- 사람이 검색할 문장은 `content`, 정확한 필터와 최종 답변 수치는 `facts`에서 읽습니다.
- URL, 크롤링 시각, HTML/UI 토큰과 `raw_rendered` 원문은 `content`에 넣지 않습니다.
- 장비 세트 효과는 장비마다 복제하지 않고 세트당 한 문서만 생성합니다.
- 확정 근거가 없는 값은 추측하지 않습니다. `coverage.withheldFields`에 누락·충돌 사유를 남기고 `facts`의 답변 가능 값에서 제거합니다.
- 현재 release 전체 동기화 시 `deleteMissing=true`이므로, 이전에 존재했던 중복 엔티티의 잔존 벡터도 삭제해야 합니다.

```text
retrieval/
├─ manifest.ko-KR.json             # 유일한 ingestion 진입점
├─ quality-report.ko-KR.json       # strict 품질 게이트 결과
└─ ko-KR/<releaseId>/
   ├─ operator/<속성>/<ID_이름>/<의미 단위>.json
   ├─ weapon/<무기 유형>/<ID_이름>/<의미 단위>.json
   ├─ gear/<세트>/<ID_이름>/<의미 단위>.json
   └─ gear-set/<세트>/<세트 ID>/effect.json
```

## 생성과 검증

```powershell
.venv\Scripts\python.exe -m epwiki_crawler retrieval build --locale ko-KR
.venv\Scripts\python.exe -m epwiki_crawler retrieval validate --locale ko-KR
```

빌드는 모든 strict gate를 통과한 release만 manifest로 승격합니다. `crawl --publish`와 `normalize`도 retrieval 생성을 자동으로 호출합니다.
