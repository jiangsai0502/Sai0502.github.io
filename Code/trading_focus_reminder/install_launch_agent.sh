#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/Users/jiangsai/Documents/GitHub/Sai0502.github.io/Code/trading_focus_reminder"
PYTHON="/opt/anaconda3/bin/python3"
PLIST="$HOME/Library/LaunchAgents/com.jiangsai.trading-focus-reminder.plist"

mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.jiangsai.trading-focus-reminder</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$APP_DIR/trading_focus_reminder.py</string>
    <string>--daemon</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$APP_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$APP_DIR/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>$APP_DIR/launchd.err.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/com.jiangsai.trading-focus-reminder"

echo "Installed and started: com.jiangsai.trading-focus-reminder"
echo "Config: $APP_DIR/config.json"
