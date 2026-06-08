from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REALTIME_JOB = PROJECT_ROOT / "services/flink-jobs/java/src/main/java/org/rva/realtime/RealtimeMetricsJob.java"


def test_realtime_metrics_job_does_not_hard_filter_low_confidence_detections():
    source = REALTIME_JOB.read_text()

    assert "conf < 0.4" not in source
    assert "t.conf >= 0.4" not in source
