# VoIP Analyzer

Analyzes VoIP call quality from PCAP files or a live capture stream. RTP stream
metrics (jitter, packet loss, MOS, R-factor, codec) plus SIP call analysis
(call list, per-call state, ladder diagrams, and SIP↔RTP correlation).

Bundled with [RemoteTrace](../README.md): `trace.sh -O analyzer` (or the `a`
toggle during a Wireshark capture) pipes the live packet stream in here.

## Usage

    python3 -m voip_analyzer analyze capture.pcap        # static RTP report
    python3 -m voip_analyzer web --port 7654             # live dashboard (stdin)
    tcpdump -U -w - 'udp' | python3 -m voip_analyzer web # live from a pipe

## Requirements

- Python 3.10+, `scapy`, `flask`, `click`, `rich`, `numpy` (see requirements.txt)
- `tshark` (Wireshark CLI) — optional; enables SIP call analysis. Without it the
  analyzer runs RTP-only. Override the binary with `VOIP_TSHARK_PATH`.
