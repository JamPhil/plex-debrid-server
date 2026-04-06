#!/usr/bin/env bash
# restore-configs.sh — Restore configuration from a backup tarball
# Usage: restore-configs.sh [backup-file]
# If no file specified, uses the most recent backup.
set -euo pipefail

PROJECT_DIR="/opt/plex-server"
BACKUP_DIR="$PROJECT_DIR/backups"

if [ -n "${1:-}" ]; then
  BACKUP_FILE="$1"
else
  BACKUP_FILE=$(ls -t "$BACKUP_DIR"/plex-server-backup-*.tar.gz 2>/dev/null | head -1)
fi

if [ -z "$BACKUP_FILE" ] || [ ! -f "$BACKUP_FILE" ]; then
  echo "ERROR: No backup file found."
  echo "Usage: $0 [backup-file]"
  echo "Available backups:"
  ls -lh "$BACKUP_DIR"/plex-server-backup-*.tar.gz 2>/dev/null || echo "  (none)"
  exit 1
fi

echo "=== Restoring from: $BACKUP_FILE ==="
echo ""
echo "This will overwrite current configs. Containers will be restarted."
echo "Press Ctrl+C within 5 seconds to cancel..."
sleep 5

# Stop the stack
echo "Stopping stack..."
cd "$PROJECT_DIR"
docker compose down

# Extract backup
echo "Restoring configs..."
tar -xzf "$BACKUP_FILE" -C "$PROJECT_DIR"

# Restart
echo "Starting stack..."
docker compose up -d

echo ""
echo "=== Restore Complete ==="
echo "Run 'docker ps' to verify all containers are healthy."
