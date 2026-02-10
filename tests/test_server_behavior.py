"""Tests for server behavior: shutdown endpoint, history limits, CLI commands."""

from __future__ import annotations

import asyncio
import json
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

import pytest
import websockets

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BINARY = PROJECT_ROOT / "target" / "release" / "rileyviewer"


class TestHistoryLimit:
    @pytest.mark.asyncio
    async def test_history_evicts_old_entries(self, server):
        """Server is configured with history_limit=50. Publish 60 items,
        verify a new client gets at most 50 in history."""
        # Publish 60 items
        ids = []
        for i in range(60):
            ids.append(server.publish({"type": "Html", "data": f"<p>{i}</p>"}))

        # Connect new client and collect history
        async with websockets.connect(server.ws_url) as ws:
            history = []
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    history.append(json.loads(raw))
                except asyncio.TimeoutError:
                    break

            # Should get at most 50 (the configured limit)
            assert len(history) <= 50

            # The oldest entries should have been evicted
            history_ids = [m["id"] for m in history]
            # First 10 IDs should NOT be in history (they were evicted)
            for old_id in ids[:10]:
                assert old_id not in history_ids

            # Last 50 IDs should all be present
            for recent_id in ids[10:]:
                assert recent_id in history_ids


class TestShutdownEndpoint:
    def test_shutdown_without_token_rejected(self, server):
        payload = json.dumps({}).encode()
        req = urllib.request.Request(
            f"{server.base_url}/api/shutdown",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 401

    def test_shutdown_with_wrong_token_rejected(self, server):
        payload = json.dumps({"token": "wrong"}).encode()
        req = urllib.request.Request(
            f"{server.base_url}/api/shutdown",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 401


class TestCliStatus:
    def test_status_reports_running(self, server):
        result = subprocess.run(
            [str(BINARY), "status"],
            capture_output=True,
            text=True,
            env=_env(server),
        )
        assert result.returncode == 0
        assert "running" in result.stdout.lower() or "Running" in result.stdout

    def test_status_reports_not_running_with_bad_state(self):
        """With an empty HOME, no state file → reports not running."""
        import tempfile, os
        env = os.environ.copy()
        env["HOME"] = tempfile.mkdtemp()
        result = subprocess.run(
            [str(BINARY), "status"],
            capture_output=True,
            text=True,
            env=env,
        )
        # Should either exit with error or print "not running"
        assert result.returncode != 0 or "not running" in result.stdout.lower()


class TestCliSendErrors:
    def test_send_nonexistent_file(self, server):
        result = subprocess.run(
            [str(BINARY), "send", "/nonexistent/file.csv"],
            capture_output=True,
            text=True,
            env=_env(server),
        )
        assert result.returncode != 0

    def test_send_no_server(self):
        """Send when no server is running should fail gracefully."""
        import tempfile, os
        env = os.environ.copy()
        env["HOME"] = tempfile.mkdtemp()
        result = subprocess.run(
            [str(BINARY), "send", "--type", "csv"],
            input="x\n1\n",
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode != 0


def _env(server) -> dict:
    """Build env dict pointing the CLI at the test server."""
    import os
    env = os.environ.copy()
    env["HOME"] = server.home_dir
    return env
