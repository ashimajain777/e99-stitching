"""
Web Viewer Server
==================
HTTP server for the Pannellum-based panoramic tour viewer.
Serves panorama images, tour.json config, and static viewer files.
"""

import http.server
import json
import os
import sys
import webbrowser
import threading
import mimetypes
from pathlib import Path
from urllib.parse import urlparse, unquote

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


class ViewerHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler for panorama viewer."""

    def __init__(self, *args, datasets_dir=None, **kwargs):
        self.datasets_dir = datasets_dir or str(config.DATASETS_DIR)
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        # API: tour configuration
        if path == '/api/tour':
            self.serve_tour_json()
            return

        # Serve panorama images from datasets/panoramas/
        if path.startswith('/panoramas/'):
            self.serve_panorama(path[11:])  # Remove '/panoramas/' prefix
            return

        # Serve any data file from datasets/
        if path.startswith('/data/'):
            self.serve_data_file(path[6:])
            return

        # Default: serve static files from web_viewer directory
        super().do_GET()

    def serve_tour_json(self):
        """Serve the tour.json configuration."""
        tour_path = Path(self.datasets_dir) / "output" / "tour.json"

        if tour_path.exists():
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            with open(tour_path, 'rb') as f:
                self.wfile.write(f.read())
        else:
            # Return empty tour so the viewer can show an error
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"scenes": {}}')

    def serve_panorama(self, filename):
        """Serve a panorama image from datasets/panoramas/."""
        file_path = Path(self.datasets_dir) / "panoramas" / filename

        if not file_path.exists():
            self.send_error(404, f"Panorama not found: {filename}")
            return

        # Security check: prevent directory traversal
        if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
            self.send_error(403, "Access denied")
            return

        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = 'image/jpeg'

        file_size = file_path.stat().st_size

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(file_size))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'public, max-age=3600')
        self.end_headers()

        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def serve_data_file(self, relative_path):
        """Serve a file from the datasets directory."""
        file_path = Path(self.datasets_dir) / relative_path

        if not file_path.exists():
            self.send_error(404, f"File not found: {relative_path}")
            return

        # Security check: prevent directory traversal
        if ".." in relative_path or relative_path.startswith("/") or relative_path.startswith("\\"):
            self.send_error(403, "Access denied")
            return

        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = 'application/octet-stream'

        file_size = file_path.stat().st_size

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(file_size))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)

    # Inherit default log_message to see all requests for debugging


def create_handler_class(datasets_dir):
    """Create a handler class with the datasets directory bound."""
    class BoundHandler(ViewerHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, datasets_dir=datasets_dir, **kwargs)
    return BoundHandler


def start_server(port: int = None, datasets_dir: str = None,
                 open_browser: bool = None):
    """Start the web viewer server.

    Args:
        port: Server port. None = config default.
        datasets_dir: Datasets directory. None = config default.
        open_browser: Auto-open browser. None = config default.
    """
    if port is None:
        port = config.WEB_SERVER_PORT
    if datasets_dir is None:
        datasets_dir = str(config.DATASETS_DIR)
    if open_browser is None:
        open_browser = config.WEB_AUTO_OPEN_BROWSER

    # Check for tour data
    tour_path = Path(datasets_dir) / "output" / "tour.json"
    pano_dir = Path(datasets_dir) / "panoramas"

    if tour_path.exists():
        with open(tour_path) as f:
            tour = json.load(f)
        num_scenes = len(tour.get("scenes", {}))
        print(f"  Tour: {num_scenes} scenes")
    else:
        print(f"  ⚠️ No tour.json found at {tour_path}")
        print(f"  Run the pipeline first: python pipeline.py run --input video.mp4")

    if pano_dir.exists():
        pano_files = list(pano_dir.glob("*.jpg")) + list(pano_dir.glob("*.png"))
        print(f"  Panoramas: {len(pano_files)} images in {pano_dir}")
    else:
        print(f"  ⚠️ No panoramas directory at {pano_dir}")

    handler_class = create_handler_class(datasets_dir)

    # Try to find an available port
    for attempt_port in range(port, port + 10):
        try:
            server = http.server.HTTPServer(('', attempt_port), handler_class)
            break
        except OSError:
            continue
    else:
        print(f"  ❌ Could not find available port in range {port}-{port + 9}")
        return

    url = f"http://localhost:{attempt_port}"

    print("\n" + "=" * 60)
    print("  E99 Street View — Web Server (v2 Updated)")
    print("=" * 60)
    print(f"  Server: {url}")
    print(f"  Data:   {datasets_dir}")
    print(f"  Press Ctrl+C to stop")
    print("=" * 60)

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.shutdown()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Start panorama viewer server")
    parser.add_argument("--port", type=int, help="Server port")
    parser.add_argument("--data", help="Datasets directory")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
    args = parser.parse_args()

    start_server(args.port, args.data, not args.no_browser)
