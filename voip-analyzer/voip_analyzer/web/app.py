"""Flask web dashboard for VoIP analyzer — PCAP upload and live SSE stream."""

import json
import logging
import queue
import tempfile
import threading
from pathlib import Path
from typing import Optional

from flask import Flask, Response, jsonify, render_template, request

from voip_analyzer.core.packet_parser import PacketParser
from voip_analyzer.core.rtp_stream import RTPStreamAnalyzer
from voip_analyzer.live_analyzer import LiveStreamAnalyzer
from voip_analyzer.metrics.codec_detector import CodecDetector
from voip_analyzer.metrics.jitter import JitterAnalyzer
from voip_analyzer.metrics.packet_loss import PacketLossAnalyzer
from voip_analyzer.metrics.quality_scores import QualityScoreCalculator

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB upload limit

# SSE fan-out. A single shared queue would let one client consume events meant
# for another (queue.get removes the item), so each connected browser gets its
# own subscriber queue. The ingest side broadcasts to all subscribers, and the
# latest snapshot is retained so a client connecting mid-capture renders current
# state immediately instead of waiting for the next push. None signals stream end.
_subscribers: "set[queue.Queue]" = set()
_subscribers_lock = threading.Lock()
_latest_event: "Optional[dict]" = None


def _subscribe() -> "queue.Queue":
    """Register a new SSE client queue and seed it with the latest snapshot."""
    q: "queue.Queue" = queue.Queue(maxsize=512)
    with _subscribers_lock:
        _subscribers.add(q)
        if _latest_event is not None:
            q.put_nowait(_latest_event)
    return q


def _unsubscribe(q: "queue.Queue") -> None:
    """Drop a disconnected client's queue."""
    with _subscribers_lock:
        _subscribers.discard(q)


def _broadcast(event: "Optional[dict]") -> None:
    """Fan an event out to every connected client; drop oldest on a full queue."""
    global _latest_event
    if event is not None:
        _latest_event = event
    with _subscribers_lock:
        targets = list(_subscribers)
    for q in targets:
        try:
            q.put_nowait(event)
        except queue.Full:
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(event)
            except queue.Full:
                pass


# ---------- Helpers ----------

def _stream_to_dict(stream) -> dict:
    """Convert a stream info object (LiveStreamInfo or RTPStreamInfo) to a plain dict."""
    loss = getattr(stream, "packet_loss", {}) or {}
    jitter = getattr(stream, "jitter", {}) or {}
    duration_attr = getattr(stream, "duration", None)
    if callable(duration_attr):
        duration_s = duration_attr()
    else:
        duration_s = getattr(stream, "duration_seconds", 0.0)

    flow_attr = getattr(stream, "flow_id", None)
    if callable(flow_attr):
        flow = flow_attr()
    else:
        flow = f"{getattr(stream, 'src_ip', '?')}:{getattr(stream, 'src_port', '?')}→{getattr(stream, 'dst_ip', '?')}:{getattr(stream, 'dst_port', '?')}"

    # packet_count is an int attribute on LiveStreamInfo but a method on RTPStream.
    pc_attr = getattr(stream, "packet_count", None)
    if callable(pc_attr):
        packets = pc_attr()
    elif pc_attr is not None:
        packets = pc_attr
    else:
        packets = len(getattr(stream, "packets", []))

    # mos_score / r_factor may be None on RTPStream before scoring.
    mos = getattr(stream, "mos_score", 0.0) or 0.0
    r_factor = getattr(stream, "r_factor", 0.0) or 0.0

    return {
        "flow": flow,
        "codec": getattr(stream, "codec_name", "Unknown"),
        "packets": packets,
        "loss_pct": round(getattr(stream, "packet_loss_pct", loss.get("loss_percentage", 0.0)) or 0.0, 2),
        "jitter_avg_ms": round(getattr(stream, "avg_jitter_ms", jitter.get("avg_ms", 0.0)) or 0.0, 2),
        "jitter_max_ms": round(getattr(stream, "max_jitter_ms", jitter.get("max_ms", 0.0)) or 0.0, 2),
        "mos": round(mos, 2),
        "r_factor": round(r_factor, 1),
        "duration_s": round(duration_s or 0.0, 1),
    }


def _analyze_pcap(filepath: str) -> dict:
    """Parse a PCAP file and return analysis results as a plain dict."""
    parser = PacketParser(verbose=False)
    all_packets = list(parser.parse_file(filepath))

    if not all_packets:
        return {"error": "No RTP packets found in file.", "streams": []}

    stream_analyzer = RTPStreamAnalyzer()
    for packet in all_packets:
        stream_analyzer.add_packet(packet)

    streams = stream_analyzer.get_streams()
    if not streams:
        return {"error": "No complete RTP streams identified.", "streams": []}

    results = []
    for stream in streams:
        if not stream.packets:
            continue
        codec_name, pt, clock_rate = CodecDetector.detect_codec(stream.packets)
        stream.codec_name = codec_name
        stream.codec_pt = pt
        stream.clock_rate = clock_rate

        sorted_packets = sorted(stream.packets, key=lambda p: p.arrival_timestamp)
        loss_metrics = PacketLossAnalyzer.analyze(sorted_packets)
        jitter_metrics = JitterAnalyzer.analyze(sorted_packets, clock_rate)
        quality = QualityScoreCalculator.calculate_call_quality_metrics(
            packet_loss_percentage=loss_metrics["loss_percentage"],
            jitter_ms=jitter_metrics["avg_ms"],
            codec_name=codec_name,
            one_way_delay_ms=jitter_metrics["avg_ms"] * 2.5,
        )
        stream.packet_loss = loss_metrics
        stream.jitter = jitter_metrics
        stream.mos_score = quality["mos"]
        stream.r_factor = quality["r_factor"]

        results.append(_stream_to_dict(stream))

    # Expose the analyzer (under a private key) so the upload route can correlate
    # SIP calls against these streams; the key is stripped before the response.
    return {
        "streams": results,
        "total_packets": len(all_packets),
        "_rtp_analyzer": stream_analyzer,
    }


# ---------- Routes ----------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    """Accept a PCAP file upload and return analysis JSON."""
    if "file" not in request.files:
        return jsonify({"error": "No file field in request."}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename."}), 400

    suffix = Path(f.filename).suffix.lower()
    if suffix not in {".pcap", ".pcapng", ".cap"}:
        return jsonify({"error": f"Unsupported file type: {suffix}"}), 400

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        f.save(tmp_path)

    try:
        result = _analyze_pcap(tmp_path)
        # Attach SIP call analysis (best-effort; RTP-only if tshark is absent).
        try:
            result["calls"] = _analyze_sip(tmp_path, result.get("_rtp_analyzer"))
        except Exception:
            logger.exception("SIP analysis failed; returning RTP-only result")
            result["calls"] = []
        result.pop("_rtp_analyzer", None)
    except Exception as exc:
        logger.exception("Analysis failed")
        return jsonify({"error": str(exc)}), 500
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return jsonify(result)


@app.route("/stream")
def stream():
    """Server-Sent Events endpoint for live capture data.

    Each client gets its own subscriber queue (seeded with the latest snapshot),
    so multiple browsers/tabs can watch the same capture without stealing each
    other's events.
    """
    def generate():
        q = _subscribe()
        try:
            while True:
                try:
                    event = q.get(timeout=15)
                except queue.Empty:
                    yield "event: heartbeat\ndata: {}\n\n"
                    continue

                if event is None:
                    yield "event: done\ndata: {}\n\n"
                    break

                yield f"data: {json.dumps(event)}\n\n"
        finally:
            _unsubscribe(q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- Live ingest ----------

def ingest_live_stream(
    analyzer: LiveStreamAnalyzer,
    parser: PacketParser,
    update_interval: float = 2.0,
    stream=None,
):
    """
    Read RTP packets from the given stream (or stdin) and push SSE events to the queue.
    Intended to run in a background daemon thread while Flask serves the browser.
    """
    import time

    last_update = time.time()
    last_check = time.time()

    try:
        for packet in parser.parse_stream(stream):
            analyzer.add_packet(packet)
            now = time.time()

            if now - last_check >= 5.0:
                analyzer.check_inactive_streams(packet.arrival_timestamp)
                last_check = now

            if now - last_update >= update_interval:
                _push_live_event(analyzer)
                last_update = now
    except Exception:
        logger.exception("Live ingest error")
    finally:
        _push_live_event(analyzer)
        _broadcast(None)


# SIP analysis is optional (requires tshark). When enabled, the web command
# registers the shared analyzer here so the live SSE payload can include calls.
_sip_analyzer = None


def set_sip_analyzer(analyzer) -> None:
    """Register the SIP dialog analyzer whose calls the dashboard should show."""
    global _sip_analyzer
    _sip_analyzer = analyzer


def _dialog_to_dict(dialog) -> dict:
    """Serialise a SipDialog for the browser (call row + ladder + correlation)."""
    return {
        "call_id": dialog.call_id,
        "from": dialog.from_uri,
        "to": dialog.to_uri,
        "state": dialog.state.value,
        "final_status_code": dialog.final_status_code,
        "setup_time": dialog.setup_time,
        "answer_time": dialog.answer_time,
        "duration": round(dialog.signaling_duration(), 1),
        "ladder": [
            {
                "ts": m.timestamp,
                "dir": m.direction,
                "label": m.label(),
                "method": m.method,
                "status_code": m.status_code,
            }
            for m in dialog.messages
        ],
        "media": [
            {"address": md.connection_address, "port": md.port, "type": md.media_type}
            for md in dialog.media
        ],
        "correlated": list(dialog.correlated_streams),
    }


def _rtp_streams_of(analyzer) -> list:
    """Streams from either a LiveStreamAnalyzer or an RTPStreamAnalyzer."""
    if analyzer is None:
        return []
    if hasattr(analyzer, "get_all_streams"):
        return analyzer.get_all_streams()
    if hasattr(analyzer, "get_streams"):
        return analyzer.get_streams()
    return []


def _correlated_calls() -> list:
    """Current SIP calls with RTP quality attached, newest first."""
    if _sip_analyzer is None:
        return []
    from voip_analyzer.core.sip_rtp_correlator import SipRtpCorrelator

    calls = _sip_analyzer.get_calls()
    streams = _rtp_streams_of(_live_rtp_analyzer)
    correlated = SipRtpCorrelator.correlate(calls, streams, stream_to_dict=_stream_to_dict)
    return [_dialog_to_dict(d) for d in correlated]


def _analyze_sip(filepath: str, rtp_analyzer=None) -> list:
    """Run SIP call analysis on an uploaded PCAP and correlate with RTP streams.

    Returns a list of _dialog_to_dict()-shaped call dicts, or [] when tshark is
    unavailable (RTP-only degradation — never raises to the caller for that).

    Note on ordering: the upload path parses RTP before this runs, so SDP-learned
    port hints are registered after the RTP parse. Correlation still matches on
    the SDP-negotiated (ip, port) endpoints, so already-identified streams attach
    correctly; only RTP streams on sub-heuristic ports that were never recognised
    during the RTP parse could be missed. Live capture avoids this because SIP
    signalling (and its SDP) precedes the media packets.
    """
    from voip_analyzer.core.tshark_runner import tshark_available

    if not tshark_available():
        return []

    from voip_analyzer.core.rtp_port_hints import get_shared_hints
    from voip_analyzer.core.sip_analyzer import SipDialogAnalyzer
    from voip_analyzer.core.sip_rtp_correlator import SipRtpCorrelator
    from voip_analyzer.core.tshark_runner import TsharkSipSource

    sip_analyzer = SipDialogAnalyzer(port_hints=get_shared_hints())
    for record in TsharkSipSource(filepath).iter_records():
        sip_analyzer.add_record(record)

    calls = sip_analyzer.get_calls()
    streams = _rtp_streams_of(rtp_analyzer)
    correlated = SipRtpCorrelator.correlate(
        calls, streams, stream_to_dict=_stream_to_dict
    )
    return [_dialog_to_dict(d) for d in correlated]


# Set by ingest_sip_stream so correlation can reach the live RTP streams.
_live_rtp_analyzer = None


def ingest_sip_stream(sip_analyzer, sip_source, rtp_analyzer=None) -> None:
    """Consume tshark SIP records into the analyzer (runs in a daemon thread).

    Pushes a live event periodically so new/updated calls reach the browser
    independently of the RTP ingest lifecycle.
    """
    import time

    global _live_rtp_analyzer
    _live_rtp_analyzer = rtp_analyzer
    set_sip_analyzer(sip_analyzer)
    # Push on a short time interval rather than every N records. A record-count
    # throttle starves SIP-only captures (a whole call is ~7 records, never
    # reaching a 25-record threshold), leaving the Calls tab empty until EOF —
    # which on a live pipe never comes. A timer surfaces calls within ~1s.
    last_push = time.time()
    try:
        for record in sip_source.iter_records():
            sip_analyzer.add_record(record)
            if rtp_analyzer is not None and time.time() - last_push >= 1.0:
                _push_live_event(rtp_analyzer)
                last_push = time.time()
    except Exception:
        logger.exception("SIP ingest error")
    finally:
        # Final push so the completed call list is delivered even if RTP already
        # ended (e.g. short captures, or SIP finishing after the RTP EOF).
        if rtp_analyzer is not None:
            _push_live_event(rtp_analyzer)


def _push_live_event(analyzer: LiveStreamAnalyzer) -> None:
    active = [_stream_to_dict(s) for s in analyzer.get_active_streams()]
    completed = [_stream_to_dict(s) for s in analyzer.get_completed_streams()]
    stats = analyzer.get_statistics()
    event = {
        "active": active,
        "completed": completed,
        "stats": stats,
        "calls": _correlated_calls(),
        "call_stats": _sip_analyzer.get_statistics() if _sip_analyzer else {},
    }
    _broadcast(event)
