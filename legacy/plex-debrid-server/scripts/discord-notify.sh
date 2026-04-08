#!/usr/bin/env bash
# discord-notify.sh — Send a Discord webhook notification
# Usage: discord-notify.sh "Title" "Message" [color]
# Color: decimal int (green=3066993, red=15158332, yellow=16776960, blue=3447003)
set -euo pipefail

TITLE="${1:-Plex Server Alert}"
MESSAGE="${2:-No details provided}"
COLOR="${3:-3066993}"

# Load webhook URL from .env
ENV_FILE="/opt/plex-server/.env"
if [ -f "$ENV_FILE" ]; then
  DISCORD_WEBHOOK_URL=$(grep "^DISCORD_WEBHOOK_URL=" "$ENV_FILE" | cut -d'=' -f2-)
fi

if [ -z "${DISCORD_WEBHOOK_URL:-}" ]; then
  echo "ERROR: DISCORD_WEBHOOK_URL not set in $ENV_FILE"
  exit 1
fi

HOSTNAME=$(hostname)
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

PAYLOAD=$(cat <<EOF
{
  "embeds": [{
    "title": "${TITLE}",
    "description": "${MESSAGE}",
    "color": ${COLOR},
    "footer": {
      "text": "${HOSTNAME} • ${TIMESTAMP}"
    }
  }]
}
EOF
)

curl -s -H "Content-Type: application/json" -d "$PAYLOAD" "$DISCORD_WEBHOOK_URL" >/dev/null 2>&1

echo "Discord notification sent: $TITLE"
