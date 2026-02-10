"""Integration tests for WebSocket broadcast and history."""

from __future__ import annotations

import asyncio
import json

import pytest
import websockets


class TestWebSocketConnection:
    @pytest.mark.asyncio
    async def test_connect_with_valid_token(self, server):
        async with websockets.connect(server.ws_url) as ws:
            # Just verify the connection succeeded (no exception thrown)
            await ws.ping()

    @pytest.mark.asyncio
    async def test_connect_without_token_rejected(self, server):
        url = f"ws://{server.host}:{server.port}/ws"
        with pytest.raises(websockets.exceptions.InvalidStatus) as exc_info:
            async with websockets.connect(url):
                pass
        assert exc_info.value.response.status_code == 401

    @pytest.mark.asyncio
    async def test_connect_with_wrong_token_rejected(self, server):
        url = f"ws://{server.host}:{server.port}/ws?token=wrong"
        with pytest.raises(websockets.exceptions.InvalidStatus) as exc_info:
            async with websockets.connect(url):
                pass
        assert exc_info.value.response.status_code == 401


class TestWebSocketBroadcast:
    @pytest.mark.asyncio
    async def test_receives_published_plot(self, server):
        async with websockets.connect(server.ws_url) as ws:
            # Drain any history messages first
            await _drain_history(ws)

            # Publish a new plot
            plot_id = server.publish({"type": "Html", "data": "<p>ws test</p>"})

            # Should receive it over the WebSocket
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            assert data["id"] == plot_id
            assert data["content"]["type"] == "Html"
            assert data["content"]["data"] == "<p>ws test</p>"

    @pytest.mark.asyncio
    async def test_multiple_clients_receive_same_plot(self, server):
        async with (
            websockets.connect(server.ws_url) as ws1,
            websockets.connect(server.ws_url) as ws2,
        ):
            await _drain_history(ws1)
            await _drain_history(ws2)

            plot_id = server.publish({"type": "Csv", "data": "x\n1\n2"})

            msg1 = json.loads(await asyncio.wait_for(ws1.recv(), timeout=5))
            msg2 = json.loads(await asyncio.wait_for(ws2.recv(), timeout=5))
            assert msg1["id"] == plot_id
            assert msg2["id"] == plot_id

    @pytest.mark.asyncio
    async def test_receives_multiple_plots_in_order(self, server):
        async with websockets.connect(server.ws_url) as ws:
            await _drain_history(ws)

            ids = []
            for i in range(5):
                ids.append(server.publish({"type": "Html", "data": f"<p>{i}</p>"}))

            received = []
            for _ in range(5):
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                received.append(msg["id"])

            assert received == ids


class TestWebSocketHistory:
    @pytest.mark.asyncio
    async def test_new_client_receives_history(self, server):
        # Publish something first
        plot_id = server.publish({"type": "Svg", "data": "<svg>history</svg>"})

        # New client should receive it as history
        async with websockets.connect(server.ws_url) as ws:
            found = False
            for _ in range(100):  # history limit is 50
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2)
                    data = json.loads(msg)
                    if data["id"] == plot_id:
                        found = True
                        break
                except asyncio.TimeoutError:
                    break
            assert found, f"Plot {plot_id} not found in history"


async def _drain_history(ws: websockets.WebSocketClientProtocol) -> list[dict]:
    """Read all history messages (sent immediately on connect)."""
    messages = []
    while True:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
            messages.append(json.loads(msg))
        except asyncio.TimeoutError:
            break
    return messages
