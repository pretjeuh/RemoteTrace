"""Correlate measured RTP streams with SIP dialogs via SDP-negotiated media.

SDP in the SIP signalling advertises where each call's media will flow
(ip:port). We match those endpoints against the source/destination of the
RTP streams the RTP analyzer measured, then attach the quality metrics
(jitter/loss/MOS) back to the specific call.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Iterable, List, Optional, Tuple

from voip_analyzer.models.sip_dialog import SipDialog

logger = logging.getLogger(__name__)


def _stream_endpoints(stream) -> List[Tuple[str, int]]:
    """Return the (ip, port) endpoints of an RTP stream, both directions.

    Handles LiveStreamInfo (src_ip/src_port/dst_ip/dst_port attributes) and
    RTPStream (flow_id 5-tuple).
    """
    endpoints: List[Tuple[str, int]] = []
    if hasattr(stream, "src_ip") and hasattr(stream, "src_port"):
        endpoints.append((stream.src_ip, int(stream.src_port)))
        endpoints.append((stream.dst_ip, int(stream.dst_port)))
    elif hasattr(stream, "flow_id"):
        flow = stream.flow_id
        flow = flow() if callable(flow) else flow
        if isinstance(flow, (tuple, list)) and len(flow) >= 4:
            endpoints.append((flow[0], int(flow[1])))
            endpoints.append((flow[2], int(flow[3])))
    return endpoints


def _stream_time_span(stream) -> Tuple[Optional[float], Optional[float]]:
    """Best-effort (start, end) timestamps for a stream, or (None, None)."""
    start = getattr(stream, "start_time", None)
    end = getattr(stream, "last_packet_time", None)
    if end is None:
        end = getattr(stream, "end_time", None)
    return start, end


def _times_overlap(
    dialog: SipDialog,
    stream_start: Optional[float],
    stream_end: Optional[float],
) -> bool:
    """Whether an RTP stream's lifetime plausibly overlaps a dialog's.

    Used to disambiguate when the same (ip, port) is reused across sequential
    calls. Missing timestamps are treated as "no evidence against" (overlap).
    """
    d_start = dialog.setup_time
    d_end = dialog.end_time
    if d_start is None or d_end is None or stream_start is None or stream_end is None:
        return True
    # Allow a small guard band: media can start slightly before the 200 OK and
    # linger just after BYE.
    guard = 2.0
    return (stream_start <= d_end + guard) and (stream_end >= d_start - guard)


class SipRtpCorrelator:
    """Attach RTP stream quality to the SIP dialogs that negotiated them."""

    @staticmethod
    def correlate(
        dialogs: Iterable[SipDialog],
        rtp_streams: Iterable,
        stream_to_dict=None,
    ) -> List[SipDialog]:
        """Return dialogs with ``correlated_streams`` populated.

        Args:
            dialogs: SIP dialogs (with SDP media endpoints).
            rtp_streams: measured RTP streams (LiveStreamInfo or RTPStream).
            stream_to_dict: optional serializer turning a stream into a plain
                dict for the web payload; defaults to a minimal projection.

        Returns:
            New dialog objects (immutable) with matched streams attached.
        """
        streams = list(rtp_streams)
        if stream_to_dict is None:
            stream_to_dict = _default_stream_dict

        # Index streams by each of their endpoints for O(1) lookup.
        by_endpoint = {}
        for s in streams:
            for ep in _stream_endpoints(s):
                by_endpoint.setdefault(ep, []).append(s)

        result: List[SipDialog] = []
        for dialog in dialogs:
            matched = []
            seen_ids = set()
            for ep in dialog.media_endpoints():
                for s in by_endpoint.get(ep, ()):  # streams touching this endpoint
                    sid = id(s)
                    if sid in seen_ids:
                        continue
                    start, end = _stream_time_span(s)
                    if not _times_overlap(dialog, start, end):
                        continue
                    seen_ids.add(sid)
                    matched.append(s)
            if matched:
                dialog = replace(
                    dialog,
                    correlated_streams=tuple(stream_to_dict(s) for s in matched),
                )
            result.append(dialog)
        return result


def _default_stream_dict(stream) -> dict:
    """Minimal quality projection when no serializer is supplied."""
    return {
        "flow": _first_endpoint_label(stream),
        "codec": getattr(stream, "codec_name", "Unknown"),
        "loss_pct": round(float(getattr(stream, "packet_loss_pct", 0.0) or 0.0), 2),
        "jitter_ms": round(float(getattr(stream, "avg_jitter_ms", 0.0) or 0.0), 2),
        "mos": round(float(getattr(stream, "mos_score", 0.0) or 0.0), 2),
    }


def _first_endpoint_label(stream) -> str:
    eps = _stream_endpoints(stream)
    if len(eps) >= 2:
        return f"{eps[0][0]}:{eps[0][1]}→{eps[1][0]}:{eps[1][1]}"
    if eps:
        return f"{eps[0][0]}:{eps[0][1]}"
    return "?"


def call_mos(dialog: SipDialog) -> Optional[float]:
    """Worst-leg MOS across a dialog's correlated streams (call-level score)."""
    scores = [
        s.get("mos")
        for s in dialog.correlated_streams
        if isinstance(s.get("mos"), (int, float)) and s.get("mos")
    ]
    return min(scores) if scores else None
