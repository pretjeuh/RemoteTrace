"""SIP dialog data model — calls, messages, negotiated media, and state."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import List, Optional, Set, Tuple


class CallState(str, Enum):
    """State of a SIP dialog, derived from methods and response codes."""

    TRYING = "Trying"
    RINGING = "Ringing"
    ANSWERED = "Answered"
    CANCELLED = "Cancelled"  # caller hung up before answer (CANCEL / 487)
    FAILED = "Failed"  # server-side rejection (4xx/5xx/6xx)
    ENDED = "Ended"


@dataclass(frozen=True)
class SipMessage:
    """A single SIP request or response within a dialog."""

    frame_number: int
    timestamp: float  # epoch seconds (frame.time_epoch)
    direction: str  # "request" | "response"
    method: Optional[str] = None  # INVITE, ACK, BYE, CANCEL, OPTIONS, REGISTER...
    status_code: Optional[int] = None  # 100, 180, 200, 401, 486...
    status_line: Optional[str] = None
    cseq: Optional[str] = None  # e.g. "1 INVITE"

    def cseq_method(self) -> Optional[str]:
        """Method a response is answering, parsed from the CSeq header."""
        if not self.cseq:
            return None
        parts = self.cseq.split()
        return parts[-1].upper() if parts else None

    def label(self) -> str:
        """Short label for a ladder-diagram arrow."""
        if self.direction == "request":
            return self.method or "?"
        code = self.status_code if self.status_code is not None else "?"
        if self.status_line:
            return self.status_line
        return str(code)


@dataclass(frozen=True)
class MediaDescriptor:
    """One negotiated media endpoint learned from an SDP c=/m= pair."""

    media_type: str  # "audio" | "video" | ...
    connection_address: str  # from SDP c= line
    port: int  # from SDP m= line
    formats: Tuple[int, ...] = ()  # RTP payload types offered
    offered_by: str = "unknown"  # "caller" | "callee" | "unknown"

    def endpoint(self) -> Tuple[str, int]:
        """The (ip, port) tuple this media will be sent to/from."""
        return (self.connection_address, self.port)


@dataclass(frozen=True)
class SipDialog:
    """A SIP dialog keyed by Call-ID, holding messages, media, and state.

    Instances are immutable; state transitions return new copies via the
    ``with_*`` helpers so callers never mutate shared dialog objects.
    """

    call_id: str
    from_uri: str = ""
    to_uri: str = ""
    is_call: bool = False  # True once an INVITE is seen (vs OPTIONS/REGISTER keepalives)
    state: CallState = CallState.TRYING
    final_status_code: Optional[int] = None
    setup_time: Optional[float] = None  # first INVITE timestamp
    answer_time: Optional[float] = None  # 200 OK to INVITE timestamp
    end_time: Optional[float] = None  # BYE / final-failure timestamp
    messages: Tuple[SipMessage, ...] = ()
    media: Tuple[MediaDescriptor, ...] = ()
    correlated_streams: Tuple[dict, ...] = ()  # attached RTP quality dicts

    def with_message(self, message: SipMessage) -> "SipDialog":
        """Return a copy with ``message`` appended (kept in arrival order)."""
        return replace(self, messages=self.messages + (message,))

    def with_media(self, descriptor: MediaDescriptor) -> "SipDialog":
        """Return a copy with a new media descriptor, de-duplicated by endpoint."""
        if any(m.endpoint() == descriptor.endpoint() for m in self.media):
            return self
        return replace(self, media=self.media + (descriptor,))

    def with_state(
        self,
        state: CallState,
        *,
        final_status_code: Optional[int] = None,
        answer_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> "SipDialog":
        """Return a copy with an updated state and optional timing fields."""
        return replace(
            self,
            state=state,
            final_status_code=(
                final_status_code
                if final_status_code is not None
                else self.final_status_code
            ),
            answer_time=answer_time if answer_time is not None else self.answer_time,
            end_time=end_time if end_time is not None else self.end_time,
        )

    def signaling_duration(self) -> float:
        """Call duration in seconds derived from signaling.

        Prefers answer→end; falls back to setup→end so failed/cancelled calls
        still report a meaningful span.
        """
        start = self.answer_time if self.answer_time is not None else self.setup_time
        if start is None or self.end_time is None:
            return 0.0
        return max(0.0, self.end_time - start)

    def media_endpoints(self) -> Set[Tuple[str, int]]:
        """Set of (ip, port) endpoints negotiated for this call's media."""
        return {m.endpoint() for m in self.media}

    def is_active(self) -> bool:
        """True while the call is still in progress (not in a terminal state)."""
        return self.state not in (
            CallState.ENDED,
            CallState.FAILED,
            CallState.CANCELLED,
        )
