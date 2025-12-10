from __future__ import annotations

import io
import json
from typing import Any


def _extract_figure_from_axes_array(obj: Any) -> Any:
    """Extract matplotlib Figure from numpy array of Axes (e.g., from arviz/seaborn).

    Many plotting libraries (arviz, seaborn facetgrid, etc.) return numpy arrays
    of matplotlib Axes objects. All axes in such an array share a single Figure,
    so we can extract it from any element.

    Returns the Figure if obj is an array of Axes, otherwise returns None.
    """
    # Check if it's array-like with flatten (numpy array or similar)
    if not (hasattr(obj, '__array__') and hasattr(obj, 'flatten')):
        return None

    try:
        flat = obj.flatten()
        if len(flat) > 0 and hasattr(flat[0], 'get_figure'):
            return flat[0].get_figure()
    except (TypeError, IndexError, AttributeError):
        pass

    return None


def send_object(rv, obj: Any) -> str:
    """Best-effort serializer dispatch for common plotting libs."""
    # numpy array of matplotlib Axes (from arviz, seaborn, etc.)
    fig = _extract_figure_from_axes_array(obj)
    if fig is not None:
        return _send_matplotlib(rv, fig)

    # seaborn often returns an object with a .figure attr
    fig = getattr(obj, "figure", None)
    if fig is not None:
        return _send_matplotlib(rv, fig)

    # matplotlib Figure or objects exposing savefig
    if hasattr(obj, "savefig"):
        return _send_matplotlib(rv, obj)

    # plotly
    if obj.__class__.__module__.startswith("plotly") or hasattr(obj, "to_plotly_json"):
        payload = obj.to_json() if hasattr(obj, "to_json") else json.dumps(obj.to_plotly_json())
        return rv.send_plotly_json(payload)

    # altair / vega-lite
    if obj.__class__.__module__.startswith("altair") or hasattr(obj, "to_dict"):
        payload = obj.to_json() if hasattr(obj, "to_json") else json.dumps(obj.to_dict())
        return rv.send_vega_json(payload)

    # ipy/html fallback
    if hasattr(obj, "_repr_html_"):
        return rv.send_html(obj._repr_html_())

    raise TypeError(f"Don't know how to send object of type {type(obj)}")


def send_object_http(viewer, obj: Any) -> str:
    """HTTP-based serializer dispatch for client mode."""
    # numpy array of matplotlib Axes (from arviz, seaborn, etc.)
    fig = _extract_figure_from_axes_array(obj)
    if fig is not None:
        return _send_matplotlib_http(viewer, fig)

    # seaborn often returns an object with a .figure attr
    fig = getattr(obj, "figure", None)
    if fig is not None:
        return _send_matplotlib_http(viewer, fig)

    # matplotlib Figure or objects exposing savefig
    if hasattr(obj, "savefig"):
        return _send_matplotlib_http(viewer, obj)

    # plotly
    if obj.__class__.__module__.startswith("plotly") or hasattr(obj, "to_plotly_json"):
        payload = obj.to_json() if hasattr(obj, "to_json") else json.dumps(obj.to_plotly_json())
        return viewer.send_plotly_json(payload)

    # altair / vega-lite
    if obj.__class__.__module__.startswith("altair") or hasattr(obj, "to_dict"):
        payload = obj.to_json() if hasattr(obj, "to_json") else json.dumps(obj.to_dict())
        return viewer.send_vega_json(payload)

    # ipy/html fallback
    if hasattr(obj, "_repr_html_"):
        return viewer.send_html(obj._repr_html_())

    raise TypeError(f"Don't know how to send object of type {type(obj)}")


def _send_matplotlib(rv, fig: Any) -> str:
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return rv.send_png(buf.getvalue())


def _send_matplotlib_http(viewer, fig: Any) -> str:
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return viewer.send_png_bytes(buf.getvalue())
