"""Tests for DELETE endpoints: single plot deletion and clear all."""

from __future__ import annotations

import asyncio
import json
import urllib.request
import urllib.error

import pytest
import websockets


SVG_CONTENT = {"type": "Svg", "data": "<svg></svg>"}


class TestDeletePlot:
    def test_delete_existing_plot(self, server):
        plot_id = server.publish(SVG_CONTENT)
        status = server.delete_plot(plot_id)
        assert status == 200

    def test_delete_nonexistent_returns_404(self, server):
        status = server.delete_plot("nonexistent-id")
        assert status == 404

    def test_delete_without_token_returns_401(self, server):
        plot_id = server.publish(SVG_CONTENT)
        payload = json.dumps({}).encode()
        url = f"{server.base_url}/api/plots/{plot_id}"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req, timeout=5):
                pytest.fail("Expected 401")
        except urllib.error.HTTPError as e:
            assert e.code == 401

    def test_delete_with_wrong_token_returns_401(self, server):
        plot_id = server.publish(SVG_CONTENT)
        payload = json.dumps({"token": "wrong-token"}).encode()
        url = f"{server.base_url}/api/plots/{plot_id}"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req, timeout=5):
                pytest.fail("Expected 401")
        except urllib.error.HTTPError as e:
            assert e.code == 401


class TestDeletedNotInHistory:
    @pytest.mark.asyncio
    async def test_deleted_plot_absent_from_history(self, server):
        plot_id = server.publish(SVG_CONTENT, title="to-delete")
        server.delete_plot(plot_id)

        async with websockets.connect(server.ws_url) as ws:
            history = []
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    history.append(json.loads(msg))
                except asyncio.TimeoutError:
                    break

            ids = [m["id"] for m in history if "id" in m and m.get("kind") is None]
            assert plot_id not in ids


class TestDeleteBroadcast:
    @pytest.mark.asyncio
    async def test_delete_broadcasts_to_ws(self, server):
        plot_id = server.publish(SVG_CONTENT)

        async with websockets.connect(server.ws_url) as ws:
            # Drain history
            while True:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    break

            server.delete_plot(plot_id)

            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            parsed = json.loads(msg)
            assert parsed["kind"] == "delete"
            assert parsed["id"] == plot_id


class TestClearAll:
    def test_clear_removes_all_plots(self, server):
        server.publish(SVG_CONTENT, title="a")
        server.publish(SVG_CONTENT, title="b")
        status = server.clear_plots()
        assert status == 200

    @pytest.mark.asyncio
    async def test_clear_leaves_empty_history(self, server):
        server.publish(SVG_CONTENT, title="c")
        server.clear_plots()

        async with websockets.connect(server.ws_url) as ws:
            history = []
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    history.append(json.loads(msg))
                except asyncio.TimeoutError:
                    break

            plot_msgs = [m for m in history if m.get("kind") is None]
            assert len(plot_msgs) == 0

    def test_clear_without_token_returns_401(self, server):
        payload = json.dumps({}).encode()
        url = f"{server.base_url}/api/plots"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req, timeout=5):
                pytest.fail("Expected 401")
        except urllib.error.HTTPError as e:
            assert e.code == 401

    def test_clear_with_wrong_token_returns_401(self, server):
        payload = json.dumps({"token": "wrong-token"}).encode()
        url = f"{server.base_url}/api/plots"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req, timeout=5):
                pytest.fail("Expected 401")
        except urllib.error.HTTPError as e:
            assert e.code == 401


class TestClearBroadcast:
    @pytest.mark.asyncio
    async def test_clear_broadcasts_to_ws(self, server):
        server.publish(SVG_CONTENT)

        async with websockets.connect(server.ws_url) as ws:
            # Drain history
            while True:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    break

            server.clear_plots()

            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            parsed = json.loads(msg)
            assert parsed["kind"] == "clear"
