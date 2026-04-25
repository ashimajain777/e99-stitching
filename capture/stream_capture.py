"""
Stream Capture
===============
Captures live FPV stream from E99 Pro drone and saves as video file.
Also supports loading pre-recorded video files for testing.
"""

import cv2
import time
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def capture_live_stream(output_path: str = None, duration: float = 60.0,
                        stream_url: str = None) -> dict:
    """Capture live FPV stream from drone and save as video file.

    Args:
        output_path: Output video file path. None = auto-generate.
        duration: Max recording duration in seconds.
        stream_url: Specific stream URL. None = try all from config.

    Returns:
        Dict with recording metadata.
    """
    if output_path is None:
        config.RAW_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(config.RAW_VIDEO_DIR / f"fpv_capture_{timestamp}.mp4")

    urls_to_try = [stream_url] if stream_url else config.STREAM_URLS
    cap = None

    for url in urls_to_try:
        print(f"  Trying stream: {url}")
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        time.sleep(1.0)

        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"  ✅ Connected: {url} ({frame.shape[1]}x{frame.shape[0]})")
                break
        cap.release()
        cap = None

    if cap is None:
        print("  ❌ Could not connect to any video stream!")
        print("  Make sure you're connected to the drone's WiFi.")
        return None

    # Get video properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or config.RECORDING_FPS

    fourcc = cv2.VideoWriter_fourcc(*config.RECORDING_CODEC)
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    print(f"  Recording to: {output_path}")
    print(f"  Resolution: {width}x{height} @ {fps:.1f} FPS")
    print(f"  Duration: {duration}s (press 'Q' to stop early)")

    frame_count = 0
    start_time = time.time()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            writer.write(frame)
            frame_count += 1
            elapsed = time.time() - start_time

            # Show preview
            preview = cv2.resize(frame, (640, 360))
            cv2.putText(preview, f"REC {elapsed:.1f}s | {frame_count} frames",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.imshow("FPV Capture (Q to stop)", preview)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            if elapsed >= duration:
                break

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        writer.release()
        cv2.destroyAllWindows()

    elapsed = time.time() - start_time
    metadata = {
        "file": output_path,
        "width": width,
        "height": height,
        "fps": fps,
        "frame_count": frame_count,
        "duration_seconds": round(elapsed, 2),
        "timestamp": datetime.now().isoformat(),
    }

    # Save metadata
    meta_path = Path(output_path).with_suffix(".json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n  ✅ Recording complete: {frame_count} frames, {elapsed:.1f}s")
    print(f"  Saved: {output_path}")
    print(f"  Metadata: {meta_path}")

    return metadata


def get_video_info(video_path: str) -> dict:
    """Get metadata from a video file.

    Args:
        video_path: Path to video file.

    Returns:
        Dict with video properties.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    info = {
        "file": video_path,
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": cap.get(cv2.CAP_PROP_FPS),
        "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        "duration_seconds": round(
            cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(cap.get(cv2.CAP_PROP_FPS), 1), 2
        ),
    }
    cap.release()
    return info


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Capture FPV stream from drone")
    parser.add_argument("--duration", type=float, default=60, help="Recording duration (seconds)")
    parser.add_argument("--output", type=str, help="Output file path")
    parser.add_argument("--url", type=str, help="Specific stream URL")
    args = parser.parse_args()

    print("=" * 60)
    print("  E99 Pro FPV Stream Capture")
    print("=" * 60)
    capture_live_stream(args.output, args.duration, args.url)
