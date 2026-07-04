#!/bin/bash
# SwiftBar / xbar menubar plugin for RemoteTrace.
# Refresh interval: 5 seconds (encoded in filename).
#
# Install:
#   SwiftBar: brew install --cask swiftbar
#   ln -s /Users/jeroen/Downloads/claude/RemoteTrace/menubar/RemoteTrace.5s.sh \
#         ~/Library/Application\ Support/SwiftBar/Plugins/RemoteTrace.5s.sh
#
# Shows capture state, analyzer toggle, and dashboard link.

REMOTETRACE_DIR="$HOME/Downloads/claude/RemoteTrace"
TOGGLE_BIN="$REMOTETRACE_DIR/voip-mirror-toggle"
STATE_FILE="$HOME/.remotetrace/state"

mirror_file=""; trace_pid=""; web_port="7654"; started_at=""; analyzer_pid=""

if [[ -f "$STATE_FILE" ]]; then
  # shellcheck disable=SC1090
  . "$STATE_FILE"
fi

_capture_alive() {
  [[ -n "$trace_pid" ]] && kill -0 "$trace_pid" 2>/dev/null
}

_analyzer_alive() {
  [[ -n "$analyzer_pid" ]] && kill -0 "$analyzer_pid" 2>/dev/null
}

if _capture_alive; then
  if _analyzer_alive; then
    echo "RT*"
  else
    echo "RT."
  fi
else
  echo "RT"
fi

echo "---"

if _capture_alive; then
  echo "Capture running (pid $trace_pid)"
  echo "Mirror: ${mirror_file##*/}"
  echo "Started: $started_at"
  echo "---"
  if _analyzer_alive; then
    echo "Analyzer: ON (pid $analyzer_pid) | color=green"
    echo "Stop VoIP Analyzer | bash=$TOGGLE_BIN param1=off terminal=false refresh=true"
  else
    echo "Analyzer: OFF | color=gray"
    echo "Start VoIP Analyzer | bash=$TOGGLE_BIN param1=on terminal=false refresh=true"
  fi
  echo "Open dashboard | href=http://localhost:$web_port"
  echo "---"
  echo "Stop capture (SIGTERM) | bash=/bin/kill param1=$trace_pid terminal=false refresh=true"
else
  echo "No active capture | color=gray"
  echo "---"
  echo "Open RemoteTrace folder | bash=/usr/bin/open param1=$REMOTETRACE_DIR terminal=false"
fi

echo "---"
echo "Refresh | refresh=true"
