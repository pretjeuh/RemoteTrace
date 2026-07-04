# RemoteTrace — Extensions & Future Versions

Living document. Tracks options we considered, what we picked first, and what we want to revisit. Each section is independent — pick any and build a version branch from it.

---

## Goal

When Wireshark is live-streaming traffic from a remote host over SSH, give the user a **toggle** to also feed the same packet stream into the VoIP Analyzer — **without** opening a second SSH/tcpdump session on the remote host.

Constraints:
- Must work over plain SSH and via jump hosts.
- mac/linux first. Windows port later.
- One remote tcpdump only — duplicate the stream locally.

---

## Mirror strategies

Once `wireshark -k -i -` starts reading from a pipe, that pipe has **one reader**. Duplication has to be in place before the stream starts, or accept a brief re-init. Four real options:

### Option A — `tee` to a live PCAP file *(PICKED FIRST)*

```bash
ssh ... tcpdump -U -w - ... \
  | tee /tmp/remotetrace-live.pcap \
  | wireshark -k -i -
```

Analyzer toggle = start/stop a tail:

```bash
tail -c +0 -f /tmp/remotetrace-live.pcap | python -m voip_analyzer live
# or web mode:
tail -c +0 -f /tmp/remotetrace-live.pcap | python -m voip_analyzer web --port 7654
```

- **Pros:** Dead simple. Toggle is start/stop a process. No back-pressure risk. File doubles as a recording.
- **Cons:** Disk writes (negligible for VoIP-volume traffic). File grows — needs rotation for very long captures.
- **Status:** Shipped.
- **Version target:** `trace.sh v2.1.0`

---

### Option B — `tee` to two FIFOs with always-on drain

```bash
FIFO_WS=/tmp/rt_ws.fifo
FIFO_VA=/tmp/rt_va.fifo
mkfifo "$FIFO_WS" "$FIFO_VA"

# Always-on drain so analyzer FIFO never back-pressures when toggle is OFF
cat "$FIFO_VA" > /dev/null &
DRAIN_PID=$!

wireshark -k -i "$FIFO_WS" &

ssh ... tcpdump -U -w - ... \
  | tee "$FIFO_WS" > "$FIFO_VA"
```

Toggle: kill the drain `cat`, replace with `python -m voip_analyzer live < "$FIFO_VA"`. Toggle off: kill analyzer, restart drain `cat`.

- **Pros:** No disk write. Pure stream duplication.
- **Cons:** Drain process is critical — if it dies, tcpdump back-pressures and Wireshark stalls too. Switchover between drain and analyzer has a millisecond hole where packets can be lost. FIFO writers need careful ordering on startup or both processes block.
- **Status:** Future version. Worth trying once Option A is shipped, for the "no disk" property.
- **Version target:** `trace.sh v2.2.0` (experimental branch)

---

### Option C — `dumpcap` ringbuffer + Wireshark live-read + analyzer tail

```bash
# dumpcap captures from SSH stdin to a ringbuffer
ssh ... tcpdump -U -w - ... \
  | dumpcap -i - -b filesize:10240 -b files:10 -w /tmp/rt-ring.pcap

# Wireshark reads the ringbuffer live (File → Open + auto-refresh, or -k -i with named pipe)
# Analyzer reads the same ringbuffer files
```

- **Pros:** Uses Wireshark-native tooling. Built-in rotation. Analyzer can re-attach without disrupting Wireshark.
- **Cons:** Wireshark's live-read of an external file is clunky compared to direct pipe. Ringbuffer rotation timing complicates analyzer's reader (needs to follow file rotation).
- **Status:** Backup if Option A's growing file becomes a problem.
- **Version target:** `trace.sh v2.3.0` (experimental)

---

### Option D — Source-side replication via virtual interface

Replicate at the remote side: tcpdump writes to a dummy interface, two separate captures read from it.

- **Pros:** Clean source-side fan-out.
- **Cons:** Requires kernel module loading on remote (`dummy`, `ip tuntap`), root privileges, persistent state. Defeats the "just SSH" simplicity.
- **Status:** Not pursuing. Documented for completeness.

---

## GUI strategies (mac first)

CLI works but you can't toggle mid-capture cleanly. Need a tray/menubar control surface.

### Option G1 — SwiftBar / xbar menubar plugin *(PICKED FIRST)*

A bash script that prints menu items to stdout. SwiftBar (or xbar) renders them in the macOS menubar.

```bash
#!/bin/bash
# RemoteTrace menubar plugin

echo "RemoteTrace"
echo "---"
if pgrep -f "trace.sh" >/dev/null; then
  echo "Capture running"
  if pgrep -f "voip_analyzer" >/dev/null; then
    echo "Disable VoIP Analyzer | bash=/usr/local/bin/voip-mirror-toggle param1=off terminal=false"
  else
    echo "Enable VoIP Analyzer | bash=/usr/local/bin/voip-mirror-toggle param1=on terminal=false"
  fi
  echo "Open dashboard | href=http://localhost:7654"
  echo "Stop capture | bash=/usr/local/bin/remotetrace-stop terminal=false"
else
  echo "Idle"
  echo "Start capture | bash=/Users/jeroen/Downloads/claude/RemoteTrace/trace.sh ..."
fi
```

- **Pros:** No Swift code. Pure shell. Iterates in seconds.
- **Cons:** Limited UX. No host picker form, just hardcoded entries (or sub-menus per host).
- **Status:** Implementing first.

---

### Option G2 — Native SwiftUI menubar app

A real `.app` with `MenuBarExtra` (SwiftUI). Form to pick host, BPF filter, output mode. Persistent presets. Toggle for analyzer.

- **Pros:** Clean UX. Forms, presets, notifications, settings panel.
- **Cons:** Requires Xcode, signing, distribution. Real Swift code to maintain.
- **Status:** End-state target once Option G1 proves the UX.
- **Version target:** Separate repo `RemoteTrace.app`.

---

### Option G3 — Tauri cross-platform app

Rust + web frontend. One codebase for mac + Windows.

- **Pros:** Cross-platform, modern. Solves the eventual Windows port too.
- **Cons:** Heavier dep stack. Tauri menubar/tray support is OK but not first-class.
- **Status:** Consider when Windows port becomes priority.

---

### Option G4 — Platypus shell-to-app wrapper

Wraps `trace.sh` as a `.app` with a basic launcher window.

- **Pros:** Click-to-launch from Finder. No code.
- **Cons:** No live toggle. One-shot launcher only.
- **Status:** Not pursuing for the toggle use case. Useful as a "Start" shortcut alongside SwiftBar.

---

## Windows port (later)

For when we cross that bridge:

- **Tray app:** small WPF/.NET tray app, or Tauri (see G3).
- **Capture pipe:** Windows pipe semantics differ — `tee` on Windows is via Git Bash or PowerShell `Tee-Object`. May need PowerShell rewrite of the duplication step.
- **Wireshark:** same `-k -i -` interface works on Windows.
- **SSH:** OpenSSH built into modern Windows works fine. Jump host syntax identical.

Existing Windows version `RemoteTrace.ps1` is a GUI capture launcher but does not implement the duplication-to-analyzer pattern. That's the work item for the Windows track.

---

## Version roadmap

| Version | What | Status |
|---------|------|--------|
| 2.0.0 | Public/Voclarion split of the Windows builds | Shipped |
| 2.1.0 | **Option A + Option G1** — tee-to-file mirror + SwiftBar menubar toggle | Shipped |
| 2.2.0 | Option B — FIFO drain (no disk write) experimental branch | Future |
| 2.3.0 | Option C — dumpcap ringbuffer experimental branch | Future |
| 3.0.0 | Option G2 — native SwiftUI menubar app | End-state mac |
| 3.x | Option G3 — Tauri cross-platform | When Windows is priority |

---

## How to use this doc

- Each option is a **self-contained recipe**. You can implement any of them without doing the others.
- When testing a new option, branch from current `trace.sh` and name it `trace-<option>.sh` (e.g. `trace-fifo.sh` for Option B). Don't rewrite the main script until the experiment proves out.
- Update the **Status** field per option as we learn. Add findings under a new `### Findings` subsection inside the option block.
- New ideas: add a new `### Option X — ...` section. Don't delete old options even if rejected — the rationale is useful.
