# Restore Guide — Rebuilding From Scratch

This guide assumes a fresh DigitalOcean droplet (Ubuntu 24.04, 2GB+ RAM) and all files from this repo.

## Prerequisites
- DigitalOcean droplet with SSH access
- Real-Debrid account with API token
- Plex account
- Discord server with webhook URL
- IPRoyal static residential proxy subscription
- Plex Watchlist RSS URL (from plex.tv/accounts)

## Step 1: Bootstrap the Server

```bash
ssh root@YOUR_DROPLET_IP

# Update system
apt-get update -y && apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Install FUSE3
apt-get install -y fuse3
sed -i 's/#user_allow_other/user_allow_other/' /etc/fuse.conf

# Set timezone
timedatectl set-timezone America/Chicago

# Create directories
mkdir -p /opt/plex-server/{zurg,rclone,scripts,docs,logs,backups} /mnt/zurg

# Configure firewall
ufw allow OpenSSH
ufw allow 32400/tcp comment 'Plex'
ufw --force enable
```

## Step 2: Copy Files

From your local machine:
```bash
scp docker-compose.yml root@IP:/opt/plex-server/
scp zurg/config.yml root@IP:/opt/plex-server/zurg/
scp rclone/rclone.conf root@IP:/opt/plex-server/rclone/
scp scripts/*.py scripts/*.sh root@IP:/opt/plex-server/scripts/
chmod +x /opt/plex-server/scripts/*.sh
```

## Step 3: Create .env File

```bash
cat > /opt/plex-server/.env << EOF
REAL_DEBRID_API_TOKEN=your_rd_token_here
PLEX_CLAIM=claim-XXXX  # Get fresh from plex.tv/claim (4 min expiry!)
PLEX_TOKEN=             # Fill after first Plex login
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_here
POSTGRES_PASSWORD=not_used_anymore_but_kept_for_reference
TIMEZONE=America/Chicago
WATCHLIST_RSS=https://rss.plex.tv/your_rss_url_here
EOF
```

## Step 4: Update Proxy in docker-compose.yml

Edit the `TORRENTIO_PROXY` line in docker-compose.yml with your current IPRoyal credentials:
```
TORRENTIO_PROXY=http://USERNAME:PASSWORD@IP:PORT
```

## Step 5: Start Everything

```bash
cd /opt/plex-server

# Get a fresh Plex claim token from plex.tv/claim
# Edit .env and paste it, then immediately run:
docker compose up -d

# Wait for containers to be healthy (~60 seconds)
docker ps
```

## Step 6: Claim Plex Server

1. Go to `http://YOUR_IP:32400/web`
2. Sign in with your Plex account
3. The server should auto-claim (if claim token hasn't expired)
4. Set up libraries:
   - Movies → `/mnt/zurg/movies`
   - TV Shows → `/mnt/zurg/shows`
5. In Plex settings, enable:
   - Scan my library automatically
   - Run a partial scan when changes are detected
   - Empty trash automatically after every scan
   - Scheduled library updates (every 15 min)

## Step 7: Get Plex Token

After logging into Plex web:
1. Open any media item → ⋯ → Get Info → View XML
2. Copy the `X-Plex-Token` value from the URL
3. Add it to `.env`: `PLEX_TOKEN=your_token_here`
4. Restart watchlist-sync: `docker compose restart watchlist-sync`

## Step 8: Set Up Cron Jobs

```bash
crontab -e
# Add these lines:
*/5 * * * * /opt/plex-server/scripts/mount-watchdog.sh
*/15 * * * * /opt/plex-server/scripts/healthcheck.sh
0 9 * * * /opt/plex-server/scripts/daily-report.sh
0 0,12 * * * /opt/plex-server/scripts/watchlist-sync.sh
```

## Step 9: Verify

```bash
# Check all containers healthy
docker ps

# Check mount
ls /mnt/zurg/shows/
docker exec plex ls /mnt/zurg/shows/

# Check Torrentio proxy
curl -sf --proxy YOUR_PROXY 'https://torrentio.strem.fun/manifest.json'

# Send test report
/opt/plex-server/scripts/daily-report.sh

# Check watchlist-sync logs
docker logs watchlist-sync
```

## After Restore: Important Notes

- Plex library section IDs will be different after recreating libraries. Check with:
  `curl http://localhost:32400/library/sections?X-Plex-Token=TOKEN`
  Update section IDs in: `watchlist-sync.py`, `watchlist-sync.sh`, `daily-report.py`

- The watchlist-sync state file starts empty. It will re-process all watchlist items and add them to RD from scratch. This is expected — it won't create duplicates because it checks RD before adding.

- Plex will need time to scan all content after restore. Initial scan of 15+ shows with 4K content can take 30-60 minutes. Disable intro/credits detection during initial scan to speed this up.

- The IPRoyal proxy subscription renews monthly. If it expires, the watchlist-sync container will log Torrentio failures. The daily report flags this under "Torrentio proxy FAILED."
