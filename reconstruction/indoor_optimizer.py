"""
Indoor Optimizer
=================
Post-reconstruction point cloud cleaning and optimization for indoor scenes.
Removes noise, outliers, and applies voxel downsampling for uniform density.

Uses plyfile + scipy + numpy (no Open3D required).
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def load_ply(ply_path: str) -> dict:
    """Load a PLY point cloud using plyfile.

    Returns:
        Dict with 'points' (Nx3), 'colors' (Nx3, 0-255 uint8 or None),
        and 'normals' (Nx3 or None).
    """
    from plyfile import PlyData

    ply = PlyData.read(ply_path)
    vertex = ply['vertex']

    points = np.column_stack([
        vertex['x'], vertex['y'], vertex['z']
    ]).astype(np.float64)

    # Try to load colors
    colors = None
    try:
        colors = np.column_stack([
            vertex['red'], vertex['green'], vertex['blue']
        ]).astype(np.uint8)
    except (ValueError, KeyError):
        pass

    # Try to load normals
    normals = None
    try:
        normals = np.column_stack([
            vertex['nx'], vertex['ny'], vertex['nz']
        ]).astype(np.float64)
    except (ValueError, KeyError):
        pass

    print(f"  Loaded: {len(points)} points from {Path(ply_path).name}")
    return {"points": points, "colors": colors, "normals": normals}


def save_ply(data: dict, ply_path: str):
    """Save a point cloud dict to PLY using plyfile.

    Args:
        data: Dict with 'points', optional 'colors', optional 'normals'.
        ply_path: Output file path.
    """
    from plyfile import PlyData, PlyElement

    points = data["points"]
    colors = data.get("colors")
    normals = data.get("normals")
    n = len(points)

    # Build dtype
    dtype_list = [('x', 'f4'), ('y', 'f4'), ('z', 'f4')]
    if normals is not None and len(normals) == n:
        dtype_list += [('nx', 'f4'), ('ny', 'f4'), ('nz', 'f4')]
    if colors is not None and len(colors) == n:
        dtype_list += [('red', 'u1'), ('green', 'u1'), ('blue', 'u1')]

    vertex_array = np.empty(n, dtype=dtype_list)
    vertex_array['x'] = points[:, 0]
    vertex_array['y'] = points[:, 1]
    vertex_array['z'] = points[:, 2]

    if normals is not None and len(normals) == n:
        vertex_array['nx'] = normals[:, 0]
        vertex_array['ny'] = normals[:, 1]
        vertex_array['nz'] = normals[:, 2]

    if colors is not None and len(colors) == n:
        vertex_array['red'] = colors[:, 0]
        vertex_array['green'] = colors[:, 1]
        vertex_array['blue'] = colors[:, 2]

    el = PlyElement.describe(vertex_array, 'vertex')
    PlyData([el], text=False).write(ply_path)
    print(f"  Saved: {n} points -> {ply_path}")


def _filter_by_mask(data: dict, mask: np.ndarray) -> dict:
    """Keep only points where mask is True."""
    result = {"points": data["points"][mask]}
    if data.get("colors") is not None:
        result["colors"] = data["colors"][mask]
    if data.get("normals") is not None:
        result["normals"] = data["normals"][mask]
    return result


def statistical_outlier_removal(data: dict, nb_neighbors: int = None,
                                std_ratio: float = None) -> dict:
    """Remove statistical outliers (points far from their neighbors).

    For each point, computes the mean distance to its k nearest neighbors.
    Points where this distance exceeds (global_mean + std_ratio * global_std)
    are removed.
    """
    from scipy.spatial import KDTree

    if nb_neighbors is None:
        nb_neighbors = config.SOR_NB_NEIGHBORS
    if std_ratio is None:
        std_ratio = config.SOR_STD_RATIO

    points = data["points"]
    before = len(points)

    tree = KDTree(points)
    # Query k+1 neighbors (first is always the point itself)
    dists, _ = tree.query(points, k=nb_neighbors + 1)
    mean_dists = dists[:, 1:].mean(axis=1)  # Exclude self (distance=0)

    global_mean = mean_dists.mean()
    global_std = mean_dists.std()
    threshold = global_mean + std_ratio * global_std

    mask = mean_dists < threshold
    result = _filter_by_mask(data, mask)

    after = len(result["points"])
    removed = before - after
    print(f"  Statistical outlier removal: {before} -> {after} "
          f"(removed {removed}, {removed/max(before,1)*100:.1f}%)")
    return result


def radius_outlier_removal(data: dict, nb_points: int = None,
                           radius: float = None) -> dict:
    """Remove radius outliers (isolated points with few neighbors).

    Removes points that have fewer than nb_points neighbors within
    the given radius.
    """
    from scipy.spatial import KDTree

    if nb_points is None:
        nb_points = config.ROR_NB_POINTS
    if radius is None:
        radius = config.ROR_RADIUS

    points = data["points"]
    before = len(points)

    tree = KDTree(points)
    # Count neighbors within radius for each point
    neighbor_counts = tree.query_ball_point(points, r=radius, return_length=True)

    # A point counts itself, so we need nb_points+1
    mask = neighbor_counts >= (nb_points + 1)
    result = _filter_by_mask(data, mask)

    after = len(result["points"])
    removed = before - after
    removal_pct = removed / max(before, 1) * 100
    print(f"  Radius outlier removal: {before} -> {after} "
          f"(removed {removed}, {removal_pct:.1f}%)")

    # Safety: if ROR wiped out > 50% of points, the radius is too tight.
    # Fall back to the input data to avoid destroying the cloud.
    if after < before * 0.5:
        print(f"  [WARN] ROR removed > 50% of points — radius {radius} too tight for this scene.")
        print(f"         Skipping ROR and keeping original {before} points.")
        return data

    return result


def voxel_downsample(data: dict, voxel_size: float = None) -> dict:
    """Downsample point cloud using voxel grid for uniform density.

    Each voxel keeps the centroid of all points falling inside it.
    Colors are averaged.
    """
    if voxel_size is None:
        voxel_size = config.VOXEL_SIZE

    points = data["points"]
    before = len(points)

    # Guard: can't downsample an empty cloud
    if before == 0:
        print("  Voxel downsample: skipped (0 points)")
        return data

    # Quantize points to voxel indices
    voxel_indices = np.floor(points / voxel_size).astype(np.int64)

    # Create unique voxel keys
    # Pack 3 ints into a single key using a large offset
    offsets = voxel_indices - voxel_indices.min(axis=0)
    dims = offsets.max(axis=0) + 1
    keys = offsets[:, 0] * (dims[1] * dims[2]) + offsets[:, 1] * dims[2] + offsets[:, 2]

    # Group points by voxel key
    unique_keys, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)

    # Compute centroids
    n_voxels = len(unique_keys)
    new_points = np.zeros((n_voxels, 3))
    np.add.at(new_points, inverse, points)
    new_points /= counts[:, np.newaxis]

    result = {"points": new_points, "colors": None, "normals": None}

    # Average colors
    if data.get("colors") is not None:
        new_colors = np.zeros((n_voxels, 3), dtype=np.float64)
        np.add.at(new_colors, inverse, data["colors"].astype(np.float64))
        new_colors /= counts[:, np.newaxis]
        result["colors"] = np.clip(new_colors, 0, 255).astype(np.uint8)

    after = n_voxels
    print(f"  Voxel downsampling ({voxel_size}m): {before} -> {after} "
          f"({after/max(before,1)*100:.1f}% retained)")
    return result


def estimate_normals(data: dict, k: int = 30) -> dict:
    """Estimate point normals using PCA on local neighborhoods."""
    from scipy.spatial import KDTree

    points = data["points"]
    tree = KDTree(points)
    _, indices = tree.query(points, k=min(k, len(points)))

    normals = np.zeros_like(points)

    for i in range(len(points)):
        neighbors = points[indices[i]]
        centered = neighbors - neighbors.mean(axis=0)
        cov = centered.T @ centered
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        # Normal is the eigenvector with smallest eigenvalue
        normals[i] = eigenvectors[:, 0]

    # Consistent orientation: flip normals pointing away from centroid
    centroid = points.mean(axis=0)
    directions = points - centroid
    flip = np.sum(normals * directions, axis=1) < 0
    normals[flip] *= -1

    data["normals"] = normals
    print(f"  Normals estimated for {len(points)} points")
    return data


def crop_to_bounding_box(data: dict, margin_factor: float = 0.1) -> dict:
    """Remove extreme outliers by cropping to a tight bounding box.

    Uses percentile-based bounds to avoid being affected by extreme outliers.
    """
    points = data["points"]
    if len(points) == 0:
        return data

    # Use 1st and 99th percentile as bounds
    lower = np.percentile(points, 1, axis=0)
    upper = np.percentile(points, 99, axis=0)

    # Add margin
    extent = upper - lower
    lower -= extent * margin_factor
    upper += extent * margin_factor

    mask = np.all((points >= lower) & (points <= upper), axis=1)

    before = len(points)
    result = _filter_by_mask(data, mask)
    after = len(result["points"])

    if before != after:
        print(f"  Bounding box crop: {before} -> {after} "
              f"(removed {before - after} extreme outliers)")
    return result


def optimize_point_cloud(input_ply: str, output_ply: str = None,
                         enable_sor: bool = True, enable_ror: bool = True,
                         enable_voxel: bool = True, enable_crop: bool = True,
                         enable_normals: bool = True) -> dict:
    """Run full indoor optimization pipeline on a point cloud.

    Args:
        input_ply: Input PLY point cloud path.
        output_ply: Output PLY path. None = overwrite with "_clean" suffix.
        enable_sor: Enable statistical outlier removal.
        enable_ror: Enable radius outlier removal.
        enable_voxel: Enable voxel downsampling.
        enable_crop: Enable bounding box cropping.
        enable_normals: Enable normal estimation.

    Returns:
        Dict with optimization statistics.
    """
    if output_ply is None:
        p = Path(input_ply)
        output_ply = str(p.parent / f"{p.stem}_clean{p.suffix}")

    print("\n" + "=" * 60)
    print("  Indoor Point Cloud Optimization")
    print("=" * 60)

    data = load_ply(input_ply)
    original_count = len(data["points"])

    if enable_crop:
        data = crop_to_bounding_box(data)

    if enable_sor:
        data = statistical_outlier_removal(data)

    if enable_ror:
        data = radius_outlier_removal(data)

    if enable_voxel:
        data = voxel_downsample(data)

    if enable_normals:
        data = estimate_normals(data)

    save_ply(data, output_ply)

    final_count = len(data["points"])
    stats = {
        "original_points": original_count,
        "final_points": final_count,
        "reduction_percent": round((1 - final_count / max(original_count, 1)) * 100, 1),
        "output_ply": output_ply,
    }

    print(f"\n  [OK] Optimization complete: {original_count} -> {final_count} points "
          f"({stats['reduction_percent']}% reduction)")

    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Optimize indoor point cloud")
    parser.add_argument("input", help="Input PLY file")
    parser.add_argument("--output", help="Output PLY file")
    parser.add_argument("--no-sor", action="store_true")
    parser.add_argument("--no-ror", action="store_true")
    parser.add_argument("--no-voxel", action="store_true")
    args = parser.parse_args()

    optimize_point_cloud(
        args.input, args.output,
        enable_sor=not args.no_sor,
        enable_ror=not args.no_ror,
        enable_voxel=not args.no_voxel,
    )
