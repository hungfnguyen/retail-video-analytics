frontend/src/
├── app/
│   ├── App.tsx
│   ├── routes.tsx
│   └── providers.tsx
│
├── shared/
│   ├── components/
│   │   ├── AppShell.tsx
│   │   ├── Sidebar.tsx
│   │   ├── TopBar.tsx
│   │   ├── MetricCard.tsx
│   │   ├── Panel.tsx
│   │   ├── StatusBadge.tsx
│   │   └── DataTable.tsx
│   ├── lib/
│   │   ├── format.ts
│   │   ├── time.ts
│   │   └── constants.ts
│   └── styles/
│       └── globals.css
│
├── features/
│   ├── live/
│   │   ├── LivePage.tsx
│   │   ├── components/
│   │   │   ├── VideoPanel.tsx
│   │   │   ├── BoundingBoxOverlay.tsx
│   │   │   ├── HeatmapOverlay.tsx
│   │   │   ├── LiveMetricCards.tsx
│   │   │   ├── AlertList.tsx
│   │   │   ├── TrafficChart.tsx
│   │   │   ├── ZoneHeatmap.tsx
│   │   │   └── PipelineHealth.tsx
│   │   ├── api/
│   │   │   └── liveApi.ts
│   │   ├── hooks/
│   │   │   ├── useLiveStats.ts
│   │   │   ├── useLiveFrame.ts
│   │   │   └── useLiveSocket.ts
│   │   ├── mocks/
│   │   │   └── liveMock.ts
│   │   └── types.ts
│   │
│   ├── analytics/
│   │   ├── AnalyticsPage.tsx
│   │   ├── components/
│   │   ├── api/
│   │   ├── hooks/
│   │   ├── mocks/
│   │   └── types.ts
│   │
│   ├── investigate/
│   │   ├── InvestigatePage.tsx
│   │   ├── components/
│   │   ├── api/
│   │   ├── hooks/
│   │   ├── mocks/
│   │   └── types.ts
│   │
│   └── system/
│       ├── SystemPage.tsx
│       ├── components/
│       ├── api/
│       ├── hooks/
│       ├── mocks/
│       └── types.ts