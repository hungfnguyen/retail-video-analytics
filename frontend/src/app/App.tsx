import { useState } from 'react'
import { AnalyticsPage } from '../features/analytics/AnalyticsPage'
import { LivePage } from '../features/live/LivePage'
import { SystemPage } from '../features/system/SystemPage'
import type { AppPage } from '../shared/components/AppShell'

function App() {
  const [activePage, setActivePage] = useState<AppPage>('live')

  if (activePage === 'analytics') {
    return (
      <AnalyticsPage
        activePage={activePage}
        onPageChange={setActivePage}
      />
    )
  }

  if (activePage === 'system') {
    return (
      <SystemPage
        activePage={activePage}
        onPageChange={setActivePage}
      />
    )
  }

  return (
    <LivePage
      activePage={activePage}
      onPageChange={setActivePage}
    />
  )
}

export default App
