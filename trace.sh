#!/bin/bash

VERSION="2.2.1"
WIRESHARK_BIN="wireshark"
USE_SUDO=false
DIRECT_MODE=false
USE_SSH_KEY=false
SSH_KEY_PATH=""
SSH_AGENT_FORWARDING=false
OUTPUT_TOOL="wireshark"
ANALYZER_PATH=""
JUMP_PORT=22
PROMPT_PASSWORDS=false
SAVE_PCAP=""
WEB_PORT=7654
MIRROR_DIR="$HOME/.remotetrace"
MIRROR_FILE=""
MIRROR_STATE_FILE="$HOME/.remotetrace/state"
ANALYZER_PID=""

usage() {
  echo "RemoteTrace v$VERSION — remote tcpdump to Wireshark/analyzer"
  echo ""
  echo "Usage: $0 -h <host> -i <interface> -f <filter> [options]"
  echo ""
  echo "Required:"
  echo "  -h <host>         Target host (where tcpdump runs)"
  echo "  -i <interface>    Network interface on target"
  echo "  -f <filter>       tcpdump BPF filter"
  echo ""
  echo "Connection:"
  echo "  -u <user>         SSH user for target host"
  echo "  -w <password>     SSH password (use -P for interactive prompt)"
  echo "  -p <port>         SSH port (default: 22)"
  echo "  -k <key>          Path to SSH private key"
  echo "  -A                SSH agent forwarding"
  echo "  -P                Prompt for passwords interactively"
  echo "  -D                Direct mode — run tcpdump on this machine"
  echo "  -s                Use sudo for tcpdump"
  echo ""
  echo "Jump host:"
  echo "  -J <jump_host>    Jump/bastion host"
  echo "  -U <jump_user>    SSH user for jump host"
  echo "  -W <jump_pass>    SSH password for jump host"
  echo "  -R <jump_port>    SSH port for jump host (default: 22)"
  echo ""
  echo "Output:"
  echo "  -O <tool>         'wireshark' (default), 'analyzer', 'both', or 'web'"
  echo "  -V <path>         Path to VoIP analyzer (if not in PATH)"
  echo "  -o <file>         Save capture to PCAP file (works with any -O mode)"
  echo "  -n <port>         Web dashboard port (default: 7654, used with -O web)"
  echo ""
  echo "Examples:"
  echo "  $0 -D -i eth0 -f 'port 80'"
  echo "  $0 -h 192.168.1.1 -i eth0 -f 'udp' -u root -k ~/.ssh/id_rsa -p 22 -O analyzer"
  echo "  $0 -h 192.168.1.1 -i eth0 -f 'udp' -u root -w mypass -p 22 -O both -o capture.pcap"
  echo "  $0 -h 10.0.0.5 -i eth0 -f 'port 5060' -u root -w pass -p 22 -O web"
  echo "  $0 -h 10.0.0.5 -i eth0 -f 'udp' -J bastion.example.com -U jumpuser -W jumppass -u root -p 22"
  exit 1
}

# ---------- Argument parsing ----------

while getopts ":u:w:h:i:p:f:sJ:U:W:R:PDk:AO:V:o:n:" opt; do
  case ${opt} in
    u ) REMOTE_USER=$OPTARG ;;
    w ) SSH_PASSWORD=$OPTARG ;;
    h ) REMOTE_HOST=$OPTARG ;;
    i ) REMOTE_INTERFACE=$OPTARG ;;
    p ) SSH_PORT=$OPTARG ;;
    f ) FILTER=$OPTARG ;;
    s ) USE_SUDO=true ;;
    J ) JUMP_HOST=$OPTARG ;;
    U ) JUMP_USER=$OPTARG ;;
    W ) JUMP_PASSWORD=$OPTARG ;;
    R ) JUMP_PORT=$OPTARG ;;
    P ) PROMPT_PASSWORDS=true ;;
    D ) DIRECT_MODE=true ;;
    k ) USE_SSH_KEY=true; SSH_KEY_PATH=$OPTARG ;;
    A ) SSH_AGENT_FORWARDING=true ;;
    O ) OUTPUT_TOOL=$OPTARG ;;
    V ) ANALYZER_PATH=$OPTARG ;;
    o ) SAVE_PCAP=$OPTARG ;;
    n ) WEB_PORT=$OPTARG ;;
    \? ) echo "[FOUT] Ongeldige optie: -$OPTARG" >&2; usage ;;
    :  ) echo "[FOUT] Optie -$OPTARG vereist een argument." >&2; usage ;;
  esac
done

# ---------- Validation ----------

if [[ "$DIRECT_MODE" == true ]]; then
  [[ -z "$REMOTE_INTERFACE" || -z "$FILTER" ]] && {
    echo "[ERROR] Direct mode requires -i and -f." >&2; usage
  }
  if [[ "$USE_SUDO" != true && $EUID -ne 0 ]]; then
    echo "[WARNING] Without sudo or root, tcpdump may lack capture permissions (use -s for sudo)."
  fi
else
  [[ -z "$REMOTE_HOST" || -z "$REMOTE_INTERFACE" || -z "$FILTER" ]] && {
    echo "[ERROR] -h, -i and -f are required for remote mode." >&2; usage
  }
  if [[ -n "$JUMP_HOST" ]]; then
    [[ -z "$JUMP_USER" ]] && { echo "[ERROR] Jump host requires -U (jump user)." >&2; usage; }
    [[ -z "$JUMP_PASSWORD" && "$PROMPT_PASSWORDS" != true && "$USE_SSH_KEY" != true ]] && {
      echo "[ERROR] Jump host requires -W, -k or -P." >&2; usage
    }
    [[ -z "$REMOTE_USER" || -z "$SSH_PORT" ]] && {
      echo "[ERROR] Jump host mode requires -u (target user) and -p (target port)." >&2; usage
    }
    [[ -z "$SSH_PASSWORD" && "$PROMPT_PASSWORDS" != true && "$USE_SSH_KEY" != true ]] && {
      echo "[ERROR] Target host requires -w, -k or -P." >&2; usage
    }
  else
    [[ -z "$REMOTE_USER" || -z "$SSH_PORT" ]] && {
      echo "[ERROR] Direct SSH requires -u and -p." >&2; usage
    }
    [[ -z "$SSH_PASSWORD" && "$PROMPT_PASSWORDS" != true && "$USE_SSH_KEY" != true ]] && {
      echo "[ERROR] Direct SSH requires -w, -k or -P." >&2; usage
    }
  fi
fi

[[ "$USE_SSH_KEY" == true && ! -f "$SSH_KEY_PATH" ]] && {
  echo "[FOUT] SSH key niet gevonden: $SSH_KEY_PATH" >&2; exit 1
}

[[ "$OUTPUT_TOOL" != "wireshark" && "$OUTPUT_TOOL" != "analyzer" && \
   "$OUTPUT_TOOL" != "both" && "$OUTPUT_TOOL" != "web" ]] && {
  echo "[FOUT] Ongeldige output tool: $OUTPUT_TOOL (kies 'wireshark', 'analyzer', 'both' of 'web')" >&2; exit 1
}

# ---------- VoIP analyzer detection ----------

_find_analyzer() {
  if [[ -n "$ANALYZER_PATH" ]]; then
    return 0
  fi
  if python3 -m voip_analyzer --help &>/dev/null 2>&1; then
    ANALYZER_PATH="python3 -m voip_analyzer"
    return 0
  fi
  # Fall back to the analyzer bundled alongside this script.
  local bundled="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/voip-analyzer"
  if [[ -d "$bundled" ]] && \
     PYTHONPATH="$bundled" python3 -m voip_analyzer --help &>/dev/null 2>&1; then
    export PYTHONPATH="$bundled:${PYTHONPATH}"
    ANALYZER_PATH="python3 -m voip_analyzer"
    return 0
  fi
  return 1
}

# ---------- Output tool detection ----------

case "$OUTPUT_TOOL" in
  analyzer|both|web)
    _find_analyzer || {
      echo "[ERROR] VoIP analyzer not found." >&2
      echo "  Install deps: pip install -r voip-analyzer/requirements.txt" >&2
      echo "  Or specify the analyzer command with -V" >&2
      exit 1
    }
    ;;
  wireshark)
    command -v "$WIRESHARK_BIN" &>/dev/null || {
      echo "[ERROR] Wireshark not found in PATH." >&2
      echo "  macOS: brew install --cask wireshark" >&2
      echo "  Linux: apt install wireshark / dnf install wireshark" >&2
      exit 1
    }
    ;;
esac

# Validate SAVE_PCAP path is writable
if [[ -n "$SAVE_PCAP" ]]; then
  SAVE_DIR=$(dirname "$SAVE_PCAP")
  [[ -d "$SAVE_DIR" ]] || { echo "[ERROR] Directory for save path does not exist: $SAVE_DIR" >&2; exit 1; }
  echo "[INFO] Capture will be saved to: $SAVE_PCAP"
fi

# ---------- Interactive password prompts ----------

if [[ "$PROMPT_PASSWORDS" == true ]]; then
  if [[ "$DIRECT_MODE" == true ]]; then
    read -rsp "Local sudo password: " SSH_PASSWORD; echo
  elif [[ -z "$JUMP_HOST" ]]; then
    read -rsp "SSH password for $REMOTE_USER@$REMOTE_HOST: " SSH_PASSWORD; echo
  fi
  if [[ -n "$JUMP_HOST" ]]; then
    read -rsp "SSH password for $JUMP_USER@$JUMP_HOST: " JUMP_PASSWORD; echo
    read -rsp "SSH password for $REMOTE_USER@$REMOTE_HOST: " SSH_PASSWORD; echo
  fi
fi

# ---------- Helpers ----------

# Detect OS: use 'ip' (Linux) or 'ifconfig' (macOS/BSD)
_iface_exists() {
  if command -v ip &>/dev/null; then
    ip link show "$1" &>/dev/null
  else
    ifconfig "$1" &>/dev/null 2>&1
  fi
}

_list_ifaces() {
  if command -v ip &>/dev/null; then
    ip -o link show | awk -F': ' '{print "  " $2}' | cut -d'@' -f1
  else
    ifconfig -l 2>/dev/null | tr ' ' '\n' | sed 's/^/  /'
  fi
}

# Escape a string for safe embedding inside a remote double-quoted shell argument.
# Escapes: backslash, double-quote, dollar, backtick.
_remote_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\$/\\\$/g; s/`/\\`/g'
}

# Build the tcpdump invocation as a double-quoted remote shell string.
# Filter is placed after -- so it cannot be misinterpreted as a tcpdump flag.
_build_tcpdump_cmd() {
  local iface filter
  iface=$(_remote_escape "$REMOTE_INTERFACE")
  filter=$(_remote_escape "$FILTER")
  if [[ "$USE_SUDO" == true ]]; then
    printf 'sudo tcpdump -i "%s" -U -s 0 -w - -- "%s"' "$iface" "$filter"
  else
    printf 'tcpdump -i "%s" -U -s 0 -w - -- "%s"' "$iface" "$filter"
  fi
}

# Open a URL in the system browser (macOS / Linux).
# When running under sudo, drop back to the invoking user so the browser opens
# in their session rather than root's (where it fails silently).
_open_browser() {
  local url="$1"
  local runner=()
  if [[ -n "$SUDO_USER" && "$SUDO_USER" != "root" ]]; then
    runner=(sudo -u "$SUDO_USER")
  fi
  if command -v open &>/dev/null; then
    "${runner[@]}" open "$url" &
  elif command -v xdg-open &>/dev/null; then
    "${runner[@]}" xdg-open "$url" &
  fi
}

# Run a full post-capture analysis on a saved PCAP file
_post_analyze() {
  local file="$1"
  if [[ ! -f "$file" || ! -s "$file" ]]; then
    echo "[INFO] No PCAP file to analyze (capture may have been empty)."
    return
  fi
  echo ""
  echo "=========================================="
  echo " Post-capture analysis: $file"
  echo "=========================================="
  read -ra ANALYZE_CMD <<< "$ANALYZER_PATH analyze"
  "${ANALYZE_CMD[@]}" "$file"
}

# Base SSH options (array, safe for quoting)
SSH_OPTS=(-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o LogLevel=ERROR)
[[ "$SSH_AGENT_FORWARDING" == true ]] && SSH_OPTS+=(-A)

# Resolve the final sink command array
case "$OUTPUT_TOOL" in
  wireshark) OUTPUT_CMD=("$WIRESHARK_BIN" -k -i -) ;;
  analyzer)  read -ra OUTPUT_CMD <<< "$ANALYZER_PATH live" ;;
  both)      read -ra OUTPUT_CMD <<< "$ANALYZER_PATH live" ;;
  web)       read -ra OUTPUT_CMD <<< "$ANALYZER_PATH web --port $WEB_PORT" ;;
esac

# ---------- Confirm helper ----------

_confirm() {
  printf "\nStart capture? (y/n) "
  read -r PROCEED
  [[ "$PROCEED" == "y" || "$PROCEED" == "Y" ]]
}

# ---------- Run capture with pipeline ----------
#
# For 'both': tees raw PCAP to file AND pipes to analyzer live simultaneously.
# For other modes with -o: tees to file, then into the output tool.
# For other modes without -o: pipes directly into the output tool.

_run_capture() {
  # $@: the capture source command (ssh … or tcpdump …)

  if [[ "$OUTPUT_TOOL" == "both" ]]; then
    local pcap_file="${SAVE_PCAP:-/tmp/remotetrace_$(date +%Y%m%d_%H%M%S).pcap}"
    [[ -z "$SAVE_PCAP" ]] && echo "[INFO] Auto-saving to: $pcap_file"
    read -ra LIVE_CMD <<< "$ANALYZER_PATH live"
    "$@" | tee "$pcap_file" | "${LIVE_CMD[@]}"
    _post_analyze "$pcap_file"
  elif [[ "$OUTPUT_TOOL" == "wireshark" ]]; then
    # Option A: always tee to mirror file. Analyzer attaches by tailing.
    _init_mirror_paths
    echo "[INFO] Mirror PCAP → $MIRROR_FILE"
    _write_state
    trap _cleanup_capture EXIT INT TERM
    _start_keypress_watcher
    if [[ -n "$SAVE_PCAP" ]]; then
      # User also wants their own copy; tee twice
      "$@" | tee "$MIRROR_FILE" | tee "$SAVE_PCAP" | "${OUTPUT_CMD[@]}"
    else
      "$@" | tee "$MIRROR_FILE" | "${OUTPUT_CMD[@]}"
    fi
    _cleanup_capture
    trap - EXIT INT TERM
  elif [[ -n "$SAVE_PCAP" ]]; then
    "$@" | tee "$SAVE_PCAP" | "${OUTPUT_CMD[@]}"
    _post_analyze "$SAVE_PCAP"
  else
    "$@" | "${OUTPUT_CMD[@]}"
  fi
}

# ---------- Web mode browser opener ----------

_maybe_open_browser() {
  if [[ "$OUTPUT_TOOL" == "web" ]]; then
    (sleep 2 && _open_browser "http://localhost:$WEB_PORT") &
    echo "[INFO] Dashboard → http://localhost:$WEB_PORT  (opening browser in 2s)"
  fi
}

# ---------- Wireshark + on-demand VoIP analyzer (Option A: tee-to-mirror) ----------
#
# Wireshark mode tees the live PCAP stream into a mirror file. The analyzer
# attaches by tailing that file. Toggle is start/stop the tail process.
# State file is consumed by the SwiftBar plugin and voip-mirror-toggle helper.

_init_mirror_paths() {
  mkdir -p "$MIRROR_DIR" 2>/dev/null || true
  if [[ -z "$MIRROR_FILE" ]]; then
    MIRROR_FILE="$MIRROR_DIR/mirror-$(date +%Y%m%d_%H%M%S).pcap"
  fi
}

_write_state() {
  local started_at
  started_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  {
    echo "mirror_file=$MIRROR_FILE"
    echo "trace_pid=$$"
    echo "web_port=$WEB_PORT"
    echo "started_at=$started_at"
    echo "analyzer_pid=${ANALYZER_PID}"
  } > "$MIRROR_STATE_FILE"
}

_clear_state() {
  rm -f "$MIRROR_STATE_FILE" 2>/dev/null || true
}

# Start the analyzer reading from the mirror file. Idempotent.
_start_analyzer_from_mirror() {
  if [[ -n "$ANALYZER_PID" ]] && kill -0 "$ANALYZER_PID" 2>/dev/null; then
    echo "[INFO] Analyzer already running (pid $ANALYZER_PID)" >&2
    return 0
  fi
  if ! _find_analyzer 2>/dev/null; then
    echo "[ERROR] VoIP analyzer not found." >&2
    return 1
  fi
  if [[ ! -f "$MIRROR_FILE" ]]; then
    echo "[ERROR] Mirror file not yet created: $MIRROR_FILE" >&2
    return 1
  fi

  echo "" >&2
  echo "[INFO] Launching VoIP Analyzer (web, port $WEB_PORT) from mirror file" >&2
  echo "[INFO] Dashboard → http://localhost:$WEB_PORT" >&2
  _open_browser "http://localhost:$WEB_PORT"

  read -ra ANALYZER_WEB_CMD <<< "$ANALYZER_PATH web --port $WEB_PORT"
  # tail from byte 0 so the analyzer sees the libpcap global header
  ( tail -c +0 -f "$MIRROR_FILE" | "${ANALYZER_WEB_CMD[@]}" ) &
  ANALYZER_PID=$!
  _write_state
}

_stop_analyzer_from_mirror() {
  if [[ -n "$ANALYZER_PID" ]]; then
    kill "$ANALYZER_PID" 2>/dev/null || true
    # Also kill the tail child if still around
    pkill -P "$ANALYZER_PID" 2>/dev/null || true
    ANALYZER_PID=""
    _write_state
    echo "[INFO] Analyzer stopped" >&2
  fi
}

# Starts a background watcher reading from /dev/tty.
# 'a' toggles the analyzer on/off. 'q' is shown in help but Ctrl-C stops capture.
_start_keypress_watcher() {
  (
    sleep 2
    echo "" >&2
    echo "[HINT] Wireshark + mirror active. Press 'a' + Enter to toggle VoIP Analyzer." >&2
    while IFS= read -r key </dev/tty; do
      case "$key" in
        a|A)
          if [[ -n "$ANALYZER_PID" ]] && kill -0 "$ANALYZER_PID" 2>/dev/null; then
            _stop_analyzer_from_mirror
          else
            _start_analyzer_from_mirror
          fi
          ;;
      esac
    done
  ) &
  KEYPRESS_WATCHER_PID=$!
}

_stop_keypress_watcher() {
  if [[ -n "${KEYPRESS_WATCHER_PID:-}" ]]; then
    kill "$KEYPRESS_WATCHER_PID" 2>/dev/null || true
  fi
}

# Cleanup hook on capture exit
_cleanup_capture() {
  _stop_keypress_watcher
  _stop_analyzer_from_mirror
  _clear_state
}

# ---------- Main execution ----------

echo "[INFO] Interface: $REMOTE_INTERFACE | Filter: $FILTER | Sudo: $USE_SUDO"
case "$OUTPUT_TOOL" in
  wireshark) echo "[INFO] Output → Wireshark + mirror PCAP  (press 'a' + Enter during capture to toggle VoIP Analyzer)" ;;
  analyzer)  echo "[INFO] Output → VoIP analyzer (live terminal)" ;;
  both)      echo "[INFO] Output → VoIP analyzer (live) + PCAP file + post-capture report" ;;
  web)       echo "[INFO] Output → VoIP analyzer (web dashboard, port $WEB_PORT)" ;;
esac

# --- Direct mode ---
if [[ "$DIRECT_MODE" == true ]]; then
  echo "[INFO] Direct mode — local tcpdump"
  _iface_exists "$REMOTE_INTERFACE" || {
    echo "[ERROR] Interface '$REMOTE_INTERFACE' not found."
    echo "Available interfaces:"
    _list_ifaces
    exit 1
  }
  _confirm || { echo "[INFO] Cancelled."; exit 0; }
  echo "[INFO] Starting..."
  _maybe_open_browser
  if [[ "$USE_SUDO" == true ]]; then
    if [[ -n "$SSH_PASSWORD" ]]; then
      # sudo with inline password: use a subshell so _run_capture receives a plain stdout stream
      _run_capture bash -c "printf '%s\n' $(printf '%q' "$SSH_PASSWORD") | sudo -S tcpdump -i $(printf '%q' "$REMOTE_INTERFACE") -U -s 0 -w - -- $(printf '%q' "$FILTER") 2>/dev/null"
    else
      _run_capture sudo tcpdump -i "$REMOTE_INTERFACE" -U -s 0 -w - -- "$FILTER"
    fi
  else
    _run_capture tcpdump -i "$REMOTE_INTERFACE" -U -s 0 -w - -- "$FILTER"
  fi

# --- Jump host mode ---
elif [[ -n "$JUMP_HOST" ]]; then
  echo "[INFO] Via jump host $JUMP_USER@$JUMP_HOST:$JUMP_PORT → $REMOTE_USER@$REMOTE_HOST:$SSH_PORT"

  TCPDUMP_CMD=$(_build_tcpdump_cmd)

  _confirm || { echo "[INFO] Cancelled."; exit 0; }
  echo "[INFO] Starting..."
  _maybe_open_browser

  if [[ "$USE_SSH_KEY" == true ]]; then
    echo "[INFO] SSH key: $SSH_KEY_PATH"
    _run_capture ssh "${SSH_OPTS[@]}" -i "$SSH_KEY_PATH" \
      -J "$JUMP_USER@$JUMP_HOST:$JUMP_PORT" \
      -p "$SSH_PORT" "$REMOTE_USER@$REMOTE_HOST" \
      "$TCPDUMP_CMD"
  elif [[ -n "$SSH_PASSWORD" ]]; then
    command -v sshpass &>/dev/null || {
      echo "[ERROR] sshpass not found (required for password auth)." >&2
      echo "  macOS: brew install hudochenkov/sshpass/sshpass" >&2
      echo "  Linux: apt install sshpass" >&2
      exit 1
    }
    # sshpass only handles one password; for jump+target both needing passwords,
    # set JUMP_SSH_COMMAND so OpenSSH uses sshpass for the jump leg too
    export JUMP_SSH_COMMAND="sshpass -p $(printf '%q' "$JUMP_PASSWORD") ssh ${SSH_OPTS[*]}"
    _run_capture sshpass -p "$SSH_PASSWORD" ssh "${SSH_OPTS[@]}" \
      -o "ProxyCommand=sshpass -p $(printf '%q' "$JUMP_PASSWORD") ssh ${SSH_OPTS[*]} -W %h:%p -p $JUMP_PORT $JUMP_USER@$JUMP_HOST" \
      -p "$SSH_PORT" "$REMOTE_USER@$REMOTE_HOST" \
      "$TCPDUMP_CMD"
  else
    # No explicit credentials — rely on ssh-agent or default key for both hops
    _run_capture ssh "${SSH_OPTS[@]}" \
      -J "$JUMP_USER@$JUMP_HOST:$JUMP_PORT" \
      -p "$SSH_PORT" "$REMOTE_USER@$REMOTE_HOST" \
      "$TCPDUMP_CMD"
  fi

# --- Direct SSH mode ---
else
  echo "[INFO] Direct SSH → $REMOTE_USER@$REMOTE_HOST:$SSH_PORT"

  TCPDUMP_CMD=$(_build_tcpdump_cmd)

  _confirm || { echo "[INFO] Cancelled."; exit 0; }
  echo "[INFO] Starting..."
  _maybe_open_browser

  if [[ "$USE_SSH_KEY" == true ]]; then
    echo "[INFO] SSH key: $SSH_KEY_PATH"
    _run_capture ssh "${SSH_OPTS[@]}" -i "$SSH_KEY_PATH" -p "$SSH_PORT" \
      "$REMOTE_USER@$REMOTE_HOST" "$TCPDUMP_CMD"
  elif [[ -n "$SSH_PASSWORD" ]]; then
    command -v sshpass &>/dev/null || {
      echo "[ERROR] sshpass not found." >&2; exit 1
    }
    _run_capture sshpass -p "$SSH_PASSWORD" ssh "${SSH_OPTS[@]}" -p "$SSH_PORT" \
      "$REMOTE_USER@$REMOTE_HOST" "$TCPDUMP_CMD"
  else
    # No explicit credentials: rely on ssh-agent or default key
    _run_capture ssh "${SSH_OPTS[@]}" -p "$SSH_PORT" \
      "$REMOTE_USER@$REMOTE_HOST" "$TCPDUMP_CMD"
  fi
fi
