import { useMemo, useState } from 'react'
import { weapons } from '../../data/catalog'
import { SectionHeader } from '../../shared/components/SectionHeader'
import { StatPill } from '../../shared/components/StatPill'

export function WeaponsPage() {
  const [searchTerm, setSearchTerm] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [rarityFilter, setRarityFilter] = useState('all')

  const typeOptions = useMemo(
    () =>
      Array.from(new Map(weapons.map((weapon) => [weapon.weaponType, weapon.weaponTypeLabel])).entries()).map(
        ([id, label]) => ({ id, label }),
      ),
    [],
  )
  const rarityOptions = useMemo(
    () =>
      Array.from(new Map(weapons.map((weapon) => [String(weapon.rarity), weapon.rarityLabel])).entries()).map(
        ([id, label]) => ({ id, label }),
      ),
    [],
  )

  const filteredWeapons = useMemo(() => {
    const normalizedSearchTerm = searchTerm.trim().toLowerCase()

    return weapons.filter((weapon) => {
      const matchesSearch =
        normalizedSearchTerm.length === 0 ||
        [weapon.name, weapon.weaponTypeLabel, weapon.acquisitionLabel, weapon.trait]
          .join(' ')
          .toLowerCase()
          .includes(normalizedSearchTerm)
      const matchesType = typeFilter === 'all' || weapon.weaponType === typeFilter
      const matchesRarity = rarityFilter === 'all' || String(weapon.rarity) === rarityFilter

      return matchesSearch && matchesType && matchesRarity
    })
  }, [rarityFilter, searchTerm, typeFilter])

  return (
    <section className="section-block" id="weapons">
      <SectionHeader
        eyebrow="Arsenal"
        title="무기 카탈로그"
        description="무기별 타입, 희귀도, 획득처, 기본 공격력, Lv.1~Lv.9 옵션 범위를 확인합니다."
      />

      <div className="catalog-toolbar" aria-label="무기 필터">
        <label>
          검색
          <input
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="무기명, 타입, 옵션 검색"
            type="search"
            value={searchTerm}
          />
        </label>
        <label>
          타입
          <select onChange={(event) => setTypeFilter(event.target.value)} value={typeFilter}>
            <option value="all">전체 타입</option>
            {typeOptions.map((option) => (
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
        <span className="catalog-count">{filteredWeapons.length}개</span>
      </div>

      <div className="catalog-grid">
        {filteredWeapons.map((weapon) => (
          <article className="catalog-card weapon-card" key={weapon.id}>
            <div className="card-heading">
              <div>
                <p className="eyebrow">{weapon.weaponTypeLabel}</p>
                <h3>{weapon.name}</h3>
              </div>
              <span className="rarity">{weapon.rarityLabel}</span>
            </div>

            <div className="stat-grid">
              <StatPill label="기본 공격력" value={weapon.attack} />
              <StatPill label="획득처" value={weapon.acquisitionLabel} />
            </div>

            <dl className="compact-list">
              <div>
                <dt>옵션</dt>
                <dd>{weapon.trait}</dd>
              </div>
              <div>
                <dt>검수 상태</dt>
                <dd>{weapon.sourceStatus === 'verified' ? '검증 완료' : '검토 필요'}</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </section>
  )
}
