"""Shared fixtures for rileyviewer integration tests.

The key fixture is `server` which builds the Rust binary, starts
`rileyviewer serve` on a random port with a known token, waits for
the health endpoint, and tears down on session end.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Generator

import pytest

# Project root (parent of tests/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(host: str, port: int, timeout: float = 15.0) -> None:
    """Poll GET /health until it returns 200 or timeout."""
    url = f"http://{host}:{port}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Server did not become healthy at {url} within {timeout}s")


class ServerInfo:
    """Container for a running test server's connection details."""

    def __init__(self, host: str, port: int, token: str, process: subprocess.Popen, home_dir: str):
        self.host = host
        self.port = port
        self.token = token
        self.process = process
        self.home_dir = home_dir

    @property
    def addr(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}/ws?token={self.token}"

    @property
    def publish_url(self) -> str:
        return f"{self.base_url}/api/publish"

    def publish(self, content: dict) -> str:
        """Publish content via HTTP POST, return the plot ID."""
        payload = json.dumps({"content": content, "token": self.token}).encode()
        req = urllib.request.Request(
            self.publish_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())["id"]


@pytest.fixture(scope="session")
def server() -> Generator[ServerInfo, None, None]:
    """Build and start a rileyviewer server for the test session.

    Yields a ServerInfo with host, port, token, and helper methods.
    The server is killed on teardown.
    """
    # Build release binary
    result = subprocess.run(
        ["cargo", "build", "--release"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"cargo build failed:\n{result.stderr}")

    binary = PROJECT_ROOT / "target" / "release" / "rileyviewer"
    if not binary.exists():
        pytest.fail(f"Binary not found at {binary}")

    host = "127.0.0.1"
    port = _find_free_port()
    token = "test-token-for-integration-tests"

    # Give the server a clean HOME so it doesn't find existing state files.
    # The CLI uses dirs::data_local_dir() which on macOS is ~/Library/Application Support.
    tmp_home = tempfile.mkdtemp(prefix="rv_test_")
    env = os.environ.copy()
    env["HOME"] = tmp_home
    env["RUST_LOG"] = "rv_server=debug"
    proc = subprocess.Popen(
        [
            str(binary),
            "serve",
            "--host", host,
            "--port", str(port),
            "--token", token,
            "--open-browser", "false",
            "--history-limit", "50",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        _wait_for_health(host, port)
    except RuntimeError:
        proc.kill()
        stdout, stderr = proc.communicate(timeout=5)
        pytest.fail(
            f"Server failed to start on {host}:{port}\n"
            f"stdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        )

    info = ServerInfo(host, port, token, proc, tmp_home)
    yield info

    # Teardown: kill the server
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
