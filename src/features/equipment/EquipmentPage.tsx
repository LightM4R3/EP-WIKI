import { useMemo, useState } from 'react'
import equipmentCategoryData from '../../data/game/equipment/categories.json'
import equipmentDataset from '../../data/game/equipment/equipment.seed.json'
import equipmentOptionCategoryData from '../../data/game/equipment/option-categories.json'
import equipmentSetCategoryData from '../../data/game/equipment/set-categories.json'
import { SectionHeader } from '../../shared/components/SectionHeader'
import { StatPill } from '../../shared/components/StatPill'

type SeedEquipment = (typeof equipmentDataset.equipment)[number]
type SeedEquipmentSet = (typeof equipmentSetCategoryData.sets)[number]
type SeedEquipmentOptionCategory = (typeof equipmentOptionCategoryData.categories)[number]

const setMap = new Map<string, SeedEquipmentSet>(
  equipmentSetCategoryData.sets.map((equipmentSet) => [equipmentSet.id, equipmentSet]),
)
const optionMap = new Map<string, SeedEquipmentOptionCategory>(
  equipmentOptionCategoryData.categories.map((option) => [option.id, option]),
)
const partOptions = equipmentCategoryData.parts.map((part) => ({ id: part.id, label: part.labelKo }))
const levelOptions = Array.from(new Set(equipmentDataset.equipment.map((equipment) => equipment.level))).sort(
  (a, b) => b - a,
)
const setOptions = equipmentSetCategoryData.sets.map((equipmentSet) => ({
  id: equipmentSet.id,
  label: equipmentSet.nameKo,
}))

function getSetName(equipment: SeedEquipment) {
  return equipment.setCategoryId ? setMap.get(equipment.setCategoryId)?.nameKo ?? '미확인 세트' : '단일 장비'
}

function getSetEffect(equipment: SeedEquipment) {
  return equipment.setCategoryId ? setMap.get(equipment.setCategoryId)?.effectKo ?? '세트 효과 검토 필요' : null
}

function getOptionLabel(optionCategoryId: string) {
  const option = optionMap.get(optionCategoryId)
  if (!option) {
    return `미확인 옵션: ${optionCategoryId}`
  }

  const forgeSummary =
    option.forgeStatus === 'available'
      ? `단조 ${option.forgeStages.map((stage) => `${stage.stage === 0 ? '0단계' : `+${stage.stage}`} ${stage.value}`).join(' / ')}`
      : option.forgeStatus === 'needs_review'
        ? '단조 검토 필요'
        : '단조 없음'

  return `${option.statKo} ${option.baseValue} · ${forgeSummary}`
}

function getEquipmentSearchText(equipment: SeedEquipment) {
  return [
    equipment.names.ko,
    equipment.partLabelKo,
    getSetName(equipment),
    equipment.options.map((option) => getOptionLabel(option.categoryId)).join(' '),
  ]
    .join(' ')
    .toLowerCase()
}

export function EquipmentPage() {
  const [searchTerm, setSearchTerm] = useState('')
  const [partFilter, setPartFilter] = useState('all')
  const [setFilter, setSetFilter] = useState('all')
  const [levelFilter, setLevelFilter] = useState('all')

  const filteredEquipment = useMemo(() => {
    const normalizedSearchTerm = searchTerm.trim().toLowerCase()

    return equipmentDataset.equipment.filter((equipment) => {
      const matchesSearch =
        normalizedSearchTerm.length === 0 || getEquipmentSearchText(equipment).includes(normalizedSearchTerm)
      const matchesPart = partFilter === 'all' || equipment.partId === partFilter
      const matchesSet = setFilter === 'all' || equipment.setCategoryId === setFilter
      const matchesLevel = levelFilter === 'all' || String(equipment.level) === levelFilter

      return matchesSearch && matchesPart && matchesSet && matchesLevel
    })
  }, [levelFilter, partFilter, searchTerm, setFilter])

  return (
    <section className="section-block" id="equipment">
      <SectionHeader
        eyebrow="Equipment"
        title="장비 카탈로그"
        description="장비의 세트, 부위, 방어력, 1~3옵션, 부위별 단조 수치를 함께 확인합니다."
      />

      <div className="equipment-summary">
        <StatPill label="장비" value={equipmentDataset.equipment.length} />
        <StatPill label="세트" value={equipmentSetCategoryData.sets.length} />
        <StatPill label="옵션 카테고리" value={equipmentOptionCategoryData.categories.length} />
        <StatPill label="단조 최대" value={`+${equipmentCategoryData.forgeRules.maxStage}`} />
      </div>

      <div className="catalog-toolbar equipment-toolbar" aria-label="장비 필터">
        <label>
          검색
          <input
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="장비명, 세트, 옵션 검색"
            type="search"
            value={searchTerm}
          />
        </label>
        <label>
          부위
          <select onChange={(event) => setPartFilter(event.target.value)} value={partFilter}>
            <option value="all">전체 부위</option>
            {partOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          세트
          <select onChange={(event) => setSetFilter(event.target.value)} value={setFilter}>
            <option value="all">전체 세트</option>
            {setOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          레벨
          <select onChange={(event) => setLevelFilter(event.target.value)} value={levelFilter}>
            <option value="all">전체 레벨</option>
            {levelOptions.map((level) => (
              <option key={level} value={level}>
                Lv. {level}
              </option>
            ))}
          </select>
        </label>
        <span className="catalog-count">{filteredEquipment.length}개</span>
      </div>

      <div className="equipment-layout">
        <SetEffectPanel />

        <div className="catalog-grid equipment-grid">
          {filteredEquipment.map((equipment) => (
            <EquipmentCard equipment={equipment} key={equipment.id} />
          ))}
        </div>
      </div>
    </section>
  )
}

function SetEffectPanel() {
  return (
    <aside className="set-effect-panel" aria-label="장비 세트 효과">
      <div>
        <p className="eyebrow">Set Effects</p>
        <h3>세트 효과</h3>
      </div>

      <div className="set-effect-list">
        {equipmentSetCategoryData.sets.map((equipmentSet) => (
          <article key={equipmentSet.id}>
            <div className="card-heading">
              <strong>{equipmentSet.nameKo}</strong>
              <span>{equipmentSet.levelBand}</span>
            </div>
            <p>{equipmentSet.effectKo}</p>
          </article>
        ))}
      </div>
    </aside>
  )
}

type EquipmentCardProps = {
  equipment: SeedEquipment
}

function EquipmentCard({ equipment }: EquipmentCardProps) {
  const setEffect = getSetEffect(equipment)

  return (
    <article className="catalog-card equipment-card">
      <div className="card-heading">
        <div>
          <p className="eyebrow">{getSetName(equipment)}</p>
          <h3>{equipment.names.ko}</h3>
        </div>
        <span className="rarity">{equipment.rarity}성</span>
      </div>

      <div className="tag-row">
        <span>{equipment.partLabelKo}</span>
        <span>Lv. {equipment.level}</span>
        <span>{equipment.forgeable ? '단조 가능' : '단조 없음'}</span>
        <span>{equipment.verification.status === 'verified' ? '검증 완료' : '검토 필요'}</span>
      </div>

      <div className="stat-grid">
        <StatPill label={equipment.defense.statKo} value={equipment.defense.value ?? '-'} />
        <StatPill label="세트 순서" value={equipment.setOrder ?? '-'} />
      </div>

      <dl className="compact-list">
        {equipment.options.map((option) => (
          <div key={`${equipment.id}-${option.slot}`}>
            <dt>{option.slot}옵션</dt>
            <dd>{getOptionLabel(option.categoryId)}</dd>
          </div>
        ))}
        {setEffect && (
          <div>
            <dt>세트 효과</dt>
            <dd>{setEffect}</dd>
          </div>
        )}
      </dl>
    </article>
  )
}
