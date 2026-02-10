"""Integration tests for the CLI send command."""

from __future__ import annotations

import base64
import io
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

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


def _env(server) -> dict:
    """Build env dict pointing the CLI at the test server.

    The server fixture already wrote its state file under server.home_dir,
    so we just set HOME to that directory.
    """
    import os
    env = os.environ.copy()
    env["HOME"] = server.home_dir
    return env
