"""
3D Mapping Pipeline — Central Configuration
=============================================
All configurable parameters for capture, reconstruction, and viewing.
Tuned for E99 Pro drone FPV footage + NVIDIA RTX 3050 GPU.
"""

from pathlib import Path

# =============================================================================
# PATHS
# =============================================================================

PROJECT_ROOT = Path(__file__).parent
DATASETS_DIR = PROJECT_ROOT / "datasets"
RAW_VIDEO_DIR = DATASETS_DIR / "raw_video"
FRAMES_ALL_DIR = DATASETS_DIR / "frames" / "all"
FRAMES_KEYFRAMES_DIR = DATASETS_DIR / "frames" / "keyframes"
PREPROCESSED_DIR = DATASETS_DIR / "preprocessed"
COLMAP_WORKSPACE = DATASETS_DIR / "colmap"
COLMAP_DB_PATH = COLMAP_WORKSPACE / "database.db"
COLMAP_SPARSE_DIR = COLMAP_WORKSPACE / "sparse"
COLMAP_DENSE_DIR = COLMAP_WORKSPACE / "dense"
COLMAP_MESH_DIR = COLMAP_WORKSPACE / "mesh"
OUTPUT_DIR = DATASETS_DIR / "output"

# =============================================================================
# STREAM CAPTURE (for live drone FPV)
# =============================================================================

DRONE_IP = "192.168.0.1"
STREAM_URLS = [
    "udp://@:8800",
    "tcp://192.168.0.1:8800",
    "http://192.168.0.1:8800/video",
]
RECORDING_FPS = 30.0
RECORDING_CODEC = "mp4v"

# =============================================================================
# FRAME EXTRACTION
# =============================================================================

EXTRACTION_FPS = 2.0          # Frames extracted per second of video
FRAME_FORMAT = "jpg"
FRAME_QUALITY = 95            # JPEG quality (1-100)

# =============================================================================
# KEYFRAME SELECTION
# =============================================================================

BLUR_THRESHOLD = 50.0         # Laplacian variance — below = blurry → reject
MOTION_MIN_THRESHOLD = 5.0    # Pixel diff — below = too similar → skip
MOTION_MAX_THRESHOLD = 80.0   # Pixel diff — above = too different → skip
BRIGHTNESS_MIN = 25.0         # Mean intensity — below = too dark
BRIGHTNESS_MAX = 240.0        # Mean intensity — above = too bright
MIN_KEYFRAMES = 30            # Keep at least this many even if quality is low

# =============================================================================
# PREPROCESSING
# =============================================================================

TARGET_WIDTH = None            # None = keep original dimensions
TARGET_HEIGHT = None

CLAHE_ENABLED = True
CLAHE_CLIP_LIMIT = 3.0
CLAHE_GRID_SIZE = (8, 8)

DENOISE_ENABLED = True
DENOISE_STRENGTH = 7

WHITE_BALANCE_ENABLED = True

# =============================================================================
# COLMAP RECONSTRUCTION
# =============================================================================

import os
COLMAP_EXECUTABLE = r"C:\Users\Ashima Jain\Downloads\COLMAP-3.9.1-windows-cuda\COLMAP-3.9.1-windows-cuda\bin\colmap.exe"

# Fix for DLL missing errors: add COLMAP internal lib folder to system PATH for this Python session
COLMAP_LIB_DIR = r"C:\Users\Ashima Jain\Downloads\COLMAP-3.9.1-windows-cuda\COLMAP-3.9.1-windows-cuda\lib"
os.environ['PATH'] = COLMAP_LIB_DIR + os.pathsep + os.environ.get('PATH', '')

# Feature extraction (SIFT)
SIFT_MAX_IMAGE_SIZE = 3200
SIFT_MAX_NUM_FEATURES = 8192
SIFT_SINGLE_CAMERA = True

# Feature matching
MATCHER_TYPE = "sequential"    # 'sequential' or 'exhaustive'
SEQUENTIAL_OVERLAP = 15        # Adjacent frames to match
SEQUENTIAL_LOOP_DETECTION = True

# Fallback: if sequential registers < this fraction of images → exhaustive
EXHAUSTIVE_FALLBACK_THRESHOLD = 0.5

# SfM Mapper
MAPPER_MIN_NUM_MATCHES = 15

# Dense reconstruction (tuned for RTX 3050 — 4GB VRAM)
DENSE_USE_GPU = True
DENSE_GPU_INDEX = 0
DENSE_MAX_IMAGE_SIZE = 1600    # Downscale for dense to fit 4GB VRAM
PATCH_MATCH_WINDOW_RADIUS = 5
PATCH_MATCH_NUM_SAMPLES = 15
PATCH_MATCH_NUM_ITERATIONS = 5
PATCH_MATCH_GEOM_CONSISTENCY = True

# Stereo fusion
FUSION_MIN_NUM_PIXELS = 5
FUSION_MAX_REPROJ_ERROR = 2.0

# =============================================================================
# INDOOR OPTIMIZATION
# =============================================================================

SOR_NB_NEIGHBORS = 20         # Statistical outlier removal: neighbors
SOR_STD_RATIO = 2.0           # Statistical outlier removal: std multiplier
ROR_NB_POINTS = 5             # Radius outlier removal: min neighbors (relaxed)
ROR_RADIUS = 0.5              # Radius outlier removal: search radius (relaxed — scene-scale dependent)
VOXEL_SIZE = 0.02             # Voxel downsampling: 2cm voxels (less aggressive)

# =============================================================================
# 3D VIEWER (Open3D Python Viewer)
# =============================================================================

VIEWER_MOVE_SPEED = 0.05
VIEWER_FAST_MULTIPLIER = 3.0
VIEWER_MOUSE_SENSITIVITY = 0.003
VIEWER_FOV = 60.0
VIEWER_POINT_SIZE = 2.0
VIEWER_BG_COLOR = [0.05, 0.05, 0.08]
VIEWER_SHOW_TRAJECTORY = True
VIEWER_SHOW_CAMERAS = True
VIEWER_WINDOW_WIDTH = 1600
VIEWER_WINDOW_HEIGHT = 900

# Collision
COLLISION_ENABLED = True
COLLISION_RADIUS = 0.05
COLLISION_GRID_SIZE = 0.02

# =============================================================================
# WEB VIEWER
# =============================================================================

WEB_SERVER_PORT = 8080
WEB_POINT_BUDGET = 2_000_000
WEB_AUTO_OPEN_BROWSER = True
