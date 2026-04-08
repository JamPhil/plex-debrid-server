#!/bin/bash
# Mount Watchdog - checks Decypharr mount on host AND inside Plex container
# Runs via cron every 5 minutes: */5 * * * *
LOGFILE="/opt/plex-server/logs/mount-watchdog.log"
WEBHOOK_URL=$(grep DISCORD_WEBHOOK_URL /opt/plex-server/.env | cut -d= -f2-)

log() { echo "$(date "+%Y-%m-%d %H:%M:%S") $1" >> "$LOGFILE"; }

send_discord() {
    curl -sf -H "Content-Type: application/json" \
        -d "{\"content\":\"$1\"}" "$WEBHOOK_URL" > /dev/null 2>&1
}

HOST_OK=false
PLEX_OK=false

# Check host mount (verify __all__ is accessible)
if ls /mnt/zurg/__all__ > /dev/null 2>&1; then
    HOST_OK=true
fi

# Check Plex container mount
if docker exec plex ls /mnt/zurg/__all__ > /dev/null 2>&1; then
    PLEX_OK=true
fi

# All good
if $HOST_OK && $PLEX_OK; then
    log "OK - mount healthy (host + plex)"
    exit 0
fi

# Host mount broken - restart decypharr
if ! $HOST_OK; then
    log "ALERT - host mount broken, restarting decypharr"
    send_discord "⚠️ **Mount Watchdog**: Host mount broken. Restarting decypharr + plex..."
    cd /opt/plex-server
    fusermount3 -uz /mnt/zurg 2>/dev/null
    docker compose restart decypharr
    sleep 20
    docker compose restart plex
    sleep 15
    if ls /mnt/zurg/__all__ > /dev/null 2>&1 && docker exec plex ls /mnt/zurg/__all__ > /dev/null 2>&1; then
        log "RECOVERED - mount restored (host + plex)"
        send_discord "✅ **Mount Watchdog**: Mount restored."
    else
        log "FAILED - mount still broken"
        send_discord "🔴 **Mount Watchdog**: Mount still broken after decypharr restart!"
    fi
    exit 0
fi

# Host OK but Plex mount broken - just restart Plex
if $HOST_OK && ! $PLEX_OK; then
    log "ALERT - plex mount disconnected, restarting plex"
    cd /opt/plex-server
    docker compose restart plex
    sleep 15
    if docker exec plex ls /mnt/zurg/__all__ > /dev/null 2>&1; then
        log "RECOVERED - plex mount restored"
    else
        log "FAILED - plex mount still broken after restart"
        send_discord "⚠️ **Mount Watchdog**: Plex mount broken. Restarted but still disconnected."
    fi
fi
