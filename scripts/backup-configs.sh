#!/usr/bin/env bash
# backup-configs.sh — Backup all configuration files to a timestamped tarball
set -euo pipefail

PROJECT_DIR="/opt/plex-server"
BACKUP_DIR="$PROJECT_DIR/backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="$BACKUP_DIR/plex-server-backup-${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "=== Backing up Plex-Debrid configs ==="

tar -czf "$BACKUP_FILE" \
  -C "$PROJECT_DIR" \
  docker-compose.yml \
  .env \
  zurg/config.yml \
  rclone/rclone.conf \
  scripts/ \
  2>/dev/null

echo "Backup saved to: $BACKUP_FILE"
echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"

# Keep only last 10 backups
cd "$BACKUP_DIR"
ls -t plex-server-backup-*.tar.gz 2>/dev/null | tail -n +11 | xargs -r rm -f
echo "Old backups cleaned up (keeping last 10)"
