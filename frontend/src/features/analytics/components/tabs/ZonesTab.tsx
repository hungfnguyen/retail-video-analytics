import { MapPin } from 'lucide-react'
import { EmptyState } from '../../../../shared/components/ui/EmptyState'

export function ZonesTab() {
  return (
    <div className="pt-5">
      <EmptyState
        title="Zone-level metrics are not available yet"
        description="Run Gold zone aggregation (gold_serving_zone_daily) to enable zone utilization and dwell breakdowns."
        icon={MapPin}
        tone="neutral"
      />
    </div>
  )
}
