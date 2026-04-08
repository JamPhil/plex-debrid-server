#!/usr/bin/env bash
# deploy.sh — Deploy the Plex-Debrid stack
# Run from /opt/plex-server after bootstrap.sh and filling in .env
set -euo pipefail

PROJECT_DIR="/opt/plex-server"
MOUNT_POINT="/mnt/zurg"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$PROJECT_DIR"

echo "=== Deploying Plex-Debrid Stack ==="

# ── Validate .env ──
echo "[1/5] Validating .env..."
source .env

MISSING=""
[ -z "${REAL_DEBRID_API_TOKEN:-}" ] && MISSING="$MISSING REAL_DEBRID_API_TOKEN"
[ -z "${PLEX_CLAIM:-}" ] && MISSING="$MISSING PLEX_CLAIM"
[ -z "${DISCORD_WEBHOOK_URL:-}" ] && MISSING="$MISSING DISCORD_WEBHOOK_URL"
[ -z "${POSTGRES_PASSWORD:-}" ] && MISSING="$MISSING POSTGRES_PASSWORD"

if [ -n "$MISSING" ]; then
  echo "ERROR: Missing required .env values:$MISSING"
  echo "Edit $PROJECT_DIR/.env and try again."
  exit 1
fi
echo "  All required values present"

# ── Write Zurg config with actual token ──
echo "[2/5] Writing Zurg config..."
cat > "$PROJECT_DIR/zurg/config.yml" <<EOF
token: ${REAL_DEBRID_API_TOKEN}
host: "0.0.0.0"
port: 9999

directories:
  movies:
    group: media
    filters:
      - regex: /.*/
        filetype: movie
  shows:
    group: media
    filters:
      - regex: /.*/
        filetype: show
EOF
echo "  Zurg config written"

# ── Pull images ──
echo "[3/5] Pulling Docker images (this may take a few minutes)..."
docker compose pull

# ── Start Zurg + rclone first ──
echo "[4/5] Starting Zurg and rclone..."
docker compose up -d zurg
echo "  Waiting for Zurg to be healthy..."
timeout 60 bash -c 'until docker inspect --format="{{.State.Health.Status}}" zurg 2>/dev/null | grep -q healthy; do sleep 2; done' || {
  echo "ERROR: Zurg failed to become healthy"
  docker logs zurg --tail 20
  exit 1
}

docker compose up -d rclone
echo "  Waiting for rclone mount..."
timeout 60 bash -c "until ls $MOUNT_POINT/movies &>/dev/null; do sleep 2; done" || {
  echo "ERROR: rclone mount failed"
  docker logs rclone --tail 20
  exit 1
}
echo "  Mount verified at $MOUNT_POINT"

# ── Start remaining services ──
echo "[5/5] Starting remaining services..."
docker compose up -d

echo "  Waiting for all containers to be healthy..."
sleep 10

# Check health of all services
ALL_HEALTHY=true
for svc in zurg rclone plex postgres riven-backend riven-frontend; do
  STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "missing")
  if [ "$STATUS" = "healthy" ]; then
    echo "  ✓ $svc: healthy"
  else
    echo "  ✗ $svc: $STATUS"
    ALL_HEALTHY=false
  fi
done

# ── Send Discord test notification ──
if [ -f "$SCRIPT_DIR/discord-notify.sh" ]; then
  bash "$SCRIPT_DIR/discord-notify.sh" \
    "Plex Server Deployed" \
    "All services are starting up. Check status with \`docker ps\`." \
    "3066993"
fi

echo ""
echo "=== Deployment Complete ==="
echo ""
if [ "$ALL_HEALTHY" = true ]; then
  echo "All containers are healthy!"
else
  echo "Some containers are still starting. Run 'docker ps' to check."
  echo "Autoheal will restart any unhealthy containers automatically."
fi
echo ""
echo "Next steps:"
echo "  1. Visit http://$(curl -s ifconfig.me):32400/web — Sign in and claim your Plex server"
echo "  2. Add libraries: Movies → /media/movies, TV Shows → /media/shows"
echo "  3. Disable transcoding (Settings → Transcoder → disable)"
echo "  4. Get your Plex token and add it to .env as PLEX_TOKEN"
echo "  5. Visit http://$(curl -s ifconfig.me):3001 — Configure Riven"
