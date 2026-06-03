import { useState } from 'react'
import { CalendarDays, Database, RefreshCw } from 'lucide-react'
import { AppShell, type AppPage } from '../../shared/components/AppShell'
import { AnalyticsPanels } from './components/AnalyticsPanels'
import { useAnalyticsData } from './hooks/useAnalyticsData'

type AnalyticsPageProps = {
  activePage: AppPage
  onPageChange: (page: AppPage) => void
}

const dayOptions = [1, 7, 14, 30]

function StatusPanel({ title, detail }: { title: string; detail: string }) {
  return (
    <section className="grid min-h-[520px] place-items-center rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center shadow-[0_14px_36px_rgba(15,23,42,0.05)]">
      <div className="max-w-xl">
        <span className="mx-auto grid h-14 w-14 place-items-center rounded-lg bg-slate-100 text-slate-600">
          <Database size={26} />
        </span>
        <h2 className="mb-2 mt-5 text-xl font-bold text-slate-950">{title}</h2>
        <p className="m-0 text-sm font-medium leading-6 text-slate-500">{detail}</p>
      </div>
    </section>
  )
}

export function AnalyticsPage({ activePage, onPageChange }: AnalyticsPageProps) {
  const [days, setDays] = useState(7)
  const { data, error, refresh } = useAnalyticsData(days)

  const statusTitle = error
    ? 'Analytics API is unavailable'
    : data?.data_status === 'error'
      ? 'Trino analytics query failed'
      : 'No lakehouse analytics rows'

  const statusDetail = error
    ? error
    : data?.error_message ?? 'Run the pipeline until Silver and Gold tables receive rows, then refresh this page.'

  return (
    <AppShell activePage={activePage} onPageChange={onPageChange}>
      <header className="mb-4 flex items-center justify-between gap-4">
        <div>
          <h1 className="m-0 text-[26px] font-bold leading-tight text-slate-950">Traffic Analytics</h1>
          <p className="m-0 mt-1 text-sm font-semibold text-slate-500">Silver detections and Gold track summaries from the lakehouse</p>
        </div>

        <div className="flex items-center gap-2.5">
          <div className="flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
            {dayOptions.map((option) => (
              <button
                className={`rounded-md px-3 py-2 text-sm font-bold transition ${
                  days === option ? 'bg-slate-950 text-white' : 'text-slate-600 hover:bg-slate-100'
                }`}
                key={option}
                onClick={() => setDays(option)}
                type="button"
              >
                {option}d
              </button>
            ))}
          </div>

          <span className="flex min-w-40 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-bold text-slate-700 shadow-sm">
            <CalendarDays size={17} />
            {data?.range_label ?? `Last ${days} days`}
          </span>

          <button
            className="grid h-10 w-10 place-items-center rounded-lg border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-blue-300 hover:text-blue-700"
            onClick={() => void refresh()}
            title="Refresh analytics"
            type="button"
          >
            <RefreshCw size={17} />
          </button>
        </div>
      </header>

      {!data && !error ? (
        <StatusPanel detail="Loading Trino-backed dashboard data." title="Loading analytics" />
      ) : data?.data_status === 'ready' ? (
        <AnalyticsPanels data={data} />
      ) : (
        <StatusPanel detail={statusDetail} title={statusTitle} />
      )}
    </AppShell>
  )
}
