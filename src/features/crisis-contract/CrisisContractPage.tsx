import { useState } from 'react'
import { crisisRisks } from '../../data/catalog'
import { SectionHeader } from '../../shared/components/SectionHeader'
import { StatPill } from '../../shared/components/StatPill'

export function CrisisContractPage() {
  const [selectedRiskIds, setSelectedRiskIds] = useState<string[]>([])

  const selectedRisks = crisisRisks.filter((risk) => selectedRiskIds.includes(risk.id))
  const selectedRiskIdSet = new Set(selectedRiskIds)
  const totalScore = selectedRisks.reduce((sum, risk) => sum + risk.score, 0)

  const missingPrerequisites = selectedRisks.flatMap((risk) =>
    risk.prerequisites.filter((requiredId) => !selectedRiskIdSet.has(requiredId)),
  )
  const conflicts = selectedRisks.flatMap((risk) =>
    risk.conflictsWith.filter((conflictId) => selectedRiskIdSet.has(conflictId)),
  )

  function toggleRisk(riskId: string) {
    setSelectedRiskIds((current) =>
      current.includes(riskId) ? current.filter((selectedId) => selectedId !== riskId) : [...current, riskId],
    )
  }

  return (
    <section className="section-block" id="crisis-contract">
      <SectionHeader
        eyebrow="Contract Builder"
        title="위기 협약 제약 선택"
        description="제약은 점수뿐 아니라 선행 조건과 충돌 조건이 중요하므로, 선택 상태를 데이터 기반으로 검증하는 방향으로 설계합니다."
      />

      <div className="contract-layout">
        <div className="risk-list" aria-label="제약 목록">
          {crisisRisks.map((risk) => {
            const selected = selectedRiskIdSet.has(risk.id)
            return (
              <button
                className={selected ? 'risk-card selected' : 'risk-card'}
                key={risk.id}
                onClick={() => toggleRisk(risk.id)}
                type="button"
              >
                <span className="risk-score">{risk.score}</span>
                <span>
                  <strong>{risk.title}</strong>
                  <small>{risk.category}</small>
                </span>
                <p>{risk.description}</p>
              </button>
            )
          })}
        </div>

        <aside className="result-panel" aria-label="선택한 위기 협약 제약">
          <p className="eyebrow">Selected Contract</p>
          <h3>선택 제약 요약</h3>

          <div className="stat-grid">
            <StatPill label="총 점수" value={totalScore} />
            <StatPill label="선택 제약" value={selectedRisks.length} />
            <StatPill label="누락 전제" value={missingPrerequisites.length} />
            <StatPill label="충돌" value={conflicts.length} />
          </div>

          {selectedRisks.length === 0 ? (
            <p className="empty-note">제약을 선택하면 이곳에 점수와 검증 상태가 표시됩니다.</p>
          ) : (
            <ul className="selected-list">
              {selectedRisks.map((risk) => (
                <li key={risk.id}>
                  <strong>{risk.title}</strong>
                  <span>{risk.score}점</span>
                </li>
              ))}
            </ul>
          )}

          {(missingPrerequisites.length > 0 || conflicts.length > 0) && (
            <div className="warning-box">
              <strong>검토 필요</strong>
              <p>선행 조건이 누락되었거나 동시에 선택할 수 없는 제약이 포함되어 있습니다.</p>
            </div>
          )}
        </aside>
      </div>
    </section>
  )
}
