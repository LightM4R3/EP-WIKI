import { useEffect, useState } from 'react'
import { CrisisContractPage } from '../features/crisis-contract/CrisisContractPage'
import { DamageCalculatorPage } from '../features/damage-calculator/DamageCalculatorPage'
import { OperatorsPage } from '../features/operators/OperatorsPage'
import { SectionHeader } from '../shared/components/SectionHeader'
import {
  defaultNavigationId,
  isNavigationId,
  navigationItems,
  type NavigationId,
} from './navigation'

const productPillars = [
  {
    title: '정보 카탈로그',
    body: '오퍼레이터, 무기, 장비, 세트 옵션처럼 출처와 버전이 중요한 데이터를 한곳에서 정리합니다.',
  },
  {
    title: '빌드 시뮬레이션',
    body: '레벨, 정예화, 스킬, 잠재, 재능, 무기, 장비 옵션을 조합해 피해량 변화를 빠르게 비교합니다.',
  },
  {
    title: '제약 빌더',
    body: '위기 협약 제약의 점수, 선행 조건, 충돌 조건을 확인하고 선택한 조합을 모아봅니다.',
  },
]

function getPageFromHash(): NavigationId {
  if (typeof window === 'undefined') {
    return defaultNavigationId
  }

  const pageId = window.location.hash.replace('#', '')
  return isNavigationId(pageId) ? pageId : defaultNavigationId
}

export function AppShell() {
  const [activePage, setActivePage] = useState<NavigationId>(getPageFromHash)

  useEffect(() => {
    function handleHashChange() {
      setActivePage(getPageFromHash())
    }

    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  return (
    <div className="app-shell">
      <header className="site-header">
        <a
          className="brand"
          href="#overview"
          aria-label="EPWIKI 홈"
          onClick={() => setActivePage('overview')}
        >
          <span className="brand-mark">E</span>
          <span>
            <strong>EPWIKI</strong>
            <small>Endfield Data & Raid Guide</small>
          </span>
        </a>

        <nav className="site-nav" aria-label="주요 카테고리">
          {navigationItems.map((item) => (
            <a
              aria-current={activePage === item.id ? 'page' : undefined}
              href={item.href}
              key={item.id}
              onClick={() => setActivePage(item.id)}
            >
              {item.label}
            </a>
          ))}
        </nav>
      </header>

      <main>{renderActivePage(activePage)}</main>
    </div>
  )
}

function renderActivePage(activePage: NavigationId) {
  switch (activePage) {
    case 'operators':
      return <OperatorsPage />
    case 'damage-calculator':
      return <DamageCalculatorPage />
    case 'crisis-contract':
      return <CrisisContractPage />
    case 'overview':
      return <OverviewPage />
  }
}

function OverviewPage() {
  return (
    <>
      <section className="overview-section" id="overview">
        <div className="overview-copy">
          <p className="eyebrow">Single View Point prototype</p>
          <h1>명일방주: 엔드필드 정보를 모으고, 조합하고, 검증하는 작업대</h1>
          <p className="lead">
            현재 단계는 실제 데이터 적재 전의 기초 골격입니다. 데이터 출처, 타입, 계산식,
            제약 선택 흐름이 서로 분리되어 이후 업데이트와 검증이 쉬운 구조를 목표로 합니다.
          </p>
        </div>

        <div className="overview-panel" aria-label="초기 제공 영역">
          {productPillars.map((pillar, index) => (
            <article className="pillar" key={pillar.title}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <h2>{pillar.title}</h2>
              <p>{pillar.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section-block">
        <SectionHeader
          eyebrow="Phase 1"
          title="구성 방향"
          description="초기에는 정확한 데이터 모델과 검증 가능한 계산 흐름을 먼저 세우고, 화면은 그 흐름을 확인할 수 있는 밀도 있는 도구 형태로 발전시킵니다."
        />

        <div className="roadmap-grid">
          <article>
            <h3>데이터 수집</h3>
            <p>원본 출처, 패치 버전, 지역 서버, 검증 상태를 함께 저장할 수 있게 스키마를 관리합니다.</p>
          </article>
          <article>
            <h3>계산 엔진</h3>
            <p>전투 공식은 UI와 분리된 순수 함수로 작성해 테스트와 공식 교체가 쉽도록 둡니다.</p>
          </article>
          <article>
            <h3>빌드 공유</h3>
            <p>선택한 세팅을 URL, JSON, 프리셋으로 저장할 수 있게 상태 구조를 단순하게 유지합니다.</p>
          </article>
          <article>
            <h3>제약 관계</h3>
            <p>위기 협약 제약은 선행 조건과 충돌 조건을 데이터로 표현해 UI가 자동으로 안내하게 만듭니다.</p>
          </article>
        </div>
      </section>
    </>
  )
}
