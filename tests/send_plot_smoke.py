#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "matplotlib",
#   "websockets>=12.0",
# ]
# ///
"""
Smoke test: start a Viewer, send a matplotlib plot, and verify it arrives over WS.

Run after `uv run maturin develop` in the repo root:
    uv run tests/send_plot_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import websockets  # noqa: E402
from rileyviewer import Viewer  # noqa: E402


async def main() -> None:
    viewer = Viewer(host="127.0.0.1", port=0)
    addr = viewer.addr
    token = viewer.token
    ws_url = f"ws://{addr}/ws"
    if token:
        ws_url += f"?token={token}"

    try:
        plot_id = send_test_plot(viewer)

        async with websockets.connect(ws_url) as ws:
            msg = await wait_for_plot(ws, plot_id)

        assert msg["id"] == plot_id, f"expected {plot_id}, got {msg['id']}"
        assert msg["content"]["type"] == "Png", f"unexpected type {msg['content']['type']}"
        print("OK", msg["id"])
    finally:
        viewer.shutdown()


def send_test_plot(viewer: Viewer) -> str:
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [0, 1, 0])
    ax.set_title("rileyviewer smoke")
    return viewer.show(fig)


async def wait_for_plot(ws: websockets.WebSocketClientProtocol, plot_id: str) -> dict[str, Any]:
    for _ in range(8):  # small history window
        raw = await ws.recv()
        msg: dict[str, Any] = json.loads(raw)
        if msg.get("id") == plot_id:
            return msg
    raise RuntimeError(f"did not receive plot {plot_id}")


if __name__ == "__main__":
    # Avoid matplotlib writing to HOME in some CI contexts
    os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.getcwd(), ".mplconfig"))
    asyncio.run(main())
