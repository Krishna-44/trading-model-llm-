#!/usr/bin/env bash
# AIFOS paper-forward 24/7 service (macOS launchd).
#
# Runs the paper-mode AIFOS instance on :8001 with the autonomous loop armed at
# boot, auto-restart on crash (KeepAlive), a size-rotated app log, and a health
# watchdog that kickstarts the service if it hangs. The :8000 AngelOne monitor is
# untouched.
#
#   scripts/paper-forward.sh install     # generate plists, load, start
#   scripts/paper-forward.sh status      # launchd state + health
#   scripts/paper-forward.sh logs        # tail the rotated app log
#   scripts/paper-forward.sh restart|stop|start|uninstall|watchdog
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$REPO/backend"
UVICORN="$BACKEND/.venv/bin/uvicorn"
PORT=8001
DOMAIN="gui/$(id -u)"
LABEL="com.aifos.paper-forward"
WLABEL="com.aifos.paper-forward.watchdog"
LA="$HOME/Library/LaunchAgents"
PLIST="$LA/$LABEL.plist"
WPLIST="$LA/$WLABEL.plist"
LOGDIR="$BACKEND/logs"
HEALTH="http://127.0.0.1:$PORT/api/health"
BAR="${AIFOS_PAPER_BAR:-0.10}"   # forward-test confidence bar (looser than the 0.62 live bar; marathon trades more at a lower bar)
MAXPOS="${AIFOS_PAPER_MAXPOS:-8}"  # max concurrent open positions for the marathon (more openings)

mkdir -p "$LA" "$LOGDIR"

write_main_plist() {
  cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <!-- caffeinate -is keeps the Mac awake (idle + AC system sleep) for as long
         as the service runs; stops the moment the service is stopped or crashes. -->
    <string>/usr/bin/caffeinate</string>
    <string>-is</string>
    <string>$UVICORN</string>
    <string>aifos.api.app:app</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>$PORT</string>
    <string>--log-level</string><string>warning</string>
  </array>
  <key>WorkingDirectory</key><string>$BACKEND</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>AIFOS_BROKER</key><string>paper</string>
    <key>AIFOS_DATABASE_URL</key><string>sqlite:///$BACKEND/paper_forward.db</string>
    <key>AIFOS_LLM_PROVIDER</key><string>none</string>
    <key>AIFOS_CONFIDENCE_THRESHOLD</key><string>$BAR</string>
    <key>AIFOS_MAX_OPEN_POSITIONS</key><string>$MAXPOS</string>
    <key>AIFOS_AUTONOMOUS_ON_START</key><string>true</string>
    <key>AIFOS_MARATHON_ON_START</key><string>true</string>
    <key>AIFOS_LOG_FILE</key><string>$LOGDIR/paper_forward.app.log</string>
    <key>PATH</key><string>/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$LOGDIR/paper_forward.boot.log</string>
  <key>StandardErrorPath</key><string>$LOGDIR/paper_forward.boot.log</string>
</dict>
</plist>
PLIST
}

write_watchdog_plist() {
  cat > "$WPLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$WLABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$REPO/scripts/paper-forward.sh</string><string>watchdog</string></array>
  <key>StartInterval</key><integer>120</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOGDIR/paper_forward.watchdog.log</string>
  <key>StandardErrorPath</key><string>$LOGDIR/paper_forward.watchdog.log</string>
</dict>
</plist>
PLIST
}

boot_out() { launchctl bootout "$DOMAIN/$1" 2>/dev/null || true; }

cmd_install() {
  pkill -f "port $PORT" 2>/dev/null || true   # stop any manually-launched instance
  sleep 1
  write_main_plist; write_watchdog_plist
  boot_out "$LABEL"; boot_out "$WLABEL"
  launchctl bootstrap "$DOMAIN" "$PLIST"
  launchctl bootstrap "$DOMAIN" "$WPLIST"
  echo "installed: $LABEL + watchdog. waiting for health…"
  sleep 5; cmd_status
}

cmd_uninstall() { boot_out "$LABEL"; boot_out "$WLABEL"; rm -f "$PLIST" "$WPLIST"; echo "uninstalled"; }
cmd_start()     { launchctl bootstrap "$DOMAIN" "$PLIST"; echo "started"; }
cmd_stop()      { boot_out "$LABEL"; echo "stopped (watchdog still loaded — run 'uninstall' to remove)"; }
cmd_restart()   { launchctl kickstart -k "$DOMAIN/$LABEL"; echo "restarted"; }
cmd_logs()      { tail -n 40 "$LOGDIR/paper_forward.app.log" 2>/dev/null || echo "(no app log yet)"; }

cmd_status() {
  if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    launchctl print "$DOMAIN/$LABEL" | grep -E "^[[:space:]]*(state|pid) " || true
  else
    echo "service: not loaded"
  fi
  code="$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$HEALTH" 2>/dev/null || echo 000)"
  echo "health: $code  ($HEALTH)"
}

cmd_watchdog() {  # invoked by the watchdog launchd job every 120s
  for _ in 1 2 3; do
    if curl -s -o /dev/null --max-time 5 "$HEALTH" 2>/dev/null; then exit 0; fi
    sleep 3
  done
  echo "$(/bin/date) watchdog: $HEALTH unhealthy -> kickstart $LABEL" >> "$LOGDIR/paper_forward.watchdog.log"
  launchctl kickstart -k "$DOMAIN/$LABEL" 2>/dev/null || true
}

case "${1:-status}" in
  install)   cmd_install ;;
  uninstall) cmd_uninstall ;;
  start)     cmd_start ;;
  stop)      cmd_stop ;;
  restart)   cmd_restart ;;
  status)    cmd_status ;;
  logs)      cmd_logs ;;
  watchdog)  cmd_watchdog ;;
  *) echo "usage: $0 {install|uninstall|start|stop|restart|status|logs|watchdog}"; exit 1 ;;
esac
