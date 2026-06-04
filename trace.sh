#!/bin/bash

VERSION="1.0.1"
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
  echo "  -O <tool>         'wireshark' (default) or 'analyzer'"
  echo "  -V <path>         Path to VoIP analyzer (if not in PATH)"
  echo ""
  echo "Examples:"
  echo "  $0 -D -i eth0 -f 'port 80'"
  echo "  $0 -h 192.168.1.1 -i eth0 -f 'port 443' -u root -k ~/.ssh/id_rsa -p 22"
  echo "  $0 -h 192.168.1.1 -i eth0 -f 'port 443' -u root -w mypass -p 22"
  echo "  $0 -h 10.0.0.5 -i eth0 -f 'udp' -J bastion.example.com -U jumpuser -W jumppass -u root -p 22"
  exit 1
}

# ---------- Argument parsing ----------

while getopts ":u:w:h:i:p:f:sJ:U:W:R:PDk:AO:V:" opt; do
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

[[ "$OUTPUT_TOOL" != "wireshark" && "$OUTPUT_TOOL" != "analyzer" ]] && {
  echo "[FOUT] Ongeldige output tool: $OUTPUT_TOOL (kies 'wireshark' of 'analyzer')" >&2; exit 1
}

# ---------- Output tool detection ----------

if [[ "$OUTPUT_TOOL" == "analyzer" ]]; then
  if [[ -z "$ANALYZER_PATH" ]]; then
    if python3 -m voip_analyzer --help &>/dev/null 2>&1; then
      ANALYZER_PATH="python3 -m voip_analyzer"
    elif [[ -d "$HOME/Downloads/claude/voip-analyser" ]] && \
         PYTHONPATH="$HOME/Downloads/claude/voip-analyser" python3 -m voip_analyzer --help &>/dev/null 2>&1; then
      export PYTHONPATH="$HOME/Downloads/claude/voip-analyser:${PYTHONPATH}"
      ANALYZER_PATH="python3 -m voip_analyzer"
    fi
  fi
  [[ -z "$ANALYZER_PATH" ]] && {
    echo "[ERROR] VoIP analyzer not found." >&2
    echo "  Install: cd ~/Downloads/claude/voip-analyser && pip install -e ." >&2
    echo "  Or specify path with -V" >&2
    exit 1
  }
  echo "[INFO] Output → VoIP analyzer"
else
  command -v "$WIRESHARK_BIN" &>/dev/null || {
    echo "[ERROR] Wireshark not found in PATH." >&2
    echo "  macOS: brew install --cask wireshark" >&2
    echo "  Linux: apt install wireshark / dnf install wireshark" >&2
    exit 1
  }
  echo "[INFO] Output → Wireshark"
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

# Base SSH options (array, safe for quoting)
SSH_OPTS=(-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o LogLevel=ERROR)
[[ "$SSH_AGENT_FORWARDING" == true ]] && SSH_OPTS+=(-A)

# Output command array (safe for "${OUTPUT_CMD[@]}")
if [[ "$OUTPUT_TOOL" == "analyzer" ]]; then
  read -ra OUTPUT_CMD <<< "$ANALYZER_PATH live"
else
  OUTPUT_CMD=("$WIRESHARK_BIN" -k -i -)
fi

# ---------- Confirm helper ----------

_confirm() {
  printf "\nStart capture? (y/n) "
  read -r PROCEED
  [[ "$PROCEED" == "y" || "$PROCEED" == "Y" ]]
}

# ---------- Main execution ----------

echo "[INFO] Interface: $REMOTE_INTERFACE | Filter: $FILTER | Sudo: $USE_SUDO"

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
  if [[ "$USE_SUDO" == true ]]; then
    if [[ -n "$SSH_PASSWORD" ]]; then
      printf '%s\n' "$SSH_PASSWORD" | sudo -S tcpdump -i "$REMOTE_INTERFACE" -U -s 0 -w - -- "$FILTER" 2>/dev/null | "${OUTPUT_CMD[@]}"
    else
      sudo tcpdump -i "$REMOTE_INTERFACE" -U -s 0 -w - -- "$FILTER" 2>/dev/null | "${OUTPUT_CMD[@]}"
    fi
  else
    tcpdump -i "$REMOTE_INTERFACE" -U -s 0 -w - -- "$FILTER" 2>/dev/null | "${OUTPUT_CMD[@]}"
  fi

# --- Jump host mode ---
elif [[ -n "$JUMP_HOST" ]]; then
  echo "[INFO] Via jump host $JUMP_USER@$JUMP_HOST:$JUMP_PORT → $REMOTE_USER@$REMOTE_HOST:$SSH_PORT"

  TCPDUMP_CMD=$(_build_tcpdump_cmd)

  _confirm || { echo "[INFO] Cancelled."; exit 0; }
  echo "[INFO] Starting..."

  # Use OpenSSH ProxyJump (-J) — cleaner than nested SSH and works with both key and password auth
  if [[ "$USE_SSH_KEY" == true ]]; then
    echo "[INFO] SSH key: $SSH_KEY_PATH"
    ssh "${SSH_OPTS[@]}" -i "$SSH_KEY_PATH" \
      -J "$JUMP_USER@$JUMP_HOST:$JUMP_PORT" \
      -p "$SSH_PORT" "$REMOTE_USER@$REMOTE_HOST" \
      "$TCPDUMP_CMD" | "${OUTPUT_CMD[@]}"
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
    sshpass -p "$SSH_PASSWORD" ssh "${SSH_OPTS[@]}" \
      -o "ProxyCommand=sshpass -p $(printf '%q' "$JUMP_PASSWORD") ssh ${SSH_OPTS[*]} -W %h:%p -p $JUMP_PORT $JUMP_USER@$JUMP_HOST" \
      -p "$SSH_PORT" "$REMOTE_USER@$REMOTE_HOST" \
      "$TCPDUMP_CMD" | "${OUTPUT_CMD[@]}"
  else
    # No explicit credentials — rely on ssh-agent or default key for both hops
    ssh "${SSH_OPTS[@]}" \
      -J "$JUMP_USER@$JUMP_HOST:$JUMP_PORT" \
      -p "$SSH_PORT" "$REMOTE_USER@$REMOTE_HOST" \
      "$TCPDUMP_CMD" | "${OUTPUT_CMD[@]}"
  fi

# --- Direct SSH mode ---
else
  echo "[INFO] Direct SSH → $REMOTE_USER@$REMOTE_HOST:$SSH_PORT"

  TCPDUMP_CMD=$(_build_tcpdump_cmd)

  _confirm || { echo "[INFO] Cancelled."; exit 0; }
  echo "[INFO] Starting..."

  if [[ "$USE_SSH_KEY" == true ]]; then
    echo "[INFO] SSH key: $SSH_KEY_PATH"
    ssh "${SSH_OPTS[@]}" -i "$SSH_KEY_PATH" -p "$SSH_PORT" \
      "$REMOTE_USER@$REMOTE_HOST" "$TCPDUMP_CMD" | "${OUTPUT_CMD[@]}"
  elif [[ -n "$SSH_PASSWORD" ]]; then
    command -v sshpass &>/dev/null || {
      echo "[ERROR] sshpass not found." >&2; exit 1
    }
    sshpass -p "$SSH_PASSWORD" ssh "${SSH_OPTS[@]}" -p "$SSH_PORT" \
      "$REMOTE_USER@$REMOTE_HOST" "$TCPDUMP_CMD" | "${OUTPUT_CMD[@]}"
  else
    # No explicit credentials: rely on ssh-agent or default key
    ssh "${SSH_OPTS[@]}" -p "$SSH_PORT" \
      "$REMOTE_USER@$REMOTE_HOST" "$TCPDUMP_CMD" | "${OUTPUT_CMD[@]}"
  fi
fi
