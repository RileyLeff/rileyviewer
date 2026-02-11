"""Integration tests for metadata (title, notes, tags) and PATCH endpoint."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

import pytest
import websockets


class TestPublishWithMetadata:
    def test_publish_with_title(self, server):
        plot_id = server.publish(
            {"type": "Html", "data": "<p>titled</p>"},
            title="My Plot",
        )
        assert plot_id  # non-empty string

    def test_publish_with_all_metadata(self, server):
        plot_id = server.publish(
            {"type": "Html", "data": "<p>full meta</p>"},
            title="Full Meta",
            notes="Some notes here",
            tags=["experiment", "v2"],
        )
        assert plot_id

    def test_publish_without_metadata_backward_compat(self, server):
        plot_id = server.publish({"type": "Html", "data": "<p>no meta</p>"})
        assert plot_id


class TestPatchMetadata:
    def test_patch_title(self, server):
        plot_id = server.publish({"type": "Html", "data": "<p>patch test</p>"})
        result = server.patch_metadata(plot_id, title="Updated Title")
        assert result["id"] == plot_id
        assert result["title"] == "Updated Title"

    def test_patch_tags(self, server):
        plot_id = server.publish({"type": "Html", "data": "<p>tag test</p>"})
        result = server.patch_metadata(plot_id, tags=["a", "b"])
        assert result["tags"] == ["a", "b"]

    def test_patch_notes(self, server):
        plot_id = server.publish({"type": "Html", "data": "<p>notes test</p>"})
        result = server.patch_metadata(plot_id, notes="hello notes")
        assert result["notes"] == "hello notes"

    def test_patch_multiple_fields(self, server):
        plot_id = server.publish({"type": "Html", "data": "<p>multi</p>"})
        result = server.patch_metadata(
            plot_id, title="T", notes="N", tags=["x"]
        )
        assert result["title"] == "T"
        assert result["notes"] == "N"
        assert result["tags"] == ["x"]

    def test_patch_preserves_unset_fields(self, server):
        """Fields not included in the PATCH body should be preserved."""
        plot_id = server.publish(
            {"type": "Html", "data": "<p>preserve</p>"},
            title="Keep Me",
            tags=["original"],
        )
        # Only update notes, title and tags should be preserved
        result = server.patch_metadata(plot_id, notes="Added notes")
        assert result["title"] == "Keep Me"
        assert result["tags"] == ["original"]
        assert result["notes"] == "Added notes"

    def test_patch_nonexistent_returns_404(self, server):
        url = f"{server.base_url}/api/plots/nonexistent-id/metadata"
        payload = json.dumps({"token": server.token, "title": "Nope"}).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 404

    def test_patch_without_token_returns_401(self, server):
        plot_id = server.publish({"type": "Html", "data": "<p>auth</p>"})
        url = f"{server.base_url}/api/plots/{plot_id}/metadata"
        payload = json.dumps({"title": "No Auth"}).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 401


class TestMetadataInHistory:
    @pytest.mark.asyncio
    async def test_history_includes_metadata(self, server):
        """Metadata should appear when fetching history over WS."""
        plot_id = server.publish(
            {"type": "Html", "data": "<p>history meta</p>"},
            title="History Title",
            tags=["hist"],
        )

        async with websockets.connect(server.ws_url) as ws:
            # Read through history until we find our plot
            found = None
            for _ in range(100):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2)
                    data = json.loads(msg)
                    if data.get("id") == plot_id:
                        found = data
                        break
                except asyncio.TimeoutError:
                    break

            assert found is not None, f"Plot {plot_id} not found in history"
            assert found["title"] == "History Title"
            assert found["tags"] == ["hist"]


class TestMetadataWebSocketBroadcast:
    @pytest.mark.asyncio
    async def test_publish_with_metadata_broadcast(self, server):
        """Published plots with metadata should be broadcast with metadata."""
        async with websockets.connect(server.ws_url) as ws:
            await _drain_history(ws)

            plot_id = server.publish(
                {"type": "Html", "data": "<p>ws meta</p>"},
                title="WS Title",
                notes="WS Notes",
                tags=["ws"],
            )

            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            assert data["id"] == plot_id
            assert data["title"] == "WS Title"
            assert data["notes"] == "WS Notes"
            assert data["tags"] == ["ws"]

    @pytest.mark.asyncio
    async def test_metadata_update_broadcast(self, server):
        """PATCH metadata should broadcast a metadata_update message."""
        plot_id = server.publish({"type": "Html", "data": "<p>update bc</p>"})

        async with websockets.connect(server.ws_url) as ws:
            await _drain_history(ws)

            server.patch_metadata(plot_id, title="Patched", tags=["new"])

            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            assert data["kind"] == "metadata_update"
            assert data["id"] == plot_id
            assert data["title"] == "Patched"
            assert data["tags"] == ["new"]


async def _drain_history(ws):
    """Drain any pending history messages from a fresh WS connection."""
    while True:
        try:
            await asyncio.wait_for(ws.recv(), timeout=0.3)
        except asyncio.TimeoutError:
            break
