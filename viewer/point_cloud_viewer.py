"""
Interactive 3D Point Cloud Viewer
===================================
Open3D-based viewer with first-person navigation.

NOTE: Requires Open3D (Python 3.8-3.11 only).
If Open3D is unavailable, use the web viewer instead:
    python pipeline.py web
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Check for Open3D availability
try:
    import open3d as o3d
    OPEN3D_AVAILABLE = True
except ImportError:
    OPEN3D_AVAILABLE = False


def launch_viewer(ply_path: str = None, mesh_path: str = None,
                  workspace: str = None):
    """Launch the interactive 3D viewer.

    If Open3D is not available, prints instructions for the web viewer.
    """
    if not OPEN3D_AVAILABLE:
        print("\n" + "=" * 60)
        print("  Open3D Desktop Viewer - NOT AVAILABLE")
        print("=" * 60)
        print()
        print("  Open3D requires Python 3.8-3.11.")
        print("  Your Python version doesn't support it.")
        print()
        print("  Use the web viewer instead (works with any Python):")
        print()
        print("    python pipeline.py web")
        print()
        print("  The web viewer opens in your browser with the same")
        print("  WASD + mouse navigation and looks even better!")
        print()
        print("=" * 60)
        return

    import numpy as np

    print("\n" + "=" * 60)
    print("  3D Point Cloud Viewer")
    print("=" * 60)

    geometries = []

    if ply_path:
        print(f"  Loading: {ply_path}")
        pcd = o3d.io.read_point_cloud(ply_path)
        print(f"  Points: {len(pcd.points)}")
        geometries.append(pcd)

    if mesh_path:
        print(f"  Loading mesh: {mesh_path}")
        mesh = o3d.io.read_triangle_mesh(mesh_path)
        mesh.compute_vertex_normals()
        print(f"  Vertices: {len(mesh.vertices)}, Triangles: {len(mesh.triangles)}")
        geometries.append(mesh)

    if not geometries:
        print("  No geometry to display!")
        return

    # Load trajectory if available
    if workspace:
        from .trajectory_visualizer import (
            find_colmap_images_txt, parse_colmap_images,
            create_camera_frustums, create_trajectory_line
        )
        images_txt = find_colmap_images_txt(workspace)
        if images_txt:
            cameras = parse_colmap_images(images_txt)
            if cameras:
                frustums = create_camera_frustums(cameras)
                traj_line = create_trajectory_line(cameras)
                geometries.append(frustums)
                geometries.append(traj_line)
                print(f"  Trajectory: {len(cameras)} camera poses")

    print("\n  Controls:")
    print("    Left mouse + drag = Rotate")
    print("    Scroll = Zoom")
    print("    Middle mouse + drag = Pan")
    print("    R = Reset view")
    print("    Q = Quit")
    print()

    # Use Open3D's built-in viewer
    o3d.visualization.draw_geometries(
        geometries,
        window_name="E99 3D Explorer",
        width=1280,
        height=720,
        point_show_normal=False,
    )

    print("  Viewer closed.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Interactive 3D viewer")
    parser.add_argument("input", help="PLY point cloud or mesh file")
    parser.add_argument("--workspace", help="COLMAP workspace for trajectory")
    args = parser.parse_args()

    path = Path(args.input)
    if path.suffix.lower() in {".obj", ".stl", ".off"}:
        launch_viewer(mesh_path=str(path), workspace=args.workspace)
    else:
        launch_viewer(ply_path=str(path), workspace=args.workspace)
