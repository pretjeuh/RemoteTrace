# Changelog

All notable changes to this project will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2.1.0] - 2026-07-04

### Added
- **Single-stream mirror** (`trace.sh`): in Wireshark output mode (`-O wireshark`), the live PCAP is tee'd into `~/.remotetrace/mirror-<timestamp>.pcap` while Wireshark streams from it. One SSH, one tcpdump — no second remote session.
- **VoIP Analyzer toggle**: pressing `a` + Enter during a Wireshark capture starts/stops the analyzer by tailing the mirror file. Fully reversible.
- **New output modes** (`trace.sh`): `-O both` (Wireshark live + VoIP Analyzer live, PCAP auto-saved, post-capture report) and `-O web` (VoIP Analyzer web dashboard with SSE live charts, browser auto-opens).
- **`-o <file>`** flag: save raw PCAP alongside any output mode.
- **`-n <port>`** flag: configure web dashboard port (default 7654).
- **VoIP Analyzer auto-detection** from PATH or `~/Downloads/claude/voip-analyser`.
- **State file** `~/.remotetrace/state` with `mirror_file`, `trace_pid`, `web_port`, `started_at`, `analyzer_pid` — consumed by external controllers.
- **`voip-mirror-toggle`** helper: `voip-mirror-toggle on|off|toggle|status` controls the analyzer against the active capture from any shell.
- **SwiftBar menubar plugin** (`menubar/RemoteTrace.5s.sh`): macOS menubar shows capture state and lets the user toggle the analyzer + open the dashboard without touching the terminal.
- **`EXTENSIONS.md`** — design doc covering alternative mirror strategies (FIFO drain, dumpcap ringbuffer) and GUI options (SwiftBar, native SwiftUI, Tauri) for future versions.

### Changed
- Wireshark mode startup message mentions "mirror PCAP" and "toggle" instead of "second capture".
- `trace.sh` bumped to v2.1.0 (previously versioned independently as 1.x; now aligned with the repo-wide version).

---

## [2.0.0] - 2026-06-07

### Added
- **`RemoteTrace.ps1`** now fully generic — no hardcoded hosts, users, or credentials

### Changed
- `RemoteTrace.ps1` jump/target fields start blank; user fills in their own infrastructure
- Added per-hop auth mode selector for both jump server and target host:
  - `Password` — SSH_ASKPASS mechanism, no interactive prompt
  - `SSH Key (Agent)` — agent forwarding (`-A`), no password needed
  - `Key File` — browse button opens file picker, passes `-i <path>` to ssh
- Capture Filter now defaults to empty (capture all) in the public build
- Both scripts bumped to v2.0.0

---

## [1.0.1] - 2026-06-04

### Changed
- Removed auto-discovery mode ("Jump Server + Auto-Discovery") from both `trace.sh` and `RemoteTrace.ps1` — this feature relied on a proprietary internal script and is not suitable for public use
- Jump host mode now always requires explicit target host, user, port, and credentials
- `RemoteTrace.ps1` connection mode dropdown simplified to "Jump Server" and "Direct Connection"
- All Dutch-language status/error messages in `trace.sh` translated to English

---

## [1.0.0] - 2026-06-04

### Added
- **`trace.sh`** — complete Linux/macOS CLI rewrite:
  - Filter quoting fully handled internally — any BPF filter works regardless of spaces, parentheses, or special characters
  - Added `--` separator before BPF filter so filters starting with `-` are never misinterpreted as tcpdump flags
  - All SSH invocations use bash arrays (`"${SSH_OPTS[@]}"`) — no `eval`, no word-splitting surprises
  - macOS/BSD compatible: interface detection uses `ifconfig` on macOS, `ip` on Linux
  - Output command (`-O`) uses safe array invocation — analyzer paths with spaces work correctly
  - Jump-host nested `sshpass` password is properly shell-escaped via `_remote_escape()`
  - `sshpass` availability checked before use, with platform-specific install instructions on failure
  - Version string (`VERSION=1.0.0`) in script header
- **`RemoteTrace.ps1`** — complete Windows rewrite:
  - Replaced `plink.exe` + `cmd.exe` with built-in `ssh.exe` (OpenSSH, ships with Windows 10 1803+)
  - Binary-safe pipe: `System.Diagnostics.Process` wires `ssh.exe` stdout directly to Wireshark stdin as raw bytes — eliminates cmd.exe text-mode PCAP corruption
  - SSH `-J` ProxyJump replaces nested `sshpass` chains
  - Passwords handled via temporary `SSH_ASKPASS` helper (written to `%TEMP%`, deleted immediately after connection)
  - Wireshark auto-discovery checks all common install paths
  - `ssh.exe` auto-discovery with error dialog and install instructions if missing
  - Zero extra dependencies on Windows 10/11 — no plink, no Cygwin, no sshpass
  - Version string (`$VERSION = "1.0.0"`) in script header
- **`README.md`** — full documentation with usage examples, option tables, BPF filter tips, SSH key setup guide, release notes
- **`CHANGELOG.md`** — this file
- **`CLAUDE.md`** — updated project guidance for future development

### Changed
- `trace.sh`: removed `eval`-based tcpdump execution in direct mode; commands now built as proper arrays
- `trace.sh`: `ip link show` for interface detection replaced with OS-aware `_iface_exists()` helper

---

## [pre-1.0] - 2025 and earlier

- `trace.sh`: initial bash implementation with direct SSH, jump host, and VoIP analyzer output modes
- `RemoteTrace.ps1`: Windows GUI using plink.exe and cmd.exe pipeline
- `Trace_all`: original VBScript tool from 2011 using plink.exe directly
