"""Ground-truth parsing and object-detection KPI helpers."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


PER_IMAGE_COLUMNS = [
    "image_name",
    "ground_truth_count",
    "prediction_count",
    "zone_person_count",
    "TP",
    "FP",
    "FN",
    "precision",
    "recall",
    "f1_score",
    "inference_time_seconds",
    "fps",
]
SUMMARY_COLUMNS = [
    "total_images",
    "total_ground_truth",
    "total_predictions",
    "total_zone_person_count",
    "total_TP",
    "total_FP",
    "total_FN",
    "overall_precision",
    "overall_recall",
    "overall_f1_score",
    "total_inference_time_seconds",
    "average_fps",
]
IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".webp"}


def names_dict(raw_names: Any) -> dict[int, str]:
    if isinstance(raw_names, list):
        return {index: str(name) for index, name in enumerate(raw_names)}
    if isinstance(raw_names, dict):
        return {int(index): str(name) for index, name in raw_names.items()}
    return {}


def person_class_id(names: dict[int, str], source: str) -> int:
    for class_id, name in names.items():
        if name.strip().lower() == "person":
            return class_id
    if len(names) == 1:
        class_id = next(iter(names))
        print(f"Warning: {source} has one class; assuming class {class_id} is person.")
        return class_id
    raise ValueError(f"Cannot identify person class in {source}: {names}")


def infer_names_from_labels(label_dir: Path) -> dict[int, str]:
    class_ids = set()
    for label_path in label_dir.glob("*.txt"):
        for line in label_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                class_ids.add(int(float(line.split()[0])))
    if len(class_ids) == 1:
        return {next(iter(class_ids)): "person"}
    return {class_id: str(class_id) for class_id in sorted(class_ids)}


def find_samples(
    dataset_root: Path, requested_split: str | None
) -> tuple[list[str], list[tuple[Path, Path]]]:
    split_names = ["train", "valid", "val", "test"] if requested_split == "all" else [
        requested_split or "test"
    ]
    samples = []
    found_splits = []
    for split in split_names:
        image_dir = dataset_root / split / "images"
        if not image_dir.is_dir():
            continue
        label_dir = image_dir.parent / "labels"
        found_splits.append(split)
        samples.extend(
            (image_path, label_dir / f"{image_path.stem}.txt")
            for image_path in sorted(image_dir.iterdir())
            if image_path.is_file()
            and image_path.suffix.lower() in IMAGE_EXTENSIONS
        )
    if not samples:
        raise FileNotFoundError("No evaluation images were found.")
    return found_splits, samples


def read_ground_truth(
    label_path: Path,
    class_id: int,
    image_width: int,
    image_height: int,
) -> list[tuple[float, float, float, float]]:
    if not label_path.is_file():
        return []

    boxes = []
    for line_number, line in enumerate(
        label_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        parts = line.split()
        if not parts:
            continue
        try:
            label_class = int(float(parts[0]))
        except ValueError:
            print(f"Warning: non-numeric class {label_path}:{line_number}")
            continue
        if label_class != class_id:
            continue
        try:
            coordinates = list(map(float, parts[1:]))
        except ValueError:
            print(f"Warning: non-numeric label {label_path}:{line_number}")
            continue
        if len(coordinates) == 4:
            center_x, center_y, width, height = coordinates
            box_width = width * image_width
            box_height = height * image_height
            x1 = center_x * image_width - box_width / 2
            y1 = center_y * image_height - box_height / 2
            boxes.append((x1, y1, x1 + box_width, y1 + box_height))
        elif len(coordinates) >= 6 and len(coordinates) % 2 == 0:
            x_values = coordinates[0::2]
            y_values = coordinates[1::2]
            boxes.append(
                (
                    min(x_values) * image_width,
                    min(y_values) * image_height,
                    max(x_values) * image_width,
                    max(y_values) * image_height,
                )
            )
        else:
            print(f"Warning: malformed label {label_path}:{line_number}")
    return boxes


def box_iou(box_a: tuple[float, ...], box_b: tuple[float, ...]) -> float:
    width = max(0.0, min(box_a[2], box_b[2]) - max(box_a[0], box_b[0]))
    height = max(0.0, min(box_a[3], box_b[3]) - max(box_a[1], box_b[1]))
    intersection = width * height
    area_a = max(0.0, box_a[2] - box_a[0]) * max(0.0, box_a[3] - box_a[1])
    area_b = max(0.0, box_b[2] - box_b[0]) * max(0.0, box_b[3] - box_b[1])
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def greedy_match(
    predictions: list[tuple[float, ...]],
    ground_truth: list[tuple[float, ...]],
    threshold: float,
) -> tuple[int, int, int]:
    pairs = []
    for prediction_index, prediction in enumerate(predictions):
        for truth_index, truth in enumerate(ground_truth):
            iou = box_iou(prediction, truth)
            if iou >= threshold:
                pairs.append((iou, prediction_index, truth_index))

    matched_predictions: set[int] = set()
    matched_truth: set[int] = set()
    for _, prediction_index, truth_index in sorted(pairs, reverse=True):
        if prediction_index in matched_predictions or truth_index in matched_truth:
            continue
        matched_predictions.add(prediction_index)
        matched_truth.add(truth_index)

    true_positives = len(matched_predictions)
    return (
        true_positives,
        len(predictions) - true_positives,
        len(ground_truth) - true_positives,
    )


def calculate_metrics(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1_score = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return precision, recall, f1_score


def filter_boxes_by_zone(
    boxes: list[tuple[float, ...]],
    zone: Any,
    image_width: int,
    image_height: int,
) -> list[tuple[float, ...]]:
    tracks = [{"bbox": list(box)} for box in boxes]
    assignments, _ = zone.assign(tracks, image_width, image_height)
    return [box for box, zones in zip(boxes, assignments) if zones]


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
