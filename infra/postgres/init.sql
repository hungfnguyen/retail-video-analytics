-- =============================================================
-- RVA PostgreSQL Schema
-- =============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS system;

-- =============================================================
-- core.cameras
-- =============================================================
CREATE TABLE core.cameras (
    camera_id     VARCHAR(50) PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    location      VARCHAR(200),
    store_id      VARCHAR(50),

    rtsp_url      VARCHAR(500),
    resolution    VARCHAR(20),  -- "1920x1080"
    fps           INTEGER DEFAULT 30,

    -- Heatmap grid config
    heatmap_grid_width   INTEGER DEFAULT 64,
    heatmap_grid_height  INTEGER DEFAULT 48,
    heatmap_decay_rate   FLOAT   DEFAULT 0.95,

    status        VARCHAR(20) DEFAULT 'active',
    last_seen     TIMESTAMPTZ,

    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- core.track_events  (partitioned by timestamp)
-- Stores: track_start, track_end, position_sample only.
-- Raw 30 FPS detections → Iceberg Bronze layer.
-- =============================================================
CREATE TABLE core.track_events (
    event_id    UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),

    camera_id   VARCHAR(50) NOT NULL REFERENCES core.cameras(camera_id),
    track_id    INTEGER     NOT NULL,
    event_type  VARCHAR(20) NOT NULL,  -- 'track_start' | 'track_end' | 'position_sample'

    timestamp   TIMESTAMPTZ NOT NULL,

    center_x    SMALLINT,
    center_y    SMALLINT,
    confidence  FLOAT,

    -- GCS path for keyframe (track_start and track_end only)
    frame_path  VARCHAR(500),

    created_at  TIMESTAMPTZ DEFAULT NOW()
) PARTITION BY RANGE (timestamp);

-- Initial monthly partitions (extend as needed)
CREATE TABLE core.track_events_2026_01
    PARTITION OF core.track_events
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE core.track_events_2026_02
    PARTITION OF core.track_events
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE core.track_events_2026_03
    PARTITION OF core.track_events
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE core.track_events_2026_04
    PARTITION OF core.track_events
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE TABLE core.track_events_2026_05
    PARTITION OF core.track_events
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE TABLE core.track_events_2026_06
    PARTITION OF core.track_events
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

-- Indexes on parent table
CREATE INDEX idx_track_events_camera_time
    ON core.track_events(camera_id, timestamp DESC);
CREATE INDEX idx_track_events_track
    ON core.track_events(track_id, camera_id);

-- =============================================================
-- core.tracks  (one row per visitor visit)
-- =============================================================
CREATE TABLE core.tracks (
    id          SERIAL      PRIMARY KEY,
    track_id    INTEGER     NOT NULL,
    camera_id   VARCHAR(50) NOT NULL REFERENCES core.cameras(camera_id),

    first_seen  TIMESTAMPTZ NOT NULL,
    last_seen   TIMESTAMPTZ NOT NULL,

    -- Sampled path at 1 point/second
    path        JSONB       NOT NULL DEFAULT '[]',

    total_duration_seconds INTEGER,
    frame_path_start       VARCHAR(500),  -- gs:// path at first appearance
    frame_path_end         VARCHAR(500),  -- gs:// path at disappearance

    created_at  TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (track_id, camera_id, first_seen)
);

-- =============================================================
-- core.alerts
-- =============================================================
CREATE TABLE core.alerts (
    alert_id        UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),

    alert_type      VARCHAR(50) NOT NULL,  -- 'crowd' | 'density_spike' | 'camera_offline'
    severity        VARCHAR(20) DEFAULT 'medium',

    camera_id       VARCHAR(50) REFERENCES core.cameras(camera_id),

    hotspot_x       INTEGER,
    hotspot_y       INTEGER,

    triggered_at    TIMESTAMPTZ NOT NULL,
    resolved_at     TIMESTAMPTZ,

    details         JSONB,
    snapshot_path   VARCHAR(500),

    status          VARCHAR(20) DEFAULT 'active',

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alerts_camera_triggered
    ON core.alerts(camera_id, triggered_at DESC);
CREATE INDEX idx_alerts_status
    ON core.alerts(status) WHERE status = 'active';

-- =============================================================
-- analytics.heatmap_snapshots
-- =============================================================
CREATE TABLE analytics.heatmap_snapshots (
    id              SERIAL      PRIMARY KEY,
    camera_id       VARCHAR(50) NOT NULL REFERENCES core.cameras(camera_id),

    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ NOT NULL,
    granularity     VARCHAR(20) NOT NULL,  -- 'minute' | 'hour' | 'day'

    grid_width      INTEGER     NOT NULL,
    grid_height     INTEGER     NOT NULL,
    heatmap_data    JSONB       NOT NULL,  -- [{"x":10,"y":20,"v":150}, ...]

    total_detections INTEGER,
    max_density      INTEGER,

    created_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (camera_id, start_time, granularity)
);

-- =============================================================
-- analytics.hourly_stats
-- =============================================================
CREATE TABLE analytics.hourly_stats (
    id                SERIAL  PRIMARY KEY,
    date              DATE    NOT NULL,
    hour              INTEGER NOT NULL,
    camera_id         VARCHAR(50) NOT NULL,

    total_detections  INTEGER,
    unique_tracks     INTEGER,
    max_concurrent    INTEGER,

    created_at        TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (date, hour, camera_id)
);

-- =============================================================
-- analytics.daily_stats
-- =============================================================
CREATE TABLE analytics.daily_stats (
    id                    SERIAL  PRIMARY KEY,
    date                  DATE    NOT NULL,
    store_id              VARCHAR(50) NOT NULL,

    total_visitors        INTEGER,
    peak_hour             INTEGER,
    peak_count            INTEGER,
    hotspot_areas         JSONB,

    prev_day_change_pct   FLOAT,

    created_at            TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (date, store_id)
);

-- =============================================================
-- system.feature_flags
-- =============================================================
CREATE TABLE system.feature_flags (
    flag_name   VARCHAR(50) PRIMARY KEY,
    enabled     BOOLEAN     DEFAULT FALSE,
    config      JSONB,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO system.feature_flags (flag_name, enabled, config) VALUES
    ('heatmap_enabled', TRUE,
     '{"decay_rate": 0.95, "grid_size": 30, "decay_interval_sec": 3}'),
    ('alerts_enabled',  TRUE,
     '{"density_threshold": 30, "crowd_threshold": 20}');
