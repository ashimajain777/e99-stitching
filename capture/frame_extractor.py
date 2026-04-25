"""
Frame Extractor
================
Extracts individual frames from video at configurable intervals.
Ensures sufficient overlap for Structure-from-Motion reconstruction.
"""

import cv2
import json
import sys
from pathlib import Path
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def extract_frames(video_path: str, output_dir: str = None,
                   extraction_fps: float = None, max_frames: int = None) -> dict:
    """Extract frames from video at specified intervals.

    Args:
        video_path: Path to input video file.
        output_dir: Output directory for frames. None = config default.
        extraction_fps: Frames to extract per second. None = config default.
        max_frames: Maximum number of frames to extract. None = no limit.

    Returns:
        Dict with extraction metadata.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if output_dir is None:
        output_dir = config.FRAMES_ALL_DIR
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if extraction_fps is None:
        extraction_fps = config.EXTRACTION_FPS

    # Open video
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / max(video_fps, 1)

    # Calculate frame interval
    frame_interval = max(1, int(video_fps / extraction_fps))
    expected_output = min(
        total_frames // frame_interval,
        max_frames or float('inf')
    )

    print(f"  Video: {video_path.name}")
    print(f"  Source: {total_frames} frames @ {video_fps:.1f} FPS ({duration:.1f}s)")
    print(f"  Extracting: 1 frame every {frame_interval} frames ({extraction_fps:.1f} FPS)")
    print(f"  Expected output: ~{int(expected_output)} frames")
    print()

    extracted = []
    frame_idx = 0
    output_idx = 0

    pbar = tqdm(total=total_frames, desc="  Extracting frames", unit="frame")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0:
            # Save frame
            filename = f"frame_{output_idx:05d}.{config.FRAME_FORMAT}"
            filepath = output_dir / filename

            if config.FRAME_FORMAT == "jpg":
                cv2.imwrite(str(filepath), frame,
                            [cv2.IMWRITE_JPEG_QUALITY, config.FRAME_QUALITY])
            else:
                cv2.imwrite(str(filepath), frame)

            extracted.append({
                "index": output_idx,
                "filename": filename,
                "source_frame": frame_idx,
                "timestamp": round(frame_idx / max(video_fps, 1), 3),
            })
            output_idx += 1

            if max_frames and output_idx >= max_frames:
                break

        frame_idx += 1
        pbar.update(1)

    pbar.close()
    cap.release()

    # Save manifest
    manifest = {
        "source_video": str(video_path),
        "video_fps": video_fps,
        "extraction_fps": extraction_fps,
        "frame_interval": frame_interval,
        "total_extracted": len(extracted),
        "output_dir": str(output_dir),
        "frames": extracted,
    }

    manifest_path = output_dir / "frames_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n  ✅ Extracted {len(extracted)} frames → {output_dir}")
    print(f"  Manifest: {manifest_path}")

    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract frames from video")
    parser.add_argument("video", help="Path to input video file")
    parser.add_argument("--output", help="Output directory")
    parser.add_argument("--fps", type=float, help="Extraction rate (FPS)")
    parser.add_argument("--max-frames", type=int, help="Maximum frames to extract")
    args = parser.parse_args()

    print("=" * 60)
    print("  Frame Extractor")
    print("=" * 60)
    extract_frames(args.video, args.output, args.fps, args.max_frames)
