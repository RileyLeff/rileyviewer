from __future__ import annotations

import io
import json
from typing import Any


def send_object(rv, obj: Any) -> str:
    """Best-effort serializer dispatch for common plotting libs."""
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


def _send_matplotlib(rv, fig: Any) -> str:
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return rv.send_png(buf.getvalue())
