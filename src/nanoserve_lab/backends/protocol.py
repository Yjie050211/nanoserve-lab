from collections.abc import AsyncIterator
from typing import Protocol

from ..schemas import RequestSpec, StreamEvent


class ProtocolError(Exception):
    """The received HTTP/SSE stream is not a complete supported response."""


class Backend(Protocol):
    def stream(self, request: RequestSpec) -> AsyncIterator[StreamEvent]: ...
