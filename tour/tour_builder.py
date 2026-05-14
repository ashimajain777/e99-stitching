"""
Tour Builder
==============
Builds a navigable virtual tour from stitched panoramas:
1. Orders viewpoints by video sequence
2. Computes connections (previous/next neighbors)
3. Estimates 2D positions for the minimap
4. Generates Pannellum-compatible tour.json configuration
"""

import json
import math
import sys
import cv2
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def load_viewpoints_report(viewpoints_dir: str = None) -> dict:
    """Load the viewpoints clustering report."""
    if viewpoints_dir is None:
        viewpoints_dir = config.VIEWPOINTS_DIR

    report_path = Path(viewpoints_dir) / "viewpoints_report.json"
    if not report_path.exists():
        raise FileNotFoundError(f"Viewpoints report not found: {report_path}")

    with open(report_path) as f:
        return json.load(f)


def estimate_positions(viewpoints: list) -> list:
    """Estimate 2D (x, y) positions for each viewpoint for the minimap.

    Uses cumulative motion between viewpoints to estimate relative positions.
    The path follows the video sequence, so positions form a rough trajectory.

    Args:
        viewpoints: List of viewpoint metadata dicts from clustering report.

    Returns:
        List of (x, y) tuples, one per viewpoint.
    """
    if not viewpoints:
        return []

    positions = [(0.0, 0.0)]  # First viewpoint at origin

    # We'll simulate a path based on frame ranges and motion
    # Direction changes based on inter-viewpoint motion magnitude
    angle = 0.0  # Current heading in radians (0 = right)
    step_size = 1.0

    for i in range(1, len(viewpoints)):
        prev_vp = viewpoints[i - 1]
        curr_vp = viewpoints[i]

        # Distance proportional to gap between frame ranges
        frame_gap = curr_vp["frame_range"][0] - prev_vp["frame_range"][1]
        distance = step_size * max(1.0, frame_gap * 0.3)

        # Slight direction variation based on motion
        motion = curr_vp.get("avg_internal_motion", 5.0)
        angle += (motion - 8.0) * 0.05  # Subtle turns

        x = positions[-1][0] + distance * math.cos(angle)
        y = positions[-1][1] + distance * math.sin(angle)
        positions.append((round(x, 2), round(y, 2)))

    # Normalize to 0-100 range for minimap
    if len(positions) > 1:
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)

        x_range = max(x_max - x_min, 0.001)
        y_range = max(y_max - y_min, 0.001)

        # Add padding (10%)
        positions = [
            (round(10 + 80 * (p[0] - x_min) / x_range, 1),
             round(10 + 80 * (p[1] - y_min) / y_range, 1))
            for p in positions
        ]

    return positions


def compute_connections(viewpoints: list, max_connections: int = None) -> list:
    """Compute navigation connections between viewpoints.

    Each viewpoint connects to its sequential neighbors (previous/next in
    video order). This creates a linear path through the space.

    Args:
        viewpoints: List of viewpoint metadata dicts.
        max_connections: Max connections per viewpoint.

    Returns:
        List of (from_idx, to_idx, direction_label) tuples.
    """
    if max_connections is None:
        max_connections = config.HOTSPOT_MAX_CONNECTIONS

    connections = []
    n = len(viewpoints)

    for i in range(n):
        # Connect to next viewpoint
        if i < n - 1:
            connections.append((i, i + 1, "forward"))

        # Connect to previous viewpoint
        if i > 0:
            connections.append((i, i - 1, "back"))

    return connections


def compute_hotspot_yaw(from_pos: tuple, to_pos: tuple) -> float:
    """Compute the yaw angle for a hotspot pointing from one position to another.

    Args:
        from_pos: (x, y) of the source viewpoint.
        to_pos: (x, y) of the target viewpoint.

    Returns:
        Yaw angle in degrees (-180 to 180).
    """
    dx = to_pos[0] - from_pos[0]
    dy = to_pos[1] - from_pos[1]
    angle = math.degrees(math.atan2(dy, dx))
    return round(angle, 1)


def build_tour(viewpoints_dir: str = None, panoramas_dir: str = None,
               output_path: str = None) -> dict:
    """Build the complete Pannellum tour configuration.

    Args:
        viewpoints_dir: Directory with viewpoints_report.json.
        panoramas_dir: Directory containing panorama images.
        output_path: Path to save tour.json.

    Returns:
        Complete tour configuration dict.
    """
    if viewpoints_dir is None:
        viewpoints_dir = config.VIEWPOINTS_DIR
    if panoramas_dir is None:
        panoramas_dir = config.PANORAMAS_DIR
    if output_path is None:
        output_path = config.TOUR_JSON_PATH

    viewpoints_dir = Path(viewpoints_dir)
    panoramas_dir = Path(panoramas_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load viewpoints report
    report = load_viewpoints_report(str(viewpoints_dir))
    viewpoints = report["viewpoints"]

    print(f"  Building tour from {len(viewpoints)} viewpoints")

    # Check which panoramas actually exist
    available = []
    for vp in viewpoints:
        pano_path = panoramas_dir / f"{vp['id']}.{config.PANO_FORMAT}"
        if pano_path.exists():
            vp["_pano_path"] = str(pano_path)
            vp["_pano_url"] = f"/panoramas/{pano_path.name}"
            available.append(vp)
        else:
            print(f"    ⚠️ Missing panorama for {vp['id']}, skipping")

    if not available:
        print("  ❌ No panorama images found!")
        return {"error": "no panoramas"}

    print(f"  Available panoramas: {len(available)}")

    # Estimate positions
    positions = estimate_positions(available)

    # Compute connections
    connections = compute_connections(available)

    # ── Build Pannellum scene config ──
    scenes = {}

    for i, vp in enumerate(available):
        scene_id = vp["id"]
        pos = positions[i] if i < len(positions) else (50, 50)

        # Build hotspots for this scene
        hotspots = []
        for from_idx, to_idx, direction in connections:
            if from_idx != i:
                continue

            target = available[to_idx]
            target_pos = positions[to_idx] if to_idx < len(positions) else (50, 50)

            # Compute yaw direction for the hotspot arrow
            yaw = compute_hotspot_yaw(pos, target_pos)

            hotspot = {
                "pitch": -5,  # Slightly below horizon
                "yaw": yaw,
                "type": "scene",
                "text": f"Go to {target['id'].replace('_', ' ').title()}",
                "sceneId": target["id"],
                "targetYaw": yaw + 180,  # Look back toward where we came from
                "cssClass": f"hotspot-arrow hotspot-{direction}",
            }
            hotspots.append(hotspot)

        scenes[scene_id] = {
            "title": f"Viewpoint {i + 1}",
            "type": "equirectangular",
            "panorama": vp["_pano_url"],
            "autoLoad": True,
            "hfov": config.PANNELLUM_HFOV,
            "minHfov": config.PANNELLUM_MIN_HFOV,
            "maxHfov": config.PANNELLUM_MAX_HFOV,
            "hotSpots": hotspots,
            "compass": config.PANNELLUM_COMPASS,
        }

    # ── Build complete tour config ──
    first_scene = available[0]["id"]

    tour = {
        "default": {
            "firstScene": first_scene,
            "sceneFadeDuration": config.SCENE_FADE_DURATION,
            "autoLoad": config.PANNELLUM_AUTO_LOAD,
            "compass": config.PANNELLUM_COMPASS,
        },
        "scenes": scenes,
        # Custom metadata (not part of Pannellum spec, used by our viewer.js)
        "_meta": {
            "total_viewpoints": len(available),
            "positions": {vp["id"]: positions[i] for i, vp in enumerate(available)},
            "scene_order": [vp["id"] for vp in available],
            "connections": [
                {"from": available[f]["id"], "to": available[t]["id"], "direction": d}
                for f, t, d in connections
            ],
            "auto_tour_delay": config.AUTO_TOUR_DELAY,
            "minimap_enabled": config.MINIMAP_ENABLED,
        }
    }

    # Save tour.json
    with open(output_path, "w") as f:
        json.dump(tour, f, indent=2)

    print(f"\n  ✅ Tour Configuration Built")
    print(f"  Scenes: {len(scenes)}")
    print(f"  Connections: {len(connections)}")
    print(f"  First scene: {first_scene}")
    print(f"  Output: {output_path}")

    return tour


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build navigable tour from panoramas")
    parser.add_argument("--viewpoints", help="Viewpoints directory")
    parser.add_argument("--panoramas", help="Panoramas directory")
    parser.add_argument("--output", help="Output tour.json path")
    args = parser.parse_args()

    print("=" * 60)
    print("  Tour Builder")
    print("=" * 60)
    build_tour(args.viewpoints, args.panoramas, args.output)
