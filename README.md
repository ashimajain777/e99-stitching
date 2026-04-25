# E99 Pro — 3D Indoor Mapping & Exploration Pipeline

Complete pipeline that converts FPV drone video into navigable 3D indoor maps.

```
Live Video → Frame Extraction → Keyframe Selection → Enhancement → COLMAP SfM/MVS → 3D Viewer
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           3D MAPPING PIPELINE                                    │
│                                                                                  │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌────────────────┐  │
│  │  E99 Pro     │    │  Frame       │    │  Keyframe    │    │  Preprocess    │  │
│  │  FPV Stream  │───▶│  Extraction  │───▶│  Selection   │───▶│  & Enhance    │  │
│  │  (WiFi)      │    │  (2 FPS)     │    │  blur/motion │    │  CLAHE/denoise│  │
│  └─────────────┘    └──────────────┘    └──────────────┘    └───────┬────────┘  │
│                                                                      │           │
│     ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ ◀──────┘           │
│     │  COLMAP       │    │  COLMAP       │    │  COLMAP       │                   │
│     │  Feature Det. │───▶│  Matching     │───▶│  SfM Mapper   │                   │
│     │  (SIFT 8192)  │    │  (Sequential) │    │  (Sparse PC)  │                   │
│     └──────────────┘    └──────────────┘    └──────┬───────┘                    │
│                                                     │                            │
│     ┌──────────────┐    ┌──────────────┐    ┌──────▼───────┐                    │
│     │  Indoor       │◀──│  Dense MVS    │◀──│  Undistort   │                    │
│     │  Optimization │    │  (RTX 3050)   │    │  Images      │                   │
│     └──────┬───────┘    └──────────────┘    └──────────────┘                    │
│            │                                                                     │
│     ┌──────▼───────────────────────────────────────────────────────────┐         │
│     │                      INTERACTIVE VIEWERS                          │         │
│     │  ┌─────────────────┐           ┌──────────────────────────┐     │         │
│     │  │  Open3D Viewer   │           │  Three.js Web Viewer      │     │         │
│     │  │  WASD + Mouse    │           │  Browser-based (premium)  │     │         │
│     │  │  Collision detect│           │  Drag & drop PLY/OBJ      │     │         │
│     │  │  Trajectory viz  │           │  Camera trajectory replay │     │         │
│     │  └─────────────────┘           └──────────────────────────┘     │         │
│     └──────────────────────────────────────────────────────────────────┘         │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Python** | 3.10+ |
| **COLMAP** | With CUDA support — [Download](https://github.com/colmap/colmap/releases) |
| **GPU** | NVIDIA RTX 3050 or better (CUDA) |
| **ffmpeg** | For video processing — [Download](https://ffmpeg.org/download.html) |
| **OS** | Windows 10/11 |

---

## Quick Start

### 1. Install Dependencies

```bash
cd e99_3d_mapping
pip install -r requirements.txt
```

### 2. Install COLMAP (CUDA)

1. Download the **Windows CUDA binary** from [COLMAP releases](https://github.com/colmap/colmap/releases)
2. Extract to a folder (e.g., `C:\COLMAP`)
3. Add the folder to your system PATH
4. Verify: `colmap --help`

### 3. Run the Pipeline

**From a video file (one command):**
```bash
python pipeline.py run --input path/to/indoor_video.mp4
```

**Sparse reconstruction only (fast, ~5 minutes):**
```bash
python pipeline.py run --input video.mp4 --sparse-only
```

**From pre-existing frames:**
```bash
python pipeline.py run --input path/to/frames_directory/
```

### 4. View the Result

**Open3D desktop viewer:**
```bash
python pipeline.py view --input datasets/output/dense_cloud_clean.ply
```

**Three.js web viewer (recommended for presentations):**
```bash
python pipeline.py web
```
Opens in your browser at `http://localhost:8080`

---

## Individual Stage Commands

Each stage can be run independently for debugging or testing:

```bash
# Capture live FPV stream from drone
python pipeline.py capture --duration 60

# Extract frames from video
python pipeline.py extract --input video.mp4 --fps 2.0

# Select keyframes (reject blurry/redundant)
python pipeline.py keyframes --input datasets/frames/all/

# Enhance images (CLAHE, denoise, white balance)
python pipeline.py enhance --input datasets/frames/keyframes/

# Run COLMAP reconstruction
python pipeline.py reconstruct --input datasets/preprocessed/

# Optimize point cloud (remove noise/outliers)
python pipeline.py optimize --input datasets/colmap/dense_cloud.ply

# Generate mesh from point cloud
python pipeline.py mesh --input datasets/output/dense_cloud_clean.ply

# Export results to output directory
python pipeline.py export
```

---

## Project Structure

```
e99_3d_mapping/
├── pipeline.py                  # Main entry point (CLI orchestrator)
├── config.py                    # All configurable parameters
├── export.py                    # PLY/OBJ/JSON export utilities
├── requirements.txt
│
├── capture/                     # Stage 1: Video & Frame Extraction
│   ├── stream_capture.py        #   Live FPV stream recording
│   ├── frame_extractor.py       #   Video → individual frames
│   └── keyframe_selector.py     #   Blur/motion/brightness filtering
│
├── preprocess/                  # Stage 2: Image Enhancement
│   └── image_enhancer.py        #   CLAHE, denoising, white balance
│
├── reconstruction/              # Stage 3: COLMAP Pipeline
│   ├── colmap_pipeline.py       #   Full COLMAP CLI wrapper
│   ├── indoor_optimizer.py      #   Point cloud cleaning & optimization
│   └── mesh_generator.py        #   Poisson mesh + decimation
│
├── viewer/                      # Stage 4: Interactive Desktop Viewer
│   ├── point_cloud_viewer.py    #   Open3D WASD+mouse navigation
│   ├── trajectory_visualizer.py #   Camera pose parsing & visualization
│   └── collision.py             #   Voxel-based collision detection
│
├── web_viewer/                  # Stage 5: Web Viewer (Three.js)
│   ├── index.html               #   Premium dark UI
│   ├── viewer.js                #   Three.js rendering + controls
│   ├── style.css                #   Glassmorphism styling
│   └── server.py                #   HTTP server for viewer + data
│
└── datasets/                    # Data storage (auto-created, gitignored)
    ├── raw_video/               #   Original recordings
    ├── frames/
    │   ├── all/                 #   All extracted frames
    │   └── keyframes/           #   Selected keyframes
    ├── preprocessed/            #   Enhanced frames
    ├── colmap/                  #   COLMAP workspace
    │   ├── database.db
    │   ├── sparse/              #   Sparse reconstruction
    │   ├── dense/               #   Dense reconstruction
    │   └── mesh/                #   Generated mesh
    └── output/                  #   Final exports (PLY, OBJ, JSON)
```

---

## Viewer Controls

### Desktop Viewer (Open3D)

| Key | Action |
|-----|--------|
| `W` / `A` / `S` / `D` | Move forward / left / backward / right |
| `Q` / `E` | Move up / down |
| `Mouse drag` | Rotate camera |
| `Scroll` | Adjust movement speed |
| `Shift` | Sprint (3x speed) |
| `1` - `9` | Snap to COLMAP camera position |
| `Space` | Toggle auto-fly along trajectory |
| `P` | Cycle point size |
| `T` | Toggle trajectory display |
| `R` | Reset view |
| `ESC` | Quit |

### Web Viewer (Three.js)

| Control | Action |
|---------|--------|
| `W/A/S/D` | Move |
| `Q/E` | Up / Down |
| `Mouse` | Look around (after click) |
| `Scroll` | Adjust speed |
| `Shift` | Sprint |
| `F` | Toggle auto-fly |
| `ESC` | Release mouse |

---

## Configuration

All parameters are in `config.py`. Key settings:

```python
# Frame extraction rate (lower = fewer frames, faster reconstruction)
EXTRACTION_FPS = 2.0

# COLMAP: increase features for low-texture indoor walls
SIFT_MAX_NUM_FEATURES = 8192

# Dense reconstruction: tuned for RTX 3050 (4GB VRAM)
DENSE_MAX_IMAGE_SIZE = 1600
PATCH_MATCH_WINDOW_RADIUS = 5

# Indoor point cloud cleaning
SOR_NB_NEIGHBORS = 20
SOR_STD_RATIO = 2.0
VOXEL_SIZE = 0.01  # 1cm voxels
```

---

## Performance Expectations

| Stage | Time (500 frames) | Bottleneck |
|-------|-------------------|------------|
| Frame Extraction | ~30s | IO |
| Keyframe Selection | ~20s | CPU |
| Image Enhancement | ~1 min | CPU |
| Feature Extraction | ~5 min | GPU |
| Feature Matching | ~3 min | GPU |
| SfM Mapper | ~2 min | CPU |
| Dense MVS (RTX 3050) | ~15 min | GPU VRAM |
| Stereo Fusion | ~2 min | RAM |
| Indoor Optimization | ~1 min | CPU |
| **Total (with GPU)** | **~30 min** | |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `COLMAP not found` | Download from releases, add to PATH. Set `COLMAP_EXECUTABLE` in config.py |
| `CUDA out of memory` | Reduce `DENSE_MAX_IMAGE_SIZE` in config.py (try 1200 or 800) |
| `Few images registered` | Try `MATCHER_TYPE = "exhaustive"` in config.py |
| `Noisy point cloud` | Increase `SOR_STD_RATIO` or decrease `SOR_NB_NEIGHBORS` |
| `Dense takes too long` | Use `--sparse-only` flag for fast preview |
| `Blurry reconstruction` | Increase `BLUR_THRESHOLD` for stricter keyframe selection |
| `Web viewer won't load` | Check browser console (F12). Ensure PLY file isn't too large |
| `Open3D import error` | `pip install open3d` (requires Python 3.8-3.11) |

---

## Output Formats

| Format | File | Description |
|--------|------|-------------|
| PLY | `sparse_cloud.ply` | Sparse colored point cloud |
| PLY | `dense_cloud.ply` | Dense colored point cloud |
| PLY | `dense_cloud_clean.ply` | Optimized dense cloud (recommended) |
| PLY | `mesh.ply` | Poisson mesh |
| OBJ | `mesh.obj` | Mesh (OBJ format) |
| JSON | `trajectory.json` | Camera positions for web viewer |

---

## License

Educational use only. Use responsibly and in compliance with local drone regulations.
