"""Tests for the adapter type-detection and serialization logic in adapters.py.

Uses mock objects to test detection paths without requiring heavy optional
dependencies (plotly, altair, polars). Real matplotlib + pandas tests use
actual libraries since they're in dev deps.
"""

from __future__ import annotations

import io
import json
import sys
import unittest.mock as mock
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "python" / "src"))

from rileyviewer.adapters import (
    _extract_figure_from_axes_array,
    _is_matplotlib_animation,
    _send_dataframe_http,
    send_object_http,
)
from rileyviewer.exceptions import UnsupportedPlotTypeError


# ---------------------------------------------------------------------------
# Helpers: fake viewer that records calls
# ---------------------------------------------------------------------------


class FakeViewer:
    """Captures send_* calls for assertion."""

    def __init__(self, default_format="svg"):
        self._default_format = default_format
        self.calls: list[tuple[str, Any]] = []

    def _record(self, method: str, data: Any) -> str:
        self.calls.append((method, data))
        return "fake-id"

    def send_svg(self, svg: str) -> str:
        return self._record("send_svg", svg)

    def send_png_bytes(self, data: bytes) -> str:
        return self._record("send_png_bytes", data)

    def send_html(self, html: str) -> str:
        return self._record("send_html", html)

    def send_plotly_json(self, payload: str) -> str:
        return self._record("send_plotly_json", payload)

    def send_vega_json(self, payload: str) -> str:
        return self._record("send_vega_json", payload)

    def send_arrow_ipc(self, data: bytes) -> str:
        return self._record("send_arrow_ipc", data)

    def send_csv(self, csv_text: str) -> str:
        return self._record("send_csv", csv_text)


# ---------------------------------------------------------------------------
# matplotlib Figure detection
# ---------------------------------------------------------------------------


class TestMatplotlibFigure:
    def test_sends_svg_by_default(self, server):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        v = FakeViewer(default_format="svg")
        fig, ax = plt.subplots()
        ax.plot([1, 2])
        send_object_http(v, fig)
        assert len(v.calls) == 1
        assert v.calls[0][0] == "send_svg"
        assert "<svg" in v.calls[0][1]
        plt.close(fig)

    def test_sends_png_when_requested(self, server):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        v = FakeViewer(default_format="png")
        fig, ax = plt.subplots()
        ax.plot([1, 2])
        send_object_http(v, fig)
        assert v.calls[0][0] == "send_png_bytes"
        assert v.calls[0][1][:4] == b"\x89PNG"
        plt.close(fig)

    def test_format_override(self, server):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        v = FakeViewer(default_format="svg")
        fig, ax = plt.subplots()
        send_object_http(v, fig, format="png")
        assert v.calls[0][0] == "send_png_bytes"
        plt.close(fig)


# ---------------------------------------------------------------------------
# matplotlib Animation detection
# ---------------------------------------------------------------------------


class TestMatplotlibAnimation:
    def test_is_matplotlib_animation(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.animation import FuncAnimation
        import numpy as np

        fig, ax = plt.subplots()
        line, = ax.plot([], [])

        def init():
            line.set_data([], [])
            return (line,)

        def update(frame):
            line.set_data([0, 1], [0, frame])
            return (line,)

        anim = FuncAnimation(fig, update, frames=range(3), init_func=init, blit=True)
        assert _is_matplotlib_animation(anim) is True
        assert _is_matplotlib_animation(fig) is False
        assert _is_matplotlib_animation("string") is False
        plt.close(fig)

    def test_animation_sends_html(self, server):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.animation import FuncAnimation

        fig, ax = plt.subplots()
        line, = ax.plot([], [])
        anim = FuncAnimation(fig, lambda f: (line,), frames=range(2), blit=True)

        v = FakeViewer()
        send_object_http(v, anim)
        assert v.calls[0][0] == "send_html"
        # Should contain injected styles
        assert "<style>" in v.calls[0][1]
        plt.close(fig)


# ---------------------------------------------------------------------------
# Numpy array of Axes (arviz/seaborn pattern)
# ---------------------------------------------------------------------------


class TestAxesArrayDetection:
    def test_extracts_figure_from_axes_array(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        fig, axes = plt.subplots(2, 2)
        assert isinstance(axes, np.ndarray)
        extracted = _extract_figure_from_axes_array(axes)
        assert extracted is fig
        plt.close(fig)

    def test_returns_none_for_non_axes_array(self):
        import numpy as np
        arr = np.array([1, 2, 3])
        assert _extract_figure_from_axes_array(arr) is None

    def test_returns_none_for_non_array(self):
        assert _extract_figure_from_axes_array("not an array") is None
        assert _extract_figure_from_axes_array(42) is None

    def test_axes_array_sends_svg(self, server):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3)
        import numpy as np
        axes_arr = np.array(axes)

        v = FakeViewer()
        send_object_http(v, axes_arr)
        assert v.calls[0][0] == "send_svg"
        plt.close(fig)


# ---------------------------------------------------------------------------
# Seaborn .figure attribute
# ---------------------------------------------------------------------------


class TestFigureAttribute:
    def test_object_with_figure_attr(self, server):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        ax.plot([1, 2, 3])

        # Simulate seaborn FacetGrid or similar
        class FakeGrid:
            def __init__(self, fig):
                self.figure = fig

        grid = FakeGrid(fig)
        v = FakeViewer()
        send_object_http(v, grid)
        assert v.calls[0][0] == "send_svg"
        plt.close(fig)


# ---------------------------------------------------------------------------
# Plotly detection (mock — no plotly dependency needed)
# ---------------------------------------------------------------------------


class TestPlotlyDetection:
    def test_plotly_via_module_name(self, server):
        # Use spec=[] to avoid MagicMock auto-generating savefig/figure attrs
        mock_fig = MagicMock(spec=[])
        mock_fig.__class__ = type("Figure", (), {"__module__": "plotly.graph_objs._figure"})
        mock_fig.to_json = MagicMock(return_value='{"data":[]}')

        v = FakeViewer()
        send_object_http(v, mock_fig)
        assert v.calls[0][0] == "send_plotly_json"
        assert v.calls[0][1] == '{"data":[]}'

    def test_plotly_via_to_plotly_json(self, server):
        # Object that has to_plotly_json but not plotly module
        mock_fig = MagicMock(spec=[])
        mock_fig.__class__ = type("CustomPlotly", (), {"__module__": "mylib"})
        mock_fig.to_plotly_json = MagicMock(return_value={"data": [{"x": [1]}]})
        # Needs to not have savefig, figure, __array__
        del mock_fig.savefig
        del mock_fig.figure
        del mock_fig.__array__
        # But must have to_plotly_json
        mock_fig.to_plotly_json = MagicMock(return_value={"data": [{"x": [1]}]})

        v = FakeViewer()
        send_object_http(v, mock_fig)
        assert v.calls[0][0] == "send_plotly_json"


# ---------------------------------------------------------------------------
# Altair / Vega-Lite detection (mock)
# ---------------------------------------------------------------------------


class TestAltairDetection:
    def test_altair_via_module_name(self, server):
        mock_chart = MagicMock(spec=[])
        mock_chart.__class__ = type("Chart", (), {"__module__": "altair.vegalite.v5.api"})
        mock_chart.to_json = MagicMock(return_value='{"$schema":"vega-lite"}')

        v = FakeViewer()
        send_object_http(v, mock_chart)
        assert v.calls[0][0] == "send_vega_json"
        assert v.calls[0][1] == '{"$schema":"vega-lite"}'


# ---------------------------------------------------------------------------
# pandas DataFrame
# ---------------------------------------------------------------------------


class TestPandasDataFrame:
    def test_pandas_sends_arrow_ipc(self, server):
        import pandas as pd

        v = FakeViewer()
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        send_object_http(v, df)
        assert v.calls[0][0] == "send_arrow_ipc"
        # Should be valid Arrow IPC bytes
        data = v.calls[0][1]
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_pandas_csv_fallback_when_no_pyarrow(self, server):
        import pandas as pd

        v = FakeViewer()
        df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})

        # Mock pyarrow import to fail
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name.startswith("pyarrow"):
                raise ImportError("mocked")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            _send_dataframe_http(v, df)

        assert v.calls[0][0] == "send_csv"
        csv_text = v.calls[0][1]
        assert "x,y" in csv_text
        assert "1,3" in csv_text


# ---------------------------------------------------------------------------
# polars DataFrame (mock — no polars dependency needed)
# ---------------------------------------------------------------------------


class TestPolarsDetection:
    def test_polars_dataframe_detected(self, server):
        import pyarrow as pa

        # Use spec=[] so MagicMock doesn't auto-generate savefig/figure attrs
        mock_df = MagicMock(spec=[])
        mock_df.__class__ = type("DataFrame", (), {"__module__": "polars.dataframe.frame"})
        mock_df.to_arrow = MagicMock(return_value=pa.table({"col": [1, 2, 3]}))

        v = FakeViewer()
        send_object_http(v, mock_df)
        assert v.calls[0][0] == "send_arrow_ipc"

    def test_polars_lazyframe_collected(self, server):
        import pyarrow as pa

        mock_lazy = MagicMock(spec=[])
        mock_lazy.__class__ = type("LazyFrame", (), {"__module__": "polars.lazyframe.frame"})

        mock_collected = MagicMock(spec=[])
        mock_collected.__class__ = type("DataFrame", (), {"__module__": "polars.dataframe.frame"})
        mock_collected.to_arrow = MagicMock(return_value=pa.table({"z": [10]}))

        mock_lazy.collect = MagicMock(return_value=mock_collected)
        mock_lazy.to_arrow = MagicMock(return_value=pa.table({"z": [10]}))

        v = FakeViewer()
        send_object_http(v, mock_lazy)
        assert v.calls[0][0] == "send_arrow_ipc"

    def test_polars_csv_fallback(self, server):
        # Mock polars DataFrame without pyarrow
        mock_df = MagicMock(spec=[])
        mock_df.__class__ = type("DataFrame", (), {"__module__": "polars.dataframe.frame"})
        mock_df.to_arrow = MagicMock()  # needed for detection
        mock_df.write_csv = MagicMock(return_value="a,b\n1,2\n")

        v = FakeViewer()

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name.startswith("pyarrow"):
                raise ImportError("mocked")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            _send_dataframe_http(v, mock_df)

        assert v.calls[0][0] == "send_csv"
        assert v.calls[0][1] == "a,b\n1,2\n"


# ---------------------------------------------------------------------------
# _repr_html_ fallback
# ---------------------------------------------------------------------------


class TestReprHtmlFallback:
    def test_repr_html_used(self, server):
        class HtmlWidget:
            def _repr_html_(self):
                return "<div>widget</div>"

        v = FakeViewer()
        send_object_http(v, HtmlWidget())
        assert v.calls[0][0] == "send_html"
        assert v.calls[0][1] == "<div>widget</div>"


# ---------------------------------------------------------------------------
# Unsupported type
# ---------------------------------------------------------------------------


class TestUnsupportedType:
    def test_raises_for_unknown_type(self, server):
        v = FakeViewer()
        with pytest.raises(UnsupportedPlotTypeError):
            send_object_http(v, 42)

    def test_raises_for_string(self, server):
        v = FakeViewer()
        with pytest.raises(UnsupportedPlotTypeError):
            send_object_http(v, "hello")

    def test_raises_for_dict(self, server):
        v = FakeViewer()
        with pytest.raises(UnsupportedPlotTypeError):
            send_object_http(v, {"key": "value"})
