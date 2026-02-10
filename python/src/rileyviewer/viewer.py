from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Optional

from . import adapters
from .adapters import MatplotlibFormat
from .exceptions import ServerConnectionError, ServerNotRunningError

DEFAULT_PORT = 7878
DEFAULT_HOST = "127.0.0.1"


def _state_dir() -> Path:
    """Get the rileyviewer state directory."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "rileyviewer"


def _read_server_state() -> Optional[dict]:
    """Read the server state file if it exists."""
    state_file = _state_dir() / "server.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None


_LOCALHOST_ALIASES = {"127.0.0.1", "localhost", "0.0.0.0", "::1", "::"}


def _addrs_match(a: str, b: str, port: int) -> bool:
    """Check if two host:port strings refer to the same local server."""
    def parse(addr: str) -> tuple:
        # Split host:port, handling IPv6 [::1]:port format
        if addr.startswith("["):
            host_part, _, port_part = addr.rpartition("]:")
            return host_part.strip("[]"), int(port_part) if port_part else port
        parts = addr.rsplit(":", 1)
        return parts[0], int(parts[1]) if len(parts) == 2 else port

    h1, p1 = parse(a)
    h2, p2 = parse(b)
    if p1 != p2:
        return False
    if h1 == h2:
        return True
    return h1 in _LOCALHOST_ALIASES and h2 in _LOCALHOST_ALIASES


def _check_server_running(host: str, port: int) -> bool:
    """Check if a server is running on the given host:port."""
    try:
        url = f"http://{host}:{port}/health"
        with urllib.request.urlopen(url, timeout=0.5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


class Viewer:
    """Python client that connects to a running RileyViewer server.

    The server must be started separately with ``rileyviewer serve``.
    Raises :class:`ServerNotRunningError` with install instructions
    if the server is not reachable.

    Args:
        host: Server host (default: 127.0.0.1).
        port: Server port (default: 7878).
        token: Auth token. Read from the server state file if not provided.
        default_format: Default matplotlib output format ("svg" or "png").
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        token: Optional[str] = None,
        default_format: MatplotlibFormat = "svg",
    ) -> None:
        self._host = host or DEFAULT_HOST
        self._port = port if port is not None else DEFAULT_PORT
        self._token = token
        self._default_format: MatplotlibFormat = default_format

        if not _check_server_running(self._host, self._port):
            raise ServerNotRunningError(self._host, self._port)

        # Read token from state file if not explicitly provided
        if not self._token:
            state = _read_server_state()
            if state and _addrs_match(state.get("addr", ""), f"{self._host}:{self._port}", self._port):
                self._token = state.get("token")

    @property
    def addr(self) -> str:
        return f"{self._host}:{self._port}"

    @property
    def token(self) -> Optional[str]:
        return self._token

    def _http_publish(self, content: dict, max_retries: int = 3) -> str:
        """Publish via HTTP POST with retry logic for transient failures."""
        url = f"http://{self._host}:{self._port}/api/publish"
        payload = {"content": content}
        if self._token:
            payload["token"] = self._token
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status != 200:
                        raise ServerConnectionError(
                            f"Server returned HTTP {resp.status}"
                        )
                    try:
                        result = json.loads(resp.read().decode("utf-8"))
                        return result["id"]
                    except (json.JSONDecodeError, KeyError) as e:
                        raise ServerConnectionError(
                            f"Unexpected response from server: {e}"
                        ) from e
            except urllib.error.HTTPError as e:
                # Don't retry client errors (4xx) - they won't succeed
                if 400 <= e.code < 500:
                    raise ServerConnectionError(
                        f"Server rejected request: HTTP {e.code} {e.reason}"
                    ) from e
                last_error = e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_error = e

            # Exponential backoff: 0.1s, 0.2s, 0.4s
            if attempt < max_retries - 1:
                time.sleep(0.1 * (2 ** attempt))

        raise ServerConnectionError(
            f"Failed to publish after {max_retries} attempts: {last_error}"
        ) from last_error

    def show(
        self,
        obj: Any,
        format: Optional[MatplotlibFormat] = None,
    ) -> str:
        """Serialize a plotting object and send it to the server.

        Args:
            obj: The plot object to send. Supported types:
                - matplotlib Figure (or objects with savefig method)
                - matplotlib Animation (FuncAnimation, ArtistAnimation)
                - numpy array of matplotlib Axes (from arviz, seaborn, etc.)
                - plotly Figure
                - altair Chart
                - any object with _repr_html_() method
            format: For matplotlib figures, the output format ("svg" or "png").
                    Defaults to the viewer's default_format (which defaults to "svg").
                    Ignored for animations (always HTML) and other plot types.

        Returns:
            The plot ID assigned by the server.
        """
        return adapters.send_object_http(self, obj, format=format)

    def send_png_bytes(self, data: bytes) -> str:
        """Send raw PNG bytes to the server."""
        encoded = base64.b64encode(data).decode("ascii")
        return self._http_publish({"type": "Png", "data": encoded})

    def send_svg(self, svg: str) -> str:
        """Send raw SVG string to the server."""
        return self._http_publish({"type": "Svg", "data": svg})

    def send_plotly_json(self, payload: str) -> str:
        """Send Plotly JSON to the server."""
        return self._http_publish({"type": "Plotly", "data": payload})

    def send_vega_json(self, payload: str) -> str:
        """Send Vega/Vega-Lite JSON to the server."""
        return self._http_publish({"type": "Vega", "data": payload})

    def send_html(self, html: str) -> str:
        """Send raw HTML to the server."""
        return self._http_publish({"type": "Html", "data": html})

    def send_arrow_ipc(self, data: bytes) -> str:
        """Send Arrow IPC bytes to the server for table rendering."""
        encoded = base64.b64encode(data).decode("ascii")
        return self._http_publish({"type": "ArrowIpc", "data": encoded})

    def send_csv(self, csv_text: str) -> str:
        """Send CSV text to the server for table rendering."""
        return self._http_publish({"type": "Csv", "data": csv_text})

    def capture(self) -> "MatplotlibContext":
        return MatplotlibContext(self)


class MatplotlibContext:
    """Context manager to collect matplotlib output and close figures on exit."""

    def __init__(self, viewer: Viewer) -> None:
        self.viewer = viewer
        self._captured_figures: list[Any] = []

    def __enter__(self) -> "MatplotlibContext":
        return self

    def push(self) -> str:
        import matplotlib.pyplot as plt

        fig = plt.gcf()
        self._captured_figures.append(fig)
        return self.viewer.show(fig)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        import matplotlib.pyplot as plt

        # Only close figures that were captured within this context
        for fig in self._captured_figures:
            plt.close(fig)
        self._captured_figures.clear()
