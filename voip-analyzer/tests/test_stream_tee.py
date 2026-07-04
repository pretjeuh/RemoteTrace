"""Tests for the live pcap fan-out tee.

The critical properties: both readers get a byte-identical copy of the source,
and a slow consumer never stalls the other or the reader.
"""

import os
import threading
import time

from voip_analyzer.core.stream_tee import PcapTee


def _feed_fd(data: bytes):
    """Return a read fd that yields ``data`` then EOF (via an os.pipe)."""
    r, w = os.pipe()

    def _write():
        os.write(w, data)
        os.close(w)

    threading.Thread(target=_write, daemon=True).start()
    return r


def test_both_readers_get_identical_bytes():
    data = bytes(range(256)) * 400  # ~100 KB, spans several 64 KB chunks
    tee = PcapTee(_feed_fd(data), buffer_chunks=1024).start()

    out_rtp = {}
    out_sip = {}

    def read_all(reader, sink):
        buf = b""
        while True:
            b = reader.read(4096)
            if not b:
                break
            buf += b
        sink["data"] = buf

    t1 = threading.Thread(target=read_all, args=(tee.rtp_reader, out_rtp))
    t2 = threading.Thread(target=read_all, args=(tee.sip_reader, out_sip))
    t1.start(); t2.start()
    t1.join(timeout=10); t2.join(timeout=10)
    tee.close()

    assert out_rtp["data"] == data
    assert out_sip["data"] == data


def test_slow_consumer_does_not_stall_fast_one():
    # The fast reader must drain fully even while the other barely reads. With a
    # small buffer the slow sink will drop chunks, but the fast sink stays whole
    # and neither the reader nor the fast consumer blocks.
    data = bytes(range(256)) * 4000  # ~1 MB
    tee = PcapTee(_feed_fd(data), buffer_chunks=4).start()

    fast_out = {}

    def read_fast():
        buf = b""
        while True:
            b = tee.rtp_reader.read(65536)
            if not b:
                break
            buf += b
        fast_out["data"] = buf

    def read_slow():
        # Deliberately sluggish: small reads with sleeps.
        while True:
            b = tee.sip_reader.read(256)
            if not b:
                break
            time.sleep(0.001)

    tf = threading.Thread(target=read_fast)
    ts = threading.Thread(target=read_slow)
    tf.start(); ts.start()

    tf.join(timeout=15)
    assert not tf.is_alive(), "fast consumer stalled — tee starvation bug"
    assert fast_out["data"] == data  # fast path lossless

    ts.join(timeout=15)
    tee.close()
