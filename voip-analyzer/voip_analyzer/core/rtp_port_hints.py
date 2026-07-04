"""Shared registry of SDP-learned RTP ports.

SIP/SDP negotiates media on dynamic ports (e.g. 6000, 21008) that the RTP
parser's static heuristics may not recognise. The SIP analyzer registers
those ports here as it reads SDP, and the RTP parser consults the registry so
it can identify the media packets that follow. Signalling precedes media, so
the hint is in place before the RTP packets arrive.
"""

from __future__ import annotations

import threading
from typing import Set


class RtpPortHints:
    """Thread-safe set of UDP ports known to carry RTP media."""

    def __init__(self) -> None:
        self._ports: Set[int] = set()
        self._lock = threading.Lock()

    def add(self, port: int) -> None:
        if port is None:
            return
        with self._lock:
            self._ports.add(int(port))

    def contains(self, port: int) -> bool:
        with self._lock:
            return int(port) in self._ports

    def snapshot(self) -> Set[int]:
        """A copy of the current hint set (for tests/inspection)."""
        with self._lock:
            return set(self._ports)

    def clear(self) -> None:
        with self._lock:
            self._ports.clear()


_shared_hints = RtpPortHints()


def get_shared_hints() -> RtpPortHints:
    """Return the process-wide singleton hint registry."""
    return _shared_hints
