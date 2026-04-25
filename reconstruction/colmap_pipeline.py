"""
COLMAP Pipeline
================
Full COLMAP reconstruction automation via CLI subprocess calls.
Handles feature extraction, matching, SfM, dense reconstruction, and meshing.

Requires COLMAP installed and accessible on PATH (or configured in config.py).
Download: https://github.com/colmap/colmap/releases
"""

import subprocess
import shutil
import time
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def find_colmap() -> str:
    """Find the COLMAP executable."""
    if config.COLMAP_EXECUTABLE:
        exe = Path(config.COLMAP_EXECUTABLE)
        if exe.exists():
            return str(exe)
        raise FileNotFoundError(f"COLMAP not found at: {config.COLMAP_EXECUTABLE}")

    # Try common locations
    candidates = [
        "colmap",
        "COLMAP.bat",
        r"C:\Program Files\COLMAP\COLMAP.bat",
        r"C:\COLMAP\COLMAP.bat",
    ]

    for candidate in candidates:
        if shutil.which(candidate):
            return candidate

    raise FileNotFoundError(
        "COLMAP not found on PATH!\n"
        "Install COLMAP with CUDA from:\n"
        "  https://github.com/colmap/colmap/releases\n"
        "Then add the COLMAP directory to your system PATH,\n"
        "or set COLMAP_EXECUTABLE in config.py."
    )


def run_colmap_cmd(colmap_exe: str, command: str, args: dict,
                   description: str = "") -> bool:
    """Run a COLMAP CLI command with arguments.

    Args:
        colmap_exe: Path to COLMAP executable.
        command: COLMAP command (e.g., 'feature_extractor').
        args: Dict of argument name → value.
        description: Human-readable description for logging.

    Returns:
        True if successful.
    """
    cmd = [colmap_exe, command]
    for key, value in args.items():
        cmd.append(f"--{key}")
        cmd.append(str(value))

    cmd_str = " ".join(cmd)

    if description:
        print(f"\n  {'─' * 56}")
        print(f"  {description}")
        print(f"  {'─' * 56}")

    print(f"  CMD: {cmd_str[:120]}{'...' if len(cmd_str) > 120 else ''}")
    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=7200,  # 2-hour timeout
        )

        elapsed = time.time() - start_time

        if result.returncode == 0:
            print(f"  ✅ Done in {elapsed:.1f}s")
            # Print last few lines of stdout for context
            stdout_lines = result.stdout.strip().split("\n")
            for line in stdout_lines[-5:]:
                if line.strip():
                    print(f"     {line.strip()}")
            return True
        else:
            print(f"  ❌ Failed (exit code {result.returncode}) after {elapsed:.1f}s")
            print(f"  STDERR: {result.stderr[:500]}")
            if result.stdout:
                print(f"  STDOUT: {result.stdout[-500:]}")
            return False

    except subprocess.TimeoutExpired:
        print(f"  ❌ Timed out after 2 hours!")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def run_feature_extraction(colmap_exe: str, database_path: str,
                           image_path: str) -> bool:
    """Step 1: Extract SIFT features from all images."""
    return run_colmap_cmd(colmap_exe, "feature_extractor", {
        "database_path": database_path,
        "image_path": image_path,
        "ImageReader.single_camera": 1 if config.SIFT_SINGLE_CAMERA else 0,
        "ImageReader.camera_model": "SIMPLE_RADIAL",
        "SiftExtraction.max_image_size": config.SIFT_MAX_IMAGE_SIZE,
        "SiftExtraction.max_num_features": config.SIFT_MAX_NUM_FEATURES,
        "SiftExtraction.use_gpu": 1 if config.DENSE_USE_GPU else 0,
        "SiftExtraction.gpu_index": config.DENSE_GPU_INDEX,
    }, "Step 1/6: Feature Extraction (SIFT)")


def run_feature_matching(colmap_exe: str, database_path: str,
                         matcher_type: str = None) -> bool:
    """Step 2: Match features between images."""
    if matcher_type is None:
        matcher_type = config.MATCHER_TYPE

    if matcher_type == "sequential":
        return run_colmap_cmd(colmap_exe, "sequential_matcher", {
            "database_path": database_path,
            "SequentialMatching.overlap": config.SEQUENTIAL_OVERLAP,
            "SequentialMatching.loop_detection": 1 if config.SEQUENTIAL_LOOP_DETECTION else 0,
            "SiftMatching.use_gpu": 1 if config.DENSE_USE_GPU else 0,
            "SiftMatching.gpu_index": config.DENSE_GPU_INDEX,
        }, "Step 2/6: Feature Matching (Sequential)")
    else:
        return run_colmap_cmd(colmap_exe, "exhaustive_matcher", {
            "database_path": database_path,
            "SiftMatching.use_gpu": 1 if config.DENSE_USE_GPU else 0,
            "SiftMatching.gpu_index": config.DENSE_GPU_INDEX,
        }, "Step 2/6: Feature Matching (Exhaustive)")


def run_sparse_reconstruction(colmap_exe: str, database_path: str,
                              image_path: str, output_path: str) -> bool:
    """Step 3: Run Structure-from-Motion to get sparse point cloud + camera poses."""
    Path(output_path).mkdir(parents=True, exist_ok=True)

    return run_colmap_cmd(colmap_exe, "mapper", {
        "database_path": database_path,
        "image_path": image_path,
        "output_path": output_path,
        "Mapper.min_num_matches": config.MAPPER_MIN_NUM_MATCHES,
        "Mapper.init_min_tri_angle": 4,
        "Mapper.multiple_models": 0,
    }, "Step 3/6: Sparse Reconstruction (SfM)")


def run_image_undistorter(colmap_exe: str, image_path: str,
                          sparse_path: str, output_path: str) -> bool:
    """Step 4a: Undistort images for dense reconstruction."""
    return run_colmap_cmd(colmap_exe, "image_undistorter", {
        "image_path": image_path,
        "input_path": sparse_path,
        "output_path": output_path,
        "output_type": "COLMAP",
        "max_image_size": config.DENSE_MAX_IMAGE_SIZE,
    }, "Step 4a/6: Image Undistortion")


def run_dense_stereo(colmap_exe: str, workspace_path: str) -> bool:
    """Step 4b: Dense stereo matching (PatchMatch)."""
    args = {
        "workspace_path": workspace_path,
        "workspace_format": "COLMAP",
        "PatchMatchStereo.window_radius": config.PATCH_MATCH_WINDOW_RADIUS,
        "PatchMatchStereo.num_samples": config.PATCH_MATCH_NUM_SAMPLES,
        "PatchMatchStereo.num_iterations": config.PATCH_MATCH_NUM_ITERATIONS,
        "PatchMatchStereo.geom_consistency": 1 if config.PATCH_MATCH_GEOM_CONSISTENCY else 0,
    }

    if config.DENSE_USE_GPU:
        args["PatchMatchStereo.gpu_index"] = str(config.DENSE_GPU_INDEX)
    else:
        args["PatchMatchStereo.gpu_index"] = "-1"

    return run_colmap_cmd(colmap_exe, "patch_match_stereo", args,
                          "Step 4b/6: Dense Stereo (PatchMatch MVS)")


def run_stereo_fusion(colmap_exe: str, workspace_path: str,
                      output_path: str) -> bool:
    """Step 5: Fuse depth maps into dense point cloud."""
    return run_colmap_cmd(colmap_exe, "stereo_fusion", {
        "workspace_path": workspace_path,
        "workspace_format": "COLMAP",
        "input_type": "geometric",
        "output_path": output_path,
        "StereoFusion.min_num_pixels": config.FUSION_MIN_NUM_PIXELS,
        "StereoFusion.max_reproj_error": config.FUSION_MAX_REPROJ_ERROR,
    }, "Step 5/6: Stereo Fusion → Dense Point Cloud")


def run_meshing(colmap_exe: str, dense_path: str, output_path: str) -> bool:
    """Step 6: Generate mesh from dense point cloud (optional)."""
    return run_colmap_cmd(colmap_exe, "poisson_mesher", {
        "input_path": dense_path,
        "output_path": output_path,
    }, "Step 6/6: Poisson Mesh Generation")


def count_registered_images(sparse_dir: str) -> int:
    """Count how many images were registered in the sparse reconstruction."""
    images_file = Path(sparse_dir) / "0" / "images.txt"
    if not images_file.exists():
        images_file = Path(sparse_dir) / "images.txt"
    if not images_file.exists():
        return 0

    count = 0
    with open(images_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                count += 1
    # images.txt has 2 lines per image (pose + points2D)
    return count // 2


def run_full_pipeline(image_path: str, workspace: str = None,
                      skip_dense: bool = False, skip_mesh: bool = False) -> dict:
    """Run the complete COLMAP reconstruction pipeline.

    Args:
        image_path: Directory containing input images.
        workspace: COLMAP workspace directory. None = config default.
        skip_dense: Skip dense reconstruction (sparse only).
        skip_mesh: Skip mesh generation.

    Returns:
        Dict with pipeline results and paths.
    """
    if workspace is None:
        workspace = str(config.COLMAP_WORKSPACE)

    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    database_path = str(workspace / "database.db")
    sparse_path = str(workspace / "sparse")
    dense_path = str(workspace / "dense")
    mesh_path = str(workspace / "mesh")

    # Clean previous run
    db_file = Path(database_path)
    if db_file.exists():
        db_file.unlink()

    results = {
        "success": False,
        "image_path": str(image_path),
        "workspace": str(workspace),
        "stages": {},
    }

    print("\n" + "=" * 60)
    print("  COLMAP 3D Reconstruction Pipeline")
    print("=" * 60)
    print(f"  Images: {image_path}")
    print(f"  Workspace: {workspace}")
    print(f"  GPU: {'Enabled' if config.DENSE_USE_GPU else 'CPU only'}")
    print(f"  Dense: {'Skip' if skip_dense else 'Yes'}")
    print(f"  Mesh: {'Skip' if skip_mesh else 'Yes'}")

    # Find COLMAP
    try:
        colmap_exe = find_colmap()
        print(f"  COLMAP: {colmap_exe}")
    except FileNotFoundError as e:
        print(f"\n  ❌ {e}")
        return results

    pipeline_start = time.time()

    # Step 1: Feature extraction
    ok = run_feature_extraction(colmap_exe, database_path, str(image_path))
    results["stages"]["feature_extraction"] = ok
    if not ok:
        print("\n  ❌ Feature extraction failed!")
        return results

    # Step 2: Feature matching
    ok = run_feature_matching(colmap_exe, database_path)
    results["stages"]["feature_matching"] = ok
    if not ok:
        # Try exhaustive matching as fallback
        print("  ⚠️ Sequential matching failed, trying exhaustive...")
        ok = run_feature_matching(colmap_exe, database_path, "exhaustive")
        results["stages"]["feature_matching_exhaustive"] = ok
        if not ok:
            print("\n  ❌ Feature matching failed!")
            return results

    # Step 3: Sparse reconstruction
    ok = run_sparse_reconstruction(colmap_exe, database_path, str(image_path), sparse_path)
    results["stages"]["sparse_reconstruction"] = ok
    if not ok:
        print("\n  ❌ Sparse reconstruction failed!")
        return results

    # Check registration quality
    registered = count_registered_images(sparse_path)
    total_images = len(list(Path(image_path).glob("*.*")))
    registration_rate = registered / max(total_images, 1)
    results["registered_images"] = registered
    results["total_images"] = total_images
    results["registration_rate"] = round(registration_rate * 100, 1)

    print(f"\n  📊 Registered {registered}/{total_images} images "
          f"({results['registration_rate']}%)")

    if registration_rate < config.EXHAUSTIVE_FALLBACK_THRESHOLD:
        print(f"  ⚠️ Low registration rate! Consider exhaustive matching.")

    # Locate the reconstruction (COLMAP creates numbered subdirectories)
    sparse_sub = Path(sparse_path) / "0"
    if not sparse_sub.exists():
        # Try to find any valid reconstruction
        subdirs = [d for d in Path(sparse_path).iterdir() if d.is_dir()]
        if subdirs:
            sparse_sub = subdirs[0]
        else:
            print("  ❌ No sparse reconstruction found!")
            return results

    results["sparse_model_path"] = str(sparse_sub)

    # Export sparse point cloud as PLY
    sparse_ply = str(workspace / "sparse_cloud.ply")
    run_colmap_cmd(colmap_exe, "model_converter", {
        "input_path": str(sparse_sub),
        "output_path": sparse_ply,
        "output_type": "PLY",
    }, "Exporting sparse point cloud to PLY")
    results["sparse_ply"] = sparse_ply

    if skip_dense:
        results["success"] = True
        elapsed = time.time() - pipeline_start
        results["total_time_seconds"] = round(elapsed, 1)
        print(f"\n  ✅ Sparse reconstruction complete in {elapsed:.1f}s")
        return results

    # Step 4a: Undistort images
    ok = run_image_undistorter(colmap_exe, str(image_path), str(sparse_sub), dense_path)
    results["stages"]["undistortion"] = ok
    if not ok:
        print("\n  ❌ Image undistortion failed!")
        results["success"] = True  # Sparse still works
        return results

    # Step 4b: Dense stereo
    ok = run_dense_stereo(colmap_exe, dense_path)
    results["stages"]["dense_stereo"] = ok
    if not ok:
        print("\n  ❌ Dense stereo failed!")
        if config.DENSE_USE_GPU:
            print("  💡 Try reducing DENSE_MAX_IMAGE_SIZE in config.py (VRAM issue?)")
        results["success"] = True  # Sparse still works
        return results

    # Step 5: Stereo fusion
    dense_ply = str(workspace / "dense_cloud.ply")
    ok = run_stereo_fusion(colmap_exe, dense_path, dense_ply)
    results["stages"]["stereo_fusion"] = ok
    results["dense_ply"] = dense_ply
    if not ok:
        print("\n  ❌ Stereo fusion failed!")
        results["success"] = True
        return results

    # Step 6: Mesh (optional)
    if not skip_mesh:
        Path(mesh_path).mkdir(parents=True, exist_ok=True)
        mesh_output = str(Path(mesh_path) / "mesh.ply")
        ok = run_meshing(colmap_exe, dense_ply, mesh_output)
        results["stages"]["meshing"] = ok
        if ok:
            results["mesh_path"] = mesh_output

    results["success"] = True
    elapsed = time.time() - pipeline_start
    results["total_time_seconds"] = round(elapsed, 1)

    print(f"\n  {'=' * 56}")
    print(f"  ✅ COLMAP Pipeline Complete — {elapsed:.1f}s total")
    print(f"  {'=' * 56}")
    if "sparse_ply" in results:
        print(f"  Sparse: {results['sparse_ply']}")
    if "dense_ply" in results:
        print(f"  Dense:  {results['dense_ply']}")
    if "mesh_path" in results:
        print(f"  Mesh:   {results['mesh_path']}")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run COLMAP reconstruction pipeline")
    parser.add_argument("images", help="Directory containing input images")
    parser.add_argument("--workspace", help="COLMAP workspace directory")
    parser.add_argument("--sparse-only", action="store_true", help="Skip dense reconstruction")
    parser.add_argument("--no-mesh", action="store_true", help="Skip mesh generation")
    args = parser.parse_args()

    run_full_pipeline(args.images, args.workspace, args.sparse_only, args.no_mesh)
