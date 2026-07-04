"""Unit tests for the SIP dialog state machine and media merging."""

from voip_analyzer.core.rtp_port_hints import RtpPortHints
from voip_analyzer.core.sip_analyzer import SipDialogAnalyzer
from voip_analyzer.core.tshark_runner import SipFieldRecord
from voip_analyzer.models.sip_dialog import CallState


def _record(
    frame,
    ts,
    *,
    method=None,
    status_code=None,
    call_id="call-1",
    cseq="1 INVITE",
    media_addrs=(),
    media_ports=(),
    media_types=(),
    from_uri="Alice <sip:alice@example.com>",
    to_uri="Bob <sip:bob@example.com>",
):
    return SipFieldRecord(
        frame_number=frame,
        timestamp=ts,
        method=method,
        status_code=status_code,
        status_line=(f"SIP/2.0 {status_code}" if status_code else None),
        call_id=call_id,
        from_uri=from_uri,
        to_uri=to_uri,
        cseq=cseq,
        media_addrs=tuple(media_addrs),
        media_ports=tuple(media_ports),
        media_types=tuple(media_types),
        media_formats=(),
    )


def _feed(records):
    analyzer = SipDialogAnalyzer(port_hints=RtpPortHints())
    for r in records:
        analyzer.add_record(r)
    return analyzer


def test_full_answered_call_reaches_ended():
    analyzer = _feed([
        _record(1, 100.0, method="INVITE"),
        _record(2, 100.1, status_code=100),
        _record(3, 100.5, status_code=180),
        _record(4, 102.0, status_code=200),
        _record(5, 102.1, method="ACK"),
        _record(6, 130.0, method="BYE"),
    ])
    (dialog,) = analyzer.get_dialogs()
    assert dialog.state == CallState.ENDED
    assert dialog.setup_time == 100.0
    assert dialog.answer_time == 102.0
    assert dialog.end_time == 130.0
    assert dialog.signaling_duration() == 28.0  # answer -> end


def test_busy_invite_marks_failed_with_code():
    analyzer = _feed([
        _record(1, 5.0, method="INVITE"),
        _record(2, 5.2, status_code=180),
        _record(3, 6.0, status_code=486),
    ])
    (dialog,) = analyzer.get_dialogs()
    assert dialog.state == CallState.FAILED
    assert dialog.final_status_code == 486
    assert dialog.end_time == 6.0


def test_cancel_before_answer_is_cancelled():
    analyzer = _feed([
        _record(1, 1.0, method="INVITE"),
        _record(2, 1.5, status_code=180),
        _record(3, 2.0, method="CANCEL", cseq="1 CANCEL"),
    ])
    (dialog,) = analyzer.get_calls()
    assert dialog.state == CallState.CANCELLED
    assert dialog.end_time == 2.0


def test_cancel_flow_with_487_is_cancelled_not_failed():
    # Real Yealink pattern: INVITE -> 100 -> 180 -> CANCEL -> 200(CANCEL) -> 487.
    # The 200 is to the CANCEL (not the INVITE) and must not read as answered;
    # the 487 confirms cancellation, not a server failure.
    analyzer = _feed([
        _record(1, 1.0, method="INVITE", cseq="102 INVITE"),
        _record(2, 1.2, status_code=100, cseq="102 INVITE"),
        _record(3, 1.5, status_code=180, cseq="102 INVITE"),
        _record(4, 3.0, method="CANCEL", cseq="102 CANCEL"),
        _record(5, 3.1, status_code=200, cseq="102 CANCEL"),
        _record(6, 3.2, status_code=487, cseq="102 INVITE"),
        _record(7, 3.3, method="ACK", cseq="102 ACK"),
    ])
    (dialog,) = analyzer.get_calls()
    assert dialog.state == CallState.CANCELLED
    assert dialog.answer_time is None


def test_auth_challenge_is_transient_not_failure():
    # 401 on the first INVITE must NOT fail the call; the re-INVITE proceeds.
    analyzer = _feed([
        _record(1, 1.0, method="INVITE", cseq="1 INVITE"),
        _record(2, 1.1, status_code=401, cseq="1 INVITE"),
        _record(3, 1.2, method="ACK", cseq="1 ACK"),
        _record(4, 1.3, method="INVITE", cseq="2 INVITE"),
        _record(5, 1.4, status_code=100, cseq="2 INVITE"),
        _record(6, 2.0, status_code=200, cseq="2 INVITE"),
        _record(7, 2.1, method="ACK", cseq="2 ACK"),
    ])
    (dialog,) = analyzer.get_dialogs()
    assert dialog.state == CallState.ANSWERED
    assert dialog.setup_time == 1.0  # first INVITE, not the re-INVITE
    assert dialog.answer_time == 2.0


def test_sdp_media_registers_port_hints_and_descriptors():
    hints = RtpPortHints()
    analyzer = SipDialogAnalyzer(port_hints=hints)
    analyzer.add_record(
        _record(
            1, 1.0, method="INVITE",
            media_addrs=("10.100.40.37",),
            media_ports=(21008,),
            media_types=("audio",),
        )
    )
    (dialog,) = analyzer.get_dialogs()
    assert hints.contains(21008)
    assert dialog.media_endpoints() == {("10.100.40.37", 21008)}


def test_options_keepalives_are_not_calls():
    # OPTIONS/REGISTER traffic must not appear in the call list.
    analyzer = _feed([
        _record(1, 1.0, method="OPTIONS", cseq="1 OPTIONS", call_id="opt-1"),
        _record(2, 1.1, status_code=200, cseq="1 OPTIONS", call_id="opt-1"),
        _record(3, 2.0, method="REGISTER", cseq="1 REGISTER", call_id="reg-1"),
    ])
    assert analyzer.get_calls() == []
    assert len(analyzer.get_dialogs()) == 2  # both tracked, neither is a call
    assert analyzer.get_statistics()["keepalive_dialogs"] == 2


def test_statistics_counts():
    analyzer = _feed([
        _record(1, 1.0, method="INVITE", call_id="a"),
        _record(2, 2.0, status_code=200, call_id="a"),
        _record(3, 2.1, method="BYE", call_id="a"),
        _record(4, 3.0, method="INVITE", call_id="b"),
        _record(5, 4.0, status_code=486, call_id="b"),
        _record(6, 5.0, method="OPTIONS", cseq="1 OPTIONS", call_id="ka"),
    ])
    stats = analyzer.get_statistics()
    assert stats["total_calls"] == 2  # keepalive excluded
    assert stats["answered_calls"] == 1
    assert stats["failed_calls"] == 1
    assert stats["keepalive_dialogs"] == 1
