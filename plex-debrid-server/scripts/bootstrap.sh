#!/usr/bin/env bash
# bootstrap.sh — Idempotent server initialization
# Run once on a fresh Ubuntu 24.04 droplet as root.
set -euo pipefail

PROJECT_DIR="/opt/plex-server"
MOUNT_POINT="/mnt/zurg"

echo "=== Plex-Debrid Server Bootstrap ==="

# ── System update ──
echo "[1/7] Updating system packages..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq

# ── Install dependencies ──
echo "[2/7] Installing dependencies..."
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  curl fuse3 jq ufw

# Enable user_allow_other for FUSE mounts
if ! grep -q "^user_allow_other" /etc/fuse.conf 2>/dev/null; then
  echo "user_allow_other" >> /etc/fuse.conf
  echo "  Enabled user_allow_other in /etc/fuse.conf"
fi

# ── Install Docker ──
echo "[3/7] Installing Docker..."
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable docker
  systemctl start docker
  echo "  Docker installed"
else
  echo "  Docker already installed"
fi

# Verify Docker Compose v2
if ! docker compose version &>/dev/null; then
  echo "ERROR: Docker Compose v2 not found. Install failed."
  exit 1
fi

# ── Create directory structure ──
echo "[4/7] Creating project directories..."
mkdir -p "$PROJECT_DIR"/{zurg,rclone,scripts,backups,logs}
mkdir -p "$MOUNT_POINT"

# ── Configure firewall ──
echo "[5/7] Configuring firewall..."
ufw --force reset >/dev/null 2>&1
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH"
ufw allow 32400/tcp comment "Plex"
ufw allow 3001/tcp comment "Riven UI"
ufw --force enable
echo "  Firewall configured (SSH, Plex, Riven UI)"

# ── Set timezone ──
echo "[6/7] Setting timezone..."
timedatectl set-timezone America/Chicago
echo "  Timezone: America/Chicago"

# ── Generate .env ──
echo "[7/7] Generating .env file..."
ENV_FILE="$PROJECT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  PG_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)
  cat > "$ENV_FILE" <<EOF
# Plex + Real-Debrid Server Configuration
# Fill in your values below.

REAL_DEBRID_API_TOKEN=
PLEX_CLAIM=
DISCORD_WEBHOOK_URL=
PLEX_TOKEN=
POSTGRES_PASSWORD=${PG_PASS}
TIMEZONE=America/Chicago
EOF
  chmod 600 "$ENV_FILE"
  echo "  Created $ENV_FILE (fill in your tokens)"
else
  echo "  $ENV_FILE already exists, skipping"
fi

echo ""
echo "=== Bootstrap Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit $ENV_FILE and add your API tokens"
echo "  2. Copy docker-compose.yml and config files to $PROJECT_DIR/"
echo "  3. Run deploy.sh to start the stack"
