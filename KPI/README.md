# Vision KPI Evaluation

This folder evaluates the repository Vision detector against the annotated
YOLO dataset. Only people whose bounding-box `bottom_center` lies inside the
provided `main_aisle` polygon are included in the KPI calculation.

## Folder Structure

```text
KPI/
  evaluate.py
  metrics.py
  README.md
  src/       Annotated dataset snapshot used for measurement
  result/    Generated KPI evidence CSV files
```

## Evaluation Configuration

- Camera: `cam_02`
- Resolution: `1280 x 720`
- Confidence threshold: `0.25`
- IoU matching threshold: `0.50`
- Zone polygon: `[(0.44, 0.22), (0.68, 0.22), (0.68, 0.96), (0.44, 0.96)]`
- Matching: greedy matching by highest IoU
- Default dataset scope: all `train`, `valid`, and `test` images

Line-crossing metrics are not calculated because the dataset contains
independent images without continuous tracking IDs.

## Run the Full Evidence Evaluation

Open PowerShell in the repository root:

```powershell
.\.venv\Scripts\python.exe KPI\evaluate.py
```

The command evaluates all available dataset splits and writes:

```text
KPI/result/vision_metrics_per_image.csv
KPI/result/vision_metrics_summary.csv
```

The terminal also prints the final TP, FP, FN, Precision, Recall, F1-score,
inference time, and FPS.

## Run Only the Test Split

```powershell
.\.venv\Scripts\python.exe KPI\evaluate.py --split test
```

Use the test-only result when reporting model generalization. The full result
includes training images and is intended as evidence that the complete
annotated dataset was processed.

## Use a Different Model

```powershell
.\.venv\Scripts\python.exe KPI\evaluate.py --model "D:\path\to\best.pt"
```

When `--model` is omitted, the evaluator uses a dataset checkpoint when one is
available; otherwise, it uses the model configured by the Vision module.

## Optional Thresholds

```powershell
.\.venv\Scripts\python.exe KPI\evaluate.py --confidence 0.25 --iou 0.50
```
