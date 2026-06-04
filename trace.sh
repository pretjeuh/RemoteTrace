#!/bin/bash

VERSION="1.0.0"
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
  echo "Gebruik: $0 -h <host> -i <interface> -f <filter> [opties]"
  echo ""
  echo "Verplichte opties:"
  echo "  -h <host>         Target host (waar tcpdump wordt uitgevoerd)"
  echo "  -i <interface>    Netwerk interface op target host"
  echo "  -f <filter>       tcpdump BPF filter"
  echo ""
  echo "Verbinding:"
  echo "  -u <user>         SSH gebruiker voor target host"
  echo "  -w <password>     SSH wachtwoord (gebruik -P voor interactief)"
  echo "  -p <port>         SSH poort (default: 22)"
  echo "  -k <key>          Pad naar SSH private key"
  echo "  -A                SSH agent forwarding"
  echo "  -P                Vraag om wachtwoord(en) interactief"
  echo "  -D                Direct mode — tcpdump lokaal op deze machine"
  echo "  -s                Gebruik sudo voor tcpdump"
  echo ""
  echo "Jump host:"
  echo "  -J <jump_host>    Jump/bastion host"
  echo "  -U <jump_user>    SSH gebruiker jump host"
  echo "  -W <jump_pass>    SSH wachtwoord jump host"
  echo "  -R <jump_port>    SSH poort jump host (default: 22)"
  echo ""
  echo "Output:"
  echo "  -O <tool>         'wireshark' of 'analyzer' (default: wireshark)"
  echo "  -V <path>         Pad naar VoIP analyzer (als niet in PATH)"
  echo ""
  echo "Voorbeelden:"
  echo "  $0 -D -i eth0 -f 'port 80'"
  echo "  $0 -h 192.168.1.1 -i eth0 -f 'port 443' -u root -k ~/.ssh/id_rsa -p 22"
  echo "  $0 -h target -i eth0 -f 'udp' -J bastion.example.com -U jumpuser -W pass"
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
    echo "[FOUT] Direct mode vereist -i en -f." >&2; usage
  }
  if [[ "$USE_SUDO" != true && $EUID -ne 0 ]]; then
    echo "[WAARSCHUWING] Zonder sudo of root zijn tcpdump-rechten mogelijk onvoldoende (-s voor sudo)."
  fi
else
  [[ -z "$REMOTE_HOST" || -z "$REMOTE_INTERFACE" || -z "$FILTER" ]] && {
    echo "[FOUT] -h, -i en -f zijn verplicht voor remote mode." >&2; usage
  }
  if [[ -n "$JUMP_HOST" ]]; then
    [[ -z "$JUMP_USER" ]] && { echo "[FOUT] Jump host vereist -U (jump user)." >&2; usage; }
    [[ -z "$JUMP_PASSWORD" && "$PROMPT_PASSWORDS" != true && "$USE_SSH_KEY" != true ]] && {
      echo "[FOUT] Jump host vereist -W, -k of -P." >&2; usage
    }
  else
    [[ -z "$REMOTE_USER" || -z "$SSH_PORT" ]] && {
      echo "[FOUT] Directe SSH vereist -u en -p." >&2; usage
    }
    [[ -z "$SSH_PASSWORD" && "$PROMPT_PASSWORDS" != true && "$USE_SSH_KEY" != true ]] && {
      echo "[FOUT] Directe SSH vereist -w, -k of -P." >&2; usage
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
    echo "[FOUT] VoIP analyzer niet gevonden." >&2
    echo "  Installeer: cd ~/Downloads/claude/voip-analyser && pip install -e ." >&2
    echo "  Of geef pad op met -V" >&2
    exit 1
  }
  echo "[INFO] Output → VoIP analyzer"
else
  command -v "$WIRESHARK_BIN" &>/dev/null || {
    echo "[FOUT] Wireshark niet gevonden in PATH." >&2
    echo "  macOS: brew install --cask wireshark" >&2
    echo "  Linux: apt install wireshark / dnf install wireshark" >&2
    exit 1
  }
  echo "[INFO] Output → Wireshark"
fi

# ---------- Interactive password prompts ----------

if [[ "$PROMPT_PASSWORDS" == true ]]; then
  if [[ "$DIRECT_MODE" == true ]]; then
    read -rsp "Password voor lokale sudo: " SSH_PASSWORD; echo
  elif [[ -z "$JUMP_HOST" ]]; then
    read -rsp "SSH password voor $REMOTE_USER@$REMOTE_HOST: " SSH_PASSWORD; echo
  fi
  if [[ -n "$JUMP_HOST" ]]; then
    read -rsp "SSH password voor $JUMP_USER@$JUMP_HOST: " JUMP_PASSWORD; echo
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
  echo "[INFO] Direct mode — lokale tcpdump"
  _iface_exists "$REMOTE_INTERFACE" || {
    echo "[FOUT] Interface '$REMOTE_INTERFACE' niet gevonden."
    echo "Beschikbare interfaces:"
    _list_ifaces
    exit 1
  }
  _confirm || { echo "[INFO] Geannuleerd."; exit 0; }
  echo "[INFO] Starten..."
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
  echo "[INFO] Via jump host $JUMP_USER@$JUMP_HOST:$JUMP_PORT → $REMOTE_HOST"

  if [[ "$USE_SSH_KEY" == true ]]; then
    echo "[INFO] SSH key: $SSH_KEY_PATH"
    JUMP_SSH=(ssh "${SSH_OPTS[@]}" -i "$SSH_KEY_PATH" -p "$JUMP_PORT" "$JUMP_USER@$JUMP_HOST")
  else
    command -v sshpass &>/dev/null || {
      echo "[FOUT] sshpass niet gevonden (vereist voor password-auth via jump host)." >&2
      echo "  macOS: brew install hudochenkov/sshpass/sshpass" >&2
      echo "  Linux: apt install sshpass" >&2
      exit 1
    }
    JUMP_SSH=(sshpass -p "$JUMP_PASSWORD" ssh "${SSH_OPTS[@]}" -p "$JUMP_PORT" "$JUMP_USER@$JUMP_HOST")
  fi

  echo "[INFO] Target info ophalen via 'f' script..."
  FULL_OUTPUT=$("${JUMP_SSH[@]}" "f $(_remote_escape "$REMOTE_HOST") all 2>/dev/null")
  CLEAN_OUTPUT=$(printf '%s' "$FULL_OUTPUT" | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g')

  TARGET_IP=$(printf '%s' "$CLEAN_OUTPUT" | grep -i 'ssh_ip' | sed 's/.*:[[:space:]]*//' | tr -d ' *' | head -1)
  ACCESS_PWD=$(printf '%s' "$CLEAN_OUTPUT" | grep -i 'access_pwd:' | sed 's/.*access_pwd:[[:space:]]*//' | sed 's/[[:space:]]*$//' | head -1)

  [[ -z "$TARGET_IP" || -z "$ACCESS_PWD" ]] && {
    echo "[FOUT] Kon IP of wachtwoord van '$REMOTE_HOST' niet ophalen." >&2
    echo "[DEBUG] TARGET_IP='$TARGET_IP'" >&2
    echo "[DEBUG] ACCESS_PWD='${ACCESS_PWD:0:3}...'" >&2
    exit 1
  }
  echo "[INFO] Target IP: $TARGET_IP"

  TCPDUMP_CMD=$(_build_tcpdump_cmd)

  _confirm || { echo "[INFO] Geannuleerd."; exit 0; }
  echo "[INFO] Starten..."

  if [[ "$SSH_AGENT_FORWARDING" == true && "$USE_SSH_KEY" == true ]]; then
    # Agent forwarding: inner SSH uses forwarded agent, no password needed
    SSH_OPTS_STR="${SSH_OPTS[*]}"
    "${JUMP_SSH[@]}" "ssh $SSH_OPTS_STR -p 22 root@\"$TARGET_IP\" \"$TCPDUMP_CMD\"" | "${OUTPUT_CMD[@]}"
  else
    ESCAPED_PWD=$(_remote_escape "$ACCESS_PWD")
    SSH_OPTS_STR="${SSH_OPTS[*]}"
    "${JUMP_SSH[@]}" "sshpass -p \"$ESCAPED_PWD\" ssh $SSH_OPTS_STR -p 22 root@\"$TARGET_IP\" \"$TCPDUMP_CMD\"" | "${OUTPUT_CMD[@]}"
  fi

# --- Direct SSH mode ---
else
  echo "[INFO] Directe SSH → $REMOTE_USER@$REMOTE_HOST:$SSH_PORT"

  TCPDUMP_CMD=$(_build_tcpdump_cmd)

  _confirm || { echo "[INFO] Geannuleerd."; exit 0; }
  echo "[INFO] Starten..."

  if [[ "$USE_SSH_KEY" == true ]]; then
    echo "[INFO] SSH key: $SSH_KEY_PATH"
    ssh "${SSH_OPTS[@]}" -i "$SSH_KEY_PATH" -p "$SSH_PORT" \
      "$REMOTE_USER@$REMOTE_HOST" "$TCPDUMP_CMD" | "${OUTPUT_CMD[@]}"
  elif [[ -n "$SSH_PASSWORD" ]]; then
    command -v sshpass &>/dev/null || {
      echo "[FOUT] sshpass niet gevonden." >&2; exit 1
    }
    sshpass -p "$SSH_PASSWORD" ssh "${SSH_OPTS[@]}" -p "$SSH_PORT" \
      "$REMOTE_USER@$REMOTE_HOST" "$TCPDUMP_CMD" | "${OUTPUT_CMD[@]}"
  else
    # No explicit credentials: rely on ssh-agent or default key
    ssh "${SSH_OPTS[@]}" -p "$SSH_PORT" \
      "$REMOTE_USER@$REMOTE_HOST" "$TCPDUMP_CMD" | "${OUTPUT_CMD[@]}"
  fi
fi
