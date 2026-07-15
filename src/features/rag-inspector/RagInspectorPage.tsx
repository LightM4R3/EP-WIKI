import { useMemo, useState } from 'react'
import retrievalManifestJson from '../../../crawler/data/rag/retrieval/manifest.ko-KR.json'
import retrievalQualityJson from '../../../crawler/data/rag/retrieval/quality-report.ko-KR.json'
import './RagInspectorPage.css'

type RagDomain = 'operator' | 'weapon' | 'gear' | 'gear_set'

type WithheldField = {
  path: string
  reason: string
  status: 'missing' | 'source_conflict' | 'source_unavailable' | 'unmapped'
}

type RetrievalDocument = {
  documentId: string
  semanticKey: string
  locale: string
  documentType: string
  channel: string
  entity: {
    type: RagDomain
    key: string
    gameEntryId?: number
    name: string
    aliases: string[]
  }
  title: string
  content: string
  facts: Record<string, unknown>
  filters: Record<string, unknown>
  provenance: {
    normalizedRef: string | null
    sourceUrl: string | null
    authority: string
    verificationStatus: string
    confidence: string
    evidenceDocumentIds: string[]
  }
  coverage: { withheldFields: WithheldField[] }
  indexing: {
    eligible: true
    contentSha256: string
    payloadSha256: string
  }
}

type ManifestRecord = {
  documentId: string
  documentType: string
  ref: string
  entity: RetrievalDocument['entity']
}

type RetrievalManifest = {
  releaseId: string
  generatedAt: string
  locale: string
  intendedUse: string
  ingestion: {
    manifestIsSoleEntryPoint: boolean
    mode: string
    deleteMissing: boolean
    forbiddenRoots: string[]
  }
  quality: {
    indexable: boolean
    coverageComplete: boolean
    refreshStatus: string
  }
  stats: {
    documents: number
    byDocumentType: Record<string, number>
  }
  documents: ManifestRecord[]
}

type RetrievalQuality = {
  verdict: string
  coverage: {
    complete: boolean
    refreshStatus: string
    withheldSourceConflicts: number
    sourceAbsent: Array<{ name: string; field: string }>
    unmappedMaterials: string[]
  }
  checks: Record<string, { passed: boolean }>
}

type InspectorDocument = RetrievalDocument & { ref: string }

type InspectorEntity = {
  key: string
  domain: RagDomain
  gameEntryId?: number
  name: string
  groupLabel: string
  sourceUrl: string | null
  normalizedRef: string | null
  documents: InspectorDocument[]
  withheldFields: WithheldField[]
}

const manifest = retrievalManifestJson as unknown as RetrievalManifest
const quality = retrievalQualityJson as unknown as RetrievalQuality
const documentModules = import.meta.glob(
  '../../../crawler/data/rag/retrieval/ko-KR/**/*.json',
  { eager: true },
) as Record<string, { default: RetrievalDocument }>
const documentPayloads = new Map(
  Object.values(documentModules).map((module) => [module.default.documentId, module.default]),
)

const domainLabels: Record<RagDomain, string> = {
  operator: '오퍼레이터',
  weapon: '무기',
  gear: '장비',
  gear_set: '장비 세트',
}
const entities = buildEntities()

const documentTypeLabels: Record<string, string> = {
  operator_profile: '기본 정보',
  operator_progression: '레벨 능력치·재료',
  operator_promotion: '정예화·장비 해금',
  operator_combat_skill: '전투 스킬',
  operator_talent: '오퍼레이터 재능',
  operator_infrastructure_talent: '인프라 재능',
  operator_potential: '잠재능력',
  weapon_profile: '기본 정보',
  weapon_progression: '기초 공격력',
  weapon_option: '무기 옵션',
  weapon_potential: '무기 잠재능력',
  gear_profile: '기본 정보·옵션',
  gear_forging: '정밀 단조',
  gear_set_effect: '세트 효과',
}

function buildEntities(): InspectorEntity[] {
  const groups = new Map<string, InspectorEntity>()
  for (const record of manifest.documents) {
    const payload = documentPayloads.get(record.documentId)
    if (!payload) continue
    const current = groups.get(payload.entity.key) ?? {
      key: payload.entity.key,
      domain: payload.entity.type,
      gameEntryId: payload.entity.gameEntryId,
      name: payload.entity.name,
      groupLabel: String(payload.filters.groupLabel ?? '-'),
      sourceUrl: payload.provenance.sourceUrl,
      normalizedRef: payload.provenance.normalizedRef,
      documents: [],
      withheldFields: [],
    }
    current.documents.push({ ...payload, ref: record.ref })
    current.withheldFields.push(...payload.coverage.withheldFields)
    groups.set(payload.entity.key, current)
  }
  return [...groups.values()].sort((left, right) => {
    const domainOrder = Object.keys(domainLabels).indexOf(left.domain) - Object.keys(domainLabels).indexOf(right.domain)
    if (domainOrder !== 0) return domainOrder
    return (left.gameEntryId ?? Number.MAX_SAFE_INTEGER) - (right.gameEntryId ?? Number.MAX_SAFE_INTEGER)
  })
}

function formatGeneratedAt(value: string) {
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export function RagInspectorPage() {
  const [query, setQuery] = useState('')
  const [domain, setDomain] = useState<'all' | RagDomain>('all')
  const [selectedEntityKey, setSelectedEntityKey] = useState(entities[0]?.key ?? '')
  const [selectedDocumentType, setSelectedDocumentType] = useState('all')

  const domainCounts = useMemo(
    () =>
      entities.reduce<Record<RagDomain, number>>(
        (counts, entity) => ({ ...counts, [entity.domain]: counts[entity.domain] + 1 }),
        { operator: 0, weapon: 0, gear: 0, gear_set: 0 },
      ),
    [],
  )
  const filteredEntities = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return entities.filter((entity) => {
      if (domain !== 'all' && entity.domain !== domain) return false
      if (!normalizedQuery) return true
      const documentText = entity.documents
        .map((document) => `${document.title} ${document.content}`)
        .join(' ')
      return `${entity.name} ${entity.key} ${entity.gameEntryId ?? ''} ${documentText}`
        .toLowerCase()
        .includes(normalizedQuery)
    })
  }, [domain, query])

  const selectedEntity =
    filteredEntities.find((entity) => entity.key === selectedEntityKey) ?? filteredEntities[0] ?? null
  const documentTypes = selectedEntity
    ? Array.from(new Set(selectedEntity.documents.map((document) => document.documentType)))
    : []
  const visibleDocuments = selectedEntity
    ? selectedEntity.documents.filter(
        (document) =>
          selectedDocumentType === 'all' || document.documentType === selectedDocumentType,
      )
    : []
  const passedChecks = Object.values(quality.checks).filter((check) => check.passed).length
  const totalChecks = Object.keys(quality.checks).length

  function selectDomain(nextDomain: 'all' | RagDomain) {
    setDomain(nextDomain)
    setSelectedEntityKey('')
    setSelectedDocumentType('all')
  }

  return (
    <section className="rag-inspector" id="rag-inspector" aria-labelledby="rag-inspector-title">
      <header className="rag-inspector__header">
        <div>
          <p className="eyebrow">Retrieval Manifest / Gameplay Facts / ko-KR</p>
          <h1 id="rag-inspector-title">RAG 데이터 검증 터미널</h1>
          <p>
            원문 감사 원장이 아니라 현재 retrieval manifest에 등록된 문서만 표시합니다. 검색 문장,
            구조화 facts, 보류한 값과 근거를 분리해 확인할 수 있습니다.
          </p>
        </div>
        <div className="rag-inspector__status">
          <span>{quality.verdict.toUpperCase()}</span>
          <strong>{entities.length.toLocaleString('ko-KR')}</strong>
          <small>ENTITIES / {manifest.stats.documents.toLocaleString('ko-KR')} DOCS</small>
        </div>
      </header>

      <div className="rag-quality-strip">
        <article className={manifest.quality.indexable ? 'is-ok' : 'is-danger'}>
          <span>STRICT GATES</span>
          <strong>{passedChecks}/{totalChecks} PASS</strong>
        </article>
        <article className={quality.checks.uniqueContentHashes?.passed ? 'is-ok' : 'is-danger'}>
          <span>DUPLICATE CONTENT</span>
          <strong>{quality.checks.uniqueContentHashes?.passed ? '0' : 'FAIL'}</strong>
        </article>
        <article className={quality.checks.uiResidue?.passed ? 'is-ok' : 'is-danger'}>
          <span>UI / RAW NOISE</span>
          <strong>{quality.checks.uiResidue?.passed ? '0' : 'FAIL'}</strong>
        </article>
        <article className={quality.coverage.withheldSourceConflicts > 0 ? 'is-warn' : 'is-ok'}>
          <span>WITHHELD CONFLICTS</span>
          <strong>{quality.coverage.withheldSourceConflicts}</strong>
        </article>
        <article>
          <span>GENERATED</span>
          <strong>{formatGeneratedAt(manifest.generatedAt)}</strong>
        </article>
      </div>

      {!manifest.quality.coverageComplete && (
        <div className="rag-inspector__warning" role="status">
          <strong>검색 가능 / refresh 검증 진행 중</strong>
          <span>
            현재 문서는 strict 검색 품질을 통과했습니다. 다만 원본 320개 중 일부는 legacy source hash라
            지속 refresh 완료 상태로 과장하지 않습니다. 충돌 수치 {quality.coverage.withheldSourceConflicts}건은
            답변 가능한 facts에서 제외했습니다.
          </span>
        </div>
      )}

      <div className="rag-inspector__toolbar">
        <label>
          <span>Manifest 문서 검색</span>
          <input
            onChange={(event) => {
              setQuery(event.target.value)
              setSelectedEntityKey('')
              setSelectedDocumentType('all')
            }}
            placeholder="이름, gameEntryId, 옵션, 스킬 텍스트"
            type="search"
            value={query}
          />
        </label>
        <div className="rag-domain-filter" aria-label="RAG 도메인 필터">
          <button className={domain === 'all' ? 'is-active' : ''} onClick={() => selectDomain('all')} type="button">
            전체 <small>{entities.length}</small>
          </button>
          {(Object.keys(domainLabels) as RagDomain[]).map((domainId) => (
            <button
              className={domain === domainId ? 'is-active' : ''}
              key={domainId}
              onClick={() => selectDomain(domainId)}
              type="button"
            >
              {domainLabels[domainId]} <small>{domainCounts[domainId]}</small>
            </button>
          ))}
        </div>
        <output>
          <strong>{filteredEntities.length}</strong>
          <span>검색 결과</span>
        </output>
      </div>

      <div className="rag-inspector__workspace">
        <aside className="rag-entity-list" aria-label="retrieval manifest 엔티티">
          {filteredEntities.map((entity) => (
            <button
              className={selectedEntity?.key === entity.key ? 'is-active' : ''}
              key={entity.key}
              onClick={() => {
                setSelectedEntityKey(entity.key)
                setSelectedDocumentType('all')
              }}
              type="button"
            >
              <span>{entity.gameEntryId ? String(entity.gameEntryId).padStart(4, '0') : 'SET'}</span>
              <div>
                <small>{domainLabels[entity.domain]}</small>
                <strong>{entity.name}</strong>
                <em>{entity.documents.length} documents</em>
              </div>
              <i className={entity.withheldFields.length > 0 ? 'is-warn' : 'is-ok'} />
            </button>
          ))}
          {filteredEntities.length === 0 && (
            <p className="rag-entity-list__empty">조건에 맞는 retrieval 데이터가 없습니다.</p>
          )}
        </aside>

        <div className="rag-document-panel">
          {selectedEntity ? (
            <>
              <header className="rag-entity-header">
                <div>
                  <span>
                    {domainLabels[selectedEntity.domain]} / {selectedEntity.gameEntryId ? `ENTRY ${selectedEntity.gameEntryId}` : 'SHARED ENTITY'}
                  </span>
                  <h2>{selectedEntity.name}</h2>
                  <p>{selectedEntity.key} · RELEASE {manifest.releaseId.slice(0, 12)}</p>
                </div>
                {selectedEntity.sourceUrl && (
                  <a href={selectedEntity.sourceUrl} rel="noreferrer" target="_blank">
                    SKPort 원문 열기 ↗
                  </a>
                )}
              </header>

              <dl className="rag-entity-facts">
                <div><dt>GROUP</dt><dd>{selectedEntity.groupLabel}</dd></div>
                <div><dt>문서</dt><dd>{selectedEntity.documents.length}개</dd></div>
                <div><dt>보류된 주장</dt><dd>{selectedEntity.withheldFields.length}개</dd></div>
                <div><dt>감사 원장</dt><dd>{selectedEntity.normalizedRef ?? '-'}</dd></div>
              </dl>

              {selectedEntity.withheldFields.length > 0 && (
                <section className="rag-normalization-gap">
                  <header>
                    <strong>추측하지 않고 보류한 값</strong>
                    <span>{selectedEntity.withheldFields.length}건</span>
                  </header>
                  <p>
                    {selectedEntity.withheldFields
                      .map((field) => `${field.path} [${field.status}] ${field.reason}`)
                      .join(' · ')}
                  </p>
                </section>
              )}

              <nav className="rag-section-tabs" aria-label="Retrieval 문서 유형">
                <button
                  className={selectedDocumentType === 'all' ? 'is-active' : ''}
                  onClick={() => setSelectedDocumentType('all')}
                  type="button"
                >
                  전체 ({selectedEntity.documents.length})
                </button>
                {documentTypes.map((documentType) => (
                  <button
                    className={selectedDocumentType === documentType ? 'is-active' : ''}
                    key={documentType}
                    onClick={() => setSelectedDocumentType(documentType)}
                    type="button"
                  >
                    {documentTypeLabels[documentType] ?? documentType} (
                    {selectedEntity.documents.filter((document) => document.documentType === documentType).length})
                  </button>
                ))}
              </nav>

              <div className="rag-document-list">
                {visibleDocuments.map((document, index) => (
                  <article className="rag-document" key={document.documentId}>
                    <header>
                      <div>
                        <span>DOC {String(index + 1).padStart(2, '0')}</span>
                        <strong>{documentTypeLabels[document.documentType] ?? document.documentType}</strong>
                      </div>
                      <code>{document.documentId}</code>
                    </header>
                    <pre>{document.content}</pre>
                    <details>
                      <summary>구조화 facts 보기</summary>
                      <pre>{JSON.stringify(document.facts, null, 2)}</pre>
                    </details>
                    <details>
                      <summary>근거·품질 정보 보기</summary>
                      <pre>{JSON.stringify({ ref: document.ref, provenance: document.provenance, coverage: document.coverage, indexing: document.indexing }, null, 2)}</pre>
                    </details>
                  </article>
                ))}
              </div>
            </>
          ) : (
            <div className="rag-document-panel__empty">왼쪽에서 확인할 엔티티를 선택하세요.</div>
          )}
        </div>
      </div>
    </section>
  )
}
