"""
Export Utilities
=================
Converts COLMAP outputs to standard formats (PLY, OBJ, JSON)
and copies final results to the output directory.
"""

import shutil
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config


def export_results(workspace: str = None, output_dir: str = None) -> dict:
    """Collect and export all reconstruction results to the output directory.

    Args:
        workspace: COLMAP workspace directory. None = config default.
        output_dir: Output directory. None = config default.

    Returns:
        Dict with exported file paths.
    """
    if workspace is None:
        workspace = str(config.COLMAP_WORKSPACE)
    if output_dir is None:
        output_dir = str(config.OUTPUT_DIR)

    workspace = Path(workspace)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    exports = {}

    print("\n  Exporting results...")

    # Copy sparse point cloud
    sparse_ply = workspace / "sparse_cloud.ply"
    if sparse_ply.exists():
        dst = output_dir / "sparse_cloud.ply"
        shutil.copy2(str(sparse_ply), str(dst))
        exports["sparse_ply"] = str(dst)
        size_mb = dst.stat().st_size / 1024 / 1024
        print(f"  ✅ Sparse PLY: {dst} ({size_mb:.1f} MB)")

    # Copy dense point cloud
    dense_ply = workspace / "dense_cloud.ply"
    if dense_ply.exists():
        dst = output_dir / "dense_cloud.ply"
        shutil.copy2(str(dense_ply), str(dst))
        exports["dense_ply"] = str(dst)
        size_mb = dst.stat().st_size / 1024 / 1024
        print(f"  ✅ Dense PLY: {dst} ({size_mb:.1f} MB)")

    # Copy cleaned point cloud
    clean_ply = workspace / "dense_cloud_clean.ply"
    if clean_ply.exists():
        dst = output_dir / "dense_cloud_clean.ply"
        shutil.copy2(str(clean_ply), str(dst))
        exports["clean_ply"] = str(dst)
        size_mb = dst.stat().st_size / 1024 / 1024
        print(f"  ✅ Clean PLY: {dst} ({size_mb:.1f} MB)")

    # Copy mesh
    for mesh_name in ["mesh.ply", "mesh.obj", "mesh_decimated.ply"]:
        mesh_path = workspace / "mesh" / mesh_name
        if mesh_path.exists():
            dst = output_dir / mesh_name
            shutil.copy2(str(mesh_path), str(dst))
            key = mesh_name.replace(".", "_")
            exports[key] = str(dst)
            size_mb = dst.stat().st_size / 1024 / 1024
            print(f"  ✅ Mesh: {dst} ({size_mb:.1f} MB)")

    # Export trajectory JSON (for web viewer)
    trajectory = export_trajectory(workspace, output_dir)
    if trajectory:
        exports["trajectory_json"] = trajectory

    # Write summary
    summary_path = output_dir / "reconstruction_summary.json"
    with open(summary_path, "w") as f:
        json.dump(exports, f, indent=2)
    print(f"  ✅ Summary: {summary_path}")

    return exports


def export_trajectory(workspace: str = None, output_dir: str = None) -> str:
    """Export COLMAP camera trajectory as JSON for the web viewer.

    Args:
        workspace: COLMAP workspace path.
        output_dir: Output directory.

    Returns:
        Path to trajectory JSON, or None.
    """
    if workspace is None:
        workspace = str(config.COLMAP_WORKSPACE)
    if output_dir is None:
        output_dir = str(config.OUTPUT_DIR)

    workspace = Path(workspace)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Import trajectory parser
    from viewer.trajectory_visualizer import find_colmap_images_txt, parse_colmap_images

    images_txt = find_colmap_images_txt(str(workspace))
    if not images_txt:
        print("  ⚠️ No images.txt found — skipping trajectory export")
        return None

    cameras = parse_colmap_images(images_txt)
    if not cameras:
        print("  ⚠️ No camera poses found")
        return None

    trajectory = {
        "camera_count": len(cameras),
        "cameras": [{
            "name": cam["name"],
            "position": cam["position"],
            "quaternion": cam["quaternion"],
        } for cam in cameras]
    }

    traj_path = str(output_dir / "trajectory.json")
    with open(traj_path, "w") as f:
        json.dump(trajectory, f, indent=2)

    print(f"  ✅ Trajectory: {traj_path} ({len(cameras)} cameras)")
    return traj_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export reconstruction results")
    parser.add_argument("--workspace", help="COLMAP workspace")
    parser.add_argument("--output", help="Output directory")
    args = parser.parse_args()

    export_results(args.workspace, args.output)
