# 정규화·근거 원장

이 디렉터리는 크롤링 원문과 구조화 결과를 함께 보존하는 **감사 원장**입니다. 원문 재검증과 파서 개선에는 필요하지만 LLM 검색 인덱스에 직접 넣으면 안 됩니다.

## 역할

- 파일 하나는 `locale + entityType + gameEntryId` 하나를 나타냅니다.
- `operator`는 속성, `weapon`은 무기 유형, `gear`는 장비 세트로 묶습니다.
- 구조화 필드와 `raw_rendered` 근거 문서가 함께 있어 추출 결과를 원문까지 역추적할 수 있습니다.
- `published`에도 일부 문서가 복제되므로 디렉터리 glob 방식으로 색인하면 중복 검색이 발생합니다.

```text
normalized/
├─ ko-KR/
│  ├─ operator/<속성>/<gameEntryId>_<이름>.json
│  ├─ weapon/<무기 유형>/<gameEntryId>_<이름>.json
│  └─ gear/<세트 이름>/<gameEntryId>_<이름>.json
├─ catalogs/
├─ manifest.ko-KR.json
└─ quality-report.ko-KR.json
```

## 검색 인덱스 정책

LLM/RAG 색인은 반드시 `../retrieval/manifest.<locale>.json`만 진입점으로 사용합니다. 이 디렉터리와 `../published`는 retrieval manifest의 `forbiddenRoots`에 명시되어 있습니다.

- `query_ready`: 일부 핵심 구조 필드가 존재한다는 뜻이며 전체 정보 검증 완료를 뜻하지 않습니다.
- `canonicalComplete`: 요청 필드 전체가 별도 검증된 상태입니다.
- `unresolvedFields`: 추측하지 않고 보류한 필드입니다.
- `sourceConflicts`: 같은 페이지 안의 값 충돌과 적용한 규칙을 보존합니다.

재생성 명령은 retrieval 생성까지 연속 실행합니다.

```powershell
.venv\Scripts\python.exe -m epwiki_crawler normalize --locale ko-KR
```
