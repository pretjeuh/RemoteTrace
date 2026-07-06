# RemoteTrace + VoIP Analyzer

Stream remote `tcpdump` output directly into Wireshark, a VoIP quality analyzer, or both — over SSH, through a jump host, with keys or passwords.

Originally a VBScript one-liner from 2011 (`Trace_all`), rewritten over the years into a robust cross-platform tool.

---

## How it works

```
[remote host]                [your machine]
 tcpdump -w -   ──SSH──►   Wireshark / VoIP Analyzer / both
```

`tcpdump` runs on the remote host and writes raw PCAP to stdout. The SSH pipe delivers those bytes to your local Wireshark and/or VoIP analyzer in real time. No temp files, no buffering.

---

## Platforms

| Tool | Platform | Dependencies |
|------|----------|-------------|
| `trace.sh` | Linux / macOS | `ssh` (system), `tcpdump` (remote), `wireshark` (local), `sshpass` (password auth only) |
| `RemoteTrace.ps1` | Windows 10/11 | `ssh.exe` (built-in), `Wireshark` |

---

## trace.sh — Linux / macOS

### Install

```bash
chmod +x trace.sh
# Optional: make globally available
ln -s $(pwd)/trace.sh /usr/local/bin/remotetrace
```

### All options

```
trace.sh -h <host> -i <interface> -f <filter> [options]
```

#### Required (remote mode)

| Flag | Description |
|------|-------------|
| `-h <host>` | Target host where tcpdump runs |
| `-i <interface>` | Network interface on the target (e.g. `eth0`, `ens18`) |
| `-f <filter>` | tcpdump BPF filter (e.g. `'udp port 5060'`) |

#### Connection

| Flag | Description |
|------|-------------|
| `-u <user>` | SSH username for target host |
| `-p <port>` | SSH port (default: 22) |
| `-w <password>` | SSH password — uses `sshpass`, must be installed |
| `-P` | Prompt for passwords interactively (more secure than `-w`) |
| `-k <key>` | Path to SSH private key |
| `-A` | Enable SSH agent forwarding |
| `-s` | Use sudo for tcpdump on the remote host |
| `-D` | Direct mode — run tcpdump on this local machine |

#### Jump host (bastion)

| Flag | Description |
|------|-------------|
| `-J <host>` | Jump host address |
| `-U <user>` | SSH username for jump host |
| `-W <password>` | SSH password for jump host |
| `-R <port>` | SSH port for jump host (default: 22) |

#### Output

| Flag | Description |
|------|-------------|
| `-O <mode>` | `wireshark` (default), `analyzer`, `both`, or `web` |
| `-o <file>` | Save raw capture to a PCAP file (works alongside any `-O` mode) |
| `-n <port>` | Web dashboard port (default: 7654, used with `-O web`) |
| `-V <path>` | Path to VoIP analyzer if not auto-detected |

---

### Connection examples

#### Direct SSH — SSH key

```bash
./trace.sh \
  -h 192.168.1.10 -u root -p 22 -k ~/.ssh/id_rsa \
  -i eth0 -f 'udp'
```

#### Direct SSH — SSH agent (key already loaded via ssh-add)

```bash
# No -k flag needed when the key is in your agent
./trace.sh \
  -h 192.168.1.10 -u root -p 22 \
  -i eth0 -f 'udp'
```

#### Direct SSH — password (inline)

```bash
./trace.sh \
  -h 192.168.1.10 -u root -p 22 -w mypassword \
  -i eth0 -f 'udp'
```

#### Direct SSH — interactive password prompt

```bash
./trace.sh \
  -h 192.168.1.10 -u root -p 22 -P \
  -i eth0 -f 'udp'
```

#### Via jump host — SSH key

```bash
./trace.sh \
  -J bastion.example.com -U jumpuser -k ~/.ssh/id_rsa \
  -h 10.0.0.5 -u root -p 22 \
  -i eth0 -f 'udp'
```

#### Via jump host — passwords

```bash
./trace.sh \
  -J bastion.example.com -U jumpuser -W jumppass \
  -h 10.0.0.5 -u root -p 22 -w targetpass \
  -i eth0 -f 'udp'
```

#### Via jump host — interactive password prompts

```bash
./trace.sh \
  -J bastion.example.com -U jumpuser -P \
  -h 10.0.0.5 -u root -p 22 \
  -i eth0 -f 'udp'
```

#### Direct mode (capture on local machine)

```bash
./trace.sh -D -i en0 -f 'port 80'

# With sudo
./trace.sh -D -s -i en0 -f 'udp'
```

---

### Output modes

#### Wireshark (default)

Live capture opened in Wireshark. Full packet inspection, decode, and follow stream.

```bash
./trace.sh -h 10.0.0.5 -u root -p 22 -k ~/.ssh/id_rsa \
  -i ens18 -f 'udp port 5060 or udp portrange 10000-65000' \
  -O wireshark
```

**While Wireshark is running**, the live capture is also mirrored to `~/.remotetrace/mirror-<timestamp>.pcap`. Press **`a` + Enter** in the terminal to toggle the VoIP Analyzer web dashboard — it reads from the mirror file, so there is **no second SSH session** against the remote host. Press `a` + Enter again to stop the analyzer. Wireshark keeps running undisturbed; you get deep packet inspection in Wireshark and live MOS/jitter metrics in the dashboard simultaneously, from a single tcpdump.

The active capture writes its state to `~/.remotetrace/state` so external controllers can toggle the analyzer without touching the terminal — see `voip-mirror-toggle` and the SwiftBar menubar plugin under `menubar/`.

Save a copy of the capture at the same time:

```bash
./trace.sh -h 10.0.0.5 -u root -p 22 -k ~/.ssh/id_rsa \
  -i ens18 -f 'udp' \
  -O wireshark -o /tmp/capture.pcap
```

#### VoIP Analyzer — terminal display

Live stream table in the terminal with MOS, jitter, packet loss, and codec per stream.

```bash
./trace.sh -h 10.0.0.5 -u root -p 22 -k ~/.ssh/id_rsa \
  -i ens18 -f 'udp portrange 10000-10100 or udp port 5060' \
  -O analyzer
```

#### VoIP Analyzer — web dashboard

Opens a browser at `http://localhost:7654` with live charts and stream table.

```bash
./trace.sh -h 10.0.0.5 -u root -p 22 -k ~/.ssh/id_rsa \
  -i ens18 -f 'udp portrange 10000-10100 or udp port 5060' \
  -O web
```

Custom port:

```bash
  -O web -n 8080
```

#### Wireshark + VoIP Analyzer simultaneously (`-O both`)

Wireshark gets the live stream for deep packet inspection **and** the VoIP analyzer shows live metrics in the terminal at the same time. The capture is also saved to a PCAP file automatically, and a full post-capture quality report is printed when the capture ends.

```bash
./trace.sh -h 10.0.0.5 -u root -p 22 -k ~/.ssh/id_rsa \
  -i ens18 -f 'udp portrange 10000-10100 or udp port 5060' \
  -O both
```

Specify where to save the PCAP (auto-saved to `/tmp/` if not set):

```bash
  -O both -o ~/captures/call_$(date +%Y%m%d_%H%M%S).pcap
```

---

### BPF filter tips

Filters are passed safely to the remote tcpdump regardless of spaces or special characters:

```bash
-f 'port 80 or port 443'
-f 'udp portrange 10000-20000'
-f 'not port 22'
-f '(host 10.0.0.1 and port 5060)'
-f 'udp portrange 10000-10100 or udp port 5060'   # VoIP only
```

---

## RemoteTrace.ps1 — Windows

### Requirements

- Windows 10 (1803+) or Windows 11 — `ssh.exe` is built-in
- [Wireshark](https://www.wireshark.org/) installed

No plink, no Cygwin, no extra downloads.

### Run

```powershell
.\RemoteTrace.ps1
```

A GUI appears. Fill in connection details and click **Start**. Wireshark opens automatically.

### Connection modes

| Mode | Description |
|------|-------------|
| Direct Connection | SSH directly to the target host |
| Jump Server | SSH through a bastion host to the target |

### Authentication options (per hop)

Both the jump host and target have independent auth:

| Mode | Description |
|------|-------------|
| Password | Delivered via `SSH_ASKPASS` — no interactive prompt needed |
| SSH Key (Agent) | Uses your running SSH agent, passes `-A` to forward |
| Key File | Browse to a `.pem`/`.ppk`/`.key` file, passes `-i <path>` |

### How Windows piping works

`RemoteTrace.ps1` uses `System.Diagnostics.Process` to wire `ssh.exe` stdout directly to Wireshark's stdin as a raw byte stream, bypassing `cmd.exe` entirely. This eliminates the text-mode `\r\n` translation that corrupts PCAP data.

---

## SSH key authentication (recommended)

Password auth requires `sshpass` on Linux/macOS. SSH keys work everywhere without extra tools:

```bash
# Generate a key
ssh-keygen -t ed25519

# Copy to target host
ssh-copy-id root@192.168.1.1

# Use with trace.sh
./trace.sh -h 192.168.1.1 -i eth0 -f 'port 443' -u root -k ~/.ssh/id_rsa -p 22
```

`sshpass` install (only needed for `-w` password mode):
```bash
# macOS
brew install hudochenkov/sshpass/sshpass
# Debian/Ubuntu
apt install sshpass
```

---

## VoIP Analyzer

### Installation

```bash
cd voip-analyser
pip install -r requirements.txt
```

### Analyze a saved PCAP file

```bash
python -m voip_analyzer analyze capture.pcap

# JSON output
python -m voip_analyzer analyze capture.pcap --output json

# Verbose debug info
python -m voip_analyzer analyze capture.pcap -v
```

### Live capture — terminal display

Reads PCAP from stdin and shows a live-updating stream table.

```bash
tcpdump -i ens18 -U -s 0 -w - 'udp portrange 10000-65000 or udp port 5060' \
  | python -m voip_analyzer live
```

| Option | Default | Description |
|--------|---------|-------------|
| `-u` / `--update-interval` | 2.0s | How often the display refreshes |
| `-w` / `--window` | 60s | Rolling window for metrics calculation |
| `-t` / `--stream-timeout` | 30s | Seconds before an inactive stream is marked complete |

### Live capture — web dashboard

```bash
tcpdump -i ens18 -U -s 0 -w - 'udp portrange 10000-65000 or udp port 5060' \
  | python -m voip_analyzer web --port 7654
```

Open **http://localhost:7654**:

- **Live Capture tab** — real-time stream table, MOS over time chart, jitter chart
- **Upload PCAP tab** — drag-and-drop a `.pcap` or `.pcapng` for post-capture analysis

### Validate a PCAP file

```bash
python -m voip_analyzer validate capture.pcap
```

### Compare two PCAP files

```bash
python -m voip_analyzer compare before.pcap after.pcap
```

---

## Metrics

| Metric | What it means |
|--------|--------------|
| **MOS** | Mean Opinion Score 1–5. ≥4.0 excellent, 3.5–4.0 good, 3.0–3.5 fair, <3.0 poor |
| **R-Factor** | ITU-T E-model score 0–100. ≥80 good, 60–80 acceptable, <60 poor |
| **Jitter avg/max** | Variation in packet arrival time in milliseconds |
| **Loss %** | RTP packet loss based on sequence number gaps |
| **Codec** | Detected audio codec (G.711 µ-law/a-law, G.722, G.729, Opus, etc.) |
| **Duration** | Length of the RTP stream in seconds |

---

## License

MIT

---

## Release notes

### [2.2.1] - 2026-07-06

#### Fixed
- **Live SIP calls now appear in the Calls tab** — the `tshark` SIP dissector runs line-buffered (`-l`) in stream mode, so SIP records surface immediately instead of block-buffering until ~1 MB of pcap has passed. Validated end-to-end against a live `tcpdump → analyzer` pipeline.
- RTP packet-loss wraparound (16-bit sequence wrap no longer reports phantom lost packets)
- Live packet-loss count that silently stayed 0 (swallowed `KeyError` on the loss result)
- `-O web` browser auto-open under `sudo` now opens in the invoking user's session

#### Added
- `voip-analyzer/tools/sip_gen.py` — loopback SIP call generator for testing live capture (no root, no `sipp`/`tcpreplay`)

### [2.2.0] - 2026-07-04

#### Added
- **Bundled VoIP Analyzer** (`voip-analyzer/`) — vendored in-repo; `trace.sh` finds it automatically
- **SIP call analysis** — a **Calls** tab with per-call state (Trying/Ringing/Answered/Cancelled/Failed/Ended), response codes, signaling duration, and an expandable ladder diagram
- **SIP↔RTP correlation** — SDP media endpoints matched to measured RTP streams so each call carries its own audio-quality metrics
- **Live SIP + RTP together** — one pcap stream fanned out to both the RTP parser and a `tshark` SIP dissector via a liveness-favoring bounded-queue tee
- SIP analysis requires `tshark` (Wireshark CLI); without it the analyzer runs RTP-only (`VOIP_TSHARK_PATH` overrides the binary)

### [2.1.0] - 2026-07-04

#### Added
- **Single-stream mirror**: Wireshark mode (`-O wireshark`) tees the live PCAP to `~/.remotetrace/mirror-<timestamp>.pcap`. Pressing **`a` + Enter** toggles the VoIP Analyzer by tailing the mirror file — one SSH, one tcpdump, two consumers.
- `-O both` mode: Wireshark live + VoIP Analyzer live simultaneously; PCAP auto-saved; post-capture report on exit
- `-O web` mode: VoIP Analyzer web dashboard with SSE live charts, browser auto-opens
- `-o <file>` flag: save raw PCAP alongside any output mode
- `-n <port>` flag: configure web dashboard port (default 7654)
- VoIP Analyzer auto-detection from PATH or `~/Downloads/claude/voip-analyser`
- **State file** `~/.remotetrace/state` with the active capture's mirror path, pids, and web port — consumed by external controllers.
- **`voip-mirror-toggle`** helper: `on|off|toggle|status` against the active capture from any shell.
- **SwiftBar menubar plugin** (`menubar/RemoteTrace.5s.sh`): toggle the analyzer and open the dashboard from the macOS menubar.
- **`EXTENSIONS.md`**: design doc for alternative mirror strategies (FIFO drain, dumpcap ringbuffer) and GUI options (SwiftBar, SwiftUI menubar, Tauri) for future versions.

### [1.0.1] - 2026-06-04

#### Changed
- Removed auto-discovery mode (relied on proprietary internal script)
- Jump host mode requires explicit target host, user, port, and credentials
- All status/error messages translated to English

### [1.0.0] - 2026-06-04

#### Added
- `trace.sh` complete rewrite: safe BPF filter quoting, SSH array invocations, macOS/BSD compatible interface detection
- `RemoteTrace.ps1` complete Windows rewrite: `ssh.exe` replaces plink, binary-safe pipe, `SSH_ASKPASS` password handling, Wireshark auto-discovery
