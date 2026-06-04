# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RemoteTrace streams remote `tcpdump` output directly into Wireshark (or a VoIP analyzer) over SSH. It supports Linux, macOS, and Windows with no extra dependencies beyond what the OS provides.

## Repository

https://github.com/pretjeuh/RemoteTrace

## Architecture

| File | Platform | Purpose |
|------|----------|---------|
| `trace.sh` | Linux / macOS | CLI bash script — direct SSH, jump host, VoIP analyzer output |
| `RemoteTrace.ps1` | Windows 10/11 | PowerShell GUI — uses built-in ssh.exe, binary-safe pipe to Wireshark |
| `Trace_all` | Windows (legacy) | Original VBScript from 2011, kept for reference |

### Connection modes (both tools)
- **Direct Connection** — SSH straight to target host
- **Jump Server + Manual Target** — SSH through bastion, manual target IP
- **Jump Server + Auto-Discovery** — SSH through bastion, auto-discover target via `f <name>` script

## Key design decisions

### Why ssh.exe instead of plink on Windows
`cmd.exe` pipes operate in text mode and corrupt binary PCAP data (`\r\n` translation). `RemoteTrace.ps1` uses `System.Diagnostics.Process` to wire `ssh.exe` stdout directly to Wireshark stdin as a raw byte stream, bypassing cmd.exe entirely.

### Filter quoting
BPF filters are passed through `_remote_escape()` (bash) / `ConvertTo-RemoteEscaped` (PowerShell) and placed after `--` in the tcpdump invocation. Any filter — including those with spaces, parentheses, or special characters — works correctly without the user needing to worry about escaping.

### SSH invocation (bash)
All SSH calls use bash arrays (`SSH_OPTS=(...); ssh "${SSH_OPTS[@]}" ...`) — never string concatenation or `eval`. This prevents word-splitting and handles edge cases in passwords/paths.

## Dependencies

### trace.sh (Linux/macOS)
- `ssh` — system
- `tcpdump` — on the remote target host
- `wireshark` — local (`brew install --cask wireshark` / `apt install wireshark`)
- `sshpass` — only needed for password auth (`brew install hudochenkov/sshpass/sshpass` / `apt install sshpass`)

### RemoteTrace.ps1 (Windows)
- `ssh.exe` — built-in on Windows 10 1803+ and Windows 11
- `Wireshark.exe` — https://www.wireshark.org/

## Releases

Whenever a change is committed and worth releasing, always do the full release flow without being asked:

1. Update `CHANGELOG.md` with the new version entry (Keep a Changelog format)
2. Update version string in `trace.sh` (`VERSION=x.y.z`) and `RemoteTrace.ps1` (`$VERSION = "x.y.z"`)
3. Update `## Release notes` section in `README.md`
4. Commit the changes
5. Tag the commit (`git tag vX.Y.Z`)
6. Push commits and tag (`git push && git push origin vX.Y.Z`)
7. Create a GitHub release: `gh release create vX.Y.Z --title "vX.Y.Z" --notes "..."`

Use semantic versioning: patch (x.y.Z) for small fixes, minor (x.Y.0) for new features, major (X.0.0) for breaking changes.
