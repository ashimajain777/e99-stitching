"""
Collision Approximation
========================
Builds an occupancy grid from the point cloud and prevents
the camera from moving through solid surfaces.

Lightweight implementation using voxel hashing for speed.
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


class CollisionGrid:
    """Sparse voxel-based collision detection for point clouds.

    Builds a hash-based occupancy grid from the point cloud points.
    Checks whether a position is inside an occupied voxel (collision)
    and provides "slide" behavior to move along surfaces.
    """

    def __init__(self, voxel_size: float = None, collision_radius: float = None):
        self.voxel_size = voxel_size or config.COLLISION_GRID_SIZE
        self.collision_radius = collision_radius or config.COLLISION_RADIUS
        self._occupied = set()  # Set of (ix, iy, iz) voxel indices
        self._bounds_min = None
        self._bounds_max = None

    def build_from_point_cloud(self, pcd):
        """Build occupancy grid from Open3D point cloud.

        Args:
            pcd: Open3D PointCloud object.
        """
        points = np.asarray(pcd.points)
        if len(points) == 0:
            print("  ⚠️ No points for collision grid")
            return

        self._bounds_min = points.min(axis=0)
        self._bounds_max = points.max(axis=0)

        # Quantize points to voxel indices
        indices = np.floor(points / self.voxel_size).astype(np.int64)

        self._occupied = set()
        for idx in indices:
            self._occupied.add(tuple(idx))

        print(f"  Collision grid built: {len(self._occupied)} occupied voxels "
              f"(voxel_size={self.voxel_size}m, radius={self.collision_radius}m)")

    def build_from_points(self, points: np.ndarray):
        """Build occupancy grid from raw numpy points.

        Args:
            points: Nx3 numpy array of point positions.
        """
        if len(points) == 0:
            return

        self._bounds_min = points.min(axis=0)
        self._bounds_max = points.max(axis=0)

        indices = np.floor(points / self.voxel_size).astype(np.int64)
        self._occupied = set()
        for idx in indices:
            self._occupied.add(tuple(idx))

    def is_occupied(self, position: np.ndarray) -> bool:
        """Check if a position collides with occupied voxels.

        Checks the voxel at the position and a sphere of neighboring
        voxels within the collision radius.

        Args:
            position: 3D position to check.

        Returns:
            True if the position is in or near an occupied voxel.
        """
        if not self._occupied:
            return False

        center = np.floor(position / self.voxel_size).astype(np.int64)
        radius_voxels = max(1, int(np.ceil(self.collision_radius / self.voxel_size)))

        for dx in range(-radius_voxels, radius_voxels + 1):
            for dy in range(-radius_voxels, radius_voxels + 1):
                for dz in range(-radius_voxels, radius_voxels + 1):
                    voxel = (center[0] + dx, center[1] + dy, center[2] + dz)
                    if voxel in self._occupied:
                        # Check actual distance
                        voxel_center = np.array(voxel) * self.voxel_size + self.voxel_size / 2
                        dist = np.linalg.norm(position - voxel_center)
                        if dist < self.collision_radius:
                            return True
        return False

    def resolve_collision(self, old_pos: np.ndarray,
                          new_pos: np.ndarray) -> np.ndarray:
        """Resolve collision by sliding along surfaces.

        If the desired new position is occupied, try moving along each
        axis independently to find a valid "slide" direction.

        Args:
            old_pos: Current valid position.
            new_pos: Desired new position.

        Returns:
            Resolved position (may be same as old_pos if fully blocked).
        """
        if not self.is_occupied(new_pos):
            return new_pos

        # Try each axis independently (slide along surface)
        delta = new_pos - old_pos
        best_pos = old_pos.copy()

        # Try X movement
        test = old_pos.copy()
        test[0] = new_pos[0]
        if not self.is_occupied(test):
            best_pos[0] = test[0]

        # Try Y movement
        test = best_pos.copy()
        test[1] = new_pos[1]
        if not self.is_occupied(test):
            best_pos[1] = test[1]

        # Try Z movement
        test = best_pos.copy()
        test[2] = new_pos[2]
        if not self.is_occupied(test):
            best_pos[2] = test[2]

        return best_pos

    @property
    def voxel_count(self) -> int:
        return len(self._occupied)
