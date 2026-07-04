"""Byte-level fan-out of one pcap stream to two consumers.

Live mode reads a single pcap byte stream from stdin, but both the scapy RTP
parser and the tshark SIP dissector each need to own a complete copy of that
stream from byte 0. A file descriptor can't be read by two consumers, so this
module reads stdin once and duplicates every chunk to two OS pipes.

Design tradeoff — liveness over completeness: each sink has a bounded queue
drained by its own writer thread. If a consumer falls behind and its queue
fills, the reader drops the oldest chunk *for that sink only* rather than
blocking. This guarantees a slow tshark can never stall the mirror or starve
the scapy path (and vice-versa). A dropped chunk degrades that consumer's view
the way real packet loss would — which the analyzers already model — instead of
hanging the whole capture.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
from typing import BinaryIO, List, Optional

logger = logging.getLogger(__name__)

_READ_CHUNK = 65536
_SENTINEL = None  # queued to signal EOF to a writer thread


class _Sink:
    """One fan-out destination: a bounded queue feeding an OS pipe."""

    def __init__(self, name: str, max_chunks: int):
        self.name = name
        self._q: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=max_chunks)
        read_fd, write_fd = os.pipe()
        self._write_fd = write_fd
        self.reader: BinaryIO = os.fdopen(read_fd, "rb", buffering=0)
        self.dropped = 0
        self._thread = threading.Thread(
            target=self._drain, name=f"tee-{name}", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def offer(self, chunk: bytes) -> None:
        """Enqueue a chunk; drop the oldest if the queue is full (never block)."""
        try:
            self._q.put_nowait(chunk)
        except queue.Full:
            try:
                self._q.get_nowait()  # discard oldest
                self.dropped += 1
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(chunk)
            except queue.Full:
                self.dropped += 1

    def close(self) -> None:
        """Signal EOF to the writer thread."""
        try:
            self._q.put_nowait(_SENTINEL)
        except queue.Full:
            # Make room for the sentinel so the writer can finish.
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            self._q.put(_SENTINEL)

    def join(self, timeout: Optional[float] = None) -> None:
        self._thread.join(timeout)

    def _drain(self) -> None:
        """Write queued chunks to the pipe until the EOF sentinel arrives."""
        try:
            while True:
                chunk = self._q.get()
                if chunk is _SENTINEL:
                    break
                try:
                    os.write(self._write_fd, chunk)
                except (BrokenPipeError, OSError) as e:
                    logger.debug("tee sink %s: consumer closed pipe (%s)", self.name, e)
                    break
        finally:
            try:
                os.close(self._write_fd)  # clean EOF for the downstream consumer
            except OSError:
                pass


class PcapTee:
    """Read a source byte stream once and fan it out to two readers."""

    def __init__(self, src_fd: int, *, buffer_chunks: int = 256):
        """
        Args:
            src_fd: File descriptor to read the pcap stream from (e.g. a dup of
                stdin). The tee owns reading from it.
            buffer_chunks: Per-sink queue depth (chunks of up to 64 KB). Larger
                tolerates burstier slow consumers at the cost of memory.
        """
        self._src_fd = src_fd
        self._rtp = _Sink("rtp", buffer_chunks)
        self._sip = _Sink("sip", buffer_chunks)
        self._reader = threading.Thread(
            target=self._read_loop, name="tee-reader", daemon=True
        )
        self._started = False

    @property
    def rtp_reader(self) -> BinaryIO:
        """Binary read-end for the scapy RTP parser."""
        return self._rtp.reader

    @property
    def sip_reader(self) -> BinaryIO:
        """Binary read-end for the tshark SIP dissector."""
        return self._sip.reader

    def start(self) -> "PcapTee":
        if self._started:
            return self
        self._started = True
        self._rtp.start()
        self._sip.start()
        self._reader.start()
        return self

    def _read_loop(self) -> None:
        try:
            while True:
                chunk = os.read(self._src_fd, _READ_CHUNK)
                if not chunk:  # EOF
                    break
                self._rtp.offer(chunk)
                self._sip.offer(chunk)
        except OSError as e:
            logger.debug("tee reader stopped: %s", e)
        finally:
            self._rtp.close()
            self._sip.close()

    def close(self) -> None:
        """Wait for the reader and both sinks to finish."""
        if not self._started:
            return
        self._reader.join(timeout=5)
        self._rtp.join(timeout=5)
        self._sip.join(timeout=5)
        if self._rtp.dropped or self._sip.dropped:
            logger.warning(
                "tee dropped chunks under load: rtp=%d sip=%d",
                self._rtp.dropped,
                self._sip.dropped,
            )

    def __enter__(self) -> "PcapTee":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()
