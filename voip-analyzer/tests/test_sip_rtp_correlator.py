"""Tests for SIP<->RTP correlation and SDP-learned port hints."""

from dataclasses import dataclass, field
from typing import List, Tuple

from voip_analyzer.core.packet_parser import PacketParser
from voip_analyzer.core.rtp_port_hints import RtpPortHints
from voip_analyzer.core.sip_rtp_correlator import SipRtpCorrelator, call_mos
from voip_analyzer.models.sip_dialog import (
    CallState,
    MediaDescriptor,
    SipDialog,
)


@dataclass
class FakeStream:
    """Stands in for LiveStreamInfo for correlation tests."""

    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    start_time: float = 0.0
    last_packet_time: float = 0.0
    codec_name: str = "G.711 PCMU"
    packet_loss_pct: float = 0.0
    avg_jitter_ms: float = 0.0
    mos_score: float = 4.4


def _dialog_with_media(call_id, endpoints, *, setup=0.0, end=100.0):
    media = tuple(
        MediaDescriptor(media_type="audio", connection_address=ip, port=port)
        for ip, port in endpoints
    )
    return SipDialog(
        call_id=call_id,
        is_call=True,
        state=CallState.ENDED,
        setup_time=setup,
        end_time=end,
        media=media,
    )


# --- port hints ------------------------------------------------------------


def test_port_hint_makes_parser_recognise_dynamic_port():
    hints = RtpPortHints()
    parser = PacketParser(port_hints=hints)
    # 6000 is below the static heuristic range and normally unrecognised.
    assert parser.is_likely_rtp_port(6000) is False
    hints.add(6000)
    assert parser.is_likely_rtp_port(6000) is True


def test_static_range_still_works_without_hints():
    parser = PacketParser(port_hints=RtpPortHints())
    assert parser.is_likely_rtp_port(16400) is True  # inside (10000, 65000)


# --- correlation -----------------------------------------------------------


def test_stream_matched_to_dialog_by_sdp_endpoint():
    dialog = _dialog_with_media("c1", [("10.0.0.2", 6000)])
    stream = FakeStream("10.0.0.1", 40000, "10.0.0.2", 6000, mos_score=3.9)

    (out,) = SipRtpCorrelator.correlate([dialog], [stream])
    assert len(out.correlated_streams) == 1
    assert out.correlated_streams[0]["mos"] == 3.9
    assert call_mos(out) == 3.9


def test_unrelated_stream_not_matched():
    dialog = _dialog_with_media("c1", [("10.0.0.2", 6000)])
    stream = FakeStream("192.168.1.1", 5000, "192.168.1.2", 7000)

    (out,) = SipRtpCorrelator.correlate([dialog], [stream])
    assert out.correlated_streams == ()
    assert call_mos(out) is None


def test_reused_port_disambiguated_by_time_overlap():
    # Two sequential calls reuse the same media endpoint; each stream must
    # attach only to the temporally overlapping call.
    call_a = _dialog_with_media("a", [("10.0.0.2", 6000)], setup=0.0, end=30.0)
    call_b = _dialog_with_media("b", [("10.0.0.2", 6000)], setup=100.0, end=130.0)

    stream_a = FakeStream("10.0.0.1", 40000, "10.0.0.2", 6000,
                          start_time=1.0, last_packet_time=29.0, mos_score=4.1)
    stream_b = FakeStream("10.0.0.1", 40000, "10.0.0.2", 6000,
                          start_time=101.0, last_packet_time=129.0, mos_score=3.2)

    out_a, out_b = SipRtpCorrelator.correlate([call_a, call_b], [stream_a, stream_b])
    assert [s["mos"] for s in out_a.correlated_streams] == [4.1]
    assert [s["mos"] for s in out_b.correlated_streams] == [3.2]


def test_worst_leg_mos_rollup():
    dialog = _dialog_with_media("c1", [("10.0.0.2", 6000), ("10.0.0.1", 40000)])
    good = FakeStream("10.0.0.1", 40000, "10.0.0.2", 6000, mos_score=4.3)
    bad = FakeStream("10.0.0.2", 6000, "10.0.0.1", 40000, mos_score=2.8)

    (out,) = SipRtpCorrelator.correlate([dialog], [good, bad])
    # Both streams touch the dialog's endpoints; worst leg wins.
    assert call_mos(out) == 2.8
