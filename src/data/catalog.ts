import type {
  AttributeKey,
  CrisisRisk,
  DamageType,
  EquipmentSet,
  Operator,
  OperatorClass,
  Weapon,
  WeaponType,
} from '../domain/types'
import operatorCategoryData from './game/operator-categories.json'
import operatorDataset from './game/operators.seed.json'
import weaponCategoryData from './game/weapon-categories.json'
import weaponDataset from './game/weapons.seed.json'
import weaponOptionCategoryData from './game/weapon/option-categories.json'

type SeedOperator = (typeof operatorDataset.operators)[number]
type SeedWeapon = (typeof weaponDataset.weapons)[number]
type SeedWeaponOptionCategory = (typeof weaponOptionCategoryData.categories)[number]
type CategoryOption = {
  id: string
  labelKo: string
}

const weaponOptionCategoryMap = new Map<string, SeedWeaponOptionCategory>(
  weaponOptionCategoryData.categories.map((category) => [category.id, category]),
)

function getDisplayName(operator: SeedOperator) {
  return operator.names.ko ?? operator.names.en
}

function getCategoryLabel(options: CategoryOption[], id: string) {
  return options.find((option) => option.id === id)?.labelKo ?? id
}

function getRarityLabel(rarity: number) {
  return operatorCategoryData.rarities.find((option) => option.stars === rarity)?.labelKo ?? `${rarity}★`
}

function getWeaponRarityLabel(rarity: number) {
  return weaponCategoryData.rarities.find((option) => option.stars === rarity)?.labelKo ?? `${rarity}★`
}

function getLocalizedEffectName(effect: { name: string; nameKo?: string }) {
  return effect.nameKo ?? effect.name
}

function getLatestStats(operator: SeedOperator) {
  return operator.combat.stats.at(-1) ?? {
    hp: 0,
    attack: 0,
    defense: 0,
    strength: 0,
    agility: 0,
    intellect: 0,
    will: 0,
    critRate: 0,
  }
}

function getWeaponDisplayName(weapon: SeedWeapon) {
  return weapon.names.ko ?? weapon.id
}

function getWeaponTraitSummary(weapon: SeedWeapon) {
  return weapon.traits
    .map((trait) => {
      const category = weaponOptionCategoryMap.get(trait.categoryId)

      if (!category) {
        return `미확인 옵션: ${trait.categoryId}`
      }

      return `${category.nameKo}: ${category.statKo} ${category.range.min}~${category.range.max.replace(/^\+/, '')}`
    })
    .join(' / ')
}

export const operators: Operator[] = operatorDataset.operators.map((operator) => {
  const latestStats = getLatestStats(operator)
  const role = operator.profile.class as OperatorClass
  const damageType = operator.profile.element as DamageType
  const weaponType = operator.profile.weaponType as WeaponType
  const mainAttribute = operator.combat.mainAttribute as AttributeKey
  const secondaryAttribute = operator.combat.secondaryAttribute as AttributeKey

  return {
    id: operator.id,
    name: getDisplayName(operator),
    faction: operator.profile.faction ?? 'Unknown',
    rarity: operator.rarity,
    rarityLabel: getRarityLabel(operator.rarity),
    role,
    roleLabel: getCategoryLabel(operatorCategoryData.classes, role),
    damageType,
    damageTypeLabel: getCategoryLabel(operatorCategoryData.elements, damageType),
    weaponType,
    weaponTypeLabel: getCategoryLabel(operatorCategoryData.weapons, weaponType),
    mainAttribute,
    mainAttributeLabel: getCategoryLabel(operatorCategoryData.stats, mainAttribute),
    secondaryAttribute,
    secondaryAttributeLabel: getCategoryLabel(operatorCategoryData.stats, secondaryAttribute),
    baseStats: {
      hp: latestStats.hp,
      attack: latestStats.attack,
      defense: latestStats.defense,
      strength: latestStats.strength,
      agility: latestStats.agility,
      intellect: latestStats.intellect,
      will: latestStats.will,
      critRate: latestStats.critRate,
    },
    talents: operator.combat.talents.map(getLocalizedEffectName),
    skills: operator.combat.skills.map(getLocalizedEffectName),
    sourceStatus: operator.verification.status as Operator['sourceStatus'],
  }
})

export const weapons: Weapon[] = weaponDataset.weapons.map((weapon) => {
  const weaponType = weapon.type as WeaponType

  return {
    id: weapon.id,
    name: getWeaponDisplayName(weapon),
    rarity: weapon.rarity,
    rarityLabel: getWeaponRarityLabel(weapon.rarity),
    weaponType,
    weaponTypeLabel: getCategoryLabel(weaponCategoryData.types, weaponType),
    acquisitionLabel: weapon.acquisition.labelKo,
    attack: weapon.stats.baseAttack,
    trait: getWeaponTraitSummary(weapon),
    sourceStatus: weapon.verification.status as Weapon['sourceStatus'],
  }
})

export const equipmentSets: EquipmentSet[] = [
  {
    id: 'hot-work-preview',
    name: 'Hot Work',
    pieces: 3,
    flatAttack: 42,
    attackPercent: 8,
    effect: 'Heat 빌드 추천 세트 기반 임시 계산 옵션',
  },
  {
    id: 'bone-crusher-preview',
    name: '본 크러셔',
    pieces: 3,
    flatAttack: 24,
    attackPercent: 14,
    effect: '스킬 사용 후 능력치 증가형 세트 컨셉',
  },
  {
    id: 'energy-guide-preview',
    name: '에너지 유도',
    pieces: 3,
    flatAttack: 18,
    attackPercent: 6,
    effect: '궁극기 에너지/보조 능력치 계열 임시 계산 옵션',
  },
]

export const crisisRisks: CrisisRisk[] = [
  {
    id: 'enemy-assault-1',
    title: '적 공격력 상승 I',
    category: '적 강화',
    score: 1,
    description: '모든 적의 공격력이 증가합니다.',
    prerequisites: [],
    conflictsWith: [],
  },
  {
    id: 'enemy-assault-2',
    title: '적 공격력 상승 II',
    category: '적 강화',
    score: 2,
    description: '모든 적의 공격력이 크게 증가합니다.',
    prerequisites: ['enemy-assault-1'],
    conflictsWith: [],
  },
  {
    id: 'squad-limit',
    title: '편성 인원 제한',
    category: '편성 제한',
    score: 2,
    description: '전투에 투입 가능한 오퍼레이터 수가 감소합니다.',
    prerequisites: [],
    conflictsWith: [],
  },
  {
    id: 'low-supply',
    title: '보급 제약',
    category: '환경',
    score: 1,
    description: '전투 중 회복 또는 자원 획득 효율이 감소합니다.',
    prerequisites: [],
    conflictsWith: ['high-mobility'],
  },
  {
    id: 'high-mobility',
    title: '기동전 환경',
    category: '환경',
    score: 1,
    description: '이동과 재배치 관련 압박이 증가합니다.',
    prerequisites: [],
    conflictsWith: ['low-supply'],
  },
]
