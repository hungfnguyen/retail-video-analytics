import argparse
import importlib.machinery
import logging
import sys
import time
from pathlib import Path
from types import ModuleType

import cv2
import numpy as np
import torch
import yaml


VISION_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = VISION_ROOT.parent.parent
EXTERNAL_ROOT = PROJECT_ROOT / "Multi-Camera-Multi-Object-Tracking"

DEFAULT_EXP_FILE = EXTERNAL_ROOT / "exps" / "example" / "mot" / "yolox_x_mix_det.py"
DEFAULT_DETECTOR_CKPT = EXTERNAL_ROOT / "pretrained" / "bytetrack_x_mot17.pth.tar"
DEFAULT_REID_MODEL = (
    EXTERNAL_ROOT
    / "pretrained"
    / "osnet_ain_x1_0_msmt17_256x128_amsgrad_ep50_lr0.0015_coslr_b64_fb10_softmax_labsmth_flip_jitter.pth"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "runtime" / "main2_external_deepsort"


def _install_external_imports(external_root: Path) -> None:
    if not external_root.exists():
        raise FileNotFoundError(f"External tracking folder not found: {external_root}")
    if "loguru" not in sys.modules:
        loguru_module = ModuleType("loguru")
        loguru_module.__spec__ = importlib.machinery.ModuleSpec("loguru", loader=None)
        loguru_module.logger = logging.getLogger("external-yolox")
        sys.modules["loguru"] = loguru_module
    if "tabulate" not in sys.modules:
        tabulate_module = ModuleType("tabulate")
        tabulate_module.__spec__ = importlib.machinery.ModuleSpec("tabulate", loader=None)
        tabulate_module.tabulate = lambda rows, headers=(), **_: "\n".join(
            " ".join(map(str, row)) if isinstance(row, (list, tuple)) else str(row)
            for row in rows
        )
        sys.modules["tabulate"] = tabulate_module
    if "pycocotools" not in sys.modules:
        pycocotools_module = ModuleType("pycocotools")
        pycocotools_module.__spec__ = importlib.machinery.ModuleSpec("pycocotools", loader=None)
        coco_module = ModuleType("pycocotools.coco")
        coco_module.__spec__ = importlib.machinery.ModuleSpec("pycocotools.coco", loader=None)
        coco_module.COCO = object
        mask_module = ModuleType("pycocotools.mask")
        mask_module.__spec__ = importlib.machinery.ModuleSpec("pycocotools.mask", loader=None)
        sys.modules["pycocotools"] = pycocotools_module
        sys.modules["pycocotools.coco"] = coco_module
        sys.modules["pycocotools.mask"] = mask_module
    if "torch.utils.tensorboard" not in sys.modules:
        tensorboard_module = ModuleType("torch.utils.tensorboard")
        tensorboard_module.__spec__ = importlib.machinery.ModuleSpec(
            "torch.utils.tensorboard", loader=None
        )

        class SummaryWriter:
            def __init__(self, *_, **__):
                pass

            def __getattr__(self, _):
                return lambda *__, **___: None

        tensorboard_module.SummaryWriter = SummaryWriter
        sys.modules["torch.utils.tensorboard"] = tensorboard_module
    sys.path.insert(0, str(external_root))
    sys.path.insert(0, str(external_root / "tools"))


def _patch_legacy_numpy_aliases() -> None:
    if not hasattr(np, "float"):
        np.float = float
    if not hasattr(np, "int"):
        np.int = int


def _load_camera_source(camera_id: str | None, source: str | None) -> tuple[str, str]:
    if source:
        return camera_id or "manual_camera", source

    config_path = PROJECT_ROOT / "configs" / "cameras.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cameras = cfg.get("cameras", [])
    if camera_id:
        matches = [camera for camera in cameras if camera.get("camera_id") == camera_id]
    else:
        matches = [camera for camera in cameras if camera.get("enabled", True)]

    if not matches:
        raise ValueError("No matching camera found in configs/cameras.yaml")

    camera = matches[0]
    source_uri = camera["source_uri"]
    source_path = Path(source_uri)
    if not source_path.is_absolute():
        source_path = PROJECT_ROOT / source_path

    return camera["camera_id"], str(source_path)


def _load_detector(exp_file: Path, ckpt_path: Path, device: torch.device, conf: float, nms: float):
    from yolox.exp import get_exp
    from yolox.utils import fuse_model

    exp = get_exp(str(exp_file), None)
    exp.test_conf = conf
    exp.nmsthre = nms

    model = exp.get_model().to(device)
    checkpoint = torch.load(str(ckpt_path), map_location="cpu")
    model.load_state_dict(checkpoint["model"])
    model.eval()
    model = fuse_model(model)
    return exp, model


def _build_predictor(model, exp, device: torch.device):
    from yolox.data.data_augment import preproc
    from yolox.utils import postprocess

    class ExternalYoloxPredictor:
        def __init__(self):
            self.model = model
            self.num_classes = exp.num_classes
            self.confthre = exp.test_conf
            self.nmsthre = exp.nmsthre
            self.test_size = exp.test_size
            self.device = device
            self.rgb_means = (0.485, 0.456, 0.406)
            self.std = (0.229, 0.224, 0.225)

        def inference(self, frame, timer):
            img_info = {"id": 0, "file_name": None}
            height, width = frame.shape[:2]
            img_info["height"] = height
            img_info["width"] = width
            img_info["raw_img"] = frame

            image, ratio = preproc(frame, self.test_size, self.rgb_means, self.std)
            img_info["ratio"] = ratio
            image = torch.from_numpy(image).unsqueeze(0).float().to(self.device)

            with torch.no_grad():
                timer.tic()
                outputs = self.model(image)
                outputs = postprocess(outputs, self.num_classes, self.confthre, self.nmsthre)
            return outputs, img_info

    return ExternalYoloxPredictor()


def _load_reid_model(model_path: Path, use_cuda: bool):
    from torchreid.reid.utils.feature_extractor import FeatureExtractor

    device = "cuda" if use_cuda and torch.cuda.is_available() else "cpu"
    return FeatureExtractor(
        model_name="osnet_ain_x1_0",
        model_path=str(model_path),
        device=device,
    )


def _create_deepsort(max_dist: float, max_age: int, n_init: int, nn_budget: int):
    from yolox.deepsort_tracker.deepsort import NearestNeighborDistanceMetric, Tracker

    metric = NearestNeighborDistanceMetric("cosine", max_dist, nn_budget)
    return Tracker(metric, max_iou_distance=0.7, max_age=max_age, n_init=n_init)


def _extract_detections(outputs, img_info, exp, class_id: int, min_confidence: float):
    if outputs is None:
        return [], [], []

    output = outputs.cpu().numpy()
    bboxes = output[:, :4] / img_info["ratio"]
    scores = output[:, 4] * output[:, 5]
    cls_ids = output[:, 6].astype(int)

    kept_boxes = []
    kept_scores = []
    kept_classes = []
    for bbox, score, cls in zip(bboxes, scores, cls_ids):
        if cls != class_id or score < min_confidence:
            continue

        x1, y1, x2, y2 = bbox
        w = max(0.0, x2 - x1)
        h = max(0.0, y2 - y1)
        if w <= 1 or h <= 1:
            continue

        kept_boxes.append([float(x1), float(y1), float(w), float(h)])
        kept_scores.append(float(score))
        kept_classes.append(int(cls))

    return kept_boxes, kept_scores, kept_classes


def _extract_reid_features(frame, boxes_tlwh, reid_model):
    crops = []
    height, width = frame.shape[:2]
    for x, y, w, h in boxes_tlwh:
        x1 = max(0, int(x))
        y1 = max(0, int(y))
        x2 = min(width - 1, int(x + w))
        y2 = min(height - 1, int(y + h))
        if x2 <= x1 or y2 <= y1:
            crops.append(None)
            continue
        crops.append(frame[y1:y2, x1:x2])

    valid_crops = [crop for crop in crops if crop is not None and crop.size > 0]
    if not valid_crops:
        return []

    raw_features = reid_model(valid_crops)
    if hasattr(raw_features, "detach"):
        raw_features = raw_features.detach().cpu().numpy()

    features = []
    feature_index = 0
    for crop in crops:
        if crop is None or crop.size == 0:
            features.append(None)
            continue
        features.append(raw_features[feature_index])
        feature_index += 1
    return features


def _update_deepsort(tracker, boxes_tlwh, scores, classes, features):
    from yolox.deepsort_tracker.detection import Detection

    detections = []
    detection_classes = []
    for box, score, cls, feature in zip(boxes_tlwh, scores, classes, features):
        if feature is None:
            continue
        detections.append(Detection(box, score, feature))
        detection_classes.append(cls)

    tracker.predict()
    tracker.update(detections, np.asarray(detection_classes))

    tracks = []
    for track in tracker.tracks:
        if not track.is_confirmed() or track.time_since_update > 1:
            continue
        x, y, w, h = track.to_tlwh()
        tracks.append(
            {
                "track_id": int(track.track_id),
                "tlwh": [float(x), float(y), float(w), float(h)],
                "class_id": int(track.class_id),
            }
        )
    return tracks


def _draw_tracks(frame, tracks, frame_id: int, fps: float):
    from yolox.utils.visualize import plot_tracking

    return plot_tracking(
        frame,
        [track["tlwh"] for track in tracks],
        [track["track_id"] for track in tracks],
        frame_id=frame_id,
        fps=fps,
    )


def _write_results(csv_path: Path, rows: list[str]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(
        "frame,track_id,x,y,w,h,class_id\n" + "".join(rows),
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> None:
    _install_external_imports(Path(args.external_root))
    _patch_legacy_numpy_aliases()

    camera_id, source = _load_camera_source(args.camera_id, args.source)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device(
        "cuda"
        if args.device == "auto" and torch.cuda.is_available()
        else args.device if args.device != "auto" else "cpu"
    )
    if args.force_gpu and device.type != "cuda":
        raise RuntimeError("GPU was requested, but CUDA is not available.")

    logging.info("Camera: %s", camera_id)
    logging.info("Source: %s", source)
    logging.info("Device: %s", device)
    logging.info("Detector checkpoint: %s", args.detector_ckpt)
    logging.info("ReID model: %s", args.reid_model)

    exp, detector = _load_detector(
        Path(args.exp_file),
        Path(args.detector_ckpt),
        device,
        conf=args.conf,
        nms=args.nms,
    )
    predictor = _build_predictor(detector, exp, device)
    reid_model = _load_reid_model(Path(args.reid_model), use_cuda=device.type == "cuda")
    tracker = _create_deepsort(
        max_dist=args.max_dist,
        max_age=args.max_age,
        n_init=args.n_init,
        nn_budget=args.nn_budget,
    )

    from yolox.tracking_utils.timer import Timer

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video source: {source}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    source_fps = cap.get(cv2.CAP_PROP_FPS) or args.fps
    output_video_path = output_dir / f"{camera_id}_main2_external_deepsort.mp4"
    output_csv_path = output_dir / f"{camera_id}_main2_external_deepsort.csv"

    writer = None
    if args.save_video:
        writer = cv2.VideoWriter(
            str(output_video_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            source_fps,
            (width, height),
        )

    timer = Timer()
    rows = []
    frame_id = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_id += 1

            outputs, img_info = predictor.inference(frame, timer)
            boxes, scores, classes = _extract_detections(
                outputs[0],
                img_info,
                exp,
                class_id=args.class_id,
                min_confidence=args.track_thresh,
            )
            features = _extract_reid_features(frame, boxes, reid_model)
            tracks = _update_deepsort(tracker, boxes, scores, classes, features)

            timer.toc()
            fps = 1.0 / max(timer.average_time, 1e-5)
            annotated = _draw_tracks(frame, tracks, frame_id, fps)

            for track in tracks:
                x, y, w, h = track["tlwh"]
                rows.append(
                    f"{frame_id},{track['track_id']},{x:.2f},{y:.2f},{w:.2f},{h:.2f},{track['class_id']}\n"
                )

            if writer:
                writer.write(annotated)
            if args.show:
                cv2.imshow("main2 external DeepSORT", annotated)
                if cv2.waitKey(1) & 0xFF in {27, ord("q")}:
                    break

            if frame_id % args.log_every == 0:
                logging.info("Processed frame=%d fps=%.2f tracks=%d", frame_id, fps, len(tracks))

            if args.max_frames > 0 and frame_id >= args.max_frames:
                break
    finally:
        cap.release()
        if writer:
            writer.release()
        if args.show:
            cv2.destroyAllWindows()

    _write_results(output_csv_path, rows)
    logging.info("Saved CSV: %s", output_csv_path)
    if args.save_video:
        logging.info("Saved video: %s", output_video_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test one-camera tracking with external YOLOX + external DeepSORT source."
    )
    parser.add_argument("--camera-id", default=None)
    parser.add_argument("--source", default=None)
    parser.add_argument("--external-root", default=str(EXTERNAL_ROOT))
    parser.add_argument("--exp-file", default=str(DEFAULT_EXP_FILE))
    parser.add_argument("--detector-ckpt", default=str(DEFAULT_DETECTOR_CKPT))
    parser.add_argument("--reid-model", default=str(DEFAULT_REID_MODEL))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    parser.add_argument("--force-gpu", action="store_true")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--nms", type=float, default=0.45)
    parser.add_argument("--track-thresh", type=float, default=0.25)
    parser.add_argument("--class-id", type=int, default=0)
    parser.add_argument("--max-dist", type=float, default=0.2)
    parser.add_argument("--max-age", type=int, default=30)
    parser.add_argument("--n-init", type=int, default=3)
    parser.add_argument("--nn-budget", type=int, default=100)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--log-every", type=int, default=30)
    parser.add_argument("--save-video", action="store_true")
    parser.add_argument("--show", action="store_true")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [main2] %(levelname)s %(message)s",
    )
    run(parse_args())


if __name__ == "__main__":
    main()
