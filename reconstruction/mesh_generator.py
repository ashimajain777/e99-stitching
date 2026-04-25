"""
Mesh Generator
===============
Generate mesh from dense point cloud using scipy Delaunay triangulation.
Exports PLY mesh. For higher-quality Poisson meshing, COLMAP's built-in
mesher is used instead (no Open3D needed).

Uses plyfile + scipy + numpy only.
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def poisson_mesh_colmap(workspace: str, output_path: str = None) -> str:
    """Generate mesh using COLMAP's built-in Poisson mesher.

    This uses COLMAP's delaunay_mesher which runs on the dense
    reconstruction directly — no Open3D needed.

    Args:
        workspace: Path to COLMAP workspace (containing dense/).
        output_path: Output mesh path. None = auto.

    Returns:
        Path to output mesh file.
    """
    import subprocess

    workspace = Path(workspace)
    if output_path is None:
        mesh_dir = workspace / "mesh"
        mesh_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(mesh_dir / "mesh.ply")

    dense_path = workspace / "dense"
    if not dense_path.exists():
        dense_path = workspace

    colmap_cmd = config.COLMAP_EXECUTABLE

    cmd = [
        colmap_cmd, "delaunay_mesher",
        "--input_path", str(dense_path),
        "--output_path", output_path,
    ]

    print(f"  Running COLMAP Delaunay mesher...")
    print(f"  Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            print(f"  [OK] Mesh generated: {output_path}")
            return output_path
        else:
            print(f"  [WARN] COLMAP mesher failed: {result.stderr[:300]}")
            return None
    except FileNotFoundError:
        print(f"  [WARN] COLMAP not found at '{colmap_cmd}'")
        return None
    except subprocess.TimeoutExpired:
        print(f"  [WARN] COLMAP mesher timed out")
        return None


def simple_mesh_from_ply(input_ply: str, output_path: str = None,
                         max_points: int = 100000) -> str:
    """Generate a simple triangulated mesh from a point cloud.

    Uses scipy Delaunay triangulation on a projected 2D grid. This is
    simpler than Poisson reconstruction but works without Open3D.

    Args:
        input_ply: Input PLY point cloud.
        output_path: Output mesh file. None = auto.
        max_points: Max points to use (downsample if larger).

    Returns:
        Path to output mesh file.
    """
    from plyfile import PlyData, PlyElement
    from scipy.spatial import Delaunay

    if output_path is None:
        p = Path(input_ply)
        output_path = str(p.parent / f"{p.stem}_mesh.ply")

    print(f"  Loading point cloud: {input_ply}")
    ply = PlyData.read(input_ply)
    vertex = ply['vertex']
    n = len(vertex['x'])

    points = np.column_stack([vertex['x'], vertex['y'], vertex['z']])

    # Load colors if available
    colors = None
    try:
        colors = np.column_stack([
            vertex['red'], vertex['green'], vertex['blue']
        ]).astype(np.uint8)
    except (ValueError, KeyError):
        pass

    print(f"  Points: {n}")

    # Downsample if too many points (Delaunay is O(n log n) in 2D)
    if n > max_points:
        indices = np.random.choice(n, max_points, replace=False)
        indices.sort()
        points = points[indices]
        if colors is not None:
            colors = colors[indices]
        n = max_points
        print(f"  Downsampled to {n} for meshing")

    # Project to 2D for Delaunay (use XZ plane — typical for indoor floors)
    points_2d = points[:, [0, 2]]  # X and Z

    print(f"  Running Delaunay triangulation...")
    tri = Delaunay(points_2d)
    faces = tri.simplices  # Nx3 array of vertex indices

    # Filter out very large/stretched triangles (artifacts)
    edge_threshold = np.percentile(
        np.linalg.norm(points[faces[:, 0]] - points[faces[:, 1]], axis=1), 95
    ) * 2

    valid = np.ones(len(faces), dtype=bool)
    for i in range(3):
        j = (i + 1) % 3
        edge_len = np.linalg.norm(points[faces[:, i]] - points[faces[:, j]], axis=1)
        valid &= (edge_len < edge_threshold)

    faces = faces[valid]
    print(f"  Mesh: {n} vertices, {len(faces)} triangles")

    # Write PLY mesh
    vertex_dtype = [('x', 'f4'), ('y', 'f4'), ('z', 'f4')]
    if colors is not None:
        vertex_dtype += [('red', 'u1'), ('green', 'u1'), ('blue', 'u1')]

    vertex_array = np.empty(n, dtype=vertex_dtype)
    vertex_array['x'] = points[:, 0]
    vertex_array['y'] = points[:, 1]
    vertex_array['z'] = points[:, 2]

    if colors is not None:
        vertex_array['red'] = colors[:, 0]
        vertex_array['green'] = colors[:, 1]
        vertex_array['blue'] = colors[:, 2]

    # Face data (list of vertex_indices arrays)
    face_dtype = [('vertex_indices', 'i4', (3,))]
    face_array = np.empty(len(faces), dtype=face_dtype)
    face_array['vertex_indices'] = faces

    vertex_el = PlyElement.describe(vertex_array, 'vertex')
    face_el = PlyElement.describe(face_array, 'face')

    PlyData([vertex_el, face_el], text=False).write(output_path)
    print(f"  [OK] Saved mesh: {output_path}")

    return output_path


def export_ply_to_obj(input_ply: str, output_path: str = None) -> str:
    """Convert a PLY mesh to OBJ format.

    Args:
        input_ply: Input PLY mesh file.
        output_path: Output OBJ path. None = auto.

    Returns:
        Path to OBJ file.
    """
    from plyfile import PlyData

    if output_path is None:
        p = Path(input_ply)
        output_path = str(p.parent / f"{p.stem}.obj")

    ply = PlyData.read(input_ply)
    vertex = ply['vertex']

    with open(output_path, 'w') as f:
        f.write(f"# Exported from E99 3D Mapping Pipeline\n")
        f.write(f"# Vertices: {len(vertex['x'])}\n\n")

        # Write vertices
        for i in range(len(vertex['x'])):
            f.write(f"v {vertex['x'][i]} {vertex['y'][i]} {vertex['z'][i]}\n")

        # Write faces if present
        if 'face' in ply:
            f.write(f"\n# Faces: {len(ply['face'])}\n")
            for face in ply['face']:
                indices = face[0]  # vertex_indices
                # OBJ uses 1-based indexing
                f.write(f"f {' '.join(str(idx + 1) for idx in indices)}\n")

    print(f"  Exported OBJ: {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate mesh from point cloud")
    parser.add_argument("input", help="Input PLY point cloud")
    parser.add_argument("--output", help="Output mesh path")
    parser.add_argument("--colmap-workspace", help="COLMAP workspace for Poisson meshing")
    parser.add_argument("--max-points", type=int, default=100000)
    args = parser.parse_args()

    print("=" * 60)
    print("  Mesh Generator")
    print("=" * 60)

    if args.colmap_workspace:
        mesh_path = poisson_mesh_colmap(args.colmap_workspace, args.output)
        if not mesh_path:
            print("  Falling back to Delaunay meshing...")
            mesh_path = simple_mesh_from_ply(args.input, args.output, args.max_points)
    else:
        mesh_path = simple_mesh_from_ply(args.input, args.output, args.max_points)
