"""
Panoramic Street View Pipeline — Central Configuration
=======================================================
All configurable parameters for capture, stitching, tour building, and viewing.
Tuned for E99 Pro drone FPV footage.
"""

from pathlib import Path

# =============================================================================
# PATHS
# =============================================================================

PROJECT_ROOT = Path(__file__).parent
DATASETS_DIR = PROJECT_ROOT / "datasets"
RAW_VIDEO_DIR = DATASETS_DIR / "raw_video"
FRAMES_ALL_DIR = DATASETS_DIR / "frames" / "all"
FRAMES_FILTERED_DIR = DATASETS_DIR / "frames" / "filtered"
ENHANCED_DIR = DATASETS_DIR / "enhanced"
VIEWPOINTS_DIR = DATASETS_DIR / "viewpoints"
PANORAMAS_DIR = DATASETS_DIR / "panoramas"
OUTPUT_DIR = DATASETS_DIR / "output"
TOUR_JSON_PATH = OUTPUT_DIR / "tour.json"

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
# FRAME FILTERING (quality gate)
# =============================================================================

BLUR_THRESHOLD = 50.0         # Laplacian variance — below = blurry → reject
BRIGHTNESS_MIN = 25.0         # Mean intensity — below = too dark
BRIGHTNESS_MAX = 240.0        # Mean intensity — above = too bright

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
# VIEWPOINT CLUSTERING
# =============================================================================
# Groups consecutive frames into "viewpoints" (stops on the tour).
# A new viewpoint starts when the camera has moved significantly.

CLUSTER_MOTION_THRESHOLD = 12.0   # Mean pixel diff — above = new viewpoint
CLUSTER_MIN_FRAMES = 3            # Minimum frames per viewpoint (else merge)
CLUSTER_MAX_FRAMES = 30           # Maximum frames per viewpoint (else split)
CLUSTER_MIN_VIEWPOINTS = 5        # Minimum total viewpoints to produce
CLUSTER_MAX_VIEWPOINTS = 40       # Maximum total viewpoints

# =============================================================================
# PANORAMA STITCHING
# =============================================================================

STITCH_MODE = "auto"              # 'auto' | 'opencv' | 'cylindrical' | 'single'
                                   # auto = try opencv stitcher, fallback to
                                   # cylindrical, fallback to single best frame

STITCH_CONFIDENCE = 0.3           # Stitcher confidence threshold (lower = more lenient)
STITCH_WARP_TYPE = "cylindrical"  # Fallback warp type: 'cylindrical' | 'spherical'

# Panorama output
PANO_OUTPUT_WIDTH = 4096          # Width of equirectangular output (height = width/2)
PANO_QUALITY = 92                 # JPEG quality for panorama images
PANO_FORMAT = "jpg"

# Camera intrinsics estimate (for cylindrical warp fallback)
# If unknown, set to None and we'll estimate from image dimensions
CAMERA_FOCAL_LENGTH = None        # Focal length in pixels (None = auto-estimate)
CAMERA_FOV_H = 120.0              # Horizontal FOV in degrees (E99 Pro wide-angle)

# =============================================================================
# TOUR BUILDER
# =============================================================================

HOTSPOT_MAX_CONNECTIONS = 3       # Max links per viewpoint (prev, next, + 1 branch)
SCENE_FADE_DURATION = 1000        # Transition fade time in ms
SCENE_AUTO_ROTATE_SPEED = 0.5     # Auto-rotate speed (degrees/sec, 0 = off)

# Auto-tour
AUTO_TOUR_DELAY = 4000            # Milliseconds at each viewpoint during auto-tour

# Minimap
MINIMAP_ENABLED = True
MINIMAP_SIZE = 200                # Minimap panel size in pixels

# =============================================================================
# WEB VIEWER
# =============================================================================

WEB_SERVER_PORT = 8080
WEB_AUTO_OPEN_BROWSER = True

# Pannellum settings
PANNELLUM_HFOV = 100              # Default horizontal field of view
PANNELLUM_MIN_HFOV = 50           # Minimum zoom (most zoomed in)
PANNELLUM_MAX_HFOV = 120          # Maximum zoom (most zoomed out)
PANNELLUM_AUTO_LOAD = True        # Auto-load first scene
PANNELLUM_COMPASS = True          # Show compass indicator
