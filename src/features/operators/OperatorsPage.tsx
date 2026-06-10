import { operators } from '../../data/catalog'
import { SectionHeader } from '../../shared/components/SectionHeader'
import { StatPill } from '../../shared/components/StatPill'

export function OperatorsPage() {
  return (
    <section className="section-block" id="operators">
      <SectionHeader
        eyebrow="Database"
        title="오퍼레이터 기본 정보"
        description="실제 데이터가 확보되면 이 영역은 검색, 필터, 상세 스탯표, 스킬/재능 비교 화면으로 확장됩니다."
      />

      <div className="operator-grid">
        {operators.map((operator) => (
          <article className="operator-card" key={operator.id}>
            <div className="card-heading">
              <div>
                <p className="eyebrow">{operator.faction}</p>
                <h3>{operator.name}</h3>
              </div>
              <span className="rarity">{operator.rarityLabel}</span>
            </div>

            <div className="tag-row">
              <span>{operator.roleLabel}</span>
              <span>{operator.damageTypeLabel}</span>
              <span>{operator.weaponTypeLabel}</span>
              <span>{operator.sourceStatus === 'verified' ? '검증 완료' : '검토 필요'}</span>
            </div>

            <div className="stat-grid">
              <StatPill label="생명력" value={operator.baseStats.hp} />
              <StatPill label="공격력" value={operator.baseStats.attack} />
              <StatPill label="방어력" value={operator.baseStats.defense} />
              <StatPill label="힘" value={operator.baseStats.strength} />
              <StatPill label="민첩" value={operator.baseStats.agility} />
              <StatPill label="지능" value={operator.baseStats.intellect} />
              <StatPill label="의지" value={operator.baseStats.will} />
              <StatPill label="치명타 확률" value={`${Math.round(operator.baseStats.critRate * 100)}%`} />
            </div>

            <dl className="compact-list">
              <div>
                <dt>주요/보조 능력치</dt>
                <dd>
                  {operator.mainAttributeLabel} / {operator.secondaryAttributeLabel}
                </dd>
              </div>
              <div>
                <dt>재능</dt>
                <dd>{operator.talents.join(', ')}</dd>
              </div>
              <div>
                <dt>스킬</dt>
                <dd>{operator.skills.join(', ')}</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </section>
  )
}
