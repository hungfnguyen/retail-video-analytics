# Current UI Gap Analysis vs Target

Date: 2026-06-17  
Branch context: `refactor-ui`  
Reference commit for current refactor baseline: `6b8cdf878ef0793a9fa42ea080d57fd90af6cfc9` (`refactor full ui`)

## 1. Scope

This document compares:

- target docs in `docs/ui/rva-ui-refactor-docs/`
- target mockup image `docs/ui/rva-ui-refactor-docs/image.png`
- current implemented UI on branch `refactor-ui`
- current lakehouse/API readiness

Purpose:

- keep one concrete gap-analysis file before the next UI rewrite
- map each gap to exact frontend files
- distinguish `frontend-only` gaps from `frontend + API mapping` gaps

---

## 2. Executive Summary

Current state after Claude's refactor:

1. `Heatmap` is the closest page to target.
2. `Live Monitor` has the right page skeleton, but several metrics and right-panel semantics are wrong.
3. `Analyst Dashboard` is the farthest from target. It still behaves like a light analytics page, not a business dashboard.
4. Backend is good enough for:
   - Live redesign
   - Heatmap redesign v1
5. Backend is only partially ready for:
   - full Analyst Dashboard target

Main implication:

- `Live` and `Heatmap` can be fixed mostly in frontend.
- `Analytics` needs both UI work and API/view-model remapping.

---

## 3. Backend Readiness Summary

## 3.1 Ready enough now

These flows are already usable for the intended UI:

- live frame / live count / alerts / queue live state
- historical heatmap cells
- traffic hourly/daily serving tables
- queue serving tables
- dwell daily serving
- alert serving

Main files reviewed:

- `services/api/src/rva_api/api/v1/live.py`
- `services/api/src/rva_api/api/v1/analytics.py`
- `services/api/src/rva_api/api/v1/analytics_queries.py`
- `services/api/src/rva_api/schemas/live.py`
- `services/api/src/rva_api/schemas/analytics.py`
- `services/gold_serving/sql/ddl/gold_serving.sql`

## 3.2 Not fully ready for target Analyst Dashboard

Current analytics API still has these limitations:

- business KPIs are mixed with technical metrics
- overview payload is not shaped exactly like the target dashboard
- zone/business insight data is weak
- some tabs are still driven by generic series instead of purpose-built business view models
- filters are still limited compared to target behavior

This does not block UI iteration completely, but it does block a fully correct target implementation.

---

## 4. Page-by-Page Assessment

| Page | Current status | Main problem |
|---|---|---|
| Live | Partial match | Wrong metric semantics, weak right-side operations panel |
| Analytics | Weak match | Layout and data model do not match target business dashboard |
| Heatmap | Best match | Good direction, but insight quality and information hierarchy still off |

---

## 5. Gap Analysis by Component / File

## 5.1 Shared Foundation

| Target requirement | Current UI | Files to change | Scope |
|---|---|---|---|
| One coherent app shell with compact operational SaaS feel | Shell is acceptable, but still visually generic in places and inconsistent across pages | `frontend/src/shared/components/AppShell.tsx`, `frontend/src/index.css` | Frontend only |
| Shared filter/control language across pages | Controls are page-specific and inconsistent; Analytics and Heatmap do not share one filter pattern | `frontend/src/shared/components/ui/PageHeader.tsx`, new shared filter component, `frontend/src/features/analytics/AnalyticsPage.tsx`, `frontend/src/features/heatmap/HeatmapPage.tsx` | Frontend only |
| KPI cards support business context, status, delta text, not just a label/value block | Current cards are cleaner than old UI but still too generic for target business storytelling | `frontend/src/shared/components/ui/MetricCard.tsx` | Frontend only |
| Remove dead/legacy component paths to reduce confusion | Repo still has old unused components next to new ones | multiple old components under `frontend/src/features/live/components`, `frontend/src/features/analytics/components`, `frontend/src/features/heatmap/components` | Frontend only |

## 5.2 Live Monitor

| Target requirement | Current UI | Files to change | Scope |
|---|---|---|---|
| Live page should feel like an operations console | Structure is close, but still reads like a dashboard plus side list | `frontend/src/features/live/LivePage.tsx` | Frontend only |
| KPI row must show valid, business-correct metrics | Current KPI row has a visible bug: `Peak Hour` renders `Invalid Date` | `frontend/src/features/live/LivePage.tsx`, possibly formatter util | Frontend only |
| Dwell metric must represent dwell, not queue/zone wait | Current live dwell card is derived from zone wait-like values, which is semantically wrong | `frontend/src/features/live/LivePage.tsx` | Frontend only |
| Camera header/subtitle should be clean and non-duplicative | Current subtitle formatting around camera name is awkward (`Cam_1 - Cam_1` style) | `frontend/src/features/live/LivePage.tsx`, `frontend/src/features/live/components/VideoPanel.tsx` | Frontend only |
| Right-side panel should summarize active operations state, not only alerts | Current right panel is basically `AlertList`; target wanted richer operations context | `frontend/src/features/live/LivePage.tsx`, `frontend/src/features/live/components/AlertList.tsx`, likely revive/rework `frontend/src/features/live/components/LiveOperationsPanel.tsx` | Frontend only |
| Queue panel should support quick operational scan | Current queue table is acceptable structurally, but still too passive and low-signal | `frontend/src/features/live/components/QueueStatusTable.tsx` | Frontend only |
| Visitor trend card should support operational reading | Current chart renders but feels generic and thin relative to target | `frontend/src/features/live/components/TrafficChart.tsx` | Frontend only |
| Zone occupancy should convey meaningful crowd pressure | Current zone occupancy is simplistic; 1 active zone can read as `100%`, which is visually misleading | `frontend/src/features/live/components/ZoneOccupancyPanel.tsx` | Frontend only |
| Mini density/heat context should support live page but not dominate it | Current bottom heat strip is acceptable but still looks decorative instead of operational | `frontend/src/features/live/components/ZoneHeatmap.tsx`, `frontend/src/features/live/LivePage.tsx` | Frontend only |

## 5.3 Analyst Dashboard

| Target requirement | Current UI | Files to change | Scope |
|---|---|---|---|
| Page should look like a business insight workspace, not a generic chart page | Current page is cleaner than old version, but still feels thin and under-modeled | `frontend/src/features/analytics/AnalyticsPage.tsx` | Frontend only |
| Filter bar should support store/camera/date pattern close to spec | Current filter bar is weak; camera behavior is limited and not aligned with target control structure | `frontend/src/features/analytics/AnalyticsPage.tsx`, `frontend/src/features/analytics/components/AnalyticsFilterBar.tsx` | Frontend only, maybe API if new filter semantics are added |
| Overview tab should have strong executive summary sections | Current Overview only covers a subset: KPI row + one trend + empty weekday panel | `frontend/src/features/analytics/components/tabs/OverviewTab.tsx` | Frontend + API mapping |
| Overview KPIs must reflect business semantics from target docs | Current metrics still lean toward observations/technical counts rather than full business framing | `frontend/src/features/analytics/adapters/analyticsViewModels.ts`, `services/api/src/rva_api/api/v1/analytics.py`, `services/api/src/rva_api/schemas/analytics.py` | Frontend + API mapping |
| Peak-hours heatmap / richer distribution views | Current page does not implement the target peak-hours insight structure | `frontend/src/features/analytics/components/tabs/OverviewTab.tsx`, possibly new chart components | Frontend + API mapping |
| Day-of-week panel should show real pattern, not placeholder empty state in normal usage | Current panel still shows a gating empty state and lacks target-level usefulness | `frontend/src/features/analytics/components/tabs/OverviewTab.tsx` | Frontend + API mapping |
| Traffic tab should feel analytical, not just a spillover of overview data | Current traffic rendering is usable but still generic | `frontend/src/features/analytics/components/tabs/TrafficTab.tsx` | Frontend only if existing data is reused well |
| Queue tab should show SLA, pressure windows, worst queues clearly | Current queue tab is not yet at target information density | `frontend/src/features/analytics/components/tabs/QueueTab.tsx` | Frontend + possibly API mapping |
| Zones tab needs real business zone analysis | Current Zones tab is the weakest area; backend/view-model is not strong enough yet | `frontend/src/features/analytics/components/tabs/ZonesTab.tsx`, `frontend/src/features/analytics/adapters/analyticsViewModels.ts`, analytics API/query layer | Frontend + API mapping |
| Alerts tab should distinguish incident history from threshold signals correctly | Current alerts handling risks flattening semantics too much unless mapped carefully | `frontend/src/features/analytics/components/tabs/AlertsTab.tsx`, `services/api/src/rva_api/api/v1/analytics_queries.py`, schema/adapters | Frontend + API mapping |

## 5.4 Heatmap

| Target requirement | Current UI | Files to change | Scope |
|---|---|---|---|
| Heatmap page should foreground spatial behavior on top of camera imagery | Current page already does this reasonably well | `frontend/src/features/heatmap/HeatmapPage.tsx` | Frontend only |
| Heat overlay controls should be simple and useful | Current settings panel is close to target | `frontend/src/features/heatmap/components/HeatmapSettingsPanel.tsx` | Frontend only |
| Insight panel should produce useful spatial interpretation, not repetitive generic labels | Current insights and hotspot naming are weak/repetitive (`Middle-Left Area`, `Upper-Left Area`) | `frontend/src/features/heatmap/components/HeatmapInsightsPanel.tsx`, `frontend/src/features/heatmap/components/TopHotspotsList.tsx`, `frontend/src/features/heatmap/adapters/heatmapViewModels.ts` | Frontend only for heuristic improvement |
| Hot zone list should feel meaningful and non-duplicative | Current list repeats similar names and weak severity labels | `frontend/src/features/heatmap/components/TopHotspotsList.tsx`, view-model adapter | Frontend only |
| Optional zone overlay / richer interpretation should degrade gracefully when geometry is missing | Current behavior is acceptable, but wording can be improved | `frontend/src/features/heatmap/components/HeatmapSettingsPanel.tsx`, `HeatmapInsightsPanel.tsx` | Frontend only |

---

## 6. Concrete File Priority

## Priority A — Highest signal, frontend-only

These should be fixed first because they are local, obvious, and do not require backend changes:

1. `frontend/src/features/live/LivePage.tsx`
2. `frontend/src/features/live/components/AlertList.tsx`
3. `frontend/src/features/live/components/QueueStatusTable.tsx`
4. `frontend/src/features/live/components/TrafficChart.tsx`
5. `frontend/src/features/live/components/ZoneOccupancyPanel.tsx`
6. `frontend/src/features/heatmap/components/HeatmapInsightsPanel.tsx`
7. `frontend/src/features/heatmap/components/TopHotspotsList.tsx`
8. `frontend/src/shared/components/ui/MetricCard.tsx`

## Priority B — Structural frontend cleanup

1. `frontend/src/features/analytics/AnalyticsPage.tsx`
2. `frontend/src/features/analytics/components/AnalyticsFilterBar.tsx`
3. `frontend/src/shared/components/AppShell.tsx`
4. `frontend/src/index.css`
5. remove or consolidate unused legacy components

## Priority C — Requires API/view-model reshaping

1. `frontend/src/features/analytics/adapters/analyticsViewModels.ts`
2. `services/api/src/rva_api/api/v1/analytics.py`
3. `services/api/src/rva_api/api/v1/analytics_queries.py`
4. `services/api/src/rva_api/schemas/analytics.py`
5. `frontend/src/features/analytics/components/tabs/OverviewTab.tsx`
6. `frontend/src/features/analytics/components/tabs/ZonesTab.tsx`
7. `frontend/src/features/analytics/components/tabs/AlertsTab.tsx`
8. `frontend/src/features/analytics/components/tabs/QueueTab.tsx`

---

## 7. What Does Not Need Immediate Backend Work

The following target improvements can be done without touching lakehouse or API contracts immediately:

- fix Live KPI semantics and display formatting
- redesign Live right-side operations composition
- improve queue/zone visual hierarchy on Live page
- improve Heatmap layout polish
- improve Heatmap hotspot naming heuristics
- standardize page headers and controls

---

## 8. What Does Need Backend / API Mapping

These items should not be treated as pure frontend work:

1. Analyst Overview target KPI model
2. richer day-of-week / peak-hour insight model
3. proper zone analytics payloads
4. alert semantics separation in business UI
5. stronger analyst filter semantics

If these are not reshaped in the API layer, the frontend will keep faking business meaning from incomplete technical payloads.

---

## 9. Recommended Execution Order

Recommended implementation order:

1. Fix `Live` first.
2. Polish `Heatmap` second.
3. Rework `Analytics` layout shell third.
4. Then reshape analytics API/view models.
5. Then finish `Analytics` business tabs.

Reason:

- this sequence gives visible quality improvements quickly
- it avoids blocking on analytics API too early
- it reduces the risk of another large but semantically wrong UI rewrite

---

## 10. Decision Rule for Next UI Pass

Use this rule during the next refactor pass:

- if the gap is visual hierarchy, component composition, labeling, formatting, or local heuristics -> fix in frontend
- if the gap is business meaning, KPI semantics, zone insight, or filter semantics -> check API contract first

Do not let the frontend invent business metrics that the backend does not actually provide.

---

## 11. Final Conclusion

Claude's refactor improved the UI baseline materially, but it did not land on the target design.

The biggest mistake was not visual quality. It was semantic mismatch:

- `Live` looks closer, but some metrics mean the wrong thing
- `Analytics` looks cleaner, but still is not the target business dashboard
- `Heatmap` is visually closest, but insight quality is still shallow

This document should be used as the implementation checklist for the next UI pass.
