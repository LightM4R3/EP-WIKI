import type { DamageBuild, DamageResult } from '../../domain/types'

const FORMULA_VERSION = 'scaffold-v0'

export function calculateDamagePreview(build: DamageBuild): DamageResult {
  const levelMultiplier = 1 + (build.level - 1) * 0.006
  const promotionMultiplier = 1 + build.promotion * 0.08
  const skillMultiplier = 1 + build.skillLevel * 0.035
  const potentialMultiplier = 1 + build.potentialRank * 0.015
  const talentMultiplier = build.talentEnabled ? 1.08 : 1
  const weaponLevelBonus = build.weaponLevel * 1.8
  const weaponTraitMultiplier = build.weaponTraitEnabled ? 1.06 : 1
  const equipmentMultiplier = 1 + build.equipmentSet.attackPercent / 100
  const forgedMultiplier = 1 + build.forgedAttackPercent / 100

  const rawAttack =
    (build.operator.baseStats.attack + build.weapon.attack + build.equipmentSet.flatAttack + weaponLevelBonus) *
    levelMultiplier *
    promotionMultiplier *
    potentialMultiplier *
    equipmentMultiplier *
    forgedMultiplier

  const finalAttack = rawAttack * talentMultiplier * weaponTraitMultiplier
  const mitigatedDefense = Math.max(0, build.enemyDefense * (1 - build.enemyDamageReduction / 100))
  const expectedHit = Math.max(finalAttack * skillMultiplier - mitigatedDefense, finalAttack * 0.05)

  return {
    expectedHit: Math.round(expectedHit),
    burstWindow: Math.round(expectedHit * 6),
    finalAttack: Math.round(finalAttack),
    mitigation: Math.round(mitigatedDefense),
    formulaVersion: FORMULA_VERSION,
  }
}
