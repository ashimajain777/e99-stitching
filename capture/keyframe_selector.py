"""
Frame Filter & Viewpoint Clusterer
=====================================
Two responsibilities:
1. Filter out bad frames (blurry, too dark, too bright)
2. Cluster remaining frames into viewpoint groups for panorama stitching
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
        return 0.0  # First frame — no motion
    diff = cv2.absdiff(prev_gray, curr_gray)
    return float(np.mean(diff))


# =========================================================================
# Stage 1: Quality Filtering
# =========================================================================

def filter_frames(input_dir: str = None, output_dir: str = None,
                  blur_threshold: float = None) -> dict:
    """Filter frames by quality — remove blurry, too dark, too bright.

    Args:
        input_dir: Directory containing extracted frames. None = config default.
        output_dir: Directory to copy good frames. None = config default.
        blur_threshold: Laplacian variance threshold. None = config default.

    Returns:
        Dict with filtering statistics.
    """
    if input_dir is None:
        input_dir = config.FRAMES_ALL_DIR
    if output_dir is None:
        output_dir = config.FRAMES_FILTERED_DIR

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if blur_threshold is None:
        blur_threshold = config.BLUR_THRESHOLD

    # Find all image files
    extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
    image_files = sorted([
        f for f in input_dir.iterdir()
        if f.suffix.lower() in extensions
    ])

    if not image_files:
        print(f"  [FAIL] No images found in {input_dir}")
        return {"total": 0, "accepted": 0}

    print(f"  Input: {len(image_files)} frames from {input_dir}")
    print(f"  Thresholds: blur>{blur_threshold:.0f}, "
          f"brightness=[{config.BRIGHTNESS_MIN:.0f}, {config.BRIGHTNESS_MAX:.0f}]")
    print()

    accepted = []
    rejected_blur = 0
    rejected_dark = 0
    rejected_bright = 0

    for img_path in tqdm(image_files, desc="  Filtering frames", unit="frame"):
        image = cv2.imread(str(img_path))
        if image is None:
            continue

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Blur check
        blur_score = compute_blur_score(gray)
        if blur_score < blur_threshold:
            rejected_blur += 1
            continue

        # Brightness check
        brightness = compute_brightness(gray)
        if brightness < config.BRIGHTNESS_MIN:
            rejected_dark += 1
            continue
        if brightness > config.BRIGHTNESS_MAX:
            rejected_bright += 1
            continue

        accepted.append(img_path)

    # Copy accepted frames
    print(f"\n  Copying {len(accepted)} accepted frames...")
    for idx, src_path in enumerate(accepted):
        dst_name = f"frame_{idx:05d}{src_path.suffix}"
        dst_path = output_dir / dst_name
        shutil.copy2(str(src_path), str(dst_path))

    stats = {
        "total_frames": len(image_files),
        "accepted": len(accepted),
        "rejected_blur": rejected_blur,
        "rejected_dark": rejected_dark,
        "rejected_bright": rejected_bright,
        "acceptance_rate": round(len(accepted) / max(len(image_files), 1) * 100, 1),
        "output_dir": str(output_dir),
    }

    # Save report
    report_path = output_dir / "filter_report.json"
    with open(report_path, "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\n  [OK] Frame Filtering Complete")
    print(f"  Accepted: {stats['accepted']}/{stats['total_frames']} "
          f"({stats['acceptance_rate']}%)")
    print(f"  Rejected — blur: {rejected_blur}, dark: {rejected_dark}, "
          f"bright: {rejected_bright}")
    print(f"  Output: {output_dir}")

    return stats


# =========================================================================
# Stage 2: Viewpoint Clustering
# =========================================================================

def cluster_into_viewpoints(input_dir: str = None, output_dir: str = None,
                            motion_threshold: float = None) -> dict:
    """Cluster consecutive frames into viewpoint groups.

    Frames where the drone is roughly stationary (low inter-frame motion)
    are grouped together into one viewpoint. A spike in motion signals
    the start of a new viewpoint.

    Args:
        input_dir: Directory containing filtered/enhanced frames.
        output_dir: Directory to create viewpoint subdirectories.
        motion_threshold: Pixel diff threshold for new viewpoint.

    Returns:
        Dict with clustering results and viewpoint metadata.
    """
    if input_dir is None:
        input_dir = config.ENHANCED_DIR
    if output_dir is None:
        output_dir = config.VIEWPOINTS_DIR

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if motion_threshold is None:
        motion_threshold = config.CLUSTER_MOTION_THRESHOLD

    # Find all image files
    extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
    image_files = sorted([
        f for f in input_dir.iterdir()
        if f.suffix.lower() in extensions
    ])

    if not image_files:
        print(f"  [FAIL] No images found in {input_dir}")
        return {"total_frames": 0, "viewpoints": 0}

    print(f"  Input: {len(image_files)} frames from {input_dir}")
    print(f"  Motion threshold: {motion_threshold:.1f} (pixel diff for new viewpoint)")
    print()

    # ── Pass 1: Compute inter-frame motion scores ──
    motion_scores = []
    prev_gray = None

    for img_path in tqdm(image_files, desc="  Computing motion", unit="frame"):
        image = cv2.imread(str(img_path))
        if image is None:
            motion_scores.append(0.0)
            continue

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Resize for faster comparison
        small = cv2.resize(gray, (320, 240))

        score = compute_motion_score(prev_gray, small)
        motion_scores.append(score)
        prev_gray = small.copy()

    # ── Pass 2: Find viewpoint boundaries ──
    # A new viewpoint starts where motion exceeds threshold
    boundaries = [0]  # First frame always starts a viewpoint
    for i, score in enumerate(motion_scores):
        if i == 0:
            continue
        if score > motion_threshold:
            boundaries.append(i)

    # Add end marker
    boundaries.append(len(image_files))

    # ── Build viewpoint groups ──
    raw_groups = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        if end > start:
            raw_groups.append(list(range(start, end)))

    # ── Enforce min/max constraints ──
    # Merge groups that are too small with their neighbor
    groups = []
    for g in raw_groups:
        if len(g) < config.CLUSTER_MIN_FRAMES and groups:
            # Merge with previous group
            groups[-1].extend(g)
        else:
            groups.append(g)

    # Split groups that are too large
    final_groups = []
    for g in groups:
        if len(g) > config.CLUSTER_MAX_FRAMES:
            # Split into chunks
            for i in range(0, len(g), config.CLUSTER_MAX_FRAMES):
                chunk = g[i:i + config.CLUSTER_MAX_FRAMES]
                if len(chunk) >= config.CLUSTER_MIN_FRAMES:
                    final_groups.append(chunk)
                elif final_groups:
                    final_groups[-1].extend(chunk)
        else:
            final_groups.append(g)

    # Enforce total viewpoint count
    if len(final_groups) < config.CLUSTER_MIN_VIEWPOINTS:
        # Too few — split the largest groups evenly
        while len(final_groups) < config.CLUSTER_MIN_VIEWPOINTS:
            # Find largest group
            largest_idx = max(range(len(final_groups)), key=lambda i: len(final_groups[i]))
            g = final_groups[largest_idx]
            if len(g) < 2 * config.CLUSTER_MIN_FRAMES:
                break  # Can't split further
            mid = len(g) // 2
            final_groups[largest_idx] = g[:mid]
            final_groups.insert(largest_idx + 1, g[mid:])

    if len(final_groups) > config.CLUSTER_MAX_VIEWPOINTS:
        # Too many — merge smallest adjacent groups
        while len(final_groups) > config.CLUSTER_MAX_VIEWPOINTS:
            # Find smallest group
            smallest_idx = min(range(len(final_groups)), key=lambda i: len(final_groups[i]))
            if smallest_idx > 0:
                final_groups[smallest_idx - 1].extend(final_groups[smallest_idx])
                final_groups.pop(smallest_idx)
            elif smallest_idx < len(final_groups) - 1:
                final_groups[smallest_idx + 1] = final_groups[smallest_idx] + final_groups[smallest_idx + 1]
                final_groups.pop(smallest_idx)
            else:
                break

    # ── Copy frames into viewpoint directories ──
    viewpoint_meta = []
    print(f"\n  Creating {len(final_groups)} viewpoint groups...")

    for vp_idx, frame_indices in enumerate(final_groups):
        vp_dir = output_dir / f"vp_{vp_idx:03d}"
        vp_dir.mkdir(parents=True, exist_ok=True)

        vp_frames = []
        best_blur = -1
        best_frame = None

        for local_idx, global_idx in enumerate(frame_indices):
            src_path = image_files[global_idx]
            dst_name = f"frame_{local_idx:03d}{src_path.suffix}"
            dst_path = vp_dir / dst_name
            shutil.copy2(str(src_path), str(dst_path))
            vp_frames.append(dst_name)

            # Track sharpest frame (for single-frame fallback)
            img = cv2.imread(str(src_path))
            if img is not None:
                blur = compute_blur_score(img)
                if blur > best_blur:
                    best_blur = blur
                    best_frame = dst_name

        # Compute average motion within this viewpoint
        vp_motions = [motion_scores[i] for i in frame_indices if i < len(motion_scores)]
        avg_motion = np.mean(vp_motions) if vp_motions else 0.0

        viewpoint_meta.append({
            "id": f"vp_{vp_idx:03d}",
            "index": vp_idx,
            "num_frames": len(frame_indices),
            "frame_range": [frame_indices[0], frame_indices[-1]],
            "avg_internal_motion": round(float(avg_motion), 2),
            "best_frame": best_frame,
            "directory": str(vp_dir),
            "frames": vp_frames,
        })

    # Save clustering report
    report = {
        "total_frames": len(image_files),
        "num_viewpoints": len(final_groups),
        "motion_threshold": motion_threshold,
        "viewpoints": viewpoint_meta,
    }

    report_path = output_dir / "viewpoints_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n  [OK] Viewpoint Clustering Complete")
    print(f"  Viewpoints: {len(final_groups)}")
    for vp in viewpoint_meta:
        print(f"    {vp['id']}: {vp['num_frames']} frames "
              f"(motion={vp['avg_internal_motion']:.1f})")
    print(f"  Report: {report_path}")

    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Filter frames and cluster into viewpoints")
    parser.add_argument("--mode", choices=["filter", "cluster", "both"], default="both",
                        help="Which stage to run")
    parser.add_argument("--input", help="Input frames directory")
    parser.add_argument("--output", help="Output directory")
    parser.add_argument("--blur", type=float, help="Blur threshold")
    parser.add_argument("--motion", type=float, help="Motion threshold for clustering")
    args = parser.parse_args()

    if args.mode in ("filter", "both"):
        print("=" * 60)
        print("  Frame Filter")
        print("=" * 60)
        filter_frames(args.input, args.output, args.blur)

    if args.mode in ("cluster", "both"):
        print("\n" + "=" * 60)
        print("  Viewpoint Clustering")
        print("=" * 60)
        cluster_into_viewpoints(args.input, args.output, args.motion)
