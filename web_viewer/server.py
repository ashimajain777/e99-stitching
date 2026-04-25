"""
Web Viewer Server
==================
Simple HTTP server to serve the Three.js 3D viewer
and provide model files from the datasets directory.
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
    """Custom HTTP handler that serves the web viewer and model files."""

    def __init__(self, *args, datasets_dir=None, **kwargs):
        self.datasets_dir = datasets_dir or str(config.DATASETS_DIR)
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        # API endpoint: list available models
        if path == '/api/models':
            self.send_models_list()
            return

        # Serve model files from datasets
        if path.startswith('/data/'):
            self.serve_data_file(path[6:])  # Remove '/data/' prefix
            return

        # Serve trajectory JSON
        if path == '/api/trajectory':
            self.serve_trajectory()
            return

        # Default: serve static files from web_viewer directory
        super().do_GET()

    def send_models_list(self):
        """List available PLY/OBJ files in the datasets directory."""
        models = []
        datasets = Path(self.datasets_dir)

        for ext in ['*.ply', '*.obj']:
            for f in datasets.rglob(ext):
                size = f.stat().st_size
                if size > 0:
                    size_str = f"{size / 1024 / 1024:.1f} MB" if size > 1024 * 1024 else f"{size / 1024:.1f} KB"
                    rel_path = f.relative_to(datasets)
                    models.append({
                        "name": f.name,
                        "url": f"/data/{str(rel_path).replace(os.sep, '/')}",
                        "size": size_str,
                        "path": str(rel_path),
                    })

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(models).encode())

    def serve_data_file(self, relative_path):
        """Serve a file from the datasets directory."""
        file_path = Path(self.datasets_dir) / relative_path

        if not file_path.exists():
            self.send_error(404, f"File not found: {relative_path}")
            return

        # Security: ensure path is within datasets
        try:
            file_path.resolve().relative_to(Path(self.datasets_dir).resolve())
        except ValueError:
            self.send_error(403, "Access denied")
            return

        # Determine content type
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

    def serve_trajectory(self):
        """Serve camera trajectory JSON."""
        traj_path = Path(self.datasets_dir) / "output" / "trajectory.json"
        if not traj_path.exists():
            # Try colmap workspace
            traj_path = Path(self.datasets_dir) / "colmap" / "trajectory.json"

        if traj_path.exists():
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            with open(traj_path, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"cameras": []}')

    def log_message(self, format, *args):
        """Suppress routine logs, show only important ones."""
        if args and '404' in str(args[0]):
            super().log_message(format, *args)


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

    handler_class = create_handler_class(datasets_dir)

    # Try to find an available port
    for attempt_port in range(port, port + 10):
        try:
            server = http.server.HTTPServer(('', attempt_port), handler_class)
            break
        except OSError:
            continue
    else:
        print(f"  ❌ Could not find available port in range {port}-{port+9}")
        return

    url = f"http://localhost:{attempt_port}"

    print("\n" + "=" * 60)
    print("  E99 3D Explorer — Web Viewer")
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
    parser = argparse.ArgumentParser(description="Start web viewer server")
    parser.add_argument("--port", type=int, help="Server port")
    parser.add_argument("--data", help="Datasets directory")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
    args = parser.parse_args()

    start_server(args.port, args.data, not args.no_browser)
