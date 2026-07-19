#!/usr/bin/env python3
"""Generate a realistic SIP call (+ optional RTP) onto the loopback interface.

Emits a complete INVITE dialog so the VoIP analyzer's Calls tab has an
ANSWERED call to classify:

    INVITE (SDP) -> 100 Trying -> 180 Ringing -> 200 OK (SDP) -> ACK
                 -> [RTP media] -> BYE -> 200 OK

All packets are UDP on 127.0.0.1. SIP on 5060, RTP on the SDP-advertised
media ports. Requires root to send on lo0 with a spoofed 5-tuple? No — plain
UDP sockets on loopback need no privileges, but scapy L3 send (sr/send) uses
raw sockets which DO need root on macOS. We therefore use ordinary UDP
sockets so this runs unprivileged; tcpdump on lo0 (which DOES need sudo) sees
the loopback frames.
"""
import socket
import sys
import time
import argparse

CALLER_IP = "127.0.0.1"
CALLEE_IP = "127.0.0.1"
SIP_PORT = 5060
CALLER_RTP = 40000
CALLEE_RTP = 40002

def sip_socket(bind_port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", bind_port))
    return s

def make_call(call_id, from_tag, to_tag, branch):
    """Return the ordered list of (sender_port, dest_port, payload) SIP msgs."""
    caller = f"<sip:alice@{CALLER_IP}>;tag={from_tag}"
    callee = f"<sip:bob@{CALLEE_IP}>"
    callee_tagged = f"<sip:bob@{CALLEE_IP}>;tag={to_tag}"
    via_caller = f"SIP/2.0/UDP {CALLER_IP}:{SIP_PORT};branch={branch}"
    cseq = "1"

    sdp_offer = (
        "v=0\r\n"
        f"o=alice 123 456 IN IP4 {CALLER_IP}\r\n"
        "s=call\r\n"
        f"c=IN IP4 {CALLER_IP}\r\n"
        "t=0 0\r\n"
        f"m=audio {CALLER_RTP} RTP/AVP 0\r\n"
        "a=rtpmap:0 PCMU/8000\r\n"
    )
    sdp_answer = (
        "v=0\r\n"
        f"o=bob 789 012 IN IP4 {CALLEE_IP}\r\n"
        "s=call\r\n"
        f"c=IN IP4 {CALLEE_IP}\r\n"
        "t=0 0\r\n"
        f"m=audio {CALLEE_RTP} RTP/AVP 0\r\n"
        "a=rtpmap:0 PCMU/8000\r\n"
    )

    def hdrs(extra_via_recv=False):
        return (
            f"Via: {via_caller}\r\n"
            f"From: {caller}\r\n"
            f"To: {callee if not extra_via_recv else callee_tagged}\r\n"
            f"Call-ID: {call_id}\r\n"
        )

    invite = (
        f"INVITE sip:bob@{CALLEE_IP} SIP/2.0\r\n"
        f"Via: {via_caller}\r\n"
        f"From: {caller}\r\n"
        f"To: {callee}\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: {cseq} INVITE\r\n"
        f"Contact: <sip:alice@{CALLER_IP}:{SIP_PORT}>\r\n"
        "Content-Type: application/sdp\r\n"
        f"Content-Length: {len(sdp_offer)}\r\n\r\n"
        f"{sdp_offer}"
    )
    def response(code, reason, sdp=""):
        ct = "Content-Type: application/sdp\r\n" if sdp else ""
        to_line = callee_tagged if code >= 180 else callee
        return (
            f"SIP/2.0 {code} {reason}\r\n"
            f"Via: {via_caller}\r\n"
            f"From: {caller}\r\n"
            f"To: {to_line}\r\n"
            f"Call-ID: {call_id}\r\n"
            f"CSeq: {cseq} INVITE\r\n"
            f"{ct}"
            f"Content-Length: {len(sdp)}\r\n\r\n"
            f"{sdp}"
        )
    ack = (
        f"ACK sip:bob@{CALLEE_IP} SIP/2.0\r\n"
        f"Via: {via_caller}\r\n"
        f"From: {caller}\r\n"
        f"To: {callee_tagged}\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: {cseq} ACK\r\n"
        "Content-Length: 0\r\n\r\n"
    )
    bye = (
        f"BYE sip:bob@{CALLEE_IP} SIP/2.0\r\n"
        f"Via: {via_caller}\r\n"
        f"From: {caller}\r\n"
        f"To: {callee_tagged}\r\n"
        f"Call-ID: {call_id}\r\n"
        "CSeq: 2 BYE\r\n"
        "Content-Length: 0\r\n\r\n"
    )
    bye_ok = (
        f"SIP/2.0 200 OK\r\n"
        f"Via: {via_caller}\r\n"
        f"From: {caller}\r\n"
        f"To: {callee_tagged}\r\n"
        f"Call-ID: {call_id}\r\n"
        "CSeq: 2 BYE\r\n"
        "Content-Length: 0\r\n\r\n"
    )
    # (direction, payload): 'req' caller->callee, 'resp' callee->caller
    return [
        ("req",  invite),
        ("resp", response(100, "Trying")),
        ("resp", response(180, "Ringing")),
        ("resp", response(200, "OK", sdp_answer)),
        ("req",  ack),
        ("req",  bye),
        ("resp", bye_ok),
    ]

def rtp_packets(n, ssrc, pt=0):
    """Minimal RTP packets: 12-byte header + 160-byte PCMU payload."""
    pkts = []
    for i in range(n):
        seq = i & 0xFFFF
        ts = (i * 160) & 0xFFFFFFFF
        hdr = bytes([0x80, pt]) + seq.to_bytes(2, "big") + ts.to_bytes(4, "big") + ssrc.to_bytes(4, "big")
        pkts.append(hdr + b"\xff" * 160)
    return pkts

def emit_call(sockets, index, rtp_count, msg_delay, paced_rtp):
    """Send one complete SIP dialog (+ optional RTP) using the given sockets."""
    caller, callee, caller_rtp, callee_rtp = sockets
    cid = f"call{index}-{int(time.time())}@{CALLER_IP}"
    msgs = make_call(cid, from_tag=f"ft{index}", to_tag=f"tt{index}",
                     branch=f"z9hG4bK{index}")
    print(f"[call {index}] Call-ID={cid}", flush=True)
    for direction, payload in msgs:
        data = payload.encode()
        if direction == "req":
            caller.sendto(data, ("127.0.0.1", 5061))
        else:
            callee.sendto(data, ("127.0.0.1", SIP_PORT))
        print(f"    -> {payload.split(chr(13)+chr(10), 1)[0]}", flush=True)
        # After ACK, send the RTP media for this call.
        if direction == "req" and payload.startswith("ACK") and rtp_count:
            for p in rtp_packets(rtp_count, ssrc=0x1111 + (index & 0xFFFF)):
                caller_rtp.sendto(p, ("127.0.0.1", CALLEE_RTP))
                if paced_rtp:
                    time.sleep(0.02)  # 20ms cadence → realistic jitter/MOS
            for p in rtp_packets(rtp_count, ssrc=0x2222 + (index & 0xFFFF)):
                callee_rtp.sendto(p, ("127.0.0.1", CALLER_RTP))
                if paced_rtp:
                    time.sleep(0.02)
            print(f"    .. sent {rtp_count}x2 RTP packets", flush=True)
        time.sleep(msg_delay)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calls", type=int, default=1,
                    help="number of calls (ignored when --loop is set)")
    ap.add_argument("--rtp", type=int, default=50, help="RTP packets per direction")
    ap.add_argument("--delay", type=float, default=0.05, help="seconds between SIP msgs")
    ap.add_argument("--loop", action="store_true",
                    help="run continuously until interrupted (simulates a busy PBX)")
    ap.add_argument("--gap", type=float, default=1.0,
                    help="seconds between calls in --loop mode")
    ap.add_argument("--paced-rtp", action="store_true",
                    help="pace RTP at 20ms/packet for realistic jitter/MOS")
    args = ap.parse_args()

    sockets = (
        sip_socket(SIP_PORT),
        sip_socket(5061),  # callee UAS on a distinct port to avoid self-recv
        sip_socket(CALLER_RTP),
        sip_socket(CALLEE_RTP),
    )

    try:
        if args.loop:
            print("[loop] continuous call generation — Ctrl+C to stop", flush=True)
            index = 0
            while True:
                emit_call(sockets, index, args.rtp, args.delay, args.paced_rtp)
                index += 1
                time.sleep(args.gap)
        else:
            for c in range(args.calls):
                emit_call(sockets, c, args.rtp, args.delay, args.paced_rtp)
                time.sleep(0.2)
            print("done.", flush=True)
    except KeyboardInterrupt:
        print("\n[loop] stopped.", flush=True)
    finally:
        for s in sockets:
            s.close()

if __name__ == "__main__":
    main()
