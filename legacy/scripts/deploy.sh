#!/usr/bin/env bash
# deploy.sh — Deploy the Plex-Debrid *Arr stack
# Run from /opt/plex-server after bootstrap.sh and filling in .env
set -euo pipefail

PROJECT_DIR="/opt/plex-server"
MOUNT_POINT="/mnt/zurg"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$PROJECT_DIR"

echo "=== Deploying Plex-Debrid *Arr Stack ==="

# ── Validate .env ──
echo "[1/7] Validating .env..."
source .env

MISSING=""
[ -z "${REAL_DEBRID_API_TOKEN:-}" ] && MISSING="$MISSING REAL_DEBRID_API_TOKEN"
[ -z "${PLEX_CLAIM:-}" ] && MISSING="$MISSING PLEX_CLAIM"
[ -z "${DISCORD_WEBHOOK_URL:-}" ] && MISSING="$MISSING DISCORD_WEBHOOK_URL"
[ -z "${GRAFANA_ADMIN_PASSWORD:-}" ] && MISSING="$MISSING GRAFANA_ADMIN_PASSWORD"

if [ -n "$MISSING" ]; then
  echo "ERROR: Missing required .env values:$MISSING"
  echo "Edit $PROJECT_DIR/.env and try again."
  exit 1
fi
echo "  All required values present"

# ── Write Zurg config with actual token ──
echo "[2/7] Writing Zurg config..."
cat > "$PROJECT_DIR/zurg/config.yml" <<EOF
zurg: v1

token: ${REAL_DEBRID_API_TOKEN}
host: "0.0.0.0"
port: 9999

check_for_changes_every_secs: 10
enable_repair: true
auto_delete_rar_torrents: true
retain_rd_torrent_name: true
retain_folder_name_extension: true

directories:
  shows:
    group_order: 10
    group: media
    filters:
      - has_episodes: true

  movies:
    group_order: 20
    group: media
    only_show_the_biggest_file: true
    filters:
      - regex: /.*/
EOF
echo "  Zurg config written"

# ── Create required directories ──
echo "[3/7] Creating mount directories..."
mkdir -p /mnt/symlinks/{radarr,sonarr}
mkdir -p /mnt/plex/{Movies,TV}
echo "  Directories created"

# ── Pull images ──
echo "[4/7] Pulling Docker images (this may take a few minutes)..."
docker compose pull

# ── Start storage layer first ──
echo "[5/7] Starting Zurg and rclone..."
docker compose up -d zurg
echo "  Waiting for Zurg to be healthy..."
timeout 60 bash -c 'until docker inspect --format="{{.State.Health.Status}}" zurg 2>/dev/null | grep -q healthy; do sleep 2; done' || {
  echo "ERROR: Zurg failed to become healthy"
  docker logs zurg --tail 20
  exit 1
}

docker compose up -d rclone
echo "  Waiting for rclone mount..."
timeout 60 bash -c "until ls $MOUNT_POINT/__all__ &>/dev/null; do sleep 2; done" || {
  echo "ERROR: rclone mount failed"
  docker logs rclone --tail 20
  exit 1
}
echo "  Mount verified at $MOUNT_POINT"

# ── Start all services ──
echo "[6/7] Starting all services..."
docker compose up -d

echo "  Waiting for containers to initialize..."
sleep 30

# ── Check health ──
echo "[7/7] Checking container health..."
ALL_HEALTHY=true
for svc in zurg rclone plex prowlarr sonarr radarr overseerr tautulli prometheus grafana; do
  STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "no-healthcheck")
  if [ "$STATUS" = "healthy" ] || [ "$STATUS" = "no-healthcheck" ]; then
    RUNNING=$(docker inspect --format='{{.State.Status}}' "$svc" 2>/dev/null || echo "missing")
    if [ "$RUNNING" = "running" ]; then
      echo "  ✓ $svc: running"
    else
      echo "  ✗ $svc: $RUNNING"
      ALL_HEALTHY=false
    fi
  else
    echo "  ✗ $svc: $STATUS"
    ALL_HEALTHY=false
  fi
done

# ── Send Discord notification ──
if [ -f "$SCRIPT_DIR/discord-notify.sh" ]; then
  bash "$SCRIPT_DIR/discord-notify.sh" \
    "Plex Server Deployed" \
    "All services starting. New *Arr stack with monitoring." \
    "3066993"
fi

SERVER_IP=$(curl -s ifconfig.me)

echo ""
echo "=== Deployment Complete ==="
echo ""
if [ "$ALL_HEALTHY" = true ]; then
  echo "All containers are running!"
else
  echo "Some containers are still starting. Run 'docker ps' to check."
  echo "Autoheal will restart any unhealthy containers automatically."
fi
echo ""
echo "=== First-Time Setup (do these in order) ==="
echo ""
echo "Step 1 — Plex:"
echo "  Visit http://$SERVER_IP:32400/web"
echo "  Sign in and claim your server"
echo "  Add libraries: Movies → /mnt/plex/Movies, TV Shows → /mnt/plex/TV"
echo "  IMPORTANT: Disable 'Generate video preview thumbnails' and 'Generate intro video markers'"
echo ""
echo "Step 2 — Prowlarr (http://$SERVER_IP:9696):"
echo "  Set up authentication"
echo "  Add indexers (Torrentio custom indexer + public trackers)"
echo "  Add Sonarr and Radarr in Settings > Apps"
echo ""
echo "Step 3 — Sonarr (http://$SERVER_IP:8989) & Radarr (http://$SERVER_IP:7878):"
echo "  Copy API keys from Settings > General → add to .env as SONARR_API_KEY / RADARR_API_KEY"
echo "  Add Torrent Blackhole download client:"
echo "    Torrent Folder: /mnt/symlinks/sonarr (or /mnt/symlinks/radarr)"
echo "    Watch Folder: /mnt/symlinks/sonarr/completed (or /mnt/symlinks/radarr/completed)"
echo "    Save Magnet Files: Yes (.magnet extension)"
echo "  Set root folder: /mnt/plex/TV (Sonarr) or /mnt/plex/Movies (Radarr)"
echo "  Configure quality profiles (follow TRaSH Guides: https://trash-guides.info/)"
echo ""
echo "Step 4 — Overseerr (http://$SERVER_IP:5055):"
echo "  Sign in with Plex account"
echo "  Connect to Sonarr and Radarr"
echo "  Enable Plex Watchlist integration"
echo "  Copy API key → add to .env as OVERSEERR_API_KEY"
echo ""
echo "Step 5 — Restart blackhole + doplarr (they need the API keys):"
echo "  docker compose up -d blackhole doplarr"
echo ""
echo "Step 6 — Grafana (http://$SERVER_IP:3000):"
echo "  Login: admin / (check GRAFANA_ADMIN_PASSWORD in .env)"
echo "  Verify Prometheus datasource is connected"
echo "  Check Server Health dashboard"
echo "  Set up Discord contact point with your webhook URL"
echo ""
echo "Step 7 — Tautulli (http://$SERVER_IP:8181):"
echo "  Connect to Plex"
echo "  Configure Discord notifications: Settings > Notification Agents > Discord"
echo "  Enable: New content added, Server down, Buffer warnings"
echo ""
echo "Step 8 — Set up cron jobs:"
echo "  crontab -e"
echo "  */5 * * * * /opt/plex-server/scripts/mount-watchdog.sh"
