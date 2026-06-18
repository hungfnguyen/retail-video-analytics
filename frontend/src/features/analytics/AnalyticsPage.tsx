import { useState } from 'react'
import { AppShell, type AppPage } from '../../shared/components/AppShell'
import { EmptyState } from '../../shared/components/ui/EmptyState'
import { PageHeader } from '../../shared/components/ui/PageHeader'
import { Tabs } from '../../shared/components/ui/Tabs'
import { AnalyticsFilterBar, datePresetToDays, type DatePreset } from './components/AnalyticsFilterBar'
import { AlertsTab } from './components/tabs/AlertsTab'
import { DwellTab } from './components/tabs/DwellTab'
import { OverviewTab } from './components/tabs/OverviewTab'
import { QueueTab } from './components/tabs/QueueTab'
import { TrafficTab } from './components/tabs/TrafficTab'
import { ZonesTab } from './components/tabs/ZonesTab'
import { useAlertHistoryData } from './hooks/useAlertHistoryData'
import { useAnalyticsData } from './hooks/useAnalyticsData'
import { useQueueData } from './hooks/useQueueData'

type AnalyticsPageProps = {
  activePage: AppPage
  onPageChange: (page: AppPage) => void
}

type AnalyticsTab = 'overview' | 'traffic' | 'queue' | 'zones' | 'alerts' | 'dwell'

const TAB_ITEMS = [
  { id: 'overview' as const, label: 'Overview' },
  { id: 'traffic' as const, label: 'Traffic' },
  { id: 'queue' as const, label: 'Queue' },
  { id: 'zones' as const, label: 'Zones' },
  { id: 'alerts' as const, label: 'Alerts' },
  { id: 'dwell' as const, label: 'Dwell Time' },
]

export function AnalyticsPage({ activePage, onPageChange }: AnalyticsPageProps) {
  const [preset, setPreset] = useState<DatePreset>('last_7_days')
  const [activeTab, setActiveTab] = useState<AnalyticsTab>('overview')

  const days = datePresetToDays[preset]
  const { data, error, refresh } = useAnalyticsData(days)
  const { data: queueData, refresh: refreshQueue } = useQueueData(days)
  const { data: alertHistoryData, refresh: refreshAlerts } = useAlertHistoryData(days)

  function refreshAll() {
    void refresh()
    void refreshQueue()
    void refreshAlerts()
  }

  function renderContent() {
    if (!data && !error) {
      return <EmptyState title="Loading analytics…" description="Querying Gold serving metrics" />
    }
    if (error || data?.data_status === 'error') {
      return (
        <EmptyState
          title={error ? 'Analytics API unavailable' : 'Analytics query failed'}
          description={error ?? data?.error_message ?? undefined}
          tone="error"
        />
      )
    }
    if (data?.data_status === 'empty') {
      return (
        <EmptyState
          title="No Gold analytics rows yet"
          description="Run the pipeline and Gold serving refresh first, then reload this page."
          tone="warning"
        />
      )
    }
    if (!data) return null

    switch (activeTab) {
      case 'overview':
        return <OverviewTab alertData={alertHistoryData ?? null} data={data} queueData={queueData ?? null} />
      case 'traffic':
        return <TrafficTab data={data} />
      case 'queue':
        return queueData
          ? <QueueTab data={queueData} />
          : <EmptyState title="Queue analytics unavailable" description="Queue serving tables are empty or still refreshing." />
      case 'zones':
        return <ZonesTab data={data} />
      case 'alerts':
        return alertHistoryData
          ? <AlertsTab data={alertHistoryData} />
          : <EmptyState title="Alert analytics unavailable" description="Alert history is empty or still refreshing." />
      case 'dwell':
        return <DwellTab data={data} />
    }
  }

  return (
    <AppShell activePage={activePage} onPageChange={onPageChange}>
      <PageHeader
        title="Analytics"
        subtitle="Business insights from Gold layer"
        actions={
          <AnalyticsFilterBar
            preset={preset}
            onPresetChange={setPreset}
            onRefresh={refreshAll}
          />
        }
      />

      <Tabs<AnalyticsTab> items={TAB_ITEMS} onChange={setActiveTab} value={activeTab} />

      <div className="pt-5">
        {renderContent()}
      </div>
    </AppShell>
  )
}
