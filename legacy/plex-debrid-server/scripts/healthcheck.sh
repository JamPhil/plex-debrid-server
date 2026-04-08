#!/bin/bash
# Health Check - monitors containers, disk, memory, and watchlist manager
LOGFILE="/opt/plex-server/logs/healthcheck.log"
WEBHOOK_URL=$(grep DISCORD_WEBHOOK_URL /opt/plex-server/.env | cut -d= -f2-)
ALERT=""

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOGFILE"; }

# Check containers (current stack: zurg, rclone, plex, autoheal)
for container in zurg rclone plex autoheal; do
    STATUS=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null)
    if [ "$STATUS" != "running" ]; then
        ALERT="${ALERT}🔴 **${container}** is ${STATUS:-missing}\n"
        log "ALERT - $container is ${STATUS:-missing}"
    fi
done

# Check container health
for container in zurg rclone plex; do
    HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null)
    if [ "$HEALTH" = "unhealthy" ]; then
        ALERT="${ALERT}⚠️ **${container}** is unhealthy\n"
        log "ALERT - $container is unhealthy"
    fi
done

# Check watchlist manager is running
if ! docker inspect --format={{.State.Status}} watchlist-sync 2>/dev/null | grep -q running; then
    ALERT="${ALERT}🔴 **watchlist-manager** is not running\n"
    log "ALERT - watchlist-manager not running"
fi

# Check disk usage
DISK_PCT=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_PCT" -gt 85 ]; then
    ALERT="${ALERT}💾 Disk usage at **${DISK_PCT}%**\n"
    log "ALERT - disk at ${DISK_PCT}%"
fi

# Check memory
MEM_TOTAL=$(free | awk '/Mem:/ {print $2}')
MEM_USED=$(free | awk '/Mem:/ {print $3}')
MEM_PCT=$((MEM_USED * 100 / MEM_TOTAL))
if [ "$MEM_PCT" -gt 90 ]; then
    ALERT="${ALERT}🧠 Memory usage at **${MEM_PCT}%**\n"
    log "ALERT - memory at ${MEM_PCT}%"
fi

fi

# Send alert if issues found
if [ -n "$ALERT" ]; then
    curl -sf -H "Content-Type: application/json" \
        -d "{\"content\":\"🚨 **Server Health Alert**\n${ALERT}\"}" \
        "$WEBHOOK_URL" > /dev/null 2>&1
    log "Alert sent to Discord"
else
    log "OK - all checks passed"
fi
