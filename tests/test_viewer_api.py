"""Integration tests for the Python Viewer API."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

# Ensure the Python package is importable
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "python" / "src"))

from rileyviewer import Viewer
from rileyviewer.exceptions import ServerNotRunningError, UnsupportedPlotTypeError


class TestViewerConnect:
    def test_connects_to_running_server(self, server):
        v = Viewer(host=server.host, port=server.port, token=server.token)
        assert v.addr == server.addr

    def test_raises_when_no_server(self):
        with pytest.raises(ServerNotRunningError):
            Viewer(host="127.0.0.1", port=1, token="x")


class TestViewerSendRaw:
    def test_send_svg(self, server):
        v = Viewer(host=server.host, port=server.port, token=server.token)
        plot_id = v.send_svg("<svg>test</svg>")
        assert isinstance(plot_id, str)

    def test_send_html(self, server):
        v = Viewer(host=server.host, port=server.port, token=server.token)
        plot_id = v.send_html("<h1>hello</h1>")
        assert isinstance(plot_id, str)

    def test_send_plotly_json(self, server):
        v = Viewer(host=server.host, port=server.port, token=server.token)
        payload = json.dumps({"data": [{"x": [1], "y": [2], "type": "scatter"}]})
        plot_id = v.send_plotly_json(payload)
        assert isinstance(plot_id, str)

    def test_send_vega_json(self, server):
        v = Viewer(host=server.host, port=server.port, token=server.token)
        payload = json.dumps({"$schema": "https://vega.github.io/schema/vega-lite/v5.json"})
        plot_id = v.send_vega_json(payload)
        assert isinstance(plot_id, str)

    def test_send_csv(self, server):
        v = Viewer(host=server.host, port=server.port, token=server.token)
        plot_id = v.send_csv("a,b\n1,2\n3,4")
        assert isinstance(plot_id, str)

    def test_send_arrow_ipc(self, server):
        import pyarrow as pa
        import pyarrow.ipc
        import io

        v = Viewer(host=server.host, port=server.port, token=server.token)
        table = pa.table({"col1": [1, 2], "col2": ["a", "b"]})
        sink = io.BytesIO()
        writer = pa.ipc.new_stream(sink, table.schema)
        writer.write_table(table)
        writer.close()
        plot_id = v.send_arrow_ipc(sink.getvalue())
        assert isinstance(plot_id, str)

    def test_send_png_bytes(self, server):
        v = Viewer(host=server.host, port=server.port, token=server.token)
        # Minimal valid PNG
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
            b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
            b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        plot_id = v.send_png_bytes(png)
        assert isinstance(plot_id, str)


class TestViewerShow:
    def test_show_matplotlib_figure(self, server):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        v = Viewer(host=server.host, port=server.port, token=server.token)
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [4, 5, 6])
        plot_id = v.show(fig)
        assert isinstance(plot_id, str)
        plt.close(fig)

    def test_show_matplotlib_as_png(self, server):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        v = Viewer(host=server.host, port=server.port, token=server.token, default_format="png")
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3])
        plot_id = v.show(fig)
        assert isinstance(plot_id, str)
        plt.close(fig)

    def test_show_pandas_dataframe(self, server):
        pytest.importorskip("pandas")
        import pandas as pd

        v = Viewer(host=server.host, port=server.port, token=server.token)
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4.0, 5.0, 6.0]})
        plot_id = v.show(df)
        assert isinstance(plot_id, str)

    def test_show_unsupported_type_raises(self, server):
        v = Viewer(host=server.host, port=server.port, token=server.token)
        with pytest.raises(UnsupportedPlotTypeError):
            v.show("just a string")


class TestViewerCapture:
    def test_capture_context_manager(self, server):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        v = Viewer(host=server.host, port=server.port, token=server.token)
        with v.capture() as ctx:
            plt.plot([1, 2, 3])
            plot_id = ctx.push()
            assert isinstance(plot_id, str)
        # Figure should be closed after context exit
