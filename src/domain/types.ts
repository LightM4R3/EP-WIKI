export type OperatorClass = 'Guard' | 'Defender' | 'Striker' | 'Supporter' | 'Caster' | 'Vanguard'

export type DamageType = 'Physical' | 'Heat' | 'Electric' | 'Cryo' | 'Nature'

export type WeaponType = 'Sword' | 'Greatsword' | 'Polearm' | 'Handcannon' | 'Arts Unit' | 'Unknown'

export type AttributeKey = 'strength' | 'agility' | 'intellect' | 'will' | 'unknown'

export type StatBlock = {
  hp: number
  attack: number
  defense: number
  strength: number
  agility: number
  intellect: number
  will: number
  critRate: number
}

export type Operator = {
  id: string
  name: string
  faction: string
  rarity: number
  rarityLabel: string
  role: OperatorClass
  roleLabel: string
  damageType: DamageType
  damageTypeLabel: string
  weaponType: WeaponType
  weaponTypeLabel: string
  mainAttribute: AttributeKey
  mainAttributeLabel: string
  secondaryAttribute: AttributeKey
  secondaryAttributeLabel: string
  baseStats: StatBlock
  talents: string[]
  skills: string[]
  sourceStatus: 'placeholder' | 'needs_review' | 'verified'
}

export type Weapon = {
  id: string
  name: string
  rarity: number
  rarityLabel: string
  weaponType: WeaponType
  weaponTypeLabel: string
  acquisitionLabel: string
  attack: number
  trait: string
  sourceStatus: 'placeholder' | 'needs_review' | 'verified'
}

export type EquipmentSet = {
  id: string
  name: string
  pieces: 2 | 3 | 4
  flatAttack: number
  attackPercent: number
  effect: string
}

export type DamageBuild = {
  operator: Operator
  weapon: Weapon
  equipmentSet: EquipmentSet
  level: number
  promotion: number
  skillLevel: number
  potentialRank: number
  talentEnabled: boolean
  weaponLevel: number
  weaponTraitEnabled: boolean
  forgedAttackPercent: number
  enemyDefense: number
  enemyDamageReduction: number
}

export type DamageResult = {
  expectedHit: number
  burstWindow: number
  finalAttack: number
  mitigation: number
  formulaVersion: string
}

export type CrisisRisk = {
  id: string
  title: string
  category: '적 강화' | '아군 약화' | '환경' | '편성 제한'
  score: number
  description: string
  prerequisites: string[]
  conflictsWith: string[]
}
