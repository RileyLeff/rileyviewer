"""Custom exceptions for rileyviewer."""

from __future__ import annotations


class RileyViewerError(Exception):
    """Base exception for all rileyviewer errors."""

    pass


class ServerConnectionError(RileyViewerError):
    """Failed to connect to or communicate with the rileyviewer server."""

    pass


class ServerNotRunningError(RileyViewerError):
    """The rileyviewer server is not running on the specified host:port."""

    def __init__(self, host: str, port: int) -> None:
        super().__init__(
            f"RileyViewer server is not running on {host}:{port}.\n\n"
            "Start the server with:\n"
            "  rileyviewer serve\n\n"
            "Install the server:\n"
            "  macOS:   brew install rileyleff/tap/rileyviewer\n"
            "  cargo:   cargo install rileyviewer\n"
            "  binary:  https://github.com/rileyleff/rileyviewer/releases"
        )


class SerializationError(RileyViewerError):
    """Failed to serialize a plot object for transmission."""

    pass


class UnsupportedPlotTypeError(SerializationError):
    """The plot object type is not supported."""

    def __init__(self, obj_type: type) -> None:
        self.obj_type = obj_type
        super().__init__(f"Don't know how to send object of type {obj_type.__name__}")
