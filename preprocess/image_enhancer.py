"""
Image Enhancer
===============
Preprocesses frames for optimal COLMAP reconstruction.
Handles low-light indoor scenes with CLAHE, denoising, and white balance.
"""

import cv2
import sys
from pathlib import Path
from tqdm import tqdm
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def apply_clahe(image: np.ndarray, clip_limit: float = None,
                grid_size: tuple = None) -> np.ndarray:
    """Apply Contrast Limited Adaptive Histogram Equalization.

    Dramatically improves low-light indoor images while preserving
    local contrast (unlike global histogram equalization).
    """
    if clip_limit is None:
        clip_limit = config.CLAHE_CLIP_LIMIT
    if grid_size is None:
        grid_size = config.CLAHE_GRID_SIZE

    # Convert to LAB color space — apply CLAHE to L channel only
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=grid_size)
    l_enhanced = clahe.apply(l)

    lab_enhanced = cv2.merge([l_enhanced, a, b])
    return cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)


def apply_denoising(image: np.ndarray, strength: int = None) -> np.ndarray:
    """Apply non-local means denoising.

    Good for indoor FPV footage which tends to be noisy due to
    small sensors and low light.
    """
    if strength is None:
        strength = config.DENOISE_STRENGTH
    return cv2.fastNlMeansDenoisingColored(image, None, strength, strength, 7, 21)


def apply_white_balance(image: np.ndarray) -> np.ndarray:
    """Apply gray-world white balance correction.

    Indoor lighting (fluorescent, LED) often has strong color casts
    that can affect feature matching. This normalizes color.
    """
    result = image.copy().astype(np.float64)
    avg_b = np.mean(result[:, :, 0])
    avg_g = np.mean(result[:, :, 1])
    avg_r = np.mean(result[:, :, 2])
    avg_all = (avg_b + avg_g + avg_r) / 3.0

    result[:, :, 0] *= avg_all / max(avg_b, 1)
    result[:, :, 1] *= avg_all / max(avg_g, 1)
    result[:, :, 2] *= avg_all / max(avg_r, 1)

    return np.clip(result, 0, 255).astype(np.uint8)


def resize_image(image: np.ndarray, width: int = None,
                 height: int = None) -> np.ndarray:
    """Resize image to target dimensions, maintaining aspect ratio if
    only one dimension is specified."""
    if width is None and height is None:
        return image

    h, w = image.shape[:2]

    if width and height:
        return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    elif width:
        scale = width / w
        new_h = int(h * scale)
        return cv2.resize(image, (width, new_h), interpolation=cv2.INTER_AREA)
    else:
        scale = height / h
        new_w = int(w * scale)
        return cv2.resize(image, (new_w, height), interpolation=cv2.INTER_AREA)


def enhance_images(input_dir: str = None, output_dir: str = None,
                   enable_clahe: bool = None, enable_denoise: bool = None,
                   enable_wb: bool = None) -> dict:
    """Enhance all images in a directory for COLMAP reconstruction.

    Args:
        input_dir: Input frames directory. None = keyframes dir.
        output_dir: Output directory. None = preprocessed dir.
        enable_clahe: Enable CLAHE. None = config default.
        enable_denoise: Enable denoising. None = config default.
        enable_wb: Enable white balance. None = config default.

    Returns:
        Dict with processing statistics.
    """
    if input_dir is None:
        input_dir = config.FRAMES_KEYFRAMES_DIR
    if output_dir is None:
        output_dir = config.PREPROCESSED_DIR

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if enable_clahe is None:
        enable_clahe = config.CLAHE_ENABLED
    if enable_denoise is None:
        enable_denoise = config.DENOISE_ENABLED
    if enable_wb is None:
        enable_wb = config.WHITE_BALANCE_ENABLED

    # Find images
    extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
    image_files = sorted([
        f for f in input_dir.iterdir()
        if f.suffix.lower() in extensions
    ])

    if not image_files:
        print(f"  ❌ No images found in {input_dir}")
        return {"total": 0, "processed": 0}

    print(f"  Input: {len(image_files)} images from {input_dir}")
    print(f"  Enhancements: CLAHE={enable_clahe}, Denoise={enable_denoise}, "
          f"WhiteBalance={enable_wb}")
    if config.TARGET_WIDTH or config.TARGET_HEIGHT:
        print(f"  Resize: {config.TARGET_WIDTH}x{config.TARGET_HEIGHT}")
    print()

    processed = 0
    for img_path in tqdm(image_files, desc="  Enhancing images", unit="img"):
        image = cv2.imread(str(img_path))
        if image is None:
            continue

        # Apply enhancements in order
        if config.TARGET_WIDTH or config.TARGET_HEIGHT:
            image = resize_image(image, config.TARGET_WIDTH, config.TARGET_HEIGHT)

        if enable_clahe:
            image = apply_clahe(image)

        if enable_denoise:
            image = apply_denoising(image)

        if enable_wb:
            image = apply_white_balance(image)

        # Save with original filename (for COLMAP compatibility)
        out_path = output_dir / img_path.name
        if img_path.suffix.lower() in {".jpg", ".jpeg"}:
            cv2.imwrite(str(out_path), image,
                        [cv2.IMWRITE_JPEG_QUALITY, config.FRAME_QUALITY])
        else:
            cv2.imwrite(str(out_path), image)

        processed += 1

    stats = {
        "total": len(image_files),
        "processed": processed,
        "clahe": enable_clahe,
        "denoise": enable_denoise,
        "white_balance": enable_wb,
        "output_dir": str(output_dir),
    }

    print(f"\n  ✅ Enhanced {processed} images → {output_dir}")
    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enhance images for reconstruction")
    parser.add_argument("--input", help="Input images directory")
    parser.add_argument("--output", help="Output directory")
    parser.add_argument("--no-clahe", action="store_true", help="Disable CLAHE")
    parser.add_argument("--no-denoise", action="store_true", help="Disable denoising")
    parser.add_argument("--no-wb", action="store_true", help="Disable white balance")
    args = parser.parse_args()

    print("=" * 60)
    print("  Image Enhancer")
    print("=" * 60)
    enhance_images(
        args.input, args.output,
        enable_clahe=not args.no_clahe,
        enable_denoise=not args.no_denoise,
        enable_wb=not args.no_wb,
    )
