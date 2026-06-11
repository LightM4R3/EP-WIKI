import { useMemo, useState } from 'react'
import { operators } from '../../data/catalog'
import { SectionHeader } from '../../shared/components/SectionHeader'
import { StatPill } from '../../shared/components/StatPill'

export function OperatorsPage() {
  const [searchTerm, setSearchTerm] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')
  const [rarityFilter, setRarityFilter] = useState('all')

  const roleOptions = useMemo(
    () =>
      Array.from(new Map(operators.map((operator) => [operator.role, operator.roleLabel])).entries()).map(
        ([id, label]) => ({ id, label }),
      ),
    [],
  )
  const rarityOptions = useMemo(
    () =>
      Array.from(new Map(operators.map((operator) => [String(operator.rarity), operator.rarityLabel])).entries()).map(
        ([id, label]) => ({ id, label }),
      ),
    [],
  )

  const filteredOperators = useMemo(() => {
    const normalizedSearchTerm = searchTerm.trim().toLowerCase()

    return operators.filter((operator) => {
      const matchesSearch =
        normalizedSearchTerm.length === 0 ||
        [operator.name, operator.faction, operator.roleLabel, operator.damageTypeLabel, operator.weaponTypeLabel]
          .join(' ')
          .toLowerCase()
          .includes(normalizedSearchTerm)
      const matchesRole = roleFilter === 'all' || operator.role === roleFilter
      const matchesRarity = rarityFilter === 'all' || String(operator.rarity) === rarityFilter

      return matchesSearch && matchesRole && matchesRarity
    })
  }, [rarityFilter, roleFilter, searchTerm])

  return (
    <section className="section-block" id="operators">
      <SectionHeader
        eyebrow="Database"
        title="오퍼레이터 기본 정보"
        description="오퍼레이터의 기본 분류, 능력치, 재능, 스킬을 확인합니다. 현재 데이터는 검수 상태를 함께 표시합니다."
      />

      <div className="catalog-toolbar" aria-label="오퍼레이터 필터">
        <label>
          검색
          <input
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="이름, 진영, 역할 검색"
            type="search"
            value={searchTerm}
          />
        </label>
        <label>
          역할
          <select onChange={(event) => setRoleFilter(event.target.value)} value={roleFilter}>
            <option value="all">전체 역할</option>
            {roleOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          희귀도
          <select onChange={(event) => setRarityFilter(event.target.value)} value={rarityFilter}>
            <option value="all">전체 희귀도</option>
            {rarityOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <span className="catalog-count">{filteredOperators.length}명</span>
      </div>

      <div className="operator-grid">
        {filteredOperators.map((operator) => (
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
