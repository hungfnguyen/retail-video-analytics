# Frontend Folder Structure

The frontend uses a feature-based structure. Each feature owns its page, API client, hooks, local components, and types.

```text
frontend/src/
|-- app/
|   |-- App.tsx
|
|-- shared/
|   |-- components/
|   |   |-- AppShell.tsx
|
|-- features/
|   |-- live/
|   |   |-- LivePage.tsx
|   |   |-- api/
|   |   |   |-- liveApi.ts
|   |   |-- components/
|   |   |   |-- AlertList.tsx
|   |   |   |-- LiveMetricCards.tsx
|   |   |   |-- PipelineHealth.tsx
|   |   |   |-- TrafficChart.tsx
|   |   |   |-- VideoPanel.tsx
|   |   |   |-- ZoneHeatmap.tsx
|   |   |-- hooks/
|   |   |   |-- useLiveData.ts
|   |   |-- types.ts
|   |
|   |-- analytics/
|   |-- investigate/
|   |-- system/
|
|-- main.tsx
|-- index.css
```

## Data Flow

The Live feature should read dashboard data through the API layer:

```text
LivePage.tsx
-> hooks/useLiveData.ts
-> api/liveApi.ts
-> FastAPI /api/v1/live/{camera_id}/dashboard
```

Frontend mock data is no longer required for the Live page because FastAPI provides the mock dashboard contract during early development.
