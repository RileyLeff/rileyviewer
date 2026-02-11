"""Integration tests for the CLI send and watch commands."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import websockets

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BINARY = PROJECT_ROOT / "target" / "release" / "rileyviewer"


class TestCliSend:
    def test_send_csv_file(self, server):
        with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
            f.write("name,value\nalice,10\nbob,20\n")
            f.flush()
            result = subprocess.run(
                [str(BINARY), "send", f.name],
                capture_output=True,
                text=True,
                env=_env(server),
            )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_send_csv_from_stdin(self, server):
        result = subprocess.run(
            [str(BINARY), "send", "--type", "csv"],
            input="x,y\n1,2\n3,4\n",
            capture_output=True,
            text=True,
            env=_env(server),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_send_svg_file(self, server):
        with tempfile.NamedTemporaryFile(suffix=".svg", mode="w", delete=False) as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg"><circle r="10"/></svg>')
            f.flush()
            result = subprocess.run(
                [str(BINARY), "send", f.name],
                capture_output=True,
                text=True,
                env=_env(server),
            )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_send_html_file(self, server):
        with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as f:
            f.write("<h1>test</h1>")
            f.flush()
            result = subprocess.run(
                [str(BINARY), "send", f.name],
                capture_output=True,
                text=True,
                env=_env(server),
            )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_send_png_file(self, server):
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
            b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
            b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png)
            f.flush()
            result = subprocess.run(
                [str(BINARY), "send", f.name],
                capture_output=True,
                text=True,
                env=_env(server),
            )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_send_arrow_file(self, server):
        import pyarrow as pa
        import pyarrow.ipc

        table = pa.table({"a": [1, 2], "b": ["x", "y"]})
        with tempfile.NamedTemporaryFile(suffix=".arrow", delete=False) as f:
            writer = pa.ipc.new_stream(f, table.schema)
            writer.write_table(table)
            writer.close()
            path = f.name
        result = subprocess.run(
            [str(BINARY), "send", path],
            capture_output=True,
            text=True,
            env=_env(server),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_send_with_type_override(self, server):
        # Send a plain text file but force csv type
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("col1,col2\nfoo,bar\n")
            f.flush()
            result = subprocess.run(
                [str(BINARY), "send", "--type", "csv", f.name],
                capture_output=True,
                text=True,
                env=_env(server),
            )
        assert result.returncode == 0, f"stderr: {result.stderr}"


class TestCliContentDetection:
    def test_detects_csv_from_extension(self, server):
        with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
            f.write("x\n1\n")
            f.flush()
            result = subprocess.run(
                [str(BINARY), "send", f.name],
                capture_output=True,
                text=True,
                env=_env(server),
            )
        assert result.returncode == 0

    def test_detects_arrow_from_magic_bytes(self, server):
        import pyarrow as pa
        import pyarrow.ipc

        # Use .dat extension so detection must rely on magic bytes
        table = pa.table({"z": [1]})
        with tempfile.NamedTemporaryFile(suffix=".dat", delete=False) as f:
            writer = pa.ipc.new_stream(f, table.schema)
            writer.write_table(table)
            writer.close()
            path = f.name
        result = subprocess.run(
            [str(BINARY), "send", path],
            capture_output=True,
            text=True,
            env=_env(server),
        )
        # Should detect arrow from magic bytes and succeed
        assert result.returncode == 0, f"stderr: {result.stderr}"


class TestCliWatch:
    @pytest.mark.asyncio
    async def test_watch_sends_new_file(self, server):
        """Write a file into a watched directory and verify it arrives via WS."""
        watch_dir = tempfile.mkdtemp()

        # Start watcher in background
        proc = subprocess.Popen(
            [str(BINARY), "watch", watch_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_env(server),
        )
        try:
            # Give watcher time to start
            time.sleep(1)

            # Connect WebSocket to receive the plot
            async with websockets.connect(server.ws_url) as ws:
                await _drain(ws)

                # Write an SVG file into the watched directory
                svg_path = os.path.join(watch_dir, "test.svg")
                with open(svg_path, "w") as f:
                    f.write('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>')

                # Wait for the watcher to pick it up and send it
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                assert data["content"]["type"] == "Svg"
                assert "<rect" in data["content"]["data"]
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    @pytest.mark.asyncio
    async def test_watch_ignores_unsupported_extension(self, server):
        """Files with unsupported extensions should not be sent."""
        watch_dir = tempfile.mkdtemp()

        proc = subprocess.Popen(
            [str(BINARY), "watch", watch_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_env(server),
        )
        try:
            time.sleep(1)

            async with websockets.connect(server.ws_url) as ws:
                await _drain(ws)

                # Write an unsupported file type
                txt_path = os.path.join(watch_dir, "notes.txt")
                with open(txt_path, "w") as f:
                    f.write("this should be ignored")

                # Then write a supported file so we know the watcher is alive
                csv_path = os.path.join(watch_dir, "data.csv")
                with open(csv_path, "w") as f:
                    f.write("x,y\n1,2\n")

                # We should get the CSV but NOT the txt
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                assert data["content"]["type"] == "Csv"

        finally:
            proc.terminate()
            proc.wait(timeout=5)

    @pytest.mark.asyncio
    async def test_watch_existing_flag(self, server):
        """--existing should send pre-existing files on startup."""
        watch_dir = tempfile.mkdtemp()

        # Write a file BEFORE starting the watcher
        html_path = os.path.join(watch_dir, "pre-existing.html")
        with open(html_path, "w") as f:
            f.write("<p>already here</p>")

        # Connect WebSocket BEFORE starting watcher so we don't miss the send
        async with websockets.connect(server.ws_url) as ws:
            await _drain(ws)

            proc = subprocess.Popen(
                [str(BINARY), "watch", "--existing", watch_dir],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_env(server),
            )
            try:
                # Should receive the pre-existing file
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                assert data["content"]["type"] == "Html"
                assert "already here" in data["content"]["data"]
            finally:
                proc.terminate()
                proc.wait(timeout=5)


async def _drain(ws) -> None:
    """Drain all pending history messages."""
    while True:
        try:
            await asyncio.wait_for(ws.recv(), timeout=0.5)
        except asyncio.TimeoutError:
            break


def _env(server) -> dict:
    """Build env dict pointing the CLI at the test server.

    The server fixture already wrote its state file under server.home_dir,
    so we just set HOME to that directory.
    """
    env = os.environ.copy()
    env["HOME"] = server.home_dir
    return env
