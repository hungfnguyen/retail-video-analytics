from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "services" / "flink-jobs" / "python" / "submit_batch_job.py"

sys.modules.setdefault(
    "fcntl",
    types.SimpleNamespace(
        LOCK_EX=1,
        LOCK_NB=2,
        LOCK_UN=8,
        flock=lambda *args, **kwargs: None,
    ),
)

spec = importlib.util.spec_from_file_location("submit_batch_job", MODULE_PATH)
submit_batch_job = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(submit_batch_job)


def test_delete_target_window_runs_delete_when_target_exists(monkeypatch):
    calls: list[tuple[str, str | None]] = []

    monkeypatch.setattr(submit_batch_job, "_target_table_exists", lambda target: True)
    monkeypatch.setattr(
        submit_batch_job,
        "_trino_run",
        lambda sql, **kwargs: calls.append((sql, kwargs.get("output_format"))) or "",
    )

    submit_batch_job._delete_target_window(
        "traffic_daily",
        "2026-06-12",
        "2026-06-19",
    )

    assert len(calls) == 1
    assert "DELETE FROM lakehouse.rva_gold_serving.gold_serving_traffic_daily" in calls[0][0]
    assert "metric_date BETWEEN DATE '2026-06-12' AND DATE '2026-06-19'" in calls[0][0]


def test_delete_target_window_skips_delete_when_target_missing(monkeypatch):
    monkeypatch.setattr(submit_batch_job, "_target_table_exists", lambda target: False)
    monkeypatch.setattr(
        submit_batch_job,
        "_trino_run",
        lambda sql, **kwargs: (_ for _ in ()).throw(AssertionError(sql)),
    )

    submit_batch_job._delete_target_window(
        "traffic_daily",
        "2026-06-12",
        "2026-06-19",
    )


def test_target_table_exists_checks_trino_information_schema(monkeypatch):
    captured: list[str] = []

    def fake_trino_run(sql, **kwargs):
        captured.append(sql)
        return "1\n"

    monkeypatch.setattr(submit_batch_job, "_trino_run", fake_trino_run)

    exists = submit_batch_job._target_table_exists(
        "lakehouse.rva_gold_serving.gold_serving_traffic_daily"
    )

    assert exists is True
    assert "lakehouse.information_schema.tables" in captured[0]
    assert "table_schema = 'rva_gold_serving'" in captured[0]
    assert "table_name = 'gold_serving_traffic_daily'" in captured[0]


def test_target_table_exists_returns_false_for_missing_table(monkeypatch):
    monkeypatch.setattr(
        submit_batch_job,
        "_trino_run",
        lambda sql, **kwargs: "0\n",
    )

    exists = submit_batch_job._target_table_exists(
        "lakehouse.rva_gold_serving.gold_serving_traffic_daily"
    )

    assert exists is False
