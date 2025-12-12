from __future__ import annotations

import io
import json
from typing import Any, Literal, Optional

from .exceptions import UnsupportedPlotTypeError

# Type alias for supported matplotlib output formats
MatplotlibFormat = Literal["svg", "png"]


def _is_matplotlib_animation(obj: Any) -> bool:
    """Check if obj is a matplotlib animation (FuncAnimation or ArtistAnimation)."""
    try:
        from matplotlib.animation import Animation
        return isinstance(obj, Animation)
    except ImportError:
        return False


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

    raise UnsupportedPlotTypeError(type(obj))


def send_object_http(
    viewer,
    obj: Any,
    format: Optional[MatplotlibFormat] = None,
) -> str:
    """HTTP-based serializer dispatch for client mode.

    Args:
        viewer: The Viewer instance to send to.
        obj: The plot object to serialize and send.
        format: For matplotlib figures, the output format ("svg" or "png").
                Defaults to viewer's default_format (which defaults to "svg").
    """
    # Resolve format from viewer default if not specified
    fmt = format or getattr(viewer, "_default_format", "svg")

    # matplotlib animations (FuncAnimation, ArtistAnimation)
    if _is_matplotlib_animation(obj):
        return _send_matplotlib_animation_http(viewer, obj)

    # numpy array of matplotlib Axes (from arviz, seaborn, etc.)
    fig = _extract_figure_from_axes_array(obj)
    if fig is not None:
        return _send_matplotlib_http(viewer, fig, fmt)

    # seaborn often returns an object with a .figure attr
    fig = getattr(obj, "figure", None)
    if fig is not None:
        return _send_matplotlib_http(viewer, fig, fmt)

    # matplotlib Figure or objects exposing savefig
    if hasattr(obj, "savefig"):
        return _send_matplotlib_http(viewer, obj, fmt)

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

    raise UnsupportedPlotTypeError(type(obj))


def _send_matplotlib(rv, fig: Any, format: MatplotlibFormat = "svg") -> str:
    """Send a matplotlib figure (legacy RustViewer API - kept for compatibility)."""
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format=format)
    plt.close(fig)

    if format == "svg":
        return rv.send_svg(buf.getvalue().decode("utf-8"))
    else:
        return rv.send_png(buf.getvalue())


def _send_matplotlib_http(viewer, fig: Any, format: MatplotlibFormat = "svg") -> str:
    """Send a matplotlib figure via HTTP."""
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format=format)
    plt.close(fig)

    if format == "svg":
        return viewer.send_svg(buf.getvalue().decode("utf-8"))
    else:
        return viewer.send_png_bytes(buf.getvalue())


def _send_matplotlib_animation_http(viewer, anim: Any) -> str:
    """Send a matplotlib animation as interactive HTML via to_jshtml()."""
    html = anim.to_jshtml()
    return viewer.send_html(html)
