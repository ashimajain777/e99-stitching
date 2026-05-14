# E99 Pro — Street View Indoor Explorer

Navigate indoor spaces captured by your E99 Pro drone in a Google Street View-like experience.

```
FPV Video → Frame Extraction → Quality Filter → Enhancement → Viewpoint Clustering → Panorama Stitching → Web Viewer
```

## How It Works

1. **Extract** frames from your drone video at 2 FPS
2. **Filter** out blurry, too dark, or too bright frames
3. **Enhance** images with CLAHE contrast boost and denoising
4. **Cluster** frames into viewpoint groups (where the drone paused/rotated)
5. **Stitch** each viewpoint's frames into a panoramic image
6. **Build** a navigable tour with hotspot connections between viewpoints
7. **Serve** the tour in a premium browser-based panorama viewer

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                   PANORAMIC STREET VIEW PIPELINE                     │
│                                                                      │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────┐ │
│  │  E99 Pro  │   │  Frame   │   │  Quality  │   │  CLAHE / Denoise│ │
│  │  Video    │──▶│  Extract │──▶│  Filter   │──▶│  Enhancement    │ │
│  └──────────┘   └──────────┘   └──────────┘   └───────┬──────────┘ │
│                                                        │             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────▼──────────┐ │
│  │  Tour Builder │◀──│  Panorama    │◀──│  Viewpoint Clustering  │ │
│  │  (tour.json)  │   │  Stitching   │   │  (motion-based groups) │ │
│  └──────┬───────┘   └──────────────┘   └────────────────────────┘ │
│         │                                                           │
│  ┌──────▼───────────────────────────────────────────────────────┐  │
│  │               PANNELLUM WEB VIEWER                            │  │
│  │  • 360° panorama look-around with mouse drag                  │  │
│  │  • Clickable hotspot arrows between viewpoints                │  │
│  │  • Minimap showing your position                              │  │
│  │  • Auto-tour mode to walk through all viewpoints              │  │
│  │  • Premium dark glassmorphism UI                              │  │
│  └───────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Python** | 3.10+ |
| **OS** | Windows 10/11 |
| **GPU** | Not required (optional CUDA acceleration for OpenCV) |

> No COLMAP, no Open3D, no heavy GPU processing needed.

---

## Quick Start

### 1. Install Dependencies

```bash
cd e99_3d_mapping
pip install -r requirements.txt
```

### 2. Run the Pipeline

**From a video file (one command):**
```bash
python pipeline.py run --input path/to/indoor_video.mp4
```

**From pre-existing frames:**
```bash
python pipeline.py run --input path/to/frames_directory/
```

### 3. Explore Your Space

```bash
python pipeline.py serve
```
Opens in your browser at `http://localhost:8080` — drag to look around, click arrows to navigate.

---

## Individual Stage Commands

Each stage can be run independently for fine-tuning:

```bash
# Capture live FPV stream from drone
python pipeline.py capture --duration 60

# Extract frames from video (2 FPS default)
python pipeline.py extract --input video.mp4 --fps 2.0

# Filter out bad frames (blurry, dark, overexposed)
python pipeline.py filter --input datasets/frames/all/

# Enhance images (CLAHE, denoise, white balance)
python pipeline.py enhance --input datasets/frames/filtered/

# Cluster frames into viewpoint groups
python pipeline.py cluster --input datasets/enhanced/

# Stitch each viewpoint into a panorama
python pipeline.py stitch --input datasets/viewpoints/

# Build the tour configuration
python pipeline.py tour --viewpoints datasets/viewpoints/ --panoramas datasets/panoramas/

# Launch the viewer
python pipeline.py serve
```

---

## Project Structure

```
e99_3d_mapping/
├── pipeline.py                  # Main CLI orchestrator
├── config.py                    # All configurable parameters
├── requirements.txt             # Python dependencies
│
├── capture/                     # Stage 1: Video & Frame Extraction
│   ├── stream_capture.py        #   Live FPV stream recording
│   ├── frame_extractor.py       #   Video → individual frames
│   └── keyframe_selector.py     #   Quality filter + viewpoint clustering
│
├── preprocess/                  # Stage 2: Image Enhancement
│   └── image_enhancer.py        #   CLAHE, denoising, white balance
│
├── stitching/                   # Stage 3: Panorama Stitching
│   └── panorama_stitcher.py     #   OpenCV stitcher + cylindrical warp
│
├── tour/                        # Stage 4: Tour Builder
│   └── tour_builder.py          #   Viewpoint graph + Pannellum config
│
├── web_viewer/                  # Stage 5: Web Viewer
│   ├── index.html               #   Pannellum panorama viewer
│   ├── viewer.js                #   Tour controller + minimap
│   ├── style.css                #   Premium dark UI
│   └── server.py                #   HTTP server
│
└── datasets/                    # Data storage (auto-created)
    ├── raw_video/               #   Original recordings
    ├── frames/
    │   ├── all/                 #   All extracted frames
    │   └── filtered/            #   Quality-filtered frames
    ├── enhanced/                #   Enhanced frames
    ├── viewpoints/              #   Clustered viewpoint groups
    │   ├── vp_000/
    │   ├── vp_001/
    │   └── ...
    ├── panoramas/               #   Stitched panorama images
    │   ├── vp_000.jpg
    │   ├── vp_001.jpg
    │   └── ...
    └── output/
        └── tour.json            #   Pannellum tour configuration
```

---

## Viewer Controls

| Control | Action |
|---------|--------|
| `Mouse drag` | Look around (pan/tilt) |
| `Scroll` | Zoom in/out |
| `← →` Arrow keys | Previous / Next viewpoint |
| `Space` | Toggle auto-tour |
| `Home` / `End` | Jump to first / last viewpoint |
| Click hotspot | Navigate to connected viewpoint |
| Minimap dot | Jump to any viewpoint |

---

## Configuration

Key settings in `config.py`:

```python
# Frame extraction rate (higher = more frames, better coverage)
EXTRACTION_FPS = 2.0

# Viewpoint clustering — lower threshold = more viewpoints
CLUSTER_MOTION_THRESHOLD = 12.0

# Stitching mode: 'auto', 'opencv', 'cylindrical', 'single'
STITCH_MODE = "auto"

# Panorama output resolution
PANO_OUTPUT_WIDTH = 4096

# Camera FOV (E99 Pro wide-angle)
CAMERA_FOV_H = 120.0
```

---

## Performance

| Stage | Time (60s video) | Notes |
|-------|------------------|-------|
| Frame Extraction | ~10s | IO-bound |
| Quality Filter | ~5s | CPU |
| Enhancement | ~15s | CPU |
| Viewpoint Clustering | ~5s | CPU |
| Panorama Stitching | 2-5 min | CPU (heaviest stage) |
| Tour Building | ~1s | CPU |
| **Total** | **~3-6 min** | No GPU required |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| All frames rejected | Lower `BLUR_THRESHOLD` in config.py (try 20) |
| Too few viewpoints | Lower `CLUSTER_MOTION_THRESHOLD` (try 8.0) |
| Stitching failures | Try `STITCH_MODE = "single"` for individual frames |
| Panoramas look dark | Set `CLAHE_CLIP_LIMIT = 4.0` for stronger enhancement |
| Web viewer blank | Check browser console (F12). Ensure tour.json exists |
| Port in use | Change `WEB_SERVER_PORT` or use `--port 9090` |

---

## Tips for Best Results

1. **Fly slowly** — the drone should move smoothly, not jerky
2. **Rotate at stops** — pausing and rotating gives better panoramas
3. **Good lighting** — indoor spaces need adequate lighting for feature detection
4. **Overlap** — ensure adjacent frames have 20-30% visual overlap
5. **Avoid solid walls** — featureless walls are hard to stitch; include furniture/details

---

## License

Educational use only. Use responsibly and in compliance with local drone regulations.
