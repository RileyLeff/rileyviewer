from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Optional

from . import adapters

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


def _check_server_running(host: str, port: int) -> bool:
    """Check if a server is running on the given host:port."""
    try:
        url = f"http://{host}:{port}/health"
        with urllib.request.urlopen(url, timeout=0.5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _find_cli_binary() -> Optional[str]:
    """Find the rileyviewer CLI binary."""
    import shutil

    # Check if it's in PATH
    cli = shutil.which("rileyviewer")
    if cli:
        return cli

    # Check common cargo install locations
    cargo_bin = Path.home() / ".cargo" / "bin" / "rileyviewer"
    if cargo_bin.exists():
        return str(cargo_bin)

    # Check if we're in development mode - look for target/debug or target/release
    # First check relative to cwd (for uv run scripts where package is in cache)
    cwd = Path.cwd()
    for profile in ["release", "debug"]:
        dev_binary = cwd / "target" / profile / "rileyviewer"
        if dev_binary.exists():
            return str(dev_binary)

    # Also check relative to the package location (for editable installs)
    pkg_dir = Path(__file__).parent.parent.parent.parent  # python/src/rileyviewer -> repo root
    for profile in ["release", "debug"]:
        dev_binary = pkg_dir / "target" / profile / "rileyviewer"
        if dev_binary.exists():
            return str(dev_binary)

    return None


def _spawn_server(
    host: str,
    port: int,
    token: Optional[str],
    dist_dir: Optional[str] = None,
    open_browser: bool = True,
) -> bool:
    """Spawn a detached server process. Returns True if successful."""
    cli = _find_cli_binary()
    if not cli:
        return False

    cmd = [cli, "serve", "--host", host, "--port", str(port)]
    cmd.extend(["--open-browser", "true" if open_browser else "false"])
    if token:
        cmd.extend(["--token", token])
    if dist_dir:
        cmd.extend(["--dist-dir", dist_dir])

    # Spawn detached process
    if sys.platform == "win32":
        # Windows: use DETACHED_PROCESS flag
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
            "creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        }
        try:
            subprocess.Popen(cmd, **kwargs)
            return True
        except OSError:
            return False
    else:
        # Unix: use double-fork via shell to fully detach
        # The shell handles backgrounding, nohup ensures survival
        cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        shell_cmd = f"nohup {cmd_str} >/dev/null 2>&1 &"
        try:
            # Use os.system for true shell backgrounding
            import os as _os
            _os.system(shell_cmd)
            return True
        except OSError:
            return False


class Viewer:
    """Python-facing viewer that connects to the RileyViewer server."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        token: Optional[str] = None,
        open_browser: bool = True,
        dist_dir: Optional[str] = None,
    ) -> None:
        self._host = host or DEFAULT_HOST
        self._port = port if port is not None else DEFAULT_PORT
        self._token = token
        self._open_browser = open_browser
        self._dist_dir = dist_dir

        # Check if server already running
        if _check_server_running(self._host, self._port):
            # Server running - read token from state file if we don't have one
            if not self._token:
                state = _read_server_state()
                if state and state.get("addr") == f"{self._host}:{self._port}":
                    self._token = state.get("token")
        else:
            # Need to start server - CLI will open browser if requested
            if not _spawn_server(self._host, self._port, self._token, self._dist_dir, self._open_browser):
                # CLI not found, fall back to embedded server
                from ._core import RustViewer
                self._inner = RustViewer(host=self._host, port=self._port, token=self._token)
                self._token = self._inner.token
                return

            # Wait for server to start (state file is written before server binds,
            # so by the time health check passes, state file is guaranteed to exist)
            for _ in range(50):  # 5 seconds max
                time.sleep(0.1)
                if _check_server_running(self._host, self._port):
                    break
            else:
                raise RuntimeError(f"Server failed to start on {self._host}:{self._port}")

            # Read token from state file (guaranteed to exist now)
            state = _read_server_state()
            if state and state.get("addr") == f"{self._host}:{self._port}":
                self._token = state.get("token")

    @property
    def addr(self) -> str:
        return f"{self._host}:{self._port}"

    @property
    def token(self) -> Optional[str]:
        return self._token

    def _http_publish(self, content: dict) -> str:
        """Publish via HTTP POST."""
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
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["id"]

    def show(self, obj: Any) -> str:
        """Serialize a plotting object and send it to the server."""
        return adapters.send_object_http(self, obj)

    def send_png_bytes(self, data: bytes) -> str:
        encoded = base64.b64encode(data).decode("ascii")
        return self._http_publish({"type": "Png", "data": encoded})

    def send_plotly_json(self, payload: str) -> str:
        return self._http_publish({"type": "Plotly", "data": payload})

    def send_vega_json(self, payload: str) -> str:
        return self._http_publish({"type": "Vega", "data": payload})

    def send_html(self, html: str) -> str:
        return self._http_publish({"type": "Html", "data": html})

    def capture(self) -> "MatplotlibContext":
        return MatplotlibContext(self)

    def shutdown(self) -> None:
        """Shutdown is now a no-op for detached servers. Use `rileyviewer stop` CLI."""
        pass


class MatplotlibContext:
    """Context manager to collect matplotlib output and close figures on exit."""

    def __init__(self, viewer: Viewer) -> None:
        self.viewer = viewer

    def __enter__(self) -> "MatplotlibContext":
        return self

    def push(self) -> str:
        import matplotlib.pyplot as plt

        fig = plt.gcf()
        return self.viewer.show(fig)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        import matplotlib.pyplot as plt

        plt.close("all")
