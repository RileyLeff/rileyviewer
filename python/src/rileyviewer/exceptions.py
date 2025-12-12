"""Custom exceptions for rileyviewer."""

from __future__ import annotations


class RileyViewerError(Exception):
    """Base exception for all rileyviewer errors."""

    pass


class ServerConnectionError(RileyViewerError):
    """Failed to connect to or communicate with the rileyviewer server."""

    pass


class ServerStartError(RileyViewerError):
    """Failed to start the rileyviewer server."""

    pass


class CLINotFoundError(RileyViewerError):
    """The rileyviewer CLI binary was not found."""

    def __init__(self) -> None:
        super().__init__(
            "rileyviewer CLI not found. Install via one of:\n"
            "  pip install rileyviewer        # includes CLI (coming soon)\n"
            "  brew install rileyleff/tap/rileyviewer\n"
            "  cargo install rileyviewer"
        )


class SerializationError(RileyViewerError):
    """Failed to serialize a plot object for transmission."""

    pass


class UnsupportedPlotTypeError(SerializationError):
    """The plot object type is not supported."""

    def __init__(self, obj_type: type) -> None:
        self.obj_type = obj_type
        super().__init__(f"Don't know how to send object of type {obj_type.__name__}")
