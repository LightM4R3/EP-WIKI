# 정규화 RAG 저장소

이 디렉터리가 자동 크롤링 결과의 영구 RAG 저장소입니다. `output`은 크롤링 중에만 사용하는 임시 공간이며 publish가 끝난 뒤 삭제해도 됩니다.

## 저장 단위

- 파일 하나는 `locale + entityType + gameEntryId` 하나를 나타냅니다.
- `operator`는 속성, `weapon`은 무기 유형, `gear`는 장비 세트 이름으로 하위 디렉터리를 나눕니다.
- 각 파일의 `normalized_profile` 문서는 질의용 핵심 필드를 명시하며, 나머지 문서는 SKPort 렌더링 텍스트와 근거 metadata를 보존합니다.

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

## 품질 상태

- `query_ready`: 분류 및 목록 질의에 필요한 필드가 원문 label을 근거로 정규화됐습니다.
- `canonicalComplete`: 희귀도, 클래스, 이미지, 재료 ID 등 요청된 모든 필드가 별도 검증까지 끝난 상태입니다.
- `unresolvedFields`: 현재 저장된 원문만으로 확정할 수 없어 추측하지 않은 필드입니다.
- `sourceConflicts`: 같은 페이지의 요약 표와 상세 표가 다른 경우 두 값을 모두 보존하고 선택 규칙을 기록합니다.

## 갱신

크롤링과 정규화를 한 번에 실행합니다.

```powershell
.venv\Scripts\python.exe -m epwiki_crawler crawl --start 1051 --end 1100 --locale ko-KR --publish
```

이미 생성된 published snapshot을 다시 정규화합니다.

```powershell
.venv\Scripts\python.exe -m epwiki_crawler normalize --locale ko-KR
```
