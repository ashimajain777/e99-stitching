"""
Keyframe Selector
==================
Filters extracted frames to keep only high-quality keyframes suitable
for 3D reconstruction. Rejects blurry, too-dark, too-bright, and
redundant/duplicate frames.
"""

import cv2
import json
import shutil
import sys
from pathlib import Path
from tqdm import tqdm
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def compute_blur_score(image: np.ndarray) -> float:
    """Compute blur score using Laplacian variance. Higher = sharper."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def compute_brightness(image: np.ndarray) -> float:
    """Compute mean brightness (0-255)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    return float(np.mean(gray))


def compute_motion_score(prev_gray: np.ndarray, curr_gray: np.ndarray) -> float:
    """Compute motion between two frames (mean absolute pixel difference)."""
    if prev_gray is None:
        return config.MOTION_MIN_THRESHOLD + 1  # Accept first frame
    diff = cv2.absdiff(prev_gray, curr_gray)
    return float(np.mean(diff))


def select_keyframes(input_dir: str = None, output_dir: str = None,
                     blur_threshold: float = None,
                     motion_min: float = None,
                     motion_max: float = None) -> dict:
    """Select high-quality keyframes from extracted frames.

    Args:
        input_dir: Directory containing extracted frames. None = config default.
        output_dir: Directory to copy selected keyframes. None = config default.
        blur_threshold: Laplacian variance threshold. None = config default.
        motion_min: Minimum motion to accept. None = config default.
        motion_max: Maximum motion to accept. None = config default.

    Returns:
        Dict with selection statistics.
    """
    if input_dir is None:
        input_dir = config.FRAMES_ALL_DIR
    if output_dir is None:
        output_dir = config.FRAMES_KEYFRAMES_DIR

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if blur_threshold is None:
        blur_threshold = config.BLUR_THRESHOLD
    if motion_min is None:
        motion_min = config.MOTION_MIN_THRESHOLD
    if motion_max is None:
        motion_max = config.MOTION_MAX_THRESHOLD

    # Find all image files
    extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
    image_files = sorted([
        f for f in input_dir.iterdir()
        if f.suffix.lower() in extensions
    ])

    if not image_files:
        print(f"  ❌ No images found in {input_dir}")
        return {"total": 0, "selected": 0}

    print(f"  Input: {len(image_files)} frames from {input_dir}")
    print(f"  Thresholds: blur>{blur_threshold:.0f}, "
          f"motion=[{motion_min:.0f}, {motion_max:.0f}], "
          f"brightness=[{config.BRIGHTNESS_MIN:.0f}, {config.BRIGHTNESS_MAX:.0f}]")
    print()

    selected = []
    rejected_blur = 0
    rejected_dark = 0
    rejected_bright = 0
    rejected_static = 0
    rejected_jump = 0

    prev_gray = None
    scores = []

    for img_path in tqdm(image_files, desc="  Analyzing frames", unit="frame"):
        image = cv2.imread(str(img_path))
        if image is None:
            continue

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # 1. Blur check
        blur_score = compute_blur_score(gray)

        # 2. Brightness check
        brightness = compute_brightness(gray)

        # 3. Motion check
        motion_score = compute_motion_score(prev_gray, gray)

        scores.append({
            "file": img_path.name,
            "blur": round(blur_score, 1),
            "brightness": round(brightness, 1),
            "motion": round(motion_score, 1),
        })

        # Apply filters
        accepted = True
        if blur_score < blur_threshold:
            rejected_blur += 1
            accepted = False
        elif brightness < config.BRIGHTNESS_MIN:
            rejected_dark += 1
            accepted = False
        elif brightness > config.BRIGHTNESS_MAX:
            rejected_bright += 1
            accepted = False
        elif motion_score < motion_min:
            rejected_static += 1
            accepted = False
        elif motion_score > motion_max:
            rejected_jump += 1
            accepted = False

        if accepted:
            selected.append(img_path)
            prev_gray = gray.copy()
        else:
            # Still update prev_gray to avoid cascading rejection
            if prev_gray is None:
                prev_gray = gray.copy()

    # If too few selected, lower thresholds and re-select
    if len(selected) < config.MIN_KEYFRAMES and len(image_files) >= config.MIN_KEYFRAMES:
        print(f"\n  ⚠️ Only {len(selected)} keyframes selected (min: {config.MIN_KEYFRAMES})")
        print(f"  Re-selecting with relaxed thresholds...")

        # Sort by blur score, take top N
        scores_sorted = sorted(scores, key=lambda s: s["blur"], reverse=True)
        selected = []
        for s in scores_sorted[:config.MIN_KEYFRAMES]:
            selected.append(input_dir / s["file"])

    # Copy selected keyframes to output directory
    print(f"\n  Copying {len(selected)} keyframes...")
    for idx, src_path in enumerate(sorted(selected)):
        dst_name = f"keyframe_{idx:05d}{src_path.suffix}"
        dst_path = output_dir / dst_name
        shutil.copy2(str(src_path), str(dst_path))

    # Statistics
    stats = {
        "total_frames": len(image_files),
        "selected": len(selected),
        "rejected_blur": rejected_blur,
        "rejected_dark": rejected_dark,
        "rejected_bright": rejected_bright,
        "rejected_static": rejected_static,
        "rejected_jump": rejected_jump,
        "acceptance_rate": round(len(selected) / max(len(image_files), 1) * 100, 1),
        "output_dir": str(output_dir),
    }

    # Save selection report
    report_path = output_dir / "keyframe_report.json"
    with open(report_path, "w") as f:
        json.dump({"stats": stats, "scores": scores}, f, indent=2)

    print(f"\n  ✅ Keyframe Selection Complete")
    print(f"  Selected: {stats['selected']}/{stats['total_frames']} "
          f"({stats['acceptance_rate']}%)")
    print(f"  Rejected — blur: {rejected_blur}, dark: {rejected_dark}, "
          f"bright: {rejected_bright}, static: {rejected_static}, jump: {rejected_jump}")
    print(f"  Output: {output_dir}")

    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Select keyframes from extracted frames")
    parser.add_argument("--input", help="Input frames directory")
    parser.add_argument("--output", help="Output keyframes directory")
    parser.add_argument("--blur", type=float, help="Blur threshold")
    args = parser.parse_args()

    print("=" * 60)
    print("  Keyframe Selector")
    print("=" * 60)
    select_keyframes(args.input, args.output, args.blur)
