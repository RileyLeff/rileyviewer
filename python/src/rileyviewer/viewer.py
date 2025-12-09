from __future__ import annotations

from typing import Any, Optional

from . import adapters
from ._core import RustViewer


class Viewer:
    """Python-facing viewer that wraps the Rust backend."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        token: Optional[str] = None,
    ) -> None:
        self._inner = RustViewer(host=host, port=port, token=token)

    @property
    def addr(self) -> str:
        return self._inner.addr

    @property
    def token(self) -> Optional[str]:
        return self._inner.token

    def show(self, obj: Any) -> str:
        """Serialize a plotting object and send it to the Rust server."""
        return adapters.send_object(self._inner, obj)

    def send_png_bytes(self, data: bytes) -> str:
        return self._inner.send_png(data)

    def send_plotly_json(self, payload: str) -> str:
        return self._inner.send_plotly_json(payload)

    def send_vega_json(self, payload: str) -> str:
        return self._inner.send_vega_json(payload)

    def send_html(self, html: str) -> str:
        return self._inner.send_html(html)

    def capture(self) -> "MatplotlibContext":
        return MatplotlibContext(self)

    def shutdown(self) -> None:
        self._inner.shutdown()


class MatplotlibContext:
    """Context manager to collect matplotlib output and close figures on exit."""

    def __init__(self, viewer: Viewer) -> None:
        self.viewer = viewer

    def __enter__(self) -> "MatplotlibContext":
        return self

    def push(self) -> str:
        import matplotlib.pyplot as plt

        fig = plt.gcf()
        return self.viewer.show(fig)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        import matplotlib.pyplot as plt

        plt.close("all")
