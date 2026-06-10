import { useState } from 'react'
import { equipmentSets, operators, weapons } from '../../data/catalog'
import type { DamageBuild } from '../../domain/types'
import { SectionHeader } from '../../shared/components/SectionHeader'
import { StatPill } from '../../shared/components/StatPill'
import { calculateDamagePreview } from './damageModel'

const initialWeapon = weapons.find((weapon) => weapon.weaponType === operators[0].weaponType) ?? weapons[0]

export function DamageCalculatorPage() {
  const [operatorId, setOperatorId] = useState(operators[0].id)
  const [weaponId, setWeaponId] = useState(initialWeapon.id)
  const [equipmentSetId, setEquipmentSetId] = useState(equipmentSets[0].id)
  const [level, setLevel] = useState(60)
  const [promotion, setPromotion] = useState(1)
  const [skillLevel, setSkillLevel] = useState(7)
  const [potentialRank, setPotentialRank] = useState(1)
  const [talentEnabled, setTalentEnabled] = useState(true)
  const [weaponLevel, setWeaponLevel] = useState(40)
  const [weaponTraitEnabled, setWeaponTraitEnabled] = useState(true)
  const [forgedAttackPercent, setForgedAttackPercent] = useState(10)
  const [enemyDefense, setEnemyDefense] = useState(260)
  const [enemyDamageReduction, setEnemyDamageReduction] = useState(0)

  const selectedOperator = operators.find((operator) => operator.id === operatorId) ?? operators[0]
  const matchingWeapons = weapons.filter((weapon) => weapon.weaponType === selectedOperator.weaponType)
  const selectableWeapons = matchingWeapons.length > 0 ? matchingWeapons : weapons
  const selectedWeapon = selectableWeapons.find((weapon) => weapon.id === weaponId) ?? selectableWeapons[0]
  const selectedEquipmentSet =
    equipmentSets.find((equipmentSet) => equipmentSet.id === equipmentSetId) ?? equipmentSets[0]

  const build: DamageBuild = {
    operator: selectedOperator,
    weapon: selectedWeapon,
    equipmentSet: selectedEquipmentSet,
    level,
    promotion,
    skillLevel,
    potentialRank,
    talentEnabled,
    weaponLevel,
    weaponTraitEnabled,
    forgedAttackPercent,
    enemyDefense,
    enemyDamageReduction,
  }

  const result = calculateDamagePreview(build)

  return (
    <section className="section-block" id="damage-calculator">
      <SectionHeader
        eyebrow="Simulator"
        title="피해량 계산기 골격"
        description="현재 공식은 UI와 데이터 흐름 확인용 임시 모델입니다. 실제 전투 공식이 확정되면 damageModel만 교체하고 화면은 그대로 유지할 수 있게 분리했습니다."
      />

      <div className="calculator-layout">
        <form className="control-panel" aria-label="피해량 계산 옵션">
          <label>
            오퍼레이터
            <select value={operatorId} onChange={(event) => setOperatorId(event.target.value)}>
              {operators.map((operator) => (
                <option key={operator.id} value={operator.id}>
                  {operator.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            무기
            <select value={selectedWeapon.id} onChange={(event) => setWeaponId(event.target.value)}>
              {selectableWeapons.map((weapon) => (
                <option key={weapon.id} value={weapon.id}>
                  {weapon.name} ({weapon.rarityLabel}, {weapon.weaponTypeLabel})
                </option>
              ))}
            </select>
          </label>

          <label>
            장비 세트
            <select value={equipmentSetId} onChange={(event) => setEquipmentSetId(event.target.value)}>
              {equipmentSets.map((equipmentSet) => (
                <option key={equipmentSet.id} value={equipmentSet.id}>
                  {equipmentSet.name}
                </option>
              ))}
            </select>
          </label>

          <RangeControl label="레벨" min={1} max={90} value={level} onChange={setLevel} />
          <RangeControl label="정예화" min={0} max={2} value={promotion} onChange={setPromotion} />
          <RangeControl label="스킬 레벨" min={1} max={10} value={skillLevel} onChange={setSkillLevel} />
          <RangeControl label="잠재 능력 등급" min={0} max={5} value={potentialRank} onChange={setPotentialRank} />
          <RangeControl label="무기 레벨" min={1} max={90} value={weaponLevel} onChange={setWeaponLevel} />
          <RangeControl
            label="장비 단조 공격력"
            min={0}
            max={40}
            value={forgedAttackPercent}
            suffix="%"
            onChange={setForgedAttackPercent}
          />
          <RangeControl label="적 방어력" min={0} max={1200} value={enemyDefense} onChange={setEnemyDefense} />
          <RangeControl
            label="적 피해 감소"
            min={0}
            max={80}
            value={enemyDamageReduction}
            suffix="%"
            onChange={setEnemyDamageReduction}
          />

          <div className="toggle-row">
            <label>
              <input
                checked={talentEnabled}
                onChange={(event) => setTalentEnabled(event.target.checked)}
                type="checkbox"
              />
              재능 적용
            </label>
            <label>
              <input
                checked={weaponTraitEnabled}
                onChange={(event) => setWeaponTraitEnabled(event.target.checked)}
                type="checkbox"
              />
              무기 기질 적용
            </label>
          </div>
        </form>

        <aside className="result-panel" aria-label="피해량 계산 결과">
          <p className="eyebrow">Result</p>
          <h3>{selectedOperator.name} 빌드 미리보기</h3>
          <div className="result-number">{result.expectedHit.toLocaleString()}</div>
          <p>예상 1회 피해량</p>

          <div className="stat-grid">
            <StatPill label="최종 공격력" value={result.finalAttack.toLocaleString()} />
            <StatPill label="6타 폭딜" value={result.burstWindow.toLocaleString()} />
            <StatPill label="방어 보정" value={result.mitigation.toLocaleString()} />
            <StatPill label="공식" value={result.formulaVersion} />
          </div>

          <dl className="compact-list">
            <div>
              <dt>무기 기질</dt>
              <dd>{selectedWeapon.trait}</dd>
            </div>
            <div>
              <dt>무기 출처 상태</dt>
              <dd>
                {selectedWeapon.acquisitionLabel} · {selectedWeapon.sourceStatus}
              </dd>
            </div>
            <div>
              <dt>세트 옵션</dt>
              <dd>{selectedEquipmentSet.effect}</dd>
            </div>
          </dl>
        </aside>
      </div>
    </section>
  )
}

type RangeControlProps = {
  label: string
  min: number
  max: number
  value: number
  suffix?: string
  onChange: (value: number) => void
}

function RangeControl({ label, min, max, value, suffix = '', onChange }: RangeControlProps) {
  return (
    <label>
      <span className="range-label">
        {label}
        <strong>
          {value}
          {suffix}
        </strong>
      </span>
      <input
        max={max}
        min={min}
        onChange={(event) => onChange(Number(event.target.value))}
        type="range"
        value={value}
      />
    </label>
  )
}
