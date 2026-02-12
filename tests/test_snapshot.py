"""Tests for session snapshot save/load endpoints."""

from __future__ import annotations

import asyncio
import gzip
import json
import urllib.request
import urllib.error

import pytest
import websockets


SVG_CONTENT = {"type": "Svg", "data": "<svg></svg>"}
HTML_CONTENT = {"type": "Html", "data": "<p>hello</p>"}


class TestSnapshotSave:
    def test_save_returns_valid_gzip_snapshot(self, server):
        server.clear_plots()
        server.publish(SVG_CONTENT, title="snap1")
        server.publish(HTML_CONTENT, title="snap2")

        data = server.save_snapshot()
        decompressed = gzip.decompress(data)
        snapshot = json.loads(decompressed)

        assert snapshot["version"] == 1
        assert snapshot["plot_count"] == 2
        assert len(snapshot["plots"]) == 2
        assert isinstance(snapshot["created_at"], int)

    def test_save_without_token_returns_401(self, server):
        url = f"{server.base_url}/api/snapshot"
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(url, timeout=5)
        assert exc_info.value.code == 401

    def test_save_empty_session(self, server):
        server.clear_plots()
        data = server.save_snapshot()
        snapshot = json.loads(gzip.decompress(data))
        assert snapshot["plots"] == []
        assert snapshot["plot_count"] == 0


class TestSnapshotLoad:
    def test_load_replaces_session(self, server):
        server.clear_plots()
        server.publish(HTML_CONTENT, title="before")

        plots = [
            {
                "id": "snap-load-1",
                "timestamp": 1000000,
                "content": {"type": "Svg", "data": "<svg>loaded</svg>"},
                "tags": [],
            },
            {
                "id": "snap-load-2",
                "timestamp": 1000001,
                "content": {"type": "Html", "data": "<p>loaded</p>"},
                "tags": [],
            },
        ]
        snapshot = {"version": 1, "created_at": 1000000, "plot_count": 2, "plots": plots}
        compressed = gzip.compress(json.dumps(snapshot).encode())

        loaded = server.load_snapshot(compressed)
        assert loaded == 2

    def test_load_without_token_returns_401(self, server):
        snapshot = {"version": 1, "created_at": 0, "plot_count": 0, "plots": []}
        compressed = gzip.compress(json.dumps(snapshot).encode())
        url = f"{server.base_url}/api/snapshot"
        req = urllib.request.Request(
            url,
            data=compressed,
            headers={"Content-Type": "application/x-rileyviewer-snapshot"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 401

    def test_load_invalid_gzip_returns_400(self, server):
        url = f"{server.base_url}/api/snapshot?token={server.token}"
        req = urllib.request.Request(
            url,
            data=b"not gzip data",
            headers={"Content-Type": "application/x-rileyviewer-snapshot"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 400

    def test_load_future_version_returns_400(self, server):
        snapshot = {"version": 999, "created_at": 0, "plot_count": 0, "plots": []}
        compressed = gzip.compress(json.dumps(snapshot).encode())
        url = f"{server.base_url}/api/snapshot?token={server.token}"
        req = urllib.request.Request(
            url,
            data=compressed,
            headers={"Content-Type": "application/x-rileyviewer-snapshot"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 400


class TestSnapshotRoundtrip:
    def test_save_then_load_preserves_plots(self, server):
        server.clear_plots()
        id1 = server.publish(SVG_CONTENT, title="first")
        id2 = server.publish(HTML_CONTENT, tags=["test"])

        snapshot_bytes = server.save_snapshot()

        server.clear_plots()

        loaded = server.load_snapshot(snapshot_bytes)
        assert loaded == 2

        # Verify by saving again
        new_snapshot = json.loads(gzip.decompress(server.save_snapshot()))
        ids = [p["id"] for p in new_snapshot["plots"]]
        assert id1 in ids
        assert id2 in ids

        # Verify metadata survived
        plot1 = next(p for p in new_snapshot["plots"] if p["id"] == id1)
        assert plot1["title"] == "first"
        plot2 = next(p for p in new_snapshot["plots"] if p["id"] == id2)
        assert plot2["tags"] == ["test"]


class TestSnapshotWebSocket:
    @pytest.mark.asyncio
    async def test_load_broadcasts_to_ws(self, server):
        server.clear_plots()

        async with websockets.connect(server.ws_url) as ws:
            # Drain any initial messages
            while True:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    break

            # Load a snapshot via HTTP
            plots = [
                {
                    "id": "ws-snap-1",
                    "timestamp": 1,
                    "content": {"type": "Html", "data": "<p>ws</p>"},
                    "tags": [],
                }
            ]
            snapshot = {"version": 1, "created_at": 1, "plot_count": 1, "plots": plots}
            compressed = gzip.compress(json.dumps(snapshot).encode())
            server.load_snapshot(compressed)

            # Should receive clear + the plot
            messages = []
            for _ in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2)
                    messages.append(json.loads(msg))
                except asyncio.TimeoutError:
                    break

            kinds = [m.get("kind") for m in messages]
            assert "clear" in kinds
            plot_ids = [m.get("id") for m in messages if "content" in m]
            assert "ws-snap-1" in plot_ids
