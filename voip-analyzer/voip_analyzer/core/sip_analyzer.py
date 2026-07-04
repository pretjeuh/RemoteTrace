"""Build and track SIP dialogs from tshark field records.

Mirrors the shape of :class:`LiveStreamAnalyzer` so the web layer can treat
SIP calls and RTP streams symmetrically.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Dict, List, Optional

from voip_analyzer.core.rtp_port_hints import RtpPortHints, get_shared_hints
from voip_analyzer.core.tshark_runner import SipFieldRecord
from voip_analyzer.models.sip_dialog import (
    CallState,
    MediaDescriptor,
    SipDialog,
    SipMessage,
)

logger = logging.getLogger(__name__)

# Response codes that are transient auth challenges, not call failures.
_AUTH_CHALLENGE_CODES = frozenset({401, 407})


class SipDialogAnalyzer:
    """Accumulate SIP frames into per-Call-ID dialogs and drive call state."""

    def __init__(self, port_hints: Optional[RtpPortHints] = None):
        """
        Args:
            port_hints: Shared registry of SDP-learned RTP ports so the RTP
                parser can recognise dynamically negotiated media ports.
                Defaults to the process-wide singleton.
        """
        self._dialogs: Dict[str, SipDialog] = {}
        self._order: List[str] = []  # preserve first-seen order for display
        self._port_hints = port_hints if port_hints is not None else get_shared_hints()

    def add_record(self, record: SipFieldRecord) -> None:
        """Fold one dissected SIP frame into its dialog."""
        dialog = self._dialogs.get(record.call_id)
        if dialog is None:
            dialog = SipDialog(
                call_id=record.call_id,
                from_uri=record.from_uri,
                to_uri=record.to_uri,
                setup_time=None,
            )
            self._order.append(record.call_id)

        message = SipMessage(
            frame_number=record.frame_number,
            timestamp=record.timestamp,
            direction="response" if record.status_code is not None else "request",
            method=record.method,
            status_code=record.status_code,
            status_line=record.status_line,
            cseq=record.cseq,
        )
        dialog = dialog.with_message(message)
        dialog = self._merge_media(dialog, record)
        dialog = self._apply_transition(dialog, message)

        self._dialogs[record.call_id] = dialog

    def _merge_media(self, dialog: SipDialog, record: SipFieldRecord) -> SipDialog:
        """Attach SDP-negotiated media endpoints and register RTP port hints."""
        if not record.media_ports:
            return dialog
        # An SDP body in a request is the caller's offer; in a response, the callee's.
        offered_by = "callee" if record.status_code is not None else "caller"
        count = len(record.media_ports)
        for i in range(count):
            port = record.media_ports[i]
            addr = record.media_addrs[i] if i < len(record.media_addrs) else ""
            mtype = record.media_types[i] if i < len(record.media_types) else "audio"
            if not addr:
                continue
            descriptor = MediaDescriptor(
                media_type=mtype,
                connection_address=addr,
                port=port,
                offered_by=offered_by,
            )
            dialog = dialog.with_media(descriptor)
            # SIP signalling precedes the media, so registering the port now lets
            # the RTP parser recognise it before those packets arrive.
            self._port_hints.add(port)
        return dialog

    def _apply_transition(self, dialog: SipDialog, message: SipMessage) -> SipDialog:
        """Advance the dialog state machine for one message."""
        if message.direction == "request":
            return self._on_request(dialog, message)
        return self._on_response(dialog, message)

    def _on_request(self, dialog: SipDialog, message: SipMessage) -> SipDialog:
        method = (message.method or "").upper()
        if method == "INVITE":
            # First INVITE sets setup time and marks this dialog as a real call
            # (vs OPTIONS/REGISTER keepalives). A re-INVITE after an auth
            # challenge must not reset an already-answered call.
            if dialog.setup_time is None:
                dialog = replace(dialog, setup_time=message.timestamp, is_call=True)
            elif not dialog.is_call:
                dialog = replace(dialog, is_call=True)
            if dialog.state in (CallState.ANSWERED, CallState.ENDED):
                return dialog
            return dialog.with_state(CallState.TRYING)
        if method == "BYE":
            if dialog.state == CallState.ANSWERED:
                return dialog.with_state(CallState.ENDED, end_time=message.timestamp)
            return dialog
        if method == "CANCEL":
            # Caller hung up before answer — distinct from a server rejection.
            if dialog.state in (CallState.TRYING, CallState.RINGING):
                return dialog.with_state(
                    CallState.CANCELLED, end_time=message.timestamp
                )
            return dialog
        return dialog

    def _on_response(self, dialog: SipDialog, message: SipMessage) -> SipDialog:
        code = message.status_code
        if code is None:
            return dialog
        # Only INVITE-transaction responses drive call state; ignore responses to
        # OPTIONS/REGISTER/BYE for the call lifecycle.
        if message.cseq_method() not in (None, "INVITE"):
            return dialog

        if 100 <= code < 180:
            if dialog.state == CallState.TRYING:
                return dialog  # 100 Trying — already trying
            return dialog
        if code == 180 or code == 183:
            if dialog.state in (CallState.TRYING,):
                return dialog.with_state(CallState.RINGING)
            return dialog
        if 200 <= code < 300:
            # A 2xx to INVITE means the call was answered.
            if dialog.state in (CallState.TRYING, CallState.RINGING):
                return dialog.with_state(
                    CallState.ANSWERED,
                    answer_time=message.timestamp,
                    final_status_code=200,
                )
            return dialog
        if code >= 300:
            # Auth challenges are transient: the UAC will re-INVITE. Stay pending.
            if code in _AUTH_CHALLENGE_CODES:
                return dialog
            # Once answered/cancelled, a late response must not override the outcome.
            if dialog.state in (
                CallState.ANSWERED,
                CallState.ENDED,
                CallState.CANCELLED,
            ):
                return dialog
            # 487 Request Terminated is the response to a CANCEL — a caller
            # cancellation, not a server rejection.
            if code == 487:
                if dialog.state in (CallState.TRYING, CallState.RINGING):
                    return dialog.with_state(
                        CallState.CANCELLED,
                        final_status_code=487,
                        end_time=message.timestamp,
                    )
                return dialog
            if dialog.state in (CallState.TRYING, CallState.RINGING):
                return dialog.with_state(
                    CallState.FAILED,
                    final_status_code=code,
                    end_time=message.timestamp,
                )
        return dialog

    # --- query API, parallel to LiveStreamAnalyzer -----------------------------

    def get_dialogs(self) -> List[SipDialog]:
        """All dialogs in first-seen order, including OPTIONS/REGISTER keepalives."""
        return [self._dialogs[cid] for cid in self._order]

    def get_calls(self) -> List[SipDialog]:
        """Dialogs that represent real calls (carried an INVITE)."""
        return [d for d in self.get_dialogs() if d.is_call]

    def get_active_calls(self) -> List[SipDialog]:
        return [d for d in self.get_calls() if d.is_active()]

    def get_completed_calls(self) -> List[SipDialog]:
        return [d for d in self.get_calls() if not d.is_active()]

    def get_statistics(self) -> Dict[str, int]:
        calls = self.get_calls()
        answered = sum(
            1 for d in calls if d.state in (CallState.ANSWERED, CallState.ENDED)
        )
        failed = sum(1 for d in calls if d.state == CallState.FAILED)
        cancelled = sum(1 for d in calls if d.state == CallState.CANCELLED)
        return {
            "total_calls": len(calls),
            "active_calls": len(self.get_active_calls()),
            "answered_calls": answered,
            "failed_calls": failed,
            "cancelled_calls": cancelled,
            "keepalive_dialogs": len(self.get_dialogs()) - len(calls),
        }
