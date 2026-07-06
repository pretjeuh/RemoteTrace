"""Tests for TsharkSipSource argv construction.

The stream path must pass ``-l`` (line-buffered output) so tshark flushes SIP
records as they arrive. Without it, tshark block-buffers stdout and live SIP
frames never surface during a short RTP-dominated capture. File mode must NOT
add ``-l`` (it flushes at EOF and the flag is unnecessary there).
"""

import io

from voip_analyzer.core.tshark_runner import TsharkSipSource

# A path that will never be probed by find_tshark's PATH lookup; we only build
# argv, we never spawn the process, so the binary need not exist.
_FAKE_TSHARK = "/usr/bin/tshark"


def test_stream_source_uses_line_buffered_output():
    """A file-like source (live pipe) forces ``-l`` for immediate flushing."""
    stream = io.BytesIO(b"")
    source = TsharkSipSource(stream, tshark_path=_FAKE_TSHARK)

    argv = source._build_argv()

    assert "-l" in argv
    # -l must come before the display filter so it applies to the read.
    assert argv.index("-l") < argv.index("-Y")
    # Stream reads from stdin.
    assert argv[argv.index("-r") + 1] == "-"


def test_file_source_omits_line_buffering():
    """A filesystem path flushes at EOF; ``-l`` is not added."""
    source = TsharkSipSource("/tmp/capture.pcap", tshark_path=_FAKE_TSHARK)

    argv = source._build_argv()

    assert "-l" not in argv
    assert argv[argv.index("-r") + 1] == "/tmp/capture.pcap"
