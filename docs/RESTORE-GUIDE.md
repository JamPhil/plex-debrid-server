# Restore Guide — Rebuilding From Scratch

This guide assumes a fresh DigitalOcean droplet (Ubuntu 24.04, 4GB+ RAM) and all files from this repo.

## Prerequisites
- DigitalOcean droplet with SSH access (4GB RAM recommended)
- Real-Debrid account with API token
- Plex account
- Discord server with webhook URL
- Discord bot token (for Doplarr media requests)

## Step 1: Bootstrap the Server

```bash
ssh root@YOUR_DROPLET_IP

# Clone the repo or copy files
git clone YOUR_REPO /opt/plex-server
cd /opt/plex-server

# Run bootstrap (installs Docker, FUSE, creates directories)
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
```

## Step 2: Configure .env

```bash
nano /opt/plex-server/.env
```

Fill in at minimum:
- `REAL_DEBRID_API_TOKEN` — from https://real-debrid.com/apitoken
- `PLEX_CLAIM` — get fresh from https://plex.tv/claim (expires in 4 min!)
- `DISCORD_WEBHOOK_URL` — from Discord server settings
- `GRAFANA_ADMIN_PASSWORD` — choose a password

Leave `SONARR_API_KEY`, `RADARR_API_KEY`, `SEERR_API_KEY` blank for now -- you'll fill these after first launch.

## Step 3: Deploy

```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

The deploy script will:
1. Write the Zurg config with your RD token
2. Create mount directories (`/mnt/symlinks/`, `/mnt/plex/`)
3. Pull all Docker images
4. Start Zurg → rclone → verify mount → start everything else
5. Print setup instructions for each service

## Step 4: Configure Services (in order)

### 4a. Plex (http://YOUR_IP:32400/web)
1. Sign in with your Plex account
2. Claim the server
3. Add libraries:
   - Movies → `/mnt/plex/Movies`
   - TV Shows → `/mnt/plex/TV`
4. **IMPORTANT**: Settings → Library → Disable:
   - "Generate video preview thumbnails"
   - "Generate intro video markers"
   (These cause excessive RD API calls and potential bans)
5. Get your Plex token: any media → ⋯ → Get Info → View XML → copy `X-Plex-Token`
6. Add to `.env`: `PLEX_TOKEN=your_token`

### 4b. Prowlarr (http://YOUR_IP:9696)
1. Set up authentication
2. Add indexers (NOTE: Torrentio, 1337x, EZTV are CloudFlare-blocked from datacenter IPs):
   - The Pirate Bay (works from datacenter)
   - YTS (works from datacenter)
3. Settings -> Apps: Add Sonarr and Radarr connections

### 4c. Sonarr (http://YOUR_IP:8989) & Radarr (http://YOUR_IP:7878)
1. Copy API keys from Settings → General
2. Add to `.env`: `SONARR_API_KEY=xxx` and `RADARR_API_KEY=xxx`
3. Settings → Download Clients → Add "Torrent Blackhole":
   - Sonarr: Torrent Folder = `/mnt/symlinks/sonarr`, Watch Folder = `/mnt/symlinks/sonarr/completed`
   - Radarr: Torrent Folder = `/mnt/symlinks/radarr`, Watch Folder = `/mnt/symlinks/radarr/completed`
   - Save Magnet Files: Yes, extension `.magnet`
4. Settings → Media Management:
   - Root folder: `/mnt/plex/TV` (Sonarr) or `/mnt/plex/Movies` (Radarr)
5. Configure quality profiles (recommended: follow https://trash-guides.info/)

### 4d. Seerr (http://YOUR_IP:5055)
1. Sign in with your Plex account
2. Connect to Sonarr and Radarr (use internal URLs: `http://sonarr:8989`, `http://radarr:7878`)
3. Enable Plex Watchlist integration
4. **IMPORTANT**: Users -> Edit user -> Permissions -> Enable "Auto Request" for both movies and TV (required for Plex Watchlist sync to create automatic requests)
5. Copy API key from Settings -> General
6. Add to `.env`: `SEERR_API_KEY=xxx`

### 4e. Verify Blackhole Configuration
- Ensure `REALDEBRID_HOST` in `.env` or docker-compose.yml is set to `https://api.real-debrid.com/rest/1.0/` (trailing slash required, `/rest/1.0/` path required). Missing the path causes 404 errors on all RD API calls.

### 4f-pre. Restart services that need API keys
```bash
cd /opt/plex-server
docker compose up -d blackhole doplarr
```

### 4f. Tautulli (http://YOUR_IP:8181)
1. Connect to Plex (use `http://localhost:32400` since Plex is on host network)
2. Settings -> Notification Agents -> Add Discord webhook
   - **IMPORTANT**: The Discord notification agent_id is **20** (not 18, which is Join). When configuring via API, use agent_id=20.
3. Enable notifications for: Recently Added, Plex Server Down

### 4g. Grafana (http://YOUR_IP:3000)
1. Login: admin / (GRAFANA_ADMIN_PASSWORD from .env)
2. Verify Prometheus datasource is connected (should be auto-provisioned)
3. Check "Plex Server Health" dashboard
4. Alerting → Contact Points → Edit "discord" → set your webhook URL

## Step 5: Set Up Cron Jobs

```bash
crontab -e
# Add:
*/5 * * * * /opt/plex-server/scripts/mount-watchdog.sh
*/2 * * * * /opt/plex-server/scripts/symlink-import.sh
```

## Step 6: Verify

```bash
# Check all containers running
docker ps

# Check FUSE mount
ls /mnt/zurg/__all__/
docker exec plex ls /mnt/zurg/__all__/

# Check symlinks directories exist
ls /mnt/symlinks/radarr/
ls /mnt/symlinks/sonarr/
ls /mnt/plex/Movies/
ls /mnt/plex/TV/

# Test end-to-end: request something in Seerr and watch it appear in Plex
```

## After Restore: Important Notes

- Sonarr/Radarr databases start empty. You'll need to re-request content through Seerr or re-add shows/movies in Sonarr/Radarr directly.

- Existing RD content will still be on the mount at `/mnt/zurg/__all__/` but won't appear in Sonarr/Radarr's library until re-imported.

- Plex will need to scan `/mnt/plex/` after content is added by the *arr stack. Initial scans with 4K content can take 30-60 minutes.

- Grafana dashboards and alert rules are auto-provisioned from `grafana/` directory. Discord webhook URL must be set manually in Grafana UI.
