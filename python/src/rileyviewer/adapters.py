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
    html = _inject_animation_styles(html)
    return viewer.send_html(html)


# Custom CSS and JS to style matplotlib animation controls
_ANIMATION_STYLES = """
<style>
/* Dark theme container - fill iframe and use flex for scaling */
html, body {
    margin: 0;
    padding: 0;
    height: 100%;
    width: 100%;
    overflow: hidden;
}

body {
    background: transparent;
    padding: 16px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    align-items: center;
    font-family: system-ui, -apple-system, sans-serif;
}

/* Animation image - scale to fill available space */
.anim-state {
    display: flex;
    justify-content: center;
    align-items: center;
    flex: 1;
    min-height: 0;
    width: 100%;
}

.anim-state img {
    max-width: 100%;
    max-height: 100%;
    width: auto;
    height: auto;
    object-fit: contain;
    border-radius: 8px;
}

/* Controls container - hidden by default, show on hover */
.anim-controls {
    opacity: 0;
    transition: opacity 0.2s ease;
    background: rgba(15, 23, 42, 0.9);
    backdrop-filter: blur(8px);
    border-radius: 12px;
    padding: 12px 16px;
    margin-top: 12px;
    border: 1px solid rgba(148, 163, 184, 0.2);
}

body:hover .anim-controls {
    opacity: 1;
}

/* Slider styling */
.anim-slider {
    width: 100%;
    height: 6px;
    border-radius: 3px;
    background: #334155;
    outline: none;
    margin-bottom: 12px;
    -webkit-appearance: none;
    appearance: none;
}

.anim-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #10b981;
    cursor: pointer;
    transition: transform 0.1s;
}

.anim-slider::-webkit-slider-thumb:hover {
    transform: scale(1.2);
}

.anim-slider::-moz-range-thumb {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #10b981;
    cursor: pointer;
    border: none;
}

/* Button container */
.anim-buttons {
    display: flex;
    justify-content: center;
    gap: 4px;
    margin-bottom: 8px;
}

/* Button styling - shadcn-like */
.anim-buttons button {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #e2e8f0;
    padding: 6px 8px;
    cursor: pointer;
    transition: all 0.15s ease;
    font-size: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.anim-buttons button:hover {
    background: #334155;
    border-color: #475569;
}

.anim-buttons button:active {
    background: #475569;
}

/* Hide Font Awesome icons, show our SVG icons */
.anim-buttons button i.fa {
    display: none;
}

.anim-buttons button svg {
    width: 14px;
    height: 14px;
    stroke: #e2e8f0;
    stroke-width: 2;
    fill: none;
}

/* Loop mode form */
.anim-controls form {
    display: flex;
    justify-content: center;
    gap: 16px;
    color: #94a3b8;
    font-size: 12px;
}

.anim-controls form label {
    display: flex;
    align-items: center;
    gap: 4px;
    cursor: pointer;
}

.anim-controls form input[type="radio"] {
    accent-color: #10b981;
}
</style>
<script>
// Replace Font Awesome icons with Lucide-style SVG icons
document.addEventListener('DOMContentLoaded', function() {
    const icons = {
        'fa-minus': '<svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"/></svg>',
        'fa-plus': '<svg viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
        'fa-fast-backward': '<svg viewBox="0 0 24 24"><polygon points="11,19 2,12 11,5"/><polygon points="22,19 13,12 22,5"/></svg>',
        'fa-step-backward': '<svg viewBox="0 0 24 24"><polygon points="19,20 9,12 19,4"/><line x1="5" y1="4" x2="5" y2="20"/></svg>',
        'fa-play fa-flip-horizontal': '<svg viewBox="0 0 24 24" style="transform:scaleX(-1)"><polygon points="5,3 19,12 5,21" fill="#e2e8f0" stroke="none"/></svg>',
        'fa-pause': '<svg viewBox="0 0 24 24"><rect x="6" y="4" width="4" height="16" fill="#e2e8f0" stroke="none"/><rect x="14" y="4" width="4" height="16" fill="#e2e8f0" stroke="none"/></svg>',
        'fa-play': '<svg viewBox="0 0 24 24"><polygon points="5,3 19,12 5,21" fill="#e2e8f0" stroke="none"/></svg>',
        'fa-step-forward': '<svg viewBox="0 0 24 24"><polygon points="5,4 15,12 5,20"/><line x1="19" y1="4" x2="19" y2="20"/></svg>',
        'fa-fast-forward': '<svg viewBox="0 0 24 24"><polygon points="13,19 22,12 13,5"/><polygon points="2,19 11,12 2,5"/></svg>'
    };

    document.querySelectorAll('.anim-buttons button i.fa').forEach(function(el) {
        const classes = el.className;
        for (const [faClass, svg] of Object.entries(icons)) {
            if (classes.includes(faClass.split(' ')[0]) &&
                (faClass.split(' ').length === 1 || classes.includes(faClass.split(' ')[1] || ''))) {
                el.insertAdjacentHTML('afterend', svg);
                break;
            }
        }
    });
});
</script>
"""


def _inject_animation_styles(html: str) -> str:
    """Inject custom CSS into matplotlib animation HTML."""
    # Insert our styles right after the Font Awesome link
    if '<link rel="stylesheet"' in html:
        # Insert after the first link tag
        parts = html.split('</head>', 1)
        if len(parts) == 2:
            return parts[0] + _ANIMATION_STYLES + '</head>' + parts[1]
        # No </head>, insert after first link
        idx = html.find('>')
        if idx > 0:
            # Find end of first link tag
            link_end = html.find('>', html.find('<link'))
            if link_end > 0:
                return html[:link_end+1] + _ANIMATION_STYLES + html[link_end+1:]
    # Fallback: prepend styles
    return _ANIMATION_STYLES + html
