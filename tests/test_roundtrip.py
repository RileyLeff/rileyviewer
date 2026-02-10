"""End-to-end round-trip tests: publish via Python → verify content over WebSocket.

Each test publishes a specific content type, then connects via WebSocket
and verifies the exact content arrives intact through the full pipeline.
"""

from __future__ import annotations

import asyncio
import base64
import json

import pytest
import websockets


class TestRoundTripSvg:
    @pytest.mark.asyncio
    async def test_svg_roundtrip(self, server):
        svg_data = '<svg xmlns="http://www.w3.org/2000/svg"><circle r="50"/></svg>'
        async with websockets.connect(server.ws_url) as ws:
            await _drain(ws)
            plot_id = server.publish({"type": "Svg", "data": svg_data})
            msg = await _recv_by_id(ws, plot_id)
            assert msg["content"]["type"] == "Svg"
            assert msg["content"]["data"] == svg_data


class TestRoundTripPng:
    @pytest.mark.asyncio
    async def test_png_roundtrip(self, server):
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
            b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
            b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        encoded = base64.b64encode(png_bytes).decode("ascii")
        async with websockets.connect(server.ws_url) as ws:
            await _drain(ws)
            plot_id = server.publish({"type": "Png", "data": encoded})
            msg = await _recv_by_id(ws, plot_id)
            assert msg["content"]["type"] == "Png"
            # Verify data survives the round trip intact
            received_bytes = base64.b64decode(msg["content"]["data"])
            assert received_bytes == png_bytes


class TestRoundTripPlotly:
    @pytest.mark.asyncio
    async def test_plotly_roundtrip(self, server):
        plotly_spec = {"data": [{"x": [1, 2, 3], "y": [4, 5, 6], "type": "scatter"}]}
        payload = json.dumps(plotly_spec)
        async with websockets.connect(server.ws_url) as ws:
            await _drain(ws)
            plot_id = server.publish({"type": "Plotly", "data": payload})
            msg = await _recv_by_id(ws, plot_id)
            assert msg["content"]["type"] == "Plotly"
            received_spec = json.loads(msg["content"]["data"])
            assert received_spec == plotly_spec


class TestRoundTripVega:
    @pytest.mark.asyncio
    async def test_vega_roundtrip(self, server):
        vega_spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "data": {"values": [{"x": 1, "y": 2}]},
            "mark": "point",
        }
        payload = json.dumps(vega_spec)
        async with websockets.connect(server.ws_url) as ws:
            await _drain(ws)
            plot_id = server.publish({"type": "Vega", "data": payload})
            msg = await _recv_by_id(ws, plot_id)
            assert msg["content"]["type"] == "Vega"
            received_spec = json.loads(msg["content"]["data"])
            assert received_spec == vega_spec


class TestRoundTripHtml:
    @pytest.mark.asyncio
    async def test_html_roundtrip(self, server):
        html = "<h1>Round trip test</h1><p>Hello &amp; world</p>"
        async with websockets.connect(server.ws_url) as ws:
            await _drain(ws)
            plot_id = server.publish({"type": "Html", "data": html})
            msg = await _recv_by_id(ws, plot_id)
            assert msg["content"]["type"] == "Html"
            assert msg["content"]["data"] == html


class TestRoundTripCsv:
    @pytest.mark.asyncio
    async def test_csv_roundtrip(self, server):
        csv_data = "name,age,city\nalice,30,nyc\nbob,25,sf\n"
        async with websockets.connect(server.ws_url) as ws:
            await _drain(ws)
            plot_id = server.publish({"type": "Csv", "data": csv_data})
            msg = await _recv_by_id(ws, plot_id)
            assert msg["content"]["type"] == "Csv"
            assert msg["content"]["data"] == csv_data


class TestRoundTripArrowIpc:
    @pytest.mark.asyncio
    async def test_arrow_ipc_roundtrip(self, server):
        import pyarrow as pa
        import pyarrow.ipc
        import io

        table = pa.table({"x": [1, 2, 3], "y": ["a", "b", "c"]})
        sink = io.BytesIO()
        writer = pa.ipc.new_stream(sink, table.schema)
        writer.write_table(table)
        writer.close()
        original_bytes = sink.getvalue()
        encoded = base64.b64encode(original_bytes).decode("ascii")

        async with websockets.connect(server.ws_url) as ws:
            await _drain(ws)
            plot_id = server.publish({"type": "ArrowIpc", "data": encoded})
            msg = await _recv_by_id(ws, plot_id)
            assert msg["content"]["type"] == "ArrowIpc"
            received_bytes = base64.b64decode(msg["content"]["data"])
            assert received_bytes == original_bytes

            # Verify the Arrow data is still parseable
            received_table = pa.ipc.open_stream(received_bytes).read_all()
            assert received_table.num_rows == 3
            assert received_table.column("x").to_pylist() == [1, 2, 3]
            assert received_table.column("y").to_pylist() == ["a", "b", "c"]


class TestRoundTripViaPython:
    """Tests using the Python Viewer class for the full client → server → WS path."""

    @pytest.mark.asyncio
    async def test_matplotlib_figure_roundtrip(self, server):
        import sys
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "python" / "src"))
        from rileyviewer import Viewer

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        v = Viewer(host=server.host, port=server.port, token=server.token)
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [10, 20, 30])
        ax.set_title("roundtrip test")

        async with websockets.connect(server.ws_url) as ws:
            await _drain(ws)
            plot_id = v.show(fig)
            msg = await _recv_by_id(ws, plot_id)
            assert msg["content"]["type"] == "Svg"
            assert "<svg" in msg["content"]["data"]

        plt.close(fig)

    @pytest.mark.asyncio
    async def test_pandas_dataframe_roundtrip(self, server):
        import sys
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "python" / "src"))
        from rileyviewer import Viewer
        import pandas as pd
        import pyarrow as pa
        import pyarrow.ipc

        v = Viewer(host=server.host, port=server.port, token=server.token)
        df = pd.DataFrame({"col_a": [10, 20, 30], "col_b": ["x", "y", "z"]})

        async with websockets.connect(server.ws_url) as ws:
            await _drain(ws)
            plot_id = v.show(df)
            msg = await _recv_by_id(ws, plot_id)
            assert msg["content"]["type"] == "ArrowIpc"

            # Decode and verify the DataFrame survived
            received_bytes = base64.b64decode(msg["content"]["data"])
            table = pa.ipc.open_stream(received_bytes).read_all()
            assert table.num_rows == 3
            assert table.column("col_a").to_pylist() == [10, 20, 30]
            assert table.column("col_b").to_pylist() == ["x", "y", "z"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _drain(ws: websockets.ClientConnection) -> None:
    """Drain all pending history messages."""
    while True:
        try:
            await asyncio.wait_for(ws.recv(), timeout=0.5)
        except asyncio.TimeoutError:
            break


async def _recv_by_id(ws: websockets.ClientConnection, plot_id: str, timeout: float = 5.0) -> dict:
    """Receive messages until we find one matching plot_id."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        remaining = deadline - asyncio.get_event_loop().time()
        raw = await asyncio.wait_for(ws.recv(), timeout=max(remaining, 0.1))
        msg = json.loads(raw)
        if msg.get("id") == plot_id:
            return msg
    raise TimeoutError(f"Did not receive plot {plot_id} within {timeout}s")
