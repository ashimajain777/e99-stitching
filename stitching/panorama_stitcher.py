"""
Panorama Stitcher
==================
Stitches frames from each viewpoint cluster into equirectangular panoramas.

Strategy:
1. Try OpenCV's built-in Stitcher (best quality, handles auto-alignment)
2. Fallback to custom cylindrical warp + feature matching
3. Last resort: use the single sharpest frame, padded to equirectangular
"""

import cv2
import json
import sys
import math
import numpy as np
from pathlib import Path
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def estimate_focal_length(image_width: int, fov_degrees: float) -> float:
    """Estimate focal length in pixels from horizontal field of view."""
    return image_width / (2.0 * math.tan(math.radians(fov_degrees / 2.0)))


def cylindrical_warp(img: np.ndarray, focal_length: float) -> np.ndarray:
    """Apply cylindrical projection to an image.

    Projects the image onto a virtual cylinder to reduce perspective
    distortion before stitching. Essential for wide-angle drone cameras.

    Args:
        img: Input BGR image.
        focal_length: Camera focal length in pixels.

    Returns:
        Cylindrically warped image.
    """
    h, w = img.shape[:2]
    cx, cy = w / 2.0, h / 2.0

    # Build coordinate maps
    y_coords, x_coords = np.mgrid[0:h, 0:w].astype(np.float32)

    # Normalize to camera coordinates
    x_norm = (x_coords - cx) / focal_length
    y_norm = (y_coords - cy) / focal_length

    # Cylindrical projection
    theta = x_norm
    h_cyl = y_norm

    # Map back to image coordinates
    x_mapped = focal_length * np.tan(theta) + cx
    y_mapped = focal_length * h_cyl / np.cos(theta) + cy

    # Apply remapping
    warped = cv2.remap(img, x_mapped, y_mapped,
                       cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_CONSTANT,
                       borderValue=(0, 0, 0))

    # Crop black borders
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        x, y, cw, ch = cv2.boundingRect(max(contours, key=cv2.contourArea))
        warped = warped[y:y+ch, x:x+cw]

    return warped


def pad_to_equirectangular(img: np.ndarray, target_width: int = None) -> np.ndarray:
    """Pad a partial panorama or single frame to equirectangular format.

    Creates a 2:1 aspect ratio image with the source centered and
    the remainder filled with a smooth dark gradient.

    Args:
        img: Source image (any aspect ratio).
        target_width: Target width. Height will be width/2.

    Returns:
        Equirectangular-formatted image.
    """
    if target_width is None:
        target_width = config.PANO_OUTPUT_WIDTH

    target_height = target_width // 2
    h, w = img.shape[:2]

    # Create dark background with subtle gradient
    equirect = np.zeros((target_height, target_width, 3), dtype=np.uint8)

    # Add subtle radial gradient for aesthetic
    cy, cx = target_height // 2, target_width // 2
    Y, X = np.ogrid[:target_height, :target_width]
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    max_dist = np.sqrt(cx ** 2 + cy ** 2)
    gradient = (15 * (1 - dist / max_dist)).clip(0, 15).astype(np.uint8)
    equirect[:, :, 0] = gradient
    equirect[:, :, 1] = gradient
    equirect[:, :, 2] = gradient + 3

    # Scale source to fit within target
    scale = min(target_width / w, target_height / h, 1.0)
    new_w = int(w * scale)
    new_h = int(h * scale)

    if scale < 1.0:
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    else:
        resized = img.copy()
        new_w, new_h = w, h

    # Center in equirectangular frame
    x_offset = (target_width - new_w) // 2
    y_offset = (target_height - new_h) // 2
    equirect[y_offset:y_offset + new_h, x_offset:x_offset + new_w] = resized

    # Blend edges for smooth transition
    blend_width = min(40, new_w // 10)
    if blend_width > 2:
        for i in range(blend_width):
            alpha = i / blend_width
            # Left edge
            if x_offset + i < target_width:
                equirect[y_offset:y_offset + new_h, x_offset + i] = \
                    (alpha * resized[:, i].astype(float) +
                     (1 - alpha) * equirect[y_offset:y_offset + new_h, x_offset + i].astype(float)).astype(np.uint8)
            # Right edge
            ri = new_w - 1 - i
            if x_offset + ri >= 0:
                equirect[y_offset:y_offset + new_h, x_offset + ri] = \
                    (alpha * resized[:, ri].astype(float) +
                     (1 - alpha) * equirect[y_offset:y_offset + new_h, x_offset + ri].astype(float)).astype(np.uint8)

    return equirect


def try_opencv_stitch(images: list) -> tuple:
    """Attempt stitching using OpenCV's built-in Stitcher.

    Args:
        images: List of BGR images to stitch.

    Returns:
        (success: bool, result_image: np.ndarray or None)
    """
    if len(images) < 2:
        return False, None

    try:
        stitcher = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)
        stitcher.setPanoConfidenceThresh(config.STITCH_CONFIDENCE)

        status, pano = stitcher.stitch(images)

        if status == cv2.Stitcher_OK:
            return True, pano
        else:
            status_names = {
                cv2.Stitcher_ERR_NEED_MORE_IMGS: "need more images",
                cv2.Stitcher_ERR_HOMOGRAPHY_EST_FAIL: "homography estimation failed",
                cv2.Stitcher_ERR_CAMERA_PARAMS_ADJUST_FAIL: "camera params adjustment failed",
            }
            reason = status_names.get(status, f"unknown error {status}")
            print(f"    OpenCV Stitcher failed: {reason}")
            return False, None
    except Exception as e:
        print(f"    OpenCV Stitcher exception: {e}")
        return False, None


def try_cylindrical_stitch(images: list, focal_length: float = None) -> tuple:
    """Attempt stitching using custom cylindrical warp + feature matching.

    Args:
        images: List of BGR images.
        focal_length: Camera focal length. None = auto-estimate.

    Returns:
        (success: bool, result_image: np.ndarray or None)
    """
    if len(images) < 2:
        return False, None

    h, w = images[0].shape[:2]

    # Estimate focal length if not provided
    if focal_length is None:
        if config.CAMERA_FOCAL_LENGTH:
            focal_length = config.CAMERA_FOCAL_LENGTH
        else:
            focal_length = estimate_focal_length(w, config.CAMERA_FOV_H)

    try:
        # Warp all images to cylindrical projection
        warped_images = []
        for img in images:
            warped = cylindrical_warp(img, focal_length)
            if warped.size > 0:
                warped_images.append(warped)

        if len(warped_images) < 2:
            return False, None

        # Simple sequential stitching with translation-only model
        result = warped_images[0].copy()

        sift = cv2.SIFT_create()
        bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)

        for i in range(1, len(warped_images)):
            img2 = warped_images[i]

            # Detect features
            gray1 = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

            kp1, des1 = sift.detectAndCompute(gray1, None)
            kp2, des2 = sift.detectAndCompute(gray2, None)

            if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
                continue

            # Match features
            matches = bf.knnMatch(des1, des2, k=2)

            # Lowe's ratio test
            good_matches = []
            for m_list in matches:
                if len(m_list) == 2:
                    m, n = m_list
                    if m.distance < 0.7 * n.distance:
                        good_matches.append(m)

            if len(good_matches) < 4:
                continue

            # Estimate homography
            src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

            H, mask = cv2.findHomography(dst_pts, src_pts, cv2.RANSAC, 5.0)
            if H is None:
                continue

            # Warp and combine
            h1, w1 = result.shape[:2]
            h2, w2 = img2.shape[:2]

            # Calculate output size
            corners = np.float32([[0, 0], [w2, 0], [w2, h2], [0, h2]]).reshape(-1, 1, 2)
            warped_corners = cv2.perspectiveTransform(corners, H)

            all_corners = np.concatenate([
                np.float32([[0, 0], [w1, 0], [w1, h1], [0, h1]]).reshape(-1, 1, 2),
                warped_corners
            ], axis=0)

            x_min = int(np.floor(all_corners[:, 0, 0].min()))
            y_min = int(np.floor(all_corners[:, 0, 1].min()))
            x_max = int(np.ceil(all_corners[:, 0, 0].max()))
            y_max = int(np.ceil(all_corners[:, 0, 1].max()))

            # Limit size to prevent memory issues
            out_w = min(x_max - x_min, config.PANO_OUTPUT_WIDTH * 2)
            out_h = min(y_max - y_min, config.PANO_OUTPUT_WIDTH)

            # Translation matrix
            T = np.float64([[1, 0, -x_min], [0, 1, -y_min], [0, 0, 1]])

            # Warp second image
            warped2 = cv2.warpPerspective(img2, T @ H, (out_w, out_h))

            # Place first image
            canvas = warped2.copy()
            y_off = -y_min
            x_off = -x_min
            y_end = min(y_off + h1, out_h)
            x_end = min(x_off + w1, out_w)

            if y_off >= 0 and x_off >= 0 and y_end > y_off and x_end > x_off:
                roi = canvas[y_off:y_end, x_off:x_end]
                src_roi = result[:y_end - y_off, :x_end - x_off]

                # Simple blend: prefer non-black pixels
                mask_existing = (roi.sum(axis=2) > 0).astype(np.float32)
                mask_new = (src_roi.sum(axis=2) > 0).astype(np.float32)
                both = (mask_existing * mask_new)[:, :, np.newaxis]

                blended = (
                    src_roi * (1 - both * 0.5) +
                    roi * both * 0.5 +
                    roi * (1 - mask_new)[:, :, np.newaxis]
                ).astype(np.uint8)

                # Where only new image has data
                only_new = ((1 - mask_existing) * mask_new)[:, :, np.newaxis]
                blended = (blended * (1 - only_new) + src_roi * only_new).astype(np.uint8)

                canvas[y_off:y_end, x_off:x_end] = blended

            result = canvas

        # Crop black borders
        gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            x, y, cw, ch = cv2.boundingRect(max(contours, key=cv2.contourArea))
            result = result[y:y + ch, x:x + cw]

        if result.size > 0:
            return True, result
        return False, None

    except Exception as e:
        print(f"    Cylindrical stitch exception: {e}")
        return False, None


def stitch_viewpoint(vp_dir: Path, output_path: Path,
                     mode: str = None) -> dict:
    """Stitch all frames in a viewpoint directory into one panorama.

    Args:
        vp_dir: Directory containing the viewpoint's frames.
        output_path: Path to save the output panorama image.
        mode: Stitching mode override. None = config default.

    Returns:
        Dict with stitching result metadata.
    """
    if mode is None:
        mode = config.STITCH_MODE

    # Load frames
    extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
    frame_files = sorted([
        f for f in vp_dir.iterdir()
        if f.suffix.lower() in extensions
    ])

    if not frame_files:
        return {"success": False, "reason": "no frames found"}

    # Read all frames
    images = []
    for f in frame_files:
        img = cv2.imread(str(f))
        if img is not None:
            images.append(img)

    if not images:
        return {"success": False, "reason": "could not read any frames"}

    result = None
    method_used = "none"

    # Subsample frames if there are too many, to drastically speed up OpenCV stitching
    # 8 evenly spaced frames cover a full 360 rotation perfectly with optimal overlap
    if len(images) > 8:
        indices = np.linspace(0, len(images) - 1, 8, dtype=int)
        stitch_images = [images[i] for i in indices]
    else:
        stitch_images = images

    # ── Strategy 1: OpenCV Stitcher ──
    if mode in ("auto", "opencv") and len(stitch_images) >= 2:
        print(f"    Trying OpenCV Stitcher ({len(stitch_images)} frames subsampled from {len(images)})...", end=" ", flush=True)
        success, pano = try_opencv_stitch(stitch_images)
        if success:
            result = pano
            method_used = "opencv_stitcher"
            print("[OK]", flush=True)
        else:
            print("[FAIL]", flush=True)

    # ── Strategy 2: Cylindrical warp + feature matching ──
    if result is None and mode in ("auto", "cylindrical") and len(stitch_images) >= 2:
        print(f"    Trying cylindrical warp stitch...", end=" ", flush=True)
        success, pano = try_cylindrical_stitch(stitch_images)
        if success:
            result = pano
            method_used = "cylindrical_warp"
            print("[OK]", flush=True)
        else:
            print("[FAIL]", flush=True)

    # ── Strategy 3: Single best frame ──
    if result is None:
        # Use the sharpest frame from the full set
        best_img = None
        best_blur = -1
        for img in images:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blur = cv2.Laplacian(gray, cv2.CV_64F).var()
            if blur > best_blur:
                best_blur = blur
                best_img = img

        if best_img is not None:
            result = best_img
            method_used = "single_frame"
            print(f"    Using single best frame (blur={best_blur:.0f})", flush=True)

    if result is None:
        return {"success": False, "reason": "all methods failed"}

    # ── Compute angular coverage ──
    h_res, w_res = result.shape[:2]
    if method_used == "single_frame":
        # Honest single-frame: report actual camera FOV, not a fake 360
        coverage_h = float(config.CAMERA_FOV_H)
        coverage_v = round(coverage_h * h_res / w_res, 1)
    else:
        # Stitched panorama: estimate coverage from how much wider it got
        orig_h, orig_w = images[0].shape[:2] if images else (h_res, w_res)
        coverage_h = min(360.0, round(config.CAMERA_FOV_H * w_res / orig_w, 1))
        coverage_v = min(180.0, round(coverage_h * h_res / w_res, 1))

    # ── Save image at native resolution (no equirect padding) ──
    # Pannellum renders correctly using haov/vaov; black-padded equirect looks terrible
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if config.PANO_FORMAT == "jpg":
        cv2.imwrite(str(output_path), result,
                    [cv2.IMWRITE_JPEG_QUALITY, config.PANO_QUALITY])
    else:
        cv2.imwrite(str(output_path), result)

    return {
        "success": True,
        "method": method_used,
        "coverage_h": coverage_h,
        "coverage_v": coverage_v,
        "input_frames": len(images),
        "output_path": str(output_path),
        "output_size": [w_res, h_res],
    }


def stitch_all_viewpoints(viewpoints_dir: str = None,
                          output_dir: str = None) -> list:
    """Stitch panoramas for all viewpoint clusters.

    Args:
        viewpoints_dir: Directory containing vp_XXX subdirectories.
        output_dir: Directory to save panorama images.

    Returns:
        List of stitching result dicts.
    """
    if viewpoints_dir is None:
        viewpoints_dir = config.VIEWPOINTS_DIR
    if output_dir is None:
        output_dir = config.PANORAMAS_DIR

    viewpoints_dir = Path(viewpoints_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find viewpoint directories
    vp_dirs = sorted([
        d for d in viewpoints_dir.iterdir()
        if d.is_dir() and d.name.startswith("vp_")
    ])

    if not vp_dirs:
        print(f"  [FAIL] No viewpoint directories found in {viewpoints_dir}")
        return []

    print(f"  Stitching {len(vp_dirs)} viewpoints from {viewpoints_dir}")
    print()

    results = []

    for vp_dir in tqdm(vp_dirs, desc="  Stitching panoramas", unit="pano"):
        vp_name = vp_dir.name
        output_path = output_dir / f"{vp_name}.{config.PANO_FORMAT}"

        print(f"\n  [VP] {vp_name}:")
        result = stitch_viewpoint(vp_dir, output_path)
        result["viewpoint_id"] = vp_name
        results.append(result)

        if result["success"]:
            size = result["output_size"]
            print(f"    -> {output_path.name} ({size[0]}x{size[1]}, {result['method']})")
        else:
            print(f"    -> FAILED: {result.get('reason', 'unknown')}")

    # Summary
    successes = sum(1 for r in results if r["success"])
    methods = {}
    for r in results:
        if r["success"]:
            m = r["method"]
            methods[m] = methods.get(m, 0) + 1

    print(f"\n  [OK] Panorama Stitching Complete")
    print(f"  Success: {successes}/{len(results)}")
    for method, count in methods.items():
        print(f"    {method}: {count}")
    print(f"  Output: {output_dir}")

    # Save report
    report_path = output_dir / "stitch_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stitch viewpoint frames into panoramas")
    parser.add_argument("--input", help="Viewpoints directory")
    parser.add_argument("--output", help="Output panoramas directory")
    parser.add_argument("--mode", choices=["auto", "opencv", "cylindrical", "single"],
                        help="Stitching mode")
    args = parser.parse_args()

    print("=" * 60)
    print("  Panorama Stitcher")
    print("=" * 60)

    if args.mode:
        config.STITCH_MODE = args.mode

    stitch_all_viewpoints(args.input, args.output)
