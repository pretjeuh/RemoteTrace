"""Run tshark to dissect SIP+SDP from a pcap file or live byte stream.

We shell out to Wireshark's tshark rather than hand-rolling a SIP parser: it
handles the awkward parts (line folding, multipart bodies, TCP reassembly)
and is battle-tested. Each dissected frame becomes a flat ``SipFieldRecord``.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from typing import Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ASCII unit separator — safe field delimiter: SIP display names contain
# commas and spaces, so a normal separator would corrupt splitting.
FIELD_SEP = "\x1f"

# Fields requested from tshark, in order. Keep this list and _FIELD_INDEX in sync.
TSHARK_FIELDS: Tuple[str, ...] = (
    "frame.number",
    "frame.time_epoch",
    "sip.Method",
    "sip.Status-Code",
    "sip.Status-Line",
    "sip.Call-ID",
    "sip.From",
    "sip.To",
    "sip.CSeq",
    "sdp.connection_info.address",
    "sdp.media.port",
    "sdp.media.media",
    "sdp.media.format",
)

_MACOS_TSHARK = "/Applications/Wireshark.app/Contents/MacOS/tshark"


class TsharkNotFoundError(RuntimeError):
    """Raised when no usable tshark binary can be located."""


@dataclass(frozen=True)
class SipFieldRecord:
    """One tshark-dissected SIP frame, validated at the parse boundary."""

    frame_number: int
    timestamp: float
    method: Optional[str]
    status_code: Optional[int]
    status_line: Optional[str]
    call_id: str
    from_uri: str
    to_uri: str
    cseq: Optional[str]
    # SDP media, aligned lists: media_types[i]/media_addrs[i]/media_ports[i]/media_formats[i]
    media_addrs: Tuple[str, ...]
    media_ports: Tuple[int, ...]
    media_types: Tuple[str, ...]
    media_formats: Tuple[str, ...]


def find_tshark() -> str:
    """Locate a tshark binary, honoring an env override.

    Order: ``VOIP_TSHARK_PATH`` env, the standard macOS app bundle path, then
    ``tshark`` on PATH. Raises :class:`TsharkNotFoundError` if none exist.
    """
    override = os.environ.get("VOIP_TSHARK_PATH")
    if override:
        if os.path.isfile(override) and os.access(override, os.X_OK):
            return override
        raise TsharkNotFoundError(
            f"VOIP_TSHARK_PATH is set but not an executable: {override}"
        )
    if os.path.isfile(_MACOS_TSHARK) and os.access(_MACOS_TSHARK, os.X_OK):
        return _MACOS_TSHARK
    found = shutil.which("tshark")
    if found:
        return found
    raise TsharkNotFoundError(
        "tshark not found. Install Wireshark, or set VOIP_TSHARK_PATH to the "
        "tshark binary. SIP analysis is unavailable without it."
    )


def tshark_available() -> bool:
    """True when a tshark binary can be located (for graceful degradation)."""
    try:
        find_tshark()
        return True
    except TsharkNotFoundError:
        return False


def _to_int(value: str) -> Optional[int]:
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _split_multi(value: str) -> Tuple[str, ...]:
    """tshark joins repeated field occurrences with commas; split them."""
    value = value.strip()
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parse_line(line: str) -> Optional[SipFieldRecord]:
    """Parse one separator-delimited tshark line into a record, or None if invalid."""
    parts = line.rstrip("\n").split(FIELD_SEP)
    # Pad short rows (trailing empty fields get dropped by some tshark builds).
    if len(parts) < len(TSHARK_FIELDS):
        parts = parts + [""] * (len(TSHARK_FIELDS) - len(parts))

    frame_number = _to_int(parts[0])
    timestamp = parts[1].strip()
    call_id = parts[5].strip()

    # A record is only meaningful with a frame number, timestamp, and Call-ID.
    if frame_number is None or not timestamp or not call_id:
        return None
    try:
        ts = float(timestamp)
    except ValueError:
        return None

    media_addrs = _split_multi(parts[9])
    media_ports_raw = _split_multi(parts[10])
    media_types = _split_multi(parts[11])
    media_ports = tuple(p for p in (_to_int(x) for x in media_ports_raw) if p is not None)

    return SipFieldRecord(
        frame_number=frame_number,
        timestamp=ts,
        method=(parts[2].strip() or None),
        status_code=_to_int(parts[3]),
        status_line=(parts[4].strip() or None),
        call_id=call_id,
        from_uri=parts[6].strip(),
        to_uri=parts[7].strip(),
        cseq=(parts[8].strip() or None),
        media_addrs=media_addrs,
        media_ports=media_ports,
        media_types=media_types,
        media_formats=_split_multi(parts[12]),
    )


class TsharkSipSource:
    """Yield :class:`SipFieldRecord` objects from a pcap file or byte stream."""

    def __init__(self, source, *, tshark_path: Optional[str] = None):
        """
        Args:
            source: A filesystem path (str) for static analysis, or a binary
                file-like object (e.g. a pipe read-end) for live streaming.
                When a stream is given, tshark reads from stdin (``-r -``).
            tshark_path: Explicit tshark binary; auto-located when omitted.
        """
        self._tshark = tshark_path or find_tshark()
        self._source = source
        self._is_stream = not isinstance(source, (str, bytes, os.PathLike))
        self._proc: Optional[subprocess.Popen] = None
        self._stderr_thread: Optional[threading.Thread] = None

    def _build_argv(self) -> List[str]:
        read_target = "-" if self._is_stream else os.fspath(self._source)
        argv = [
            self._tshark,
            "-r",
            read_target,
        ]
        # Live streams: force line-buffered output. Without -l, tshark
        # block-buffers stdout and holds SIP records until ~1MB of pcap has
        # passed through. In a live capture dominated by RTP, sparse SIP
        # frames then never surface during a short capture, leaving the Calls
        # tab empty. File mode flushes at EOF, so it doesn't need this.
        if self._is_stream:
            argv.append("-l")
        argv += [
            "-Y",
            "sip",
            "-T",
            "fields",
            "-E",
            f"separator={FIELD_SEP}",
            "-E",
            "occurrence=a",
        ]
        for fieldname in TSHARK_FIELDS:
            argv += ["-e", fieldname]
        return argv

    def _drain_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        for raw in self._proc.stderr:
            msg = raw.decode("utf-8", "replace").rstrip()
            if msg:
                logger.debug("tshark stderr: %s", msg)

    def iter_records(self) -> Generator[SipFieldRecord, None, None]:
        """Start tshark and yield parsed SIP records until EOF."""
        argv = self._build_argv()
        logger.info("Starting tshark SIP dissection: %s", " ".join(argv[:6]) + " ...")

        stdin = self._source if self._is_stream else subprocess.DEVNULL
        self._proc = subprocess.Popen(
            argv,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

        parsed = 0
        skipped = 0
        try:
            assert self._proc.stdout is not None
            for raw in self._proc.stdout:
                line = raw.decode("utf-8", "replace")
                record = _parse_line(line)
                if record is None:
                    skipped += 1
                    continue
                parsed += 1
                yield record
        finally:
            self.close()
            logger.info(
                "tshark SIP dissection done: %d records, %d skipped", parsed, skipped
            )

    def close(self) -> None:
        """Terminate the tshark subprocess if still running."""
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
        self._proc = None

    def __enter__(self) -> "TsharkSipSource":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
