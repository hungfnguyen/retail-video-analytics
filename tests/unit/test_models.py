"""Unit tests for core.models — event contract validation."""

from core.models import (
    AlertEvent,
    BBox,
    Centroid,
    ClipCreatedResult,
    DetectionFrameEvent,
    DetectionObject,
    ImageSize,
    SampledFrameResult,
    Source,
    TrackLifecycleEvent,
)


class TestDetectionFrameEvent:
    def test_minimal_event_serializes(self):
        event = DetectionFrameEvent(
            pipeline_run_id="run_001",
            source=Source(store_id="s1", camera_id="c1", stream_id="s1_stream"),
            frame_index=42,
            capture_ts="2026-05-11T10:30:00Z",
            image_size=ImageSize(width=1920, height=1080),
            detections=[],
        )
        payload = event.to_pulsar_payload()
        assert b'"schema_version"' in payload
        assert b'"1.0"' in payload

    def test_event_with_detections(self):
        det = DetectionObject(
            det_id="42-0",
            **{"class": "person"},
            class_id=0,
            conf=0.87,
            bbox=BBox(x1=100, y1=200, x2=300, y2=620),
            bbox_norm={"x": 0.05, "y": 0.18, "w": 0.15, "h": 0.57},
            centroid=Centroid(x=200, y=410),
            centroid_norm={"x": 0.10, "y": 0.38},
            track_id=7,
        )
        event = DetectionFrameEvent(
            pipeline_run_id="run_002",
            source=Source(store_id="s1", camera_id="c1", stream_id="s1_stream"),
            frame_index=1,
            capture_ts="2026-05-11T10:30:00Z",
            image_size=ImageSize(width=1920, height=1080),
            detections=[det],
        )
        payload = event.to_pulsar_payload()
        assert b'"track_id":7' in payload


class TestBBox:
    def test_bbox_validation(self):
        bbox = BBox(x1=0.0, y1=0.0, x2=100.0, y2=200.0)
        assert bbox.x2 > bbox.x1
        assert bbox.y2 > bbox.y1


class TestSampledFrameResult:
    def test_minimal_result(self):
        result = SampledFrameResult(
            pipeline_run_id="run_001",
            source={"store_id": "s1", "camera_id": "c1"},
            frame_index=10,
            capture_ts="2026-05-11T10:30:00Z",
            upload_ts="2026-05-11T10:30:02Z",
            image_size={"width": 1920, "height": 1080},
            bucket="test-bucket",
            s3_key="frames/2026-05-11/s1/c1/10h/key.jpg",
            s3_uri="s3://test-bucket/frames/2026-05-11/s1/c1/10h/key.jpg",
            byte_size=45678,
            jpeg_quality=85,
        )
        assert result.event_type == "sampled_frame_created"


class TestClipCreatedResult:
    def test_minimal_result(self):
        result = ClipCreatedResult(
            pipeline_run_id="run_001",
            alert_id="c1_100_density_high",
            alert_type="density_high",
            source={"store_id": "s1", "camera_id": "c1"},
            trigger_frame_index=100,
            trigger_ts="2026-05-11T10:30:00Z",
            upload_ts="2026-05-11T10:30:05Z",
            bucket="test-bucket",
            clip_s3_key="clips/2026-05-11/s1/c1/c1_100_density_high.mp4",
            clip_s3_uri="s3://test-bucket/clips/2026-05-11/s1/c1/c1_100_density_high.mp4",
            clip_duration_sec=10.0,
            frame_count=250,
            byte_size=1234567,
        )
        assert result.event_type == "clip_created"
        assert result.clip_duration_sec == 10.0


class TestAlertEvent:
    def test_alert_event(self):
        alert = AlertEvent(
            event_type="density_alert",
            alert_id="alert_001",
            pipeline_run_id="run_001",
            source=Source(store_id="s1", camera_id="c1", stream_id="s1_stream"),
            alert_type="density_high",
            trigger_frame_index=100,
            trigger_ts="2026-05-11T10:30:00Z",
            current_count=15,
            threshold=10,
        )
        assert alert.current_count > alert.threshold


class TestDetectionFrameEventId:
    def test_event_id_auto_generated_when_missing(self):
        event = DetectionFrameEvent(
            pipeline_run_id="run_001",
            source=Source(store_id="s1", camera_id="c1", stream_id="s1_stream"),
            frame_index=42,
            capture_ts="2026-05-11T10:30:00Z",
            image_size=ImageSize(width=1920, height=1080),
            detections=[],
        )
        assert len(event.event_id) == 16
        assert all(c in "0123456789abcdef" for c in event.event_id)

    def test_event_id_passed_through_when_provided(self):
        event = DetectionFrameEvent(
            pipeline_run_id="run_001",
            source=Source(store_id="s1", camera_id="c1", stream_id="s1_stream"),
            frame_index=42,
            capture_ts="2026-05-11T10:30:00Z",
            event_id="abcd1234abcd1234",
            image_size=ImageSize(width=1920, height=1080),
            detections=[],
        )
        assert event.event_id == "abcd1234abcd1234"

    def test_event_id_deterministic_same_inputs(self):
        kwargs = dict(
            pipeline_run_id="run_001",
            source=Source(store_id="s1", camera_id="c1", stream_id="s1_stream"),
            frame_index=42,
            capture_ts="2026-05-11T10:30:00Z",
            image_size=ImageSize(width=1920, height=1080),
            detections=[],
        )
        e1 = DetectionFrameEvent(**kwargs)
        e2 = DetectionFrameEvent(**kwargs)
        assert e1.event_id == e2.event_id

    def test_event_id_differs_per_frame_index(self):
        base = dict(
            pipeline_run_id="run_001",
            source=Source(store_id="s1", camera_id="c1", stream_id="s1_stream"),
            capture_ts="2026-05-11T10:30:00Z",
            image_size=ImageSize(width=1920, height=1080),
            detections=[],
        )
        e1 = DetectionFrameEvent(frame_index=1, **base)
        e2 = DetectionFrameEvent(frame_index=2, **base)
        assert e1.event_id != e2.event_id

    def test_to_pulsar_payload_contains_event_id(self):
        event = DetectionFrameEvent(
            pipeline_run_id="run_001",
            source=Source(store_id="s1", camera_id="c1", stream_id="s1_stream"),
            frame_index=42,
            capture_ts="2026-05-11T10:30:00Z",
            event_id="deadbeef12345678",
            image_size=ImageSize(width=1920, height=1080),
            detections=[],
        )
        payload = event.to_pulsar_payload()
        assert b'"event_id":"deadbeef12345678"' in payload


class TestTrackLifecycleEvent:
    def test_track_started(self):
        event = TrackLifecycleEvent(
            event_type="track_started",
            pipeline_run_id="run_001",
            source=Source(store_id="s1", camera_id="c1", stream_id="s1_stream"),
            track_id=42,
            event_ts="2026-05-11T10:30:00Z",
            bbox=BBox(x1=100, y1=200, x2=300, y2=620),
            centroid=Centroid(x=200, y=410),
            confidence=0.87,
        )
        assert event.track_id == 42
        assert event.bbox.x1 == 100
