# Test tools

## `sip_gen.py` — loopback SIP call generator

Generates realistic SIP calls (and synthetic RTP) onto `127.0.0.1` using plain
UDP sockets. No root, no `sipp`/`tcpreplay` — handy for exercising the live SIP
capture path end-to-end.

Each call is a complete answered dialog:

```
INVITE (SDP) → 100 Trying → 180 Ringing → 200 OK (SDP) → ACK
             → [RTP media] → BYE → 200 OK
```

### Usage

```bash
# Generate 3 calls with 50 RTP packets/direction each
python tools/sip_gen.py --calls 3 --rtp 50 --delay 0.04
```

Options:

- `--calls N` — number of calls to generate (default 1)
- `--rtp N` — RTP packets per direction, sent after ACK (default 50; 0 = none)
- `--delay S` — seconds between SIP messages (default 0.05)

### Validating live capture

On macOS, loopback capture needs membership in the `access_bpf` group (no sudo
otherwise). Run the analyzer against a live capture, then fire the generator:

```bash
# Terminal 1 — real live pipeline (as trace.sh -O web does)
tcpdump -i lo0 -U -s 0 -w - udp | python -m voip_analyzer web --port 7654

# Terminal 2 — generate traffic
python tools/sip_gen.py --calls 3 --rtp 50
```

The dashboard's Calls tab should show the answered calls with their SIP ladders.

> Use **tcpdump** as the capture source, not `tshark -i`. tcpdump writes the
> pcap global header immediately; `tshark -i` withholds it until the first
> packet, which stalls readers that expect a header at startup.
