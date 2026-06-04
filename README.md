# RemoteTrace

Stream remote `tcpdump` output directly into Wireshark (or a VoIP analyzer) over SSH — from Linux, macOS, or Windows, with no extra dependencies beyond what your OS already provides.

Originally a VBScript one-liner from 2011 (`Trace_all`), rewritten over the years into a robust cross-platform tool.

---

## How it works

```
[remote host]                [your machine]
 tcpdump -w -   ──SSH──►   Wireshark / VoIP analyzer
```

`tcpdump` runs on the remote host and writes raw PCAP to stdout. The SSH pipe delivers those bytes to your local Wireshark in real time. No temp files, no buffering.

---

## Platforms

| Tool | Platform | Dependencies |
|------|----------|-------------|
| `trace.sh` | Linux / macOS | `ssh` (system), `tcpdump` (remote), `wireshark` (local), `sshpass` (only for password auth) |
| `RemoteTrace.ps1` | Windows 10/11 | `ssh.exe` (built-in), `Wireshark` |

---

## trace.sh — Linux / macOS

### Install

```bash
git clone https://github.com/pretjeuh/RemoteTrace.git
chmod +x RemoteTrace/trace.sh
```

### Usage

```bash
# Direct: capture on this machine
./trace.sh -D -i eth0 -f 'port 80'

# Remote: direct SSH with key
./trace.sh -h 192.168.1.1 -i eth0 -f 'port 443' -u root -k ~/.ssh/id_rsa -p 22

# Remote: direct SSH with password
./trace.sh -h 192.168.1.1 -i eth0 -f 'port 443' -u root -w mypassword -p 22

# Via jump host (auto-discover target IP + password via 'f' script)
./trace.sh -h myserver -i eth0 -f 'udp' -J bastion.example.com -U jumpuser -W jumppass

# Via jump host (manual target)
./trace.sh -h 10.0.0.5 -i eth0 -f 'port 5060' -J bastion.example.com -U jumpuser -W jumppass -u root -p 22

# Pipe to VoIP analyzer instead of Wireshark
./trace.sh -h pbx.example.com -i eth0 -f 'udp portrange 10000-20000' -u root -k ~/.ssh/id_rsa -p 22 -O analyzer
```

### Options

| Option | Description |
|--------|-------------|
| `-h <host>` | Target host (where tcpdump runs) |
| `-i <iface>` | Network interface on target |
| `-f <filter>` | tcpdump BPF filter |
| `-u <user>` | SSH user for target |
| `-w <pass>` | SSH password for target |
| `-p <port>` | SSH port (default: 22) |
| `-k <key>` | SSH private key path |
| `-A` | SSH agent forwarding |
| `-P` | Prompt for passwords interactively |
| `-D` | Direct mode — run tcpdump locally |
| `-s` | Use sudo for tcpdump |
| `-J <host>` | Jump / bastion host |
| `-U <user>` | Jump host SSH user |
| `-W <pass>` | Jump host SSH password |
| `-R <port>` | Jump host SSH port (default: 22) |
| `-O <tool>` | Output: `wireshark` (default) or `analyzer` |
| `-V <path>` | Path to VoIP analyzer binary |

### BPF filter tips

Filters are passed safely to the remote tcpdump regardless of spaces, parentheses, or special characters:

```bash
-f 'port 80 or port 443'
-f 'udp portrange 10000-20000'
-f 'not port 22'
-f '(host 10.0.0.1 and port 5060)'
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

A GUI appears. Fill in your connection details and click **Start**. Wireshark opens automatically and begins receiving packets.

### Connection modes

| Mode | Description |
|------|-------------|
| Jump Server + Auto-Discovery | SSH to jump host, run `f <name>` to discover target IP + password automatically |
| Jump Server + Manual Target | SSH to jump host, then to a manually specified target |
| Direct Connection | SSH directly to target host |

### How Windows piping works

Previous versions used `plink.exe` piped through `cmd.exe`, which corrupts binary PCAP data (text-mode `\r\n` translation). `RemoteTrace.ps1` now uses `System.Diagnostics.Process` to wire `ssh.exe` stdout directly to Wireshark's stdin as a raw byte stream — no corruption possible.

---

## SSH key authentication (recommended)

Password authentication requires `sshpass` on Linux/macOS (not needed on Windows). SSH key authentication works everywhere without extra tools:

```bash
# Generate a key if you don't have one
ssh-keygen -t ed25519

# Copy it to your target host
ssh-copy-id root@192.168.1.1

# Use it with trace.sh
./trace.sh -h 192.168.1.1 -i eth0 -f 'port 443' -u root -k ~/.ssh/id_rsa -p 22
```

---

## VoIP analyzer integration (trace.sh)

```bash
# Real-time VoIP quality on a remote PBX
./trace.sh -h pbx.example.com -i eth0 -f 'udp portrange 10000-20000' \
  -u root -k ~/.ssh/id_rsa -p 22 -O analyzer
```

Requires the [voip-analyser](https://github.com/pretjeuh/voip-analyser) tool. The script auto-detects it if installed, or specify the path with `-V`.

---

## License

MIT

---

## Release notes

### [1.0.0] - 2026-06-04

#### Added
- **`trace.sh`** — complete Linux/macOS CLI rewrite for v1.0.0:
  - Filter quoting fully handled internally — any BPF filter works regardless of spaces, parentheses, or special characters
  - Added `--` separator before BPF filter so filters starting with `-` can't be misinterpreted as tcpdump flags
  - All SSH invocations use arrays (`"${SSH_OPTS[@]}"`) — no more `eval`, no word-splitting surprises
  - macOS/BSD compatible: interface detection now uses `ifconfig` on macOS and `ip` on Linux
  - Output command (`-O`) uses safe array invocation — spaces in analyzer paths work correctly
  - Password for nested jump-host `sshpass` is now properly shell-escaped before embedding
  - `sshpass` availability is checked before use, with install instructions on failure
- **`RemoteTrace.ps1`** — complete Windows rewrite for v1.0.0:
  - Replaced `plink.exe` + `cmd.exe` with built-in `ssh.exe` (OpenSSH, ships with Windows 10 1803+)
  - Binary-safe pipe: `System.Diagnostics.Process` wires `ssh.exe` stdout directly to Wireshark's stdin as a raw byte stream — eliminates the `cmd.exe` text-mode PCAP corruption that was the primary Windows failure mode
  - SSH `-J` ProxyJump replaces nested `sshpass` chains — cleaner, more reliable
  - Passwords handled via temporary `SSH_ASKPASS` helper script (written to `%TEMP%`, deleted immediately after connection)
  - Wireshark auto-discovery checks all common install paths
  - `ssh.exe` auto-discovery with clear error message and install instructions if missing
  - Removed all `plink.exe` dependency — zero extra downloads required on Windows 10/11

#### Improved (both platforms)
- Version string (`VERSION=1.0.0`) embedded in both tools
- Consistent error messages with actionable fix instructions
