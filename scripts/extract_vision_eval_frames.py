"""Extract evenly distributed frames from one or more videos."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

import cv2


VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    fps: float
    frame_count: int
    duration_seconds: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract frames distributed evenly across the combined video duration."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        default=[Path("data/videos/video_main.mp4")],
        help="Video files or directories containing videos.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("vision_eval/images"),
        help="Directory for extracted JPEG images.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=180,
        help="Total number of frames to extract.",
    )
    parser.add_argument(
        "--start-sample",
        type=int,
        default=1,
        help="One-based sample number to resume from.",
    )
    return parser.parse_args()


def find_videos(inputs: list[Path]) -> list[Path]:
    videos: set[Path] = set()

    for input_path in inputs:
        if input_path.is_file() and input_path.suffix.lower() in VIDEO_EXTENSIONS:
            videos.add(input_path.resolve())
        elif input_path.is_dir():
            videos.update(
                path.resolve()
                for path in input_path.rglob("*")
                if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
            )
        else:
            raise FileNotFoundError(f"Video input does not exist: {input_path}")

    if not videos:
        raise ValueError("No supported video files were found.")

    return sorted(videos)


def inspect_video(path: Path) -> VideoInfo:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")

    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    capture.release()

    if fps <= 0 or frame_count <= 0:
        raise RuntimeError(f"Invalid video metadata: {path}")

    return VideoInfo(
        path=path,
        fps=fps,
        frame_count=frame_count,
        duration_seconds=frame_count / fps,
    )


def extract_frames(
    videos: list[VideoInfo],
    output_dir: Path,
    count: int,
    start_sample: int = 1,
) -> int:
    if count <= 0:
        raise ValueError("Frame count must be greater than zero.")
    if start_sample < 1 or start_sample > count:
        raise ValueError("Start sample must be between 1 and the frame count.")

    total_duration = sum(video.duration_seconds for video in videos)
    if total_duration <= 0:
        raise ValueError("Combined video duration must be greater than zero.")

    output_dir.mkdir(parents=True, exist_ok=True)

    cumulative_ends: list[float] = []
    elapsed = 0.0
    for video in videos:
        elapsed += video.duration_seconds
        cumulative_ends.append(elapsed)

    targets_by_video: dict[Path, list[tuple[int, int]]] = {
        video.path: [] for video in videos
    }

    for sample_index in range(start_sample - 1, count):
        global_time = (sample_index + 0.5) * total_duration / count
        video_index = min(bisect_right(cumulative_ends, global_time), len(videos) - 1)
        video = videos[video_index]
        video_start = 0.0 if video_index == 0 else cumulative_ends[video_index - 1]
        local_time = global_time - video_start
        frame_index = min(int(local_time * video.fps), video.frame_count - 1)
        targets_by_video[video.path].append((sample_index, frame_index))

    saved = 0
    for video in videos:
        targets = targets_by_video[video.path]
        if not targets:
            continue

        video_output_dir = output_dir / video.path.stem
        video_output_dir.mkdir(parents=True, exist_ok=True)

        capture = cv2.VideoCapture(str(video.path))
        if not capture.isOpened():
            raise RuntimeError(f"Cannot open video: {video.path}")

        target_position = 0
        first_target_frame = targets[0][1]
        last_target_frame = targets[-1][1]
        start_frame = max(first_target_frame - 250, 0)
        capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        try:
            for frame_index in range(start_frame, last_target_frame + 1):
                if not capture.grab():
                    raise RuntimeError(
                        f"Cannot read frame {frame_index} from video: {video.path}"
                    )

                if (
                    target_position >= len(targets)
                    or targets[target_position][1] != frame_index
                ):
                    continue

                ok, frame = capture.retrieve()
                if not ok:
                    raise RuntimeError(
                        f"Cannot decode frame {frame_index} from video: {video.path}"
                    )

                while target_position < len(targets) and (
                    targets[target_position][1] == frame_index
                ):
                    sample_index, _ = targets[target_position]
                    filename = (
                        f"{sample_index + 1:04d}_{video.path.stem}_"
                        f"frame_{frame_index:08d}.jpg"
                    )
                    image_path = video_output_dir / filename
                    if not cv2.imwrite(str(image_path), frame):
                        raise RuntimeError(
                            f"Cannot write image: {image_path}"
                        )

                    saved += 1
                    target_position += 1
        finally:
            capture.release()

    return saved


def main() -> None:
    args = parse_args()
    video_paths = find_videos(args.inputs)
    videos = [inspect_video(path) for path in video_paths]

    for video in videos:
        print(
            f"Video: {video.path} | frames={video.frame_count} | "
            f"fps={video.fps:.3f} | duration={video.duration_seconds:.2f}s"
        )

    saved = extract_frames(videos, args.output, args.count, args.start_sample)
    print(f"Extracted {saved} frames to {args.output.resolve()}")


if __name__ == "__main__":
    main()
