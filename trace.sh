#!/bin/bash

WIRESHARK_BIN="wireshark"
USE_SUDO=false
DIRECT_MODE=false
USE_SSH_KEY=false
SSH_KEY_PATH=""
SSH_AGENT_FORWARDING=false

usage() {
  echo "Gebruik: $0 -h <host> -i <interface> -f <filter> [-s] [-u <user>] [-w <password>] [-p <port>] [-J <jump_host>] [-U <jump_user>] [-W <jump_password>] [-R <jump_port>] [-P] [-D] [-k <key_path>] [-A]"
  echo ""
  echo "Verplichte opties:"
  echo "  -h <host>         Target host (waar tcpdump wordt uitgevoerd)"
  echo "  -i <interface>    Netwerk interface op target host"
  echo "  -f <filter>       tcpdump filter"
  echo ""
  echo "Optionele opties:"
  echo "  -s                Gebruik sudo voor tcpdump"
  echo "  -u <user>         SSH gebruiker voor target host (alleen voor directe verbinding)"
  echo "  -w <password>     SSH wachtwoord voor target host (alleen voor directe verbinding)"
  echo "  -p <port>         SSH poort voor target host (alleen voor directe verbinding)"
  echo "  -D                Direct mode - voer tcpdump lokaal uit op deze machine"
  echo ""
  echo "SSH key opties:"
  echo "  -k <key_path>     Pad naar SSH private key"
  echo "  -A                Activeer SSH agent forwarding"
  echo ""
  echo "Jump host opties:"
  echo "  -J <jump_host>    Jump host/bastion host waar 'f' script beschikbaar is"
  echo "  -U <jump_user>    SSH gebruiker voor jump host"
  echo "  -W <jump_password> SSH wachtwoord voor jump host"
  echo "  -R <jump_port>    SSH poort voor jump host (default: 22)"
  echo "  -P                Prompt voor passwords (veiliger voor complexe passwords)"
  echo ""
  echo "Direct mode gebruik:"
  echo "  $0 -D -i eth0 -f 'port 80'"
  echo "  $0 -D -i eth0 -f 'port 80' -s -P  (met sudo en password prompt)"
  echo "  $0 -D -i eth0 -f 'port 80' -P     (zonder sudo, maar met password prompt)"
  echo ""
  echo "Remote mode gebruik:"
  echo "  $0 -h server.example.com -i eth0 -f 'port 443' -u root -w password -p 22"
  echo "  $0 -h server.example.com -i eth0 -f 'port 443' -u root -k ~/.ssh/id_rsa -p 22"
  echo "  $0 -h server.example.com -i eth0 -f 'port 443' -u root -k ~/.ssh/id_rsa -p 22 -A"
  echo ""
  echo "Jump host gebruik:"
  echo "  $0 -h target-server -i eth0 -f 'port 22' -J bastion.example.com -U jumpuser -W jumppass"
  echo "  $0 -h target-server -i eth0 -f 'port 22' -J bastion.example.com -U jumpuser -k ~/.ssh/id_rsa -A"
  exit 1
}

# Default values
JUMP_PORT=22
PROMPT_PASSWORDS=false

# Parse command line options
while getopts ":u:w:h:i:p:f:sJ:U:W:R:PDk:A" opt; do
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
    \? ) echo "[FOUT] Ongeldige optie: -$OPTARG" >&2; usage ;;
    : ) echo "[FOUT] Optie -$OPTARG vereist een argument." >&2; usage ;;
  esac
done

# Direct mode validation
if [[ "$DIRECT_MODE" == true ]]; then
  # In direct mode, only interface and filter are required
  if [[ -z "$REMOTE_INTERFACE" || -z "$FILTER" ]]; then
    echo "[FOUT] Direct mode vereist -i (interface) en -f (filter)." >&2
    usage
  fi
  
  # Check if running as root when sudo is not specified
  if [[ "$USE_SUDO" != true && $EUID -ne 0 ]]; then
    echo "[WAARSCHUWING] Direct mode zonder sudo vereist mogelijk root privileges voor tcpdump."
    echo "Overweeg het gebruik van -s flag voor sudo, of voer het script als root uit."
  fi
else
  # Remote mode validation (existing validation)
  if [[ -z "$REMOTE_HOST" || -z "$REMOTE_INTERFACE" || -z "$FILTER" ]]; then
    echo "[FOUT] Verplichte argumenten ontbreken (-h, -i, -f zijn verplicht voor remote mode)." >&2
    usage
  fi

  # Verify jump host arguments if jump host is specified
  if [[ -n "$JUMP_HOST" ]]; then
    if [[ -z "$JUMP_USER" ]]; then
      echo "[FOUT] Jump host vereist minimaal -U (jump user)." >&2
      usage
    fi
    # Jump host requires either password, SSH key, or prompt flag
    if [[ -z "$JUMP_PASSWORD" && "$PROMPT_PASSWORDS" != true && "$USE_SSH_KEY" != true ]]; then
      echo "[FOUT] Jump host vereist -W (jump password), -k (SSH key), of -P (prompt)." >&2
      usage
    fi
  else
    # For direct SSH connection
    if [[ -z "$REMOTE_USER" || -z "$SSH_PORT" ]]; then
      echo "[FOUT] Voor directe verbinding zijn -u en -p verplicht." >&2
      usage
    fi
    # SSH authentication requires either password, SSH key, or prompt flag
    if [[ -z "$SSH_PASSWORD" && "$PROMPT_PASSWORDS" != true && "$USE_SSH_KEY" != true ]]; then
      echo "[FOUT] Voor directe verbinding is -w (password), -k (SSH key), of -P (prompt) verplicht." >&2
      usage
    fi
  fi
fi

# Verify SSH key file exists if specified
if [[ "$USE_SSH_KEY" == true && ! -f "$SSH_KEY_PATH" ]]; then
  echo "[FOUT] SSH key bestand niet gevonden: $SSH_KEY_PATH" >&2
  exit 1
fi

# Handle password prompting if -P flag is used
if [[ "$PROMPT_PASSWORDS" == true ]]; then
  if [[ "$DIRECT_MODE" == true ]]; then
    # For direct mode, always prompt when -P is used
    if [[ "$USE_SUDO" == true ]]; then
      echo -n "Sudo password voor lokale machine: "
    else
      echo -n "Password voor lokale machine: "
    fi
    read -s SSH_PASSWORD
    echo
  elif [[ -z "$JUMP_HOST" ]]; then
    # For direct SSH connection, always prompt when -P is used (override -w)
    echo -n "SSH password voor $REMOTE_USER@$REMOTE_HOST: "
    read -s SSH_PASSWORD
    echo
  fi
  
  if [[ -n "$JUMP_HOST" ]]; then
    # For jump host, always prompt when -P is used (override -W)
    echo -n "SSH password voor $JUMP_USER@$JUMP_HOST: "
    read -s JUMP_PASSWORD
    echo
  fi
fi

# Build SSH options
SSH_OPTIONS="-o StrictHostKeyChecking=no"
if [[ "$SSH_AGENT_FORWARDING" == true ]]; then
  SSH_OPTIONS="$SSH_OPTIONS -A"
  echo "[INFO] SSH agent forwarding geactiveerd"
fi

# Build tcpdump command
if [ "$USE_SUDO" = true ]; then
    if [[ "$DIRECT_MODE" == true && -n "$SSH_PASSWORD" ]]; then
        # For direct mode with sudo password
        TCPDUMP_CMD="echo '$SSH_PASSWORD' | sudo -S tcpdump -i $REMOTE_INTERFACE -U -s 0 -w - $FILTER"
    else
        TCPDUMP_CMD="sudo tcpdump -i $REMOTE_INTERFACE -U -s 0 -w - $FILTER"
    fi
else
    TCPDUMP_CMD="tcpdump -i $REMOTE_INTERFACE -U -s 0 -w - $FILTER"
fi

# Execute based on mode
if [[ "$DIRECT_MODE" == true ]]; then
    # Direct mode - run tcpdump locally
    echo "[INFO] Direct mode - uitvoeren van tcpdump op lokale machine..."
    echo "[INFO] Interface: $REMOTE_INTERFACE | Filter: $FILTER | Sudo: $USE_SUDO"
    
    # Check if interface exists
    if ! ip link show "$REMOTE_INTERFACE" &> /dev/null; then
        echo "[FOUT] Interface '$REMOTE_INTERFACE' bestaat niet op deze machine."
        echo "Beschikbare interfaces:"
        ip link show | grep -E '^[0-9]+:' | awk '{print $2}' | sed 's/://g'
        exit 1
    fi
    
    # Check if Wireshark is installed
    if ! command -v "$WIRESHARK_BIN" &> /dev/null; then
        echo "[FOUT] Wireshark is niet geïnstalleerd of niet gevonden in PATH."
        exit 1
    fi
    
    echo ""
    echo "Ready to start Wireshark capture locally. Would you like to proceed? (y/n)"
    read -r PROCEED
    
    if [[ "$PROCEED" == "y" || "$PROCEED" == "Y" ]]; then
        echo "[INFO] Starting local Wireshark capture..."
        # Run tcpdump locally and pipe to Wireshark
        if [[ "$USE_SUDO" == true && -n "$SSH_PASSWORD" ]]; then
            # Use sudo with password via stdin
            echo "$SSH_PASSWORD" | sudo -S tcpdump -i "$REMOTE_INTERFACE" -U -s 0 -w - $FILTER | "$WIRESHARK_BIN" -k -i -
        else
            # Run without password (either no sudo or system will prompt)
            eval "$TCPDUMP_CMD" | "$WIRESHARK_BIN" -k -i -
        fi
    else
        echo "[INFO] Capture cancelled by user."
    fi

elif [[ -n "$JUMP_HOST" ]]; then
    # Jump host mode
    echo "[INFO] Verbinden via jump host $JUMP_USER@$JUMP_HOST:$JUMP_PORT naar $REMOTE_HOST..."
    echo "[INFO] Interface: $REMOTE_INTERFACE | Filter: $FILTER | Sudo: $USE_SUDO"
    
    # Build jump host SSH command
    if [[ "$USE_SSH_KEY" == true ]]; then
        echo "[INFO] Gebruik SSH key voor jump host authenticatie: $SSH_KEY_PATH"
        JUMP_SSH_CMD="ssh $SSH_OPTIONS -i $SSH_KEY_PATH -p $JUMP_PORT $JUMP_USER@$JUMP_HOST"
    else
        echo "[INFO] Gebruik password authenticatie voor jump host"
        JUMP_SSH_CMD="sshpass -p \"$JUMP_PASSWORD\" ssh $SSH_OPTIONS -p $JUMP_PORT $JUMP_USER@$JUMP_HOST"
    fi
    
    # Get target IP and access password using 'f' script
    echo "[INFO] Ophalen target info via 'f' script..."
    FULL_OUTPUT=$($JUMP_SSH_CMD "f $REMOTE_HOST all 2>/dev/null")
    
    # Extract target IP
    TARGET_IP=$(echo "$FULL_OUTPUT" | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g' | grep -i 'ssh_ip' | sed 's/.*: *//g' | tr -d '*' | tr -d ' ' | head -1)
    
    # Extract access password
    ACCESS_PWD=$(echo "$FULL_OUTPUT" | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g' | grep -i 'access_pwd:' | sed 's/.*access_pwd:[[:space:]]*//g' | sed 's/[[:space:]]*$//g' | head -1)
    
    if [[ -z "$TARGET_IP" || -z "$ACCESS_PWD" ]]; then
        echo "[FOUT] Kon IP adres of access password van $REMOTE_HOST niet ophalen"
        echo "[DEBUG] TARGET_IP: '$TARGET_IP'"
        echo "[DEBUG] ACCESS_PWD: '${ACCESS_PWD:0:5}...'"
        exit 1
    fi
    
    echo "[INFO] Target IP: $TARGET_IP"
    echo "[INFO] Access password extracted successfully"
    
    echo ""
    echo "Ready to start Wireshark capture. Would you like to proceed? (y/n)"
    read -r PROCEED
    
    if [[ "$PROCEED" == "y" || "$PROCEED" == "Y" ]]; then
        echo "[INFO] Starting Wireshark capture..."
        echo "[INFO] Executing nested SSH command with proper quoting..."
        
        # Build the nested SSH command
        if [[ "$SSH_AGENT_FORWARDING" == true && "$USE_SSH_KEY" == true ]]; then
            # Use SSH agent forwarding to target host
            echo "[INFO] Gebruik SSH agent forwarding naar target host"
            $JUMP_SSH_CMD "ssh $SSH_OPTIONS -p 22 root@$TARGET_IP \"$TCPDUMP_CMD\"" | "$WIRESHARK_BIN" -k -i -
        else
            # Use password authentication to target host
            $JUMP_SSH_CMD "sshpass -p '$ACCESS_PWD' ssh $SSH_OPTIONS -p 22 root@$TARGET_IP \"$TCPDUMP_CMD\"" | "$WIRESHARK_BIN" -k -i -
        fi
    else
        echo "[INFO] Capture cancelled by user."
    fi
else
    # Direct SSH connection mode
    echo "[INFO] Directe verbinding met $REMOTE_USER@$REMOTE_HOST via SSH poort $SSH_PORT..."
    echo "[INFO] Interface: $REMOTE_INTERFACE | Filter: $FILTER | Sudo: $USE_SUDO"
    
    echo ""
    echo "Ready to start Wireshark capture. Would you like to proceed? (y/n)"
    read -r PROCEED
    
    if [[ "$PROCEED" == "y" || "$PROCEED" == "Y" ]]; then
        echo "[INFO] Starting Wireshark capture..."
        
        # Build SSH command based on authentication method
        if [[ "$USE_SSH_KEY" == true ]]; then
            echo "[INFO] Gebruik SSH key authenticatie: $SSH_KEY_PATH"
            ssh $SSH_OPTIONS -i "$SSH_KEY_PATH" -p "$SSH_PORT" \
                "$REMOTE_USER@$REMOTE_HOST" "$TCPDUMP_CMD" | "$WIRESHARK_BIN" -k -i -
        elif [[ -n "$SSH_PASSWORD" ]]; then
            echo "[INFO] Gebruik password authenticatie"
            sshpass -p "$SSH_PASSWORD" ssh $SSH_OPTIONS -p "$SSH_PORT" \
                "$REMOTE_USER@$REMOTE_HOST" "$TCPDUMP_CMD" | "$WIRESHARK_BIN" -k -i -
        else
            # Try using SSH without password (might use ssh-agent or default keys)
            echo "[INFO] Gebruik SSH zonder expliciet password of key (mogelijk ssh-agent of default keys)"
            ssh $SSH_OPTIONS -p "$SSH_PORT" \
                "$REMOTE_USER@$REMOTE_HOST" "$TCPDUMP_CMD" | "$WIRESHARK_BIN" -k -i -
        fi
    else
        echo "[INFO] Capture cancelled by user."
    fi
fi