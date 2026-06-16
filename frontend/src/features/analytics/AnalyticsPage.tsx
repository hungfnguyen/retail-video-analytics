import { useState } from 'react'
import { AppShell, type AppPage } from '../../shared/components/AppShell'
import { PageHeader } from '../../shared/components/ui/PageHeader'
import { Tabs } from '../../shared/components/ui/Tabs'
import { EmptyState } from '../../shared/components/ui/EmptyState'
import { AnalyticsFilterBar, datePresetToDays } from './components/AnalyticsFilterBar'
import { AlertsTab } from './components/tabs/AlertsTab'
import { OverviewTab } from './components/tabs/OverviewTab'
import { QueueTab } from './components/tabs/QueueTab'
import { TrafficTab } from './components/tabs/TrafficTab'
import { ZonesTab } from './components/tabs/ZonesTab'
import { useAlertHistoryData } from './hooks/useAlertHistoryData'
import { useAnalyticsData } from './hooks/useAnalyticsData'
import { useQueueData } from './hooks/useQueueData'
import type { DatePreset } from './components/AnalyticsFilterBar'

type AnalyticsPageProps = {
  activePage: AppPage
  onPageChange: (page: AppPage) => void
}

type AnalyticsTab = 'overview' | 'traffic' | 'queue' | 'zones' | 'alerts'

const TAB_ITEMS = [
  { id: 'overview' as const, label: 'Overview' },
  { id: 'traffic' as const, label: 'Traffic' },
  { id: 'queue' as const, label: 'Queue' },
  { id: 'zones' as const, label: 'Zones' },
  { id: 'alerts' as const, label: 'Alerts' },
]

export function AnalyticsPage({ activePage, onPageChange }: AnalyticsPageProps) {
  const [preset, setPreset] = useState<DatePreset>('last_7_days')
  const [activeTab, setActiveTab] = useState<AnalyticsTab>('overview')

  const days = datePresetToDays[preset]
  const { data, error, refresh } = useAnalyticsData(days)
  const { data: queueData } = useQueueData(days)
  const { data: alertHistoryData } = useAlertHistoryData(days)

  function renderTabContent() {
    if (!data && !error) {
      return <EmptyState title="Loading analytics data…" description="Querying Gold lakehouse via Trino" />
    }
    if (error || data?.data_status === 'error') {
      return (
        <EmptyState
          title={error ? 'Analytics API unavailable' : 'Trino query failed'}
          description={error ?? data?.error_message ?? undefined}
          tone="error"
        />
      )
    }
    if (data?.data_status === 'empty') {
      return (
        <EmptyState
          title="No data in lakehouse yet"
          description="Run the pipeline until Gold tables receive rows, then refresh."
          tone="warning"
        />
      )
    }
    if (!data) return null

    switch (activeTab) {
      case 'overview':
        return <OverviewTab data={data} queueData={queueData ?? null} alertData={alertHistoryData ?? null} />
      case 'traffic':
        return <TrafficTab data={data} />
      case 'queue':
        return queueData
          ? <QueueTab data={queueData} />
          : <EmptyState title="No queue data" description="Gold queue tables are empty or still loading" />
      case 'zones':
        return <ZonesTab />
      case 'alerts':
        return alertHistoryData
          ? <AlertsTab data={alertHistoryData} />
          : <EmptyState title="No alert data" description="Gold alerts table is empty or still loading" />
    }
  }

  return (
    <AppShell activePage={activePage} onPageChange={onPageChange}>
      <PageHeader
        title="Analyst Dashboard"
        subtitle="Business insights from Gold lakehouse metrics"
        actions={
          <AnalyticsFilterBar
            preset={preset}
            onPresetChange={setPreset}
            onRefresh={() => void refresh()}
          />
        }
      />

      <Tabs<AnalyticsTab>
        value={activeTab}
        onChange={setActiveTab}
        items={TAB_ITEMS}
      />

      {renderTabContent()}
    </AppShell>
  )
}
