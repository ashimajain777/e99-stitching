"""
Panoramic Street View Pipeline - Main Orchestrator
=====================================================
One-command execution from drone video -> panoramic street view tour.

Usage:
    # Full pipeline from video file
    python pipeline.py run --input video.mp4

    # Individual stages
    python pipeline.py extract --input video.mp4
    python pipeline.py filter --input datasets/frames/all/
    python pipeline.py enhance --input datasets/frames/filtered/
    python pipeline.py cluster --input datasets/enhanced/
    python pipeline.py stitch --input datasets/viewpoints/
    python pipeline.py tour --input datasets/panoramas/
    python pipeline.py serve

    # Live drone capture
    python pipeline.py capture --duration 60
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Fix Windows cp1252 encoding — force UTF-8 for all console output
# Must happen BEFORE colorama wraps stdout
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))
import config

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(wrap=False)  # Don't wrap stdout — avoids encoding issues
    GREEN = Fore.GREEN
    RED = Fore.RED
    CYAN = Fore.CYAN
    YELLOW = Fore.YELLOW
    DIM = Style.DIM
    RESET = Style.RESET_ALL
    BRIGHT = Style.BRIGHT
except ImportError:
    GREEN = RED = CYAN = YELLOW = DIM = RESET = BRIGHT = ""


def banner():
    print(f"""
{CYAN}{BRIGHT}+==============================================================+
|                                                              |
|   ######  #####   #####      #####  ##  ##                   |
|   ##     ##   ## ##   ##     ##     ##  ##                   |
|   ####    ######  ######     #####  ##  ##                   |
|   ##          ##      ##         ##  ## ##                   |
|   ######  #####   #####      #####    ##                    |
|                                                              |
|   Street View -- Indoor Drone Explorer                       |
|   Panoramic Tour from FPV Video                              |
|                                                              |
+==============================================================+{RESET}
""")


def print_stage(name, stage_num=None, total=None):
    if stage_num and total:
        prefix = f"[{stage_num}/{total}]"
    else:
        prefix = ">>>"
    print(f"\n{CYAN}{BRIGHT}{'=' * 60}")
    print(f"  {prefix} {name}")
    print(f"{'=' * 60}{RESET}")


def print_success(msg):
    print(f"  {GREEN}[OK] {msg}{RESET}")


def print_error(msg):
    print(f"  {RED}[FAIL] {msg}{RESET}")


def print_warn(msg):
    print(f"  {YELLOW}[WARN] {msg}{RESET}")


def print_info(msg):
    print(f"  {DIM}{msg}{RESET}")


# ================================================================
# Individual Stage Commands
# ================================================================

def cmd_capture(args):
    """Capture live FPV stream from drone."""
    from capture.stream_capture import capture_live_stream
    print_stage("Live FPV Stream Capture")
    capture_live_stream(args.output, args.duration)


def cmd_extract(args):
    """Extract frames from video."""
    from capture.frame_extractor import extract_frames
    print_stage("Frame Extraction")
    extract_frames(args.input, args.output, args.fps, args.max_frames)


def cmd_filter(args):
    """Filter frames by quality."""
    from capture.keyframe_selector import filter_frames
    print_stage("Frame Quality Filter")
    filter_frames(args.input, args.output, args.blur)


def cmd_enhance(args):
    """Enhance images for stitching."""
    from preprocess.image_enhancer import enhance_images
    print_stage("Image Enhancement")
    enhance_images(args.input, args.output)


def cmd_cluster(args):
    """Cluster frames into viewpoints."""
    from capture.keyframe_selector import cluster_into_viewpoints
    print_stage("Viewpoint Clustering")
    cluster_into_viewpoints(args.input, args.output, args.motion)


def cmd_stitch(args):
    """Stitch panoramas for each viewpoint."""
    from stitching.panorama_stitcher import stitch_all_viewpoints
    print_stage("Panorama Stitching")
    stitch_all_viewpoints(args.input, args.output)


def cmd_tour(args):
    """Build tour configuration."""
    from tour.tour_builder import build_tour
    print_stage("Tour Builder")
    build_tour(args.viewpoints, args.panoramas, args.output)


def cmd_serve(args):
    """Launch web viewer."""
    from web_viewer.server import start_server
    print_stage("Street View Server")
    start_server(args.port, args.data)


# ================================================================
# Full Pipeline
# ================================================================

def cmd_run(args):
    """Run the complete pipeline: video -> panoramic street view."""
    banner()

    total_stages = 6
    overall_start = time.time()
    results = {}

    # ── Determine input type ──
    input_path = Path(args.input)

    if input_path.is_file():
        # ── Stage 1: Extract frames from video ──
        print_stage("Frame Extraction", 1, total_stages)
        from capture.frame_extractor import extract_frames
        config.FRAMES_ALL_DIR.mkdir(parents=True, exist_ok=True)

        manifest = extract_frames(
            str(input_path),
            str(config.FRAMES_ALL_DIR),
            args.fps or config.EXTRACTION_FPS,
        )
        results["extraction"] = manifest

        frames_dir = config.FRAMES_ALL_DIR

    elif input_path.is_dir():
        # Input is already frames
        print_info(f"Input is a directory: {input_path}")
        print_info("Skipping frame extraction.")
        frames_dir = input_path
        total_stages = 5
    else:
        print_error(f"Input not found: {input_path}")
        return

    # ── Stage 2: Filter bad frames ──
    stage = 2 if input_path.is_file() else 1
    print_stage("Frame Quality Filter", stage, total_stages)
    from capture.keyframe_selector import filter_frames
    config.FRAMES_FILTERED_DIR.mkdir(parents=True, exist_ok=True)

    filter_stats = filter_frames(
        str(frames_dir),
        str(config.FRAMES_FILTERED_DIR),
    )
    results["filtering"] = filter_stats

    if filter_stats["accepted"] == 0:
        print_error("No frames passed quality filter! Try lowering BLUR_THRESHOLD in config.py")
        return

    # ── Stage 3: Enhance frames ──
    stage += 1
    print_stage("Image Enhancement", stage, total_stages)
    from preprocess.image_enhancer import enhance_images
    config.ENHANCED_DIR.mkdir(parents=True, exist_ok=True)

    enhance_stats = enhance_images(
        str(config.FRAMES_FILTERED_DIR),
        str(config.ENHANCED_DIR),
    )
    results["enhancement"] = enhance_stats

    # ── Stage 4: Cluster into viewpoints ──
    stage += 1
    print_stage("Viewpoint Clustering", stage, total_stages)
    from capture.keyframe_selector import cluster_into_viewpoints

    cluster_report = cluster_into_viewpoints(
        str(config.ENHANCED_DIR),
        str(config.VIEWPOINTS_DIR),
    )
    results["clustering"] = cluster_report

    if cluster_report["num_viewpoints"] == 0:
        print_error("No viewpoints created! Check your video has enough frames.")
        return

    # ── Stage 5: Stitch panoramas ──
    stage += 1
    print_stage("Panorama Stitching", stage, total_stages)
    from stitching.panorama_stitcher import stitch_all_viewpoints

    stitch_results = stitch_all_viewpoints(
        str(config.VIEWPOINTS_DIR),
        str(config.PANORAMAS_DIR),
    )
    results["stitching"] = stitch_results

    successes = sum(1 for r in stitch_results if r.get("success"))
    if successes == 0:
        print_error("No panoramas were created! Check frame quality.")
        return

    # ── Stage 6: Build tour ──
    stage += 1
    print_stage("Tour Builder", stage, total_stages)
    from tour.tour_builder import build_tour

    tour = build_tour(
        str(config.VIEWPOINTS_DIR),
        str(config.PANORAMAS_DIR),
        str(config.TOUR_JSON_PATH),
    )
    results["tour"] = tour

    # ── Summary ──
    total_time = time.time() - overall_start

    print(f"\n{GREEN}{BRIGHT}{'=' * 60}")
    print(f"  PIPELINE COMPLETE")
    print(f"{'=' * 60}{RESET}")
    print(f"  Total time: {total_time:.1f}s ({total_time / 60:.1f} min)")
    print(f"  Panoramas created: {successes}/{len(stitch_results)}")
    print(f"  Tour scenes: {len(tour.get('scenes', {}))}")

    # List output files
    print(f"\n  Output files:")
    for d in [config.PANORAMAS_DIR, config.OUTPUT_DIR]:
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.is_file():
                    size = f.stat().st_size
                    size_str = f"{size / 1024 / 1024:.1f}MB" if size > 1024 * 1024 else f"{size / 1024:.0f}KB"
                    print(f"    > {f.name} ({size_str})")

    print(f"\n  {CYAN}To explore your space:{RESET}")
    print(f"    python pipeline.py serve")
    print(f"    -> Opens http://localhost:{config.WEB_SERVER_PORT}")
    print()


# ================================================================
# CLI Entry Point
# ================================================================

def main():
    parser = argparse.ArgumentParser(
        description="E99 Street View — Indoor Drone Explorer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  run          Full pipeline: video -> panoramic tour
  capture      Record live FPV stream from drone
  extract      Extract frames from video
  filter       Remove blurry/dark/bright frames
  enhance      Enhance images (CLAHE, denoise)
  cluster      Group frames into viewpoints
  stitch       Stitch panoramas per viewpoint
  tour         Build Pannellum tour.json
  serve        Launch web viewer

Examples:
  python pipeline.py run --input video.mp4
  python pipeline.py run --input path/to/images/
  python pipeline.py serve
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Pipeline command")

    # --- run ---
    p_run = subparsers.add_parser("run", help="Full pipeline: video -> tour")
    p_run.add_argument("--input", required=True, help="Input video file or frames directory")
    p_run.add_argument("--fps", type=float, help="Frame extraction rate")

    # --- capture ---
    p_cap = subparsers.add_parser("capture", help="Record live FPV stream")
    p_cap.add_argument("--duration", type=float, default=60, help="Recording duration (seconds)")
    p_cap.add_argument("--output", help="Output video file path")

    # --- extract ---
    p_ext = subparsers.add_parser("extract", help="Extract frames from video")
    p_ext.add_argument("--input", required=True, help="Input video file")
    p_ext.add_argument("--output", help="Output frames directory")
    p_ext.add_argument("--fps", type=float, help="Extraction rate (FPS)")
    p_ext.add_argument("--max-frames", type=int, help="Max frames to extract")

    # --- filter ---
    p_flt = subparsers.add_parser("filter", help="Filter bad frames")
    p_flt.add_argument("--input", help="Input frames directory")
    p_flt.add_argument("--output", help="Output directory")
    p_flt.add_argument("--blur", type=float, help="Blur threshold")

    # --- enhance ---
    p_enh = subparsers.add_parser("enhance", help="Enhance images")
    p_enh.add_argument("--input", help="Input images directory")
    p_enh.add_argument("--output", help="Output directory")

    # --- cluster ---
    p_cls = subparsers.add_parser("cluster", help="Cluster frames into viewpoints")
    p_cls.add_argument("--input", help="Input enhanced frames directory")
    p_cls.add_argument("--output", help="Output viewpoints directory")
    p_cls.add_argument("--motion", type=float, help="Motion threshold")

    # --- stitch ---
    p_stc = subparsers.add_parser("stitch", help="Stitch panoramas")
    p_stc.add_argument("--input", help="Viewpoints directory")
    p_stc.add_argument("--output", help="Output panoramas directory")

    # --- tour ---
    p_tour = subparsers.add_parser("tour", help="Build tour configuration")
    p_tour.add_argument("--viewpoints", help="Viewpoints directory")
    p_tour.add_argument("--panoramas", help="Panoramas directory")
    p_tour.add_argument("--output", help="Output tour.json path")

    # --- serve ---
    p_srv = subparsers.add_parser("serve", help="Launch web viewer")
    p_srv.add_argument("--port", type=int, help="Server port")
    p_srv.add_argument("--data", help="Datasets directory")

    args = parser.parse_args()

    if args.command is None:
        banner()
        parser.print_help()
        return

    # Dispatch
    commands = {
        "run": cmd_run,
        "capture": cmd_capture,
        "extract": cmd_extract,
        "filter": cmd_filter,
        "enhance": cmd_enhance,
        "cluster": cmd_cluster,
        "stitch": cmd_stitch,
        "tour": cmd_tour,
        "serve": cmd_serve,
    }

    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        print(f"\n  {YELLOW}Interrupted by user.{RESET}")
    except Exception as e:
        print(f"\n  {RED}Error: {e}{RESET}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
