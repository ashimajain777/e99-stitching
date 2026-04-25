"""
Trajectory Visualizer
======================
Parses COLMAP camera poses and creates visualization primitives:
- Camera frustum wireframes at each pose
- Smooth spline path through camera positions
- Replay mode for animated fly-through
"""

import sys
import json
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def quaternion_to_rotation_matrix(qw, qx, qy, qz):
    """Convert quaternion to 3x3 rotation matrix."""
    R = np.array([
        [1 - 2*qy*qy - 2*qz*qz, 2*qx*qy - 2*qz*qw, 2*qx*qz + 2*qy*qw],
        [2*qx*qy + 2*qz*qw, 1 - 2*qx*qx - 2*qz*qz, 2*qy*qz - 2*qx*qw],
        [2*qx*qz - 2*qy*qw, 2*qy*qz + 2*qx*qw, 1 - 2*qx*qx - 2*qy*qy],
    ])
    return R


def parse_colmap_images(images_txt_path: str) -> list:
    """Parse COLMAP images.txt to extract camera poses.

    COLMAP images.txt format (per image, 2 lines):
        IMAGE_ID QW QX QY QZ TX TY TZ CAMERA_ID IMAGE_NAME
        POINTS2D[] (x y POINT3D_ID ...)

    Returns:
        List of dicts with position, rotation, and image name.
    """
    cameras = []
    path = Path(images_txt_path)

    if not path.exists():
        print(f"  ⚠️ images.txt not found: {path}")
        return cameras

    with open(path, "r") as f:
        lines = [l.strip() for l in f.readlines() if l.strip() and not l.startswith("#")]

    # Process pairs of lines
    for i in range(0, len(lines), 2):
        if i >= len(lines):
            break
        parts = lines[i].split()
        if len(parts) < 10:
            continue

        image_id = int(parts[0])
        qw, qx, qy, qz = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
        tx, ty, tz = float(parts[5]), float(parts[6]), float(parts[7])
        camera_id = int(parts[8])
        image_name = parts[9]

        # COLMAP stores camera-to-world transform as world-to-camera
        R = quaternion_to_rotation_matrix(qw, qx, qy, qz)
        t = np.array([tx, ty, tz])

        # Camera position in world coordinates
        camera_pos = -R.T @ t

        cameras.append({
            "id": image_id,
            "name": image_name,
            "position": camera_pos.tolist(),
            "rotation": R.tolist(),
            "translation": t.tolist(),
            "quaternion": [qw, qx, qy, qz],
        })

    # Sort by image name for sequential ordering
    cameras.sort(key=lambda c: c["name"])
    print(f"  Parsed {len(cameras)} camera poses from {path.name}")
    return cameras


def find_colmap_images_txt(workspace: str = None) -> str:
    """Find the images.txt file in the COLMAP workspace."""
    if workspace is None:
        workspace = str(config.COLMAP_SPARSE_DIR)

    workspace = Path(workspace)

    # Try common locations
    candidates = [
        workspace / "0" / "images.txt",
        workspace / "images.txt",
        workspace / "sparse" / "0" / "images.txt",
        workspace / "sparse" / "images.txt",
    ]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    # Search recursively
    for f in workspace.rglob("images.txt"):
        return str(f)

    return None


def create_camera_frustums(cameras: list, scale: float = 0.1):
    """Create Open3D line set for camera frustum visualization.

    Args:
        cameras: List of camera dicts from parse_colmap_images.
        scale: Size of camera frustum wireframes.

    Returns:
        Open3D LineSet geometry.
    """
    import open3d as o3d

    all_points = []
    all_lines = []
    all_colors = []

    for idx, cam in enumerate(cameras):
        pos = np.array(cam["position"])
        R = np.array(cam["rotation"])

        # Frustum corner offsets (camera coordinates)
        w, h = scale * 0.8, scale * 0.6
        d = scale
        corners_cam = np.array([
            [0, 0, 0],       # Camera center
            [-w, -h, d],     # Top-left
            [w, -h, d],      # Top-right
            [w, h, d],       # Bottom-right
            [-w, h, d],      # Bottom-left
        ])

        # Transform to world coordinates
        corners_world = (R.T @ corners_cam.T).T + pos

        # Add points
        base_idx = len(all_points)
        all_points.extend(corners_world.tolist())

        # Frustum lines (center to each corner + rectangle)
        lines = [
            [0, 1], [0, 2], [0, 3], [0, 4],  # Center to corners
            [1, 2], [2, 3], [3, 4], [4, 1],    # Rectangle
        ]
        for line in lines:
            all_lines.append([base_idx + line[0], base_idx + line[1]])

        # Color gradient (start=blue → end=red)
        t = idx / max(len(cameras) - 1, 1)
        color = [t, 0.3, 1 - t]
        all_colors.extend([color] * len(lines))

    line_set = o3d.geometry.LineSet()
    line_set.points = o3d.utility.Vector3dVector(all_points)
    line_set.lines = o3d.utility.Vector2iVector(all_lines)
    line_set.colors = o3d.utility.Vector3dVector(all_colors)

    return line_set


def create_trajectory_line(cameras: list, smooth: bool = True):
    """Create a smooth trajectory line through camera positions.

    Args:
        cameras: List of camera dicts.
        smooth: Apply cubic spline interpolation.

    Returns:
        Open3D LineSet geometry.
    """
    import open3d as o3d

    if len(cameras) < 2:
        return o3d.geometry.LineSet()

    positions = np.array([cam["position"] for cam in cameras])

    if smooth and len(positions) >= 4:
        from scipy.interpolate import CubicSpline
        t_original = np.linspace(0, 1, len(positions))
        t_smooth = np.linspace(0, 1, len(positions) * 10)

        cs_x = CubicSpline(t_original, positions[:, 0])
        cs_y = CubicSpline(t_original, positions[:, 1])
        cs_z = CubicSpline(t_original, positions[:, 2])

        smooth_positions = np.column_stack([
            cs_x(t_smooth), cs_y(t_smooth), cs_z(t_smooth)
        ])
        positions = smooth_positions

    # Create line segments
    lines = [[i, i + 1] for i in range(len(positions) - 1)]

    # Color gradient along trajectory
    colors = []
    for i in range(len(lines)):
        t = i / max(len(lines) - 1, 1)
        colors.append([0.2 + 0.8 * t, 1.0 - 0.5 * t, 0.2 + 0.3 * (1 - t)])

    line_set = o3d.geometry.LineSet()
    line_set.points = o3d.utility.Vector3dVector(positions)
    line_set.lines = o3d.utility.Vector2iVector(lines)
    line_set.colors = o3d.utility.Vector3dVector(colors)

    return line_set


def export_trajectory_json(cameras: list, output_path: str) -> str:
    """Export camera trajectory as JSON for the web viewer.

    Args:
        cameras: List of camera dicts.
        output_path: Output JSON file path.

    Returns:
        Path to JSON file.
    """
    trajectory = {
        "camera_count": len(cameras),
        "cameras": []
    }

    for cam in cameras:
        trajectory["cameras"].append({
            "name": cam["name"],
            "position": cam["position"],
            "quaternion": cam["quaternion"],
        })

    with open(output_path, "w") as f:
        json.dump(trajectory, f, indent=2)

    print(f"  Exported trajectory: {output_path} ({len(cameras)} cameras)")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Parse COLMAP camera trajectory")
    parser.add_argument("images_txt", help="Path to COLMAP images.txt")
    parser.add_argument("--export-json", help="Export trajectory as JSON")
    args = parser.parse_args()

    cameras = parse_colmap_images(args.images_txt)
    for cam in cameras[:5]:
        print(f"  {cam['name']}: pos={[round(p, 3) for p in cam['position']]}")
    if len(cameras) > 5:
        print(f"  ... and {len(cameras) - 5} more")

    if args.export_json:
        export_trajectory_json(cameras, args.export_json)
