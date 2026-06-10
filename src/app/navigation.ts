export const navigationItems = [
  { id: 'overview', href: '#overview', label: '개요' },
  { id: 'operators', href: '#operators', label: '오퍼레이터' },
  { id: 'damage-calculator', href: '#damage-calculator', label: '피해량 계산' },
  { id: 'crisis-contract', href: '#crisis-contract', label: '위기 협약' },
] as const

export type NavigationId = (typeof navigationItems)[number]['id']

export const defaultNavigationId: NavigationId = 'overview'

export function isNavigationId(value: string): value is NavigationId {
  return navigationItems.some((item) => item.id === value)
}
