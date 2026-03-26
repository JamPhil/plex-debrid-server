#!/usr/bin/env bash
# update-stack.sh — Pull latest Docker images and restart changed containers
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NOTIFY="$SCRIPT_DIR/discord-notify.sh"

cd /opt/plex-server

echo "=== Updating Plex-Debrid Stack ==="

# Record current image digests
echo "Recording current image versions..."
BEFORE=$(docker compose images --format json 2>/dev/null || docker compose images)

# Pull latest images
echo "Pulling latest images..."
docker compose pull

# Recreate only containers with new images
echo "Recreating updated containers..."
docker compose up -d --remove-orphans

# Check what changed
AFTER=$(docker compose images --format json 2>/dev/null || docker compose images)

echo ""
echo "=== Update Complete ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"

# Notify
bash "$NOTIFY" \
  "Stack Updated" \
  "All containers have been updated to latest images and restarted." \
  "3066993"
