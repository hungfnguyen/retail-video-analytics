# UI Foundation and Shared Components

This document defines the design system and reusable components for the RVA UI refactor.

---

## 1. Design direction

Style: modern SaaS dashboard, clean, high signal, operational but not noisy.

Visual language:

- Dark left sidebar.
- Light content surface.
- White cards with subtle borders.
- Blue as primary action/state.
- Green for healthy/good.
- Amber for warning/medium.
- Red for critical/high.
- Slate/gray for neutral/supporting text.

The UI should feel like an operations console for retail managers, not a research notebook.

---

## 2. Layout constants

Recommended values:

```text
Sidebar width: 248px
Main padding: 24px
Card radius: rounded-xl or rounded-lg consistently
Card border: border-slate-200
Card background: bg-white
Page background: bg-slate-50
Grid gap: 16px to 20px
KPI card min height: 112px
```

Current code uses `p-5.5`, which is unusual. Prefer standard Tailwind spacing such as `p-6`, `gap-4`, `gap-5`.

---

## 3. Typography

Recommended text hierarchy:

```text
Page title: text-2xl or text-[26px], font-bold, text-slate-950
Page subtitle: text-sm, font-medium, text-slate-500
Section title: text-base or text-[17px], font-bold, text-slate-950
KPI label: text-sm, font-semibold, text-slate-500
KPI value: text-2xl to text-3xl, font-bold
KPI meta: text-xs, font-medium, text-slate-500
Table header: text-xs uppercase tracking-wide text-slate-500
```

Avoid oversized numbers unless they are truly primary operational metrics.

---

## 4. Shared component specs

### 4.1 PageHeader

Path:

```text
shared/components/ui/PageHeader.tsx
```

Purpose:

- Standardize page title, subtitle, right-side controls.

Props:

```ts
type PageHeaderProps = {
  title: string
  subtitle?: string
  badge?: React.ReactNode
  actions?: React.ReactNode
}
```

Usage:

```tsx
<PageHeader
  title="Analyst Dashboard"
  subtitle="Business insights from the Gold lakehouse layer"
  actions={<AnalyticsFilterBar ... />}
/>
```

---

### 4.2 FilterBar

Path:

```text
shared/components/ui/FilterBar.tsx
```

Purpose:

- One consistent component for store/camera/zone/date range/refresh controls.
- Avoid duplicated filter UI between Analytics and Heatmap.

Recommended structure:

```text
[Store dropdown] [Camera dropdown] [Zone dropdown] [Date range dropdown] [Refresh]
```

Props:

```ts
type DateRangePreset = 'today' | 'yesterday' | 'last_7_days' | 'last_14_days' | 'last_30_days' | 'custom'

type DashboardFilters = {
  storeId: string
  cameraId: string
  zoneId: string
  dateRange: DateRangePreset
  compareToPrevious?: boolean
}

type FilterBarProps = {
  filters: DashboardFilters
  onChange: (next: DashboardFilters) => void
  stores?: Array<{ id: string; label: string }>
  cameras?: Array<{ id: string; label: string }>
  zones?: Array<{ id: string; label: string }>
  onRefresh?: () => void
  isRefreshing?: boolean
  disabledFields?: Array<'store' | 'camera' | 'zone' | 'dateRange'>
}
```

Important implementation note:

The current backend mainly accepts `days`, and heatmap accepts `camera_id` + `days`. For Phase 1, keep extra filters UI either hidden or soft-disabled if the backend cannot apply them yet. Do not fake filtered numbers without clear data support.

---

### 4.3 MetricCard

Path:

```text
shared/components/ui/MetricCard.tsx
```

Purpose:

- Standard KPI card used across Live, Analyst, Heatmap.

Props:

```ts
type MetricTone = 'blue' | 'green' | 'amber' | 'red' | 'violet' | 'slate'

type MetricCardProps = {
  label: string
  value: string | number
  unit?: string
  meta?: string
  delta?: {
    value: string
    direction: 'up' | 'down' | 'flat'
    intent: 'good' | 'bad' | 'neutral'
  }
  icon?: React.ComponentType<{ size?: number; className?: string }>
  tone?: MetricTone
}
```

Guidelines:

- Do not show `Avg confidence` as top-level business KPI.
- Use deltas when possible: `+12% vs previous period`, `-32s vs yesterday`.
- Use red/amber only for action-required metrics.

---

### 4.4 SectionCard

Path:

```text
shared/components/ui/SectionCard.tsx
```

Purpose:

- Standard wrapper for charts, tables, lists.

Props:

```ts
type SectionCardProps = {
  title: string
  subtitle?: string
  badge?: React.ReactNode
  actions?: React.ReactNode
  children: React.ReactNode
  className?: string
}
```

---

### 4.5 StatusBadge

Path:

```text
shared/components/ui/StatusBadge.tsx
```

Purpose:

- Consistent severity/status badges.

Statuses:

```text
low -> green
medium -> amber
high -> red
ok -> green
warning -> amber
critical/down -> red
neutral -> slate
live -> green dot + LIVE
```

---

### 4.6 EmptyState

Path:

```text
shared/components/ui/EmptyState.tsx
```

Use for:

- No lakehouse rows.
- No alerts.
- No heatmap cells.
- API not ready.

Props:

```ts
type EmptyStateProps = {
  title: string
  description?: string
  action?: React.ReactNode
  tone?: 'neutral' | 'warning' | 'error'
}
```

---

### 4.7 Tabs

Path:

```text
shared/components/ui/Tabs.tsx
```

Use for Analyst Dashboard internal tabs:

```text
Overview | Traffic | Queue | Zones | Alerts
```

Props:

```ts
type TabItem<T extends string> = {
  id: T
  label: string
  badge?: string | number
}

type TabsProps<T extends string> = {
  value: T
  onChange: (value: T) => void
  items: Array<TabItem<T>>
}
```

---

## 5. Chart guidelines

Charts must answer a business question. Each chart must have:

- Clear title.
- Clear time range.
- Clear y-axis unit.
- Tooltip formatting.
- Empty state.

Recommended chart components:

```text
shared/components/ui/ChartContainer.tsx
features/analytics/components/charts/VisitorsTrendChart.tsx
features/analytics/components/charts/PeakHourHeatmapChart.tsx
features/analytics/components/charts/QueueWaitTrendChart.tsx
features/analytics/components/charts/TopZonesChart.tsx
features/analytics/components/charts/AlertBreakdownChart.tsx
features/live/components/LiveTrafficSparkline.tsx
```

Avoid chart types that look impressive but do not answer a question.

Use:

- Line chart for trends.
- Bar chart for comparisons.
- Horizontal bar for ranking.
- Heatmap grid for hour/day patterns.
- Small sparkline only as secondary context.

Do not overuse pie charts.

---

## 6. Utility formatters

Path:

```text
shared/utils/format.ts
```

Move duplicated formatters into one place:

```ts
export function formatNumber(value: number): string
export function formatPercent(value: number, digits = 1): string
export function formatDuration(seconds: number): string
export function formatDurationMs(ms: number): string
export function formatRelativeTime(iso: string): string
export function formatTimestamp(iso: string): string
export function formatDateRangeLabel(days: number): string
```

Current code repeats duration, percent, timestamp, and relative time formatting across pages. Consolidating this reduces inconsistencies.

---

## 7. Data safety rules

All UI components must handle:

- `null` data.
- Empty arrays.
- `data_status` equal to `empty`.
- `data_status` equal to `error`.
- Missing optional fields.
- Slow backend queries.

Do not let charts render broken axes because data length is 0.

---

## 8. Responsive behavior

The current body has min width 1180px. Keep this for now.

For large screens:

- Use 12-column or CSS grid layout.
- Prefer `grid-cols-[...]` for precise dashboard layout.
- Keep main content readable; do not stretch tables too much.

For narrower screens above 1180px:

- KPI row can wrap from 5 columns to 3 columns.
- Live camera and alert panel can stack if needed.

---

## 9. Recommended shared visual tokens

Use Tailwind class objects in components rather than repeating strings everywhere.

Example:

```ts
export const toneClasses = {
  blue: {
    icon: 'bg-blue-50 text-blue-700 ring-blue-100',
    value: 'text-blue-700',
  },
  green: {
    icon: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
    value: 'text-emerald-700',
  },
  amber: {
    icon: 'bg-amber-50 text-amber-700 ring-amber-100',
    value: 'text-amber-700',
  },
  red: {
    icon: 'bg-red-50 text-red-700 ring-red-100',
    value: 'text-red-700',
  },
  slate: {
    icon: 'bg-slate-100 text-slate-700 ring-slate-200',
    value: 'text-slate-900',
  },
}
```

---

## 10. Do not do in this refactor

- Do not add GenAI copilot yet.
- Do not add new backend endpoints unless required by the user.
- Do not migrate to another chart library.
- Do not introduce Redux/global state unless there is a clear reason.
- Do not turn the UI into a camera-only security dashboard.
- Do not expose internal table names in business-facing labels unless in debug/diagnostics.
