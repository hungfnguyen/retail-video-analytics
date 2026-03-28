# Visualization & Dashboard

## Overview

The visualization layer centers on **Heatmap Overlay** directly on video — density visualization rendered on top of live camera frames.

### Feature Summary

| Feature | Status | Description |
|---------|--------|-------------|
| **Heatmap Overlay** | Primary | Density visualization on video stream |
| **Bounding Boxes** | Primary | Display detections with track IDs |
| **Track Count** | Primary | Unique person count |
| **Zone Analytics** | Removed | Not needed — heatmap provides full spatial information |

---

## 1. User Personas

### 1.1 Store Manager

| Attribute | Value |
|-----------|-------|
| **Skill Level** | Non-technical |
| **Key Questions** | Which areas are crowded? How many visitors today? |
| **Preferred Tool** | Simple dashboard + email reports |

### 1.2 Security / Operations

| Attribute | Value |
|-----------|-------|
| **Skill Level** | Basic technical |
| **Key Questions** | Any unusual crowding? Are cameras working? |
| **Preferred Tool** | Live heatmap + alerts |

### 1.3 Data Analyst

| Attribute | Value |
|-----------|-------|
| **Skill Level** | Technical |
| **Key Questions** | Hourly patterns? Day-over-day comparison? Hotspot areas? |
| **Preferred Tool** | Historical heatmap + data export |

---

## 2. Primary Visualization: Heatmap Overlay

### 2.1 Live Heatmap on Video

```
┌──────────────────────────────────────────────────────────────────┐
│                     LIVE CAMERA VIEW + HEATMAP                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                                                            │  │
│  │   [Video Frame]                                            │  │
│  │                                                            │  │
│  │       ████████                    ███████████              │  │
│  │     ██████████████             ███████████████████         │  │
│  │    ████HOT████████   P:137    ██████HOT██████████ P:200    │  │
│  │     ██████████████             ███████████████████         │  │
│  │       ████████                    ███████████              │  │
│  │                                                            │  │
│  │              ┌─────┐                                       │  │
│  │              │P:62 │  ← Bounding box with track ID         │  │
│  │              └─────┘                                       │  │
│  │                                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ ◄◄  ►  ▶▶ │  Show Boxes │ Opacity │ Cold ─────────── Hot  │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Heatmap Algorithm

```python
import numpy as np
import cv2

class HeatmapOverlay:
    def __init__(self, width, height, cell_size=30, decay=0.95):
        self.cell_size = cell_size
        self.grid_w = width // cell_size
        self.grid_h = height // cell_size
        self.grid = np.zeros((self.grid_h, self.grid_w), dtype=np.float32)
        self.decay = decay

    def update(self, detections):
        """Update heatmap with new detections"""
        # Apply decay
        self.grid *= self.decay

        # Add new points
        for det in detections:
            cx = int((det['x'] + det['w']/2) / self.cell_size)
            cy = int((det['y'] + det['h']/2) / self.cell_size)

            if 0 <= cx < self.grid_w and 0 <= cy < self.grid_h:
                self.grid[cy, cx] += 1.0

    def render(self, frame, alpha=0.4):
        """Render heatmap overlay on frame"""
        # Upscale grid to frame size
        heatmap = cv2.resize(self.grid, (frame.shape[1], frame.shape[0]))

        # Gaussian blur for smooth effect
        heatmap = cv2.GaussianBlur(heatmap, (51, 51), 0)

        # Normalize to 0-255
        if heatmap.max() > 0:
            heatmap = (heatmap / heatmap.max() * 255).astype(np.uint8)
        else:
            heatmap = np.zeros_like(heatmap, dtype=np.uint8)

        # Apply colormap (COLORMAP_JET: blue→green→yellow→red)
        heatmap_colored = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)

        # Create mask (only show where heatmap > threshold)
        mask = heatmap > 10
        mask = np.stack([mask] * 3, axis=-1)

        # Blend
        result = frame.copy()
        result[mask] = cv2.addWeighted(
            frame, 1 - alpha,
            heatmap_colored, alpha,
            0
        )[mask]

        return result
```

### 2.3 Controls

| Control | Function |
|---------|----------|
| **Play/Pause** | Play/pause video stream |
| **Rewind/Forward** | Navigate recorded video |
| **Show Boxes** | Toggle bounding boxes on/off |
| **Opacity** | Adjust heatmap overlay opacity |
| **Color Scale** | Heatmap color legend (Cold → Hot) |

---

## 3. Streamlit Dashboard Pages

### 3.1 Page: Live Monitor (Primary)

```python
# pages/1_Live_Monitor.py
import streamlit as st
import cv2
import numpy as np
from services.redis_client import RedisService
from services.video_stream import VideoStream
from components.heatmap import HeatmapOverlay

st.set_page_config(page_title="Live Monitor", layout="wide")
st.title("Live Monitor")

# Sidebar controls
with st.sidebar:
    show_heatmap = st.checkbox("Heatmap", value=True)
    show_boxes = st.checkbox("Bounding Boxes", value=True)
    heatmap_opacity = st.slider("Opacity", 0.1, 0.8, 0.4)
    decay_rate = st.slider("Decay Rate", 0.9, 0.99, 0.95)

# Main content
col1, col2 = st.columns([3, 1])

with col1:
    # Video placeholder
    video_placeholder = st.empty()

    # Color scale legend
    st.image("assets/color_scale.png", caption="Cold → Hot")

with col2:
    st.subheader("Statistics")

    # Real-time stats
    stats_placeholder = st.empty()

    # Current count
    st.metric("Current Count", "15", "+3")

    # Top hotspots
    st.subheader("Hotspots")
    hotspots = [
        {"area": "Center", "density": 45},
        {"area": "Left corner", "density": 32},
        {"area": "Right side", "density": 28},
    ]
    for hs in hotspots:
        st.progress(hs["density"] / 50, text=f"{hs['area']}: {hs['density']}")
```

### 3.2 Page: Historical Heatmap

```python
# pages/2_Historical.py
import streamlit as st
from datetime import datetime, timedelta

st.title("Historical Heatmap Analysis")

# Date/time selector
col1, col2 = st.columns(2)
with col1:
    selected_date = st.date_input("Date", datetime.now())
with col2:
    time_range = st.selectbox("Time Range", [
        "Last 1 hour",
        "Last 6 hours",
        "Last 24 hours",
        "Custom range"
    ])

# Heatmap comparison
st.subheader("Heatmap Comparison")
col1, col2 = st.columns(2)

with col1:
    st.caption("Morning (9:00 - 12:00)")
    st.image("heatmap_morning.png")

with col2:
    st.caption("Afternoon (14:00 - 18:00)")
    st.image("heatmap_afternoon.png")

# Hourly traffic chart
st.subheader("Hourly Traffic")
st.line_chart(hourly_data)

# Top hotspot areas over time
st.subheader("Hotspot Trends")
st.area_chart(hotspot_trends)
```

### 3.3 Page: Track Replay

```python
# pages/3_Track_Replay.py
import streamlit as st

st.title("Track Replay")

# Track ID input
track_id = st.number_input("Track ID", min_value=1, value=42)

if st.button("Load Track"):
    # Load track path from PostgreSQL
    track = load_track(track_id)

    if track:
        st.success(f"Track {track_id} found!")

        # Display track info
        col1, col2, col3 = st.columns(3)
        col1.metric("Duration", f"{track['duration']}s")
        col2.metric("Distance", f"{track['distance']}px")
        col3.metric("Camera", track['camera_id'])

        # Video with track overlay
        video_placeholder = st.empty()

        # Playback controls
        col1, col2, col3, col4 = st.columns(4)
        col1.button("Start")
        col2.button("-1s")
        col3.button("Pause")
        col4.button("+1s")
    else:
        st.error("Track not found")
```

### 3.4 Page: Alerts

```python
# pages/4_Alerts.py
import streamlit as st

st.title("Alerts")

# Alert settings
with st.expander("Alert Settings"):
    density_threshold = st.slider("Density Alert Threshold", 10, 50, 30)
    crowd_threshold = st.slider("Crowd Alert (people)", 5, 30, 15)

# Active alerts
st.subheader("Active Alerts")

alerts = get_active_alerts()
for alert in alerts:
    with st.container():
        col1, col2, col3 = st.columns([1, 3, 1])
        col1.write(f"Warning: {alert['type']}")
        col2.write(f"Camera: {alert['camera_id']} | Density: {alert['density']}")
        col3.button("Acknowledge", key=alert['id'])

# Alert history
st.subheader("Alert History")
st.dataframe(alert_history)
```

---

## 4. Grafana Dashboards

### 4.1 Dashboard: Traffic Overview

| Panel | Type | Data Source |
|-------|------|-------------|
| Total Visitors Today | Stat | `analytics.daily_stats` |
| Current Count | Gauge | Redis `stats:count` |
| Hourly Traffic | Time Series | `analytics.hourly_stats` |
| Peak Hours | Bar Chart | Aggregated hourly |
| Week Comparison | Time Series | Daily comparison |

### 4.2 Dashboard: System Health

| Panel | Type | Metric |
|-------|------|--------|
| Camera Status | Table | `system.camera_health` |
| Detection Rate | Time Series | `stats:detections` |
| FPS | Gauge | Redis `stats:fps` |
| Redis Memory | Gauge | Redis INFO |
| Active Alerts | Stat | Alert count |

---

## 5. REST API Endpoints

### 5.1 Heatmap API

```
GET /api/heatmap/live/{camera_id}
Response:
{
  "camera_id": "cam_01",
  "grid_width": 64,
  "grid_height": 48,
  "data": [
    {"x": 32, "y": 24, "value": 45.2},
    {"x": 33, "y": 24, "value": 38.1},
    ...
  ],
  "max_value": 45.2,
  "timestamp": "2024-03-28T14:30:00Z"
}

GET /api/heatmap/historical/{camera_id}
    ?start_time=2024-03-28T09:00:00Z
    &end_time=2024-03-28T18:00:00Z
    &granularity=hour
```

### 5.2 Stats API

```
GET /api/stats/{camera_id}
Response:
{
  "camera_id": "cam_01",
  "current_count": 15,
  "fps": 28.5,
  "active_tracks": 12,
  "detections_per_minute": 450,
  "hotspots": [
    {"x": 32, "y": 24, "density": 45},
    {"x": 48, "y": 30, "density": 32}
  ]
}

GET /api/stats/historical/{camera_id}
    ?date=2024-03-28
```

### 5.3 WebSocket

```
WS /api/ws/stream/{camera_id}

Messages:
- detection: {"type": "detection", "track_id": 42, "x": 150, "y": 200}
- heatmap: {"type": "heatmap", "hotspots": [...]}
- stats: {"type": "stats", "count": 15, "fps": 28}
- alert: {"type": "alert", "alert_type": "density_spike", ...}
```

---

## 6. Technical Requirements

### Dependencies

```txt
# requirements.txt
streamlit>=1.30.0
opencv-python-headless>=4.9.0
numpy>=1.26.0
redis>=5.0.0
asyncpg>=0.29.0
google-cloud-storage>=2.14.0
plotly>=5.18.0
websockets>=12.0
pillow>=10.2.0
```

### Performance Requirements

| Metric | Target | Notes |
|--------|--------|-------|
| Heatmap update (Redis poll) | < 500ms | Streamlit refresh every 0.5-1 second |
| WebSocket latency | < 50ms | FastAPI → Streamlit |
| Video frame display | 1-3 FPS | Streamlit HTTP model limitation |
| Overlay rendering | < 30ms | OpenCV + NumPy on server |

> **Important**: Streamlit is not a native WebSocket client — it uses HTTP polling.
> For smooth video (>10 FPS), use `streamlit-webrtc` or an MJPEG stream
> via a FastAPI endpoint (`/api/stream/{camera_id}/mjpeg`), embedded with `st.markdown`.

### Color Scale

```python
# Heatmap color scale (JET colormap)
COLOR_SCALE = {
    0: (0, 0, 128),      # Dark blue (cold)
    25: (0, 128, 255),   # Light blue
    50: (0, 255, 128),   # Green
    75: (255, 255, 0),   # Yellow
    100: (255, 0, 0),    # Red (hot)
}
```

---

## Related Documents

- [02_ARCHITECTURE_IMPROVED.md](./02_ARCHITECTURE_IMPROVED.md) - System architecture
- [03_DATABASE_SCHEMA.md](./03_DATABASE_SCHEMA.md) - Database schema
- [05_ACTION_PLAN.md](./05_ACTION_PLAN.md) - Implementation guide
