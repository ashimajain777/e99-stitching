"""
3D Mapping Pipeline - Main Orchestrator
=========================================
One-command execution from video -> 3D model -> interactive viewer.

Usage:
    # Full pipeline from video file
    python pipeline.py run --input video.mp4

    # Full pipeline from pre-extracted frames
    python pipeline.py run --frames path/to/frames/

    # Individual stages
    python pipeline.py extract --input video.mp4
    python pipeline.py keyframes --input datasets/frames/all/
    python pipeline.py enhance --input datasets/frames/keyframes/
    python pipeline.py reconstruct --input datasets/preprocessed/
    python pipeline.py optimize --input datasets/colmap/dense_cloud.ply
    python pipeline.py view --input datasets/output/dense_cloud_clean.ply
    python pipeline.py web

    # Live drone capture
    python pipeline.py capture --duration 60

    # Sparse-only (fast preview)
    python pipeline.py run --input video.mp4 --sparse-only
"""

import argparse
import sys
import time
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))
import config

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init()
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
|   ######  #####   #####      #####  ####                     |
|   ##     ##   ## ##   ##         ## ##  ##                    |
|   ####    ######  ######     ##### ##  ##                    |
|   ##          ##      ##         ## ##  ##                    |
|   ######  #####   #####     #####  ####                      |
|                                                              |
|   3D Mapping & Exploration Pipeline                          |
|   Indoor Drone Reconstruction using COLMAP                   |
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


def cmd_keyframes(args):
    """Select keyframes from extracted frames."""
    from capture.keyframe_selector import select_keyframes
    print_stage("Keyframe Selection")
    select_keyframes(args.input, args.output, args.blur)


def cmd_enhance(args):
    """Enhance images for reconstruction."""
    from preprocess.image_enhancer import enhance_images
    print_stage("Image Enhancement")
    enhance_images(args.input, args.output)


def cmd_reconstruct(args):
    """Run COLMAP reconstruction."""
    from reconstruction.colmap_pipeline import run_full_pipeline
    print_stage("COLMAP 3D Reconstruction")
    run_full_pipeline(
        args.input, args.workspace,
        skip_dense=args.sparse_only,
        skip_mesh=args.no_mesh,
    )


def cmd_optimize(args):
    """Optimize point cloud for indoor scenes."""
    from reconstruction.indoor_optimizer import optimize_point_cloud
    print_stage("Indoor Optimization")
    optimize_point_cloud(args.input, args.output)


def cmd_mesh(args):
    """Generate mesh from point cloud."""
    from reconstruction.mesh_generator import simple_mesh_from_ply, poisson_mesh_colmap
    print_stage("Mesh Generation")
    
    if args.workspace:
        poisson_mesh_colmap(args.workspace, args.output)
    else:
        max_points = args.decimate if args.decimate else 100000
        simple_mesh_from_ply(args.input, args.output, max_points)


def cmd_view(args):
    """Launch Open3D interactive viewer."""
    from viewer.point_cloud_viewer import launch_viewer
    print_stage("Interactive 3D Viewer")

    path = Path(args.input)
    if path.suffix.lower() in {".obj", ".stl", ".off"}:
        launch_viewer(mesh_path=str(path), workspace=args.workspace)
    else:
        launch_viewer(ply_path=str(path), workspace=args.workspace)


def cmd_web(args):
    """Launch Three.js web viewer."""
    from web_viewer.server import start_server
    print_stage("Web Viewer")
    start_server(args.port, args.data)


def cmd_export(args):
    """Export final results."""
    from export import export_results
    print_stage("Export Results")
    export_results(args.workspace, args.output)


# ================================================================
# Full Pipeline
# ================================================================

def cmd_run(args):
    """Run the complete pipeline: video -> 3D model -> viewer."""
    banner()

    total_stages = 6  # extract, keyframes, enhance, reconstruct, optimize, export
    if args.sparse_only:
        total_stages = 5

    overall_start = time.time()
    results = {}

    # ── Determine input type ──
    input_path = Path(args.input)
    images_dir = None

    if input_path.is_file():
        # Input is a video file -> extract frames
        print_stage("Frame Extraction", 1, total_stages)
        from capture.frame_extractor import extract_frames
        config.FRAMES_ALL_DIR.mkdir(parents=True, exist_ok=True)

        manifest = extract_frames(
            str(input_path),
            str(config.FRAMES_ALL_DIR),
            args.fps or config.EXTRACTION_FPS,
        )
        results["extraction"] = manifest

        # Keyframe selection
        print_stage("Keyframe Selection", 2, total_stages)
        from capture.keyframe_selector import select_keyframes
        config.FRAMES_KEYFRAMES_DIR.mkdir(parents=True, exist_ok=True)

        kf_stats = select_keyframes(
            str(config.FRAMES_ALL_DIR),
            str(config.FRAMES_KEYFRAMES_DIR),
        )
        results["keyframes"] = kf_stats

        images_dir = config.FRAMES_KEYFRAMES_DIR

    elif input_path.is_dir():
        # Input is a directory of frames - skip extraction
        print_info(f"Input is a directory: {input_path}")
        print_info("Skipping extraction and keyframe selection.")
        images_dir = input_path
    else:
        print_error(f"Input not found: {input_path}")
        return

    # ── Preprocessing ──
    stage_offset = 3 if input_path.is_file() else 1
    print_stage("Image Enhancement", stage_offset, total_stages)
    from preprocess.image_enhancer import enhance_images
    config.PREPROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    enhance_stats = enhance_images(
        str(images_dir),
        str(config.PREPROCESSED_DIR),
    )
    results["enhancement"] = enhance_stats

    # Use preprocessed images for reconstruction
    recon_input = config.PREPROCESSED_DIR

    # ── COLMAP Reconstruction ──
    print_stage("COLMAP 3D Reconstruction", stage_offset + 1, total_stages)
    from reconstruction.colmap_pipeline import run_full_pipeline

    recon_results = run_full_pipeline(
        str(recon_input),
        str(config.COLMAP_WORKSPACE),
        skip_dense=args.sparse_only,
        skip_mesh=True,  # We'll do meshing after optimization
    )
    results["reconstruction"] = recon_results

    if not recon_results.get("success"):
        print_error("Reconstruction failed!")
        return

    # ── Indoor Optimization ──
    # Find the best available point cloud
    ply_to_optimize = None
    if "dense_ply" in recon_results and Path(recon_results["dense_ply"]).exists():
        ply_to_optimize = recon_results["dense_ply"]
    elif "sparse_ply" in recon_results and Path(recon_results["sparse_ply"]).exists():
        ply_to_optimize = recon_results["sparse_ply"]

    if ply_to_optimize:
        print_stage("Indoor Optimization", stage_offset + 2, total_stages)
        from reconstruction.indoor_optimizer import optimize_point_cloud

        opt_stats = optimize_point_cloud(ply_to_optimize)
        results["optimization"] = opt_stats

    # ── Export ──
    print_stage("Export Results", stage_offset + 3, total_stages)
    from export import export_results
    export_data = export_results()
    results["export"] = export_data

    # ── Summary ──
    total_time = time.time() - overall_start

    print(f"\n{GREEN}{BRIGHT}{'=' * 60}")
    print(f"  PIPELINE COMPLETE")
    print(f"{'=' * 60}{RESET}")
    print(f"  Total time: {total_time:.1f}s ({total_time/60:.1f} min)")

    if recon_results.get("registered_images"):
        print(f"  Registered images: {recon_results['registered_images']}/"
              f"{recon_results.get('total_images', '?')}")

    if "optimization" in results:
        opt = results["optimization"]
        print(f"  Final point cloud: {opt.get('final_points', '?')} points")

    print(f"\n  Output directory: {config.OUTPUT_DIR}")

    # List output files
    if config.OUTPUT_DIR.exists():
        for f in sorted(config.OUTPUT_DIR.iterdir()):
            if f.is_file():
                size = f.stat().st_size
                size_str = f"{size/1024/1024:.1f}MB" if size > 1024*1024 else f"{size/1024:.0f}KB"
                print(f"    > {f.name} ({size_str})")

    print(f"\n  {CYAN}To view the reconstruction:{RESET}")
    print(f"    python pipeline.py view --input datasets/output/dense_cloud_clean.ply")
    print(f"    python pipeline.py web")
    print()


# ================================================================
# CLI Entry Point
# ================================================================

def main():
    parser = argparse.ArgumentParser(
        description="E99 3D Mapping and Exploration Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  run          Full pipeline: video -> 3D model
  capture      Record live FPV stream from drone
  extract      Extract frames from video
  keyframes    Select best keyframes
  enhance      Enhance images for reconstruction
  reconstruct  Run COLMAP reconstruction
  optimize     Clean and optimize point cloud
  mesh         Generate mesh from point cloud
  view         Launch Open3D interactive viewer
  web          Launch Three.js web viewer
  export       Export final results

Examples:
  python pipeline.py run --input video.mp4
  python pipeline.py run --input video.mp4 --sparse-only
  python pipeline.py run --input path/to/images/
  python pipeline.py view --input datasets/output/dense_cloud_clean.ply
  python pipeline.py web
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Pipeline command")

    # --- run ---
    p_run = subparsers.add_parser("run", help="Full pipeline: video -> 3D model")
    p_run.add_argument("--input", required=True, help="Input video file or frames directory")
    p_run.add_argument("--fps", type=float, help="Frame extraction rate")
    p_run.add_argument("--sparse-only", action="store_true", help="Skip dense reconstruction")
    p_run.add_argument("--no-mesh", action="store_true", help="Skip mesh generation")

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

    # --- keyframes ---
    p_kf = subparsers.add_parser("keyframes", help="Select keyframes")
    p_kf.add_argument("--input", help="Input frames directory")
    p_kf.add_argument("--output", help="Output keyframes directory")
    p_kf.add_argument("--blur", type=float, help="Blur threshold")

    # --- enhance ---
    p_enh = subparsers.add_parser("enhance", help="Enhance images")
    p_enh.add_argument("--input", help="Input images directory")
    p_enh.add_argument("--output", help="Output directory")

    # --- reconstruct ---
    p_rec = subparsers.add_parser("reconstruct", help="Run COLMAP reconstruction")
    p_rec.add_argument("--input", required=True, help="Input images directory")
    p_rec.add_argument("--workspace", help="COLMAP workspace directory")
    p_rec.add_argument("--sparse-only", action="store_true", help="Skip dense reconstruction")
    p_rec.add_argument("--no-mesh", action="store_true", help="Skip mesh generation")

    # --- optimize ---
    p_opt = subparsers.add_parser("optimize", help="Optimize point cloud")
    p_opt.add_argument("--input", required=True, help="Input PLY file")
    p_opt.add_argument("--output", help="Output PLY file")

    # --- mesh ---
    p_mesh = subparsers.add_parser("mesh", help="Generate mesh from point cloud")
    p_mesh.add_argument("--input", required=True, help="Input PLY point cloud")
    p_mesh.add_argument("--output", help="Output mesh path")
    p_mesh.add_argument("--depth", type=int, default=9, help="Poisson depth")
    p_mesh.add_argument("--decimate", type=int, help="Target triangle count")
    p_mesh.add_argument("--workspace", help="COLMAP workspace for poisson mesher")

    # --- view ---
    p_view = subparsers.add_parser("view", help="Launch Open3D viewer")
    p_view.add_argument("--input", required=True, help="PLY or mesh file")
    p_view.add_argument("--workspace", help="COLMAP workspace for trajectory")

    # --- web ---
    p_web = subparsers.add_parser("web", help="Launch web viewer")
    p_web.add_argument("--port", type=int, help="Server port")
    p_web.add_argument("--data", help="Datasets directory")

    # --- export ---
    p_exp = subparsers.add_parser("export", help="Export results")
    p_exp.add_argument("--workspace", help="COLMAP workspace")
    p_exp.add_argument("--output", help="Output directory")

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
        "keyframes": cmd_keyframes,
        "enhance": cmd_enhance,
        "reconstruct": cmd_reconstruct,
        "optimize": cmd_optimize,
        "mesh": cmd_mesh,
        "view": cmd_view,
        "web": cmd_web,
        "export": cmd_export,
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
