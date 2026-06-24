"""Evaluate the Vision detector against annotated people inside main_aisle."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import yaml

KPI_ROOT = Path(__file__).resolve().parent
REPO_ROOT = KPI_ROOT.parent
VISION_ROOT = REPO_ROOT / "services" / "vision"
sys.path.insert(0, str(VISION_ROOT))

from detect.supervision_yolo_detector import SupervisionYoloDetector
from metrics import (
    PER_IMAGE_COLUMNS,
    SUMMARY_COLUMNS,
    calculate_metrics,
    filter_boxes_by_zone,
    find_samples,
    greedy_match,
    infer_names_from_labels,
    names_dict,
    person_class_id,
    read_ground_truth,
    write_csv,
)
from features.detections import detections_to_track_objects
from zones.zone_manager import RetailZoneRuntime, ZoneSpec

CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the Vision module on annotated person images."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=KPI_ROOT / "src",
    )
    parser.add_argument(
        "--model",
        type=Path,
        help="Optional checkpoint. Defaults to dataset best.pt or Vision config model.",
    )
    parser.add_argument(
        "--split",
        choices=("all", "test", "valid", "val"),
        default="all",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=KPI_ROOT / "result",
    )
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.5)
    return parser.parse_args()


def dataset_names(dataset_root: Path) -> tuple[dict[int, str], Path | None]:
    yaml_path = next(
        (
            path
            for path in (dataset_root / "data.yaml", dataset_root / "data.yml")
            if path.is_file()
        ),
        None,
    )
    if yaml_path is None:
        return {}, None
    payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return names_dict(payload.get("names")), yaml_path


def configured_model_name() -> str:
    config_path = (
        REPO_ROOT / "configs" / "cameras.yaml"
        if (REPO_ROOT / "configs" / "cameras.yaml").is_file()
        else REPO_ROOT / "configs" / "cameras.yaml.example"
    )
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return str(payload.get("settings", {}).get("model_name", "yolo11l.pt"))


def find_model(dataset_root: Path, requested: Path | None) -> str:
    if requested is not None:
        model_path = requested.resolve()
        if not model_path.is_file():
            raise FileNotFoundError(f"Model checkpoint does not exist: {model_path}")
        return str(model_path)
    dataset_models = sorted(dataset_root.rglob("*.pt"))
    best_model = next(
        (path for path in dataset_models if path.name.lower() == "best.pt"),
        None,
    )
    selected_model = best_model or (dataset_models[0] if dataset_models else None)
    return str(selected_model.resolve()) if selected_model else configured_model_name()


def zone_runtime() -> RetailZoneRuntime:
    return RetailZoneRuntime(
        version="cam_02-evaluation",
        zones=[
            ZoneSpec(
                zone_id="main_aisle",
                zone_name="Main Aisle",
                zone_type="aisle",
                priority=70,
                polygon_norm=[
                    [0.44, 0.22],
                    [0.68, 0.22],
                    [0.68, 0.96],
                    [0.44, 0.96],
                ],
            )
        ],
        lines=[],
    )


def main() -> None:
    args = parse_args()
    dataset_root = args.dataset.resolve()
    splits, samples = find_samples(dataset_root, args.split)
    names, yaml_path = dataset_names(dataset_root)
    if not names:
        names = infer_names_from_labels(samples[0][1].parent)
    ground_truth_person_id = person_class_id(names, "dataset labels")
    labels_available = any(label_path.is_file() for _, label_path in samples)
    model_name = find_model(dataset_root, args.model)

    detector = SupervisionYoloDetector(
        model_name,
        conf_thres=args.confidence,
        class_filter=None,
        iou=0.70,
        imgsz=1280,
        half=True,
    )
    model_person_id = person_class_id(names_dict(detector.names), "Vision model")
    detector.class_filter = [model_person_id]
    zone = zone_runtime()

    print(f"Dataset: {dataset_root}")
    print(f"data.yaml: {yaml_path or 'not found'}")
    print(f"Splits: {', '.join(splits)} ({len(samples)} images)")
    print(f"Vision model: {detector.model_path}")
    print(f"Ground-truth person class: {ground_truth_person_id}")
    print(f"Model person class: {model_person_id}")
    print("Line crossing skipped: image samples have no continuous tracking IDs.")
    if not labels_available:
        print("Warning: labels unavailable; detection accuracy metrics will be blank.")

    rows: list[dict[str, Any]] = []
    totals = {"gt": 0, "pred": 0, "zone": 0, "tp": 0, "fp": 0, "fn": 0}
    total_inference_time = 0.0

    for image_path, label_path in samples:
        frame = cv2.imread(str(image_path))
        if frame is None:
            print(f"Warning: cannot read image, skipped: {image_path}")
            continue
        frame = cv2.resize(frame, (CAMERA_WIDTH, CAMERA_HEIGHT))
        started = time.perf_counter()
        detections = detector.predict(frame)
        inference_time = time.perf_counter() - started
        tracks = detections_to_track_objects(detections, detector.names)
        raw_predictions = [tuple(map(float, track["bbox"])) for track in tracks]
        predictions = filter_boxes_by_zone(
            raw_predictions, zone, CAMERA_WIDTH, CAMERA_HEIGHT
        )
        ground_truth = read_ground_truth(
            label_path,
            ground_truth_person_id,
            CAMERA_WIDTH,
            CAMERA_HEIGHT,
        )
        ground_truth = filter_boxes_by_zone(
            ground_truth, zone, CAMERA_WIDTH, CAMERA_HEIGHT
        )
        zone_count = len(predictions)

        if labels_available:
            tp, fp, fn = greedy_match(predictions, ground_truth, args.iou)
            precision, recall, f1 = calculate_metrics(tp, fp, fn)
            metric_values: dict[str, Any] = {
                "ground_truth_count": len(ground_truth),
                "TP": tp,
                "FP": fp,
                "FN": fn,
                "precision": precision,
                "recall": recall,
                "f1_score": f1,
            }
            totals["gt"] += len(ground_truth)
            totals["tp"] += tp
            totals["fp"] += fp
            totals["fn"] += fn
        else:
            metric_values = {
                key: ""
                for key in (
                    "ground_truth_count",
                    "TP",
                    "FP",
                    "FN",
                    "precision",
                    "recall",
                    "f1_score",
                )
            }

        totals["pred"] += len(predictions)
        totals["zone"] += zone_count
        total_inference_time += inference_time
        rows.append(
            {
                "image_name": image_path.name,
                **metric_values,
                "prediction_count": len(predictions),
                "zone_person_count": zone_count,
                "inference_time_seconds": inference_time,
                "fps": 1 / inference_time if inference_time else 0.0,
            }
        )

    if labels_available:
        precision, recall, f1 = calculate_metrics(
            totals["tp"], totals["fp"], totals["fn"]
        )
        summary_metrics: dict[str, Any] = {
            "total_ground_truth": totals["gt"],
            "total_TP": totals["tp"],
            "total_FP": totals["fp"],
            "total_FN": totals["fn"],
            "overall_precision": precision,
            "overall_recall": recall,
            "overall_f1_score": f1,
        }
    else:
        summary_metrics = {
            key: ""
            for key in (
                "total_ground_truth",
                "total_TP",
                "total_FP",
                "total_FN",
                "overall_precision",
                "overall_recall",
                "overall_f1_score",
            )
        }

    summary = {
        "total_images": len(rows),
        **summary_metrics,
        "total_predictions": totals["pred"],
        "total_zone_person_count": totals["zone"],
        "total_inference_time_seconds": total_inference_time,
        "average_fps": len(rows) / total_inference_time
        if total_inference_time
        else 0.0,
    }
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "vision_metrics_per_image.csv", PER_IMAGE_COLUMNS, rows)
    write_csv(output_dir / "vision_metrics_summary.csv", SUMMARY_COLUMNS, [summary])

    print("\nFinal summary")
    for column in SUMMARY_COLUMNS:
        print(f"{column}: {summary[column]}")
    print(f"CSV output: {output_dir}")


if __name__ == "__main__":
    main()
