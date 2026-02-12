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
        try:
            # Split host:port, handling IPv6 [::1]:port format
            if addr.startswith("["):
                host_part, _, port_part = addr.rpartition("]:")
                return host_part.strip("[]"), int(port_part) if port_part else port
            parts = addr.rsplit(":", 1)
            return parts[0], int(parts[1]) if len(parts) == 2 else port
        except (ValueError, TypeError):
            return addr, port

    h1, p1 = parse(a)
    h2, p2 = parse(b)
    if p1 != p2:
        return False
    if h1 == h2:
        return True
    return h1 in _LOCALHOST_ALIASES and h2 in _LOCALHOST_ALIASES


def _format_host(host: str) -> str:
    """Wrap IPv6 addresses in brackets for URL construction."""
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def _check_server_running(host: str, port: int) -> bool:
    """Check if a server is running on the given host:port."""
    try:
        url = f"http://{_format_host(host)}:{port}/health"
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

    def _http_publish(
        self,
        content: dict,
        *,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[list[str]] = None,
        max_retries: int = 3,
    ) -> str:
        """Publish via HTTP POST with retry logic for transient failures."""
        url = f"http://{_format_host(self._host)}:{self._port}/api/publish"
        payload = {"content": content}
        if self._token:
            payload["token"] = self._token
        if title is not None:
            payload["title"] = title
        if notes is not None:
            payload["notes"] = notes
        if tags is not None:
            payload["tags"] = tags
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
        *,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[list[str]] = None,
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
            title: Optional title for the plot.
            notes: Optional notes/description.
            tags: Optional list of tags.

        Returns:
            The plot ID assigned by the server.
        """
        return adapters.send_object_http(
            self, obj, format=format, title=title, notes=notes, tags=tags
        )

    def send_png_bytes(
        self, data: bytes, *, title: Optional[str] = None, notes: Optional[str] = None, tags: Optional[list[str]] = None
    ) -> str:
        """Send raw PNG bytes to the server."""
        encoded = base64.b64encode(data).decode("ascii")
        return self._http_publish({"type": "Png", "data": encoded}, title=title, notes=notes, tags=tags)

    def send_svg(
        self, svg: str, *, title: Optional[str] = None, notes: Optional[str] = None, tags: Optional[list[str]] = None
    ) -> str:
        """Send raw SVG string to the server."""
        return self._http_publish({"type": "Svg", "data": svg}, title=title, notes=notes, tags=tags)

    def send_plotly_json(
        self, payload: str, *, title: Optional[str] = None, notes: Optional[str] = None, tags: Optional[list[str]] = None
    ) -> str:
        """Send Plotly JSON to the server."""
        return self._http_publish({"type": "Plotly", "data": payload}, title=title, notes=notes, tags=tags)

    def send_vega_json(
        self, payload: str, *, title: Optional[str] = None, notes: Optional[str] = None, tags: Optional[list[str]] = None
    ) -> str:
        """Send Vega/Vega-Lite JSON to the server."""
        return self._http_publish({"type": "Vega", "data": payload}, title=title, notes=notes, tags=tags)

    def send_html(
        self, html: str, *, title: Optional[str] = None, notes: Optional[str] = None, tags: Optional[list[str]] = None
    ) -> str:
        """Send raw HTML to the server."""
        return self._http_publish({"type": "Html", "data": html}, title=title, notes=notes, tags=tags)

    def send_arrow_ipc(
        self, data: bytes, *, title: Optional[str] = None, notes: Optional[str] = None, tags: Optional[list[str]] = None
    ) -> str:
        """Send Arrow IPC bytes to the server for table rendering."""
        encoded = base64.b64encode(data).decode("ascii")
        return self._http_publish({"type": "ArrowIpc", "data": encoded}, title=title, notes=notes, tags=tags)

    def send_csv(
        self, csv_text: str, *, title: Optional[str] = None, notes: Optional[str] = None, tags: Optional[list[str]] = None
    ) -> str:
        """Send CSV text to the server for table rendering."""
        return self._http_publish({"type": "Csv", "data": csv_text}, title=title, notes=notes, tags=tags)

    def update_metadata(
        self,
        plot_id: str,
        *,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """Update metadata on an existing plot.

        Args:
            plot_id: The plot ID returned from a previous send/show call.
            title: New title (or None to clear, omit to leave unchanged).
            notes: New notes (or None to clear, omit to leave unchanged).
            tags: New tag list (omit to leave unchanged).

        Returns:
            Dict with updated id, title, notes, tags.
        """
        url = f"http://{_format_host(self._host)}:{self._port}/api/plots/{plot_id}/metadata"
        payload: dict = {}
        if self._token:
            payload["token"] = self._token
        if title is not None:
            payload["title"] = title
        if notes is not None:
            payload["notes"] = notes
        if tags is not None:
            payload["tags"] = tags

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status != 200:
                    raise ServerConnectionError(f"Server returned HTTP {resp.status}")
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ValueError(f"Plot {plot_id!r} not found") from e
            raise ServerConnectionError(f"Server error: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ServerConnectionError(f"Failed to update metadata: {e}") from e

    def delete(self, plot_id: str) -> None:
        """Delete a single plot from the server.

        Args:
            plot_id: The plot ID returned from a previous send/show call.

        Raises:
            ValueError: If the plot_id does not exist on the server.
        """
        url = f"http://{_format_host(self._host)}:{self._port}/api/plots/{plot_id}"
        payload: dict = {}
        if self._token:
            payload["token"] = self._token
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        try:
            urllib.request.urlopen(req, timeout=5).close()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ValueError(f"Plot {plot_id!r} not found") from e
            raise ServerConnectionError(f"Delete failed: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ServerConnectionError(f"Failed to delete: {e}") from e

    def clear(self) -> None:
        """Clear all plots from the server."""
        url = f"http://{_format_host(self._host)}:{self._port}/api/plots"
        payload: dict = {}
        if self._token:
            payload["token"] = self._token
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        try:
            urllib.request.urlopen(req, timeout=5).close()
        except urllib.error.HTTPError as e:
            raise ServerConnectionError(f"Clear failed: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ServerConnectionError(f"Failed to clear: {e}") from e

    def save_snapshot(self, path: str | Path) -> None:
        """Save the current session to a .rvw snapshot file.

        Args:
            path: File path to write the snapshot to.
        """
        path = Path(path)
        token_param = f"?token={self._token}" if self._token else ""
        url = f"http://{_format_host(self._host)}:{self._port}/api/snapshot{token_param}"
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            raise ServerConnectionError(f"Failed to save snapshot: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ServerConnectionError(f"Failed to save snapshot: {e}") from e
        path.write_bytes(data)

    def load_snapshot(self, path: str | Path) -> int:
        """Load a .rvw snapshot file into the viewer, replacing the current session.

        Args:
            path: File path to the snapshot to load.

        Returns:
            Number of plots loaded.
        """
        path = Path(path)
        data = path.read_bytes()
        token_param = f"?token={self._token}" if self._token else ""
        url = f"http://{_format_host(self._host)}:{self._port}/api/snapshot{token_param}"
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/x-rileyviewer-snapshot"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("loaded", 0)
        except urllib.error.HTTPError as e:
            raise ServerConnectionError(f"Failed to load snapshot: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ServerConnectionError(f"Failed to load snapshot: {e}") from e

    def capture(self) -> "MatplotlibContext":
        return MatplotlibContext(self)


class MatplotlibContext:
    """Context manager to collect matplotlib output and close figures on exit."""

    def __init__(self, viewer: Viewer) -> None:
        self.viewer = viewer
        self._captured_figures: list[Any] = []

    def __enter__(self) -> "MatplotlibContext":
        return self

    def push(
        self,
        *,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> str:
        import matplotlib.pyplot as plt

        fig = plt.gcf()
        self._captured_figures.append(fig)
        return self.viewer.show(fig, title=title, notes=notes, tags=tags)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        import matplotlib.pyplot as plt

        # Only close figures that were captured within this context
        for fig in self._captured_figures:
            plt.close(fig)
        self._captured_figures.clear()
