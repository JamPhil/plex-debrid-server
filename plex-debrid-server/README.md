# Plex + Real-Debrid Streaming Server

An automated Plex media server that streams content via Real-Debrid. Add a show or movie to your Plex Watchlist, and it automatically appears in your Plex library within minutes. Remove it from your watchlist, and it gets cleaned up after 24 hours.

No local storage needed. No torrenting on your machine. Content streams directly from Real-Debrid's servers through a FUSE mount.

## How It Works

```
You add "The Mandalorian" to Plex Watchlist
        |
        v
Watchlist Manager (custom Python script, runs every 60s)
  - Polls Plex Watchlist RSS feed
  - Searches Torrentio for the best torrent (via residential proxy)
  - Prefers: complete series > season packs > individual episodes
  - Prefers: 4K > 1080p, English required
  - Sends the single best torrent hash to Real-Debrid
        |
        v
Real-Debrid checks if the torrent is cached (usually instant)
        |
        v
Zurg (WebDAV bridge) exposes RD content as files
        |
        v
rclone FUSE-mounts Zurg to /mnt/zurg/ on the server
        |
        v
Plex scans the mount and adds the content to your library
        |
        v
You watch "The Mandalorian" on your TV
```

## Architecture

**Server:** DigitalOcean droplet (2GB RAM, 2 vCPU, Ubuntu 24.04)

**5 Docker containers:**

| Container | Purpose | Image |
|-----------|---------|-------|
| **zurg** | Real-Debrid WebDAV bridge — exposes RD content as browsable files | `ghcr.io/debridmediamanager/zurg-testing` |
| **rclone** | FUSE-mounts Zurg's WebDAV to `/mnt/zurg/` so Plex can read files | `rclone/rclone` |
| **plex** | Media server — serves content to your TV/devices | `lscr.io/linuxserver/plex` |
| **watchlist-sync** | Custom Python script — the "brain" that monitors your watchlist, finds torrents via Torrentio, and sends them to Real-Debrid | `python:3.12-slim` |
| **autoheal** | Auto-restarts any container that becomes unhealthy | `willfarrell/autoheal` |

**4 cron jobs:**

| Schedule | Script | Purpose |
|----------|--------|---------|
| Every 5 min | `mount-watchdog.sh` | Detects and fixes broken FUSE mounts |
| Every 15 min | `healthcheck.sh` | Checks all containers, disk, memory — Discord alert on issues |
| Daily 9am CT | `daily-report.sh` | Comprehensive status report to Discord (server, debrid, plex) |
| 2x daily | `watchlist-sync.sh` | Removes RD content that's no longer on your watchlist (24h grace period) |

## External Services

| Service | Purpose | Cost |
|---------|---------|------|
| **Real-Debrid** | Torrent cache/CDN — stores and streams the actual media files | ~$20/6 months |
| **Plex** | Media server platform — free tier is sufficient | Free |
| **IPRoyal** | Residential HTTP proxy — Torrentio blocks datacenter IPs, so the proxy makes requests look residential | ~$4/month |
| **DigitalOcean** | Cloud server hosting | ~$12/month |
| **Discord** | Receives health alerts and daily reports via webhook | Free |

## Key Design Decisions (and why)

### Custom watchlist manager instead of Riven
We initially deployed Riven (a popular automation tool for debrid services) but it caused major problems:
- **Duplicate torrents:** Riven scrapes at show, season, AND episode level independently. A single show would generate 10+ duplicate torrents in Real-Debrid.
- **No containment logic:** It didn't understand that a season pack (S01) already contains individual episodes (S01E01, S01E02, etc.), so it would download both.
- **Heavy resource usage:** Riven needed PostgreSQL, a separate frontend/backend, and consumed ~500MB RAM on our 2GB server.
- **Complex configuration:** Settings often didn't behave as expected, and the web UI added complexity.

Our custom script is ~500 lines of Python with zero dependencies beyond the standard library. It checks Real-Debrid before adding anything (preventing duplicates), prefers season packs over individual episodes, and uses a simple scoring system for quality.

### IPRoyal residential proxy instead of direct Torrentio access
Torrentio (the torrent search API) blocks requests from datacenter IPs like DigitalOcean. We tried several workarounds:
- **Prowlarr + public indexers:** Most indexers (1337x, EZTV, TPB) are also Cloudflare-blocked from datacenters
- **FlareSolverr:** Added complexity, timed out frequently
- **SSH tunnel through home PC:** Worked but required keeping a terminal window open 24/7
- **IPRoyal residential proxy ($4/mo):** Permanent, reliable, no maintenance

### rslave mount propagation for Plex
The FUSE mount (`/mnt/zurg`) would disconnect inside the Plex container when Plex restarted. After many debugging sessions, the fix was:
- Mount the parent directory (`/mnt/zurg`) instead of subdirectories (`/mnt/zurg/movies`, `/mnt/zurg/shows`)
- Use `rslave` propagation instead of `rshared`
- This ensures Plex always sees the current mount state from the host

### Plex library sections are 3 and 4 (not 1 and 2)
The libraries were recreated during setup to fix mount paths. All scripts must reference section 3 (Movies) and section 4 (TV Shows). This is a common gotcha when debugging.

## File Structure (on server at /opt/plex-server/)

```
/opt/plex-server/
  docker-compose.yml    # All container definitions
  .env                  # Secrets (RD token, Plex token, Discord webhook, proxy creds)
  zurg/
    config.yml          # Zurg config (RD token, directory structure)
  rclone/
    rclone.conf         # rclone WebDAV config pointing to Zurg
  scripts/
    watchlist-sync.py   # The "brain" — monitors watchlist, finds torrents, sends to RD
    watchlist-sync.sh   # Cleanup script — removes RD content not on watchlist (24h grace)
    daily-report.sh     # Comprehensive daily Discord report
    healthcheck.sh      # Container/disk/memory health check with Discord alerts
    mount-watchdog.sh   # FUSE mount auto-repair
  logs/                 # Script logs
```

## Common Issues and Fixes

### Content not appearing in Plex
1. Check if the FUSE mount is working inside Plex: `docker exec plex ls /mnt/zurg/shows/`
2. If empty, restart rclone then Plex: `docker compose restart rclone && sleep 20 && docker compose restart plex`
3. Trigger a manual scan: `curl -X POST "http://localhost:32400/library/sections/4/refresh?force=1&X-Plex-Token=$PLEX_TOKEN"`
4. Empty trash: `curl -X PUT "http://localhost:32400/library/sections/4/emptyTrash?X-Plex-Token=$PLEX_TOKEN"`

### Plex scan stuck on a specific folder
Some torrent files are marked as "downloaded" in RD but aren't actually accessible. Plex hangs trying to read them.
- Check which folder is stuck: look at Plex activities
- Delete the bad torrent from RD (the watchlist manager will re-add a working version)
- Restart Plex

### RD 451 error (Unavailable For Legal Reasons)
Some content is blocked by Real-Debrid for legal reasons. Nothing can be done — the content simply isn't available through RD. The script logs these and moves on.

### Torrentio 403 errors
Means the proxy is down or the IP got flagged. Check IPRoyal dashboard. The health check will alert you via Discord.

### Deleted content still showing in Plex
Plex caches metadata aggressively. After deleting content from RD:
1. Wait for Zurg to refresh (~30 seconds)
2. Trigger a Plex scan
3. Empty Plex trash (this is the step people miss)

### Watchlist items not being found
Some niche content won't have torrents available on Torrentio. The script will retry periodically. Check the daily report for items that are on the watchlist but not in Plex.

## Rebuilding From Scratch

If you need to rebuild the server completely:

1. Create a new DigitalOcean droplet (Ubuntu 24.04, 2GB RAM, 2 vCPU)
2. SSH in and install Docker: `curl -fsSL https://get.docker.com | sh`
3. Install FUSE: `apt install -y fuse3` and enable `user_allow_other` in `/etc/fuse.conf`
4. Clone this repo to `/opt/plex-server/`
5. Copy your `.env` file (see `.env.template` for required variables)
6. Get a fresh Plex claim token from https://plex.tv/claim (expires in 4 minutes!)
7. Run `docker compose up -d`
8. Set up Plex libraries pointing to `/mnt/zurg/movies` (section 3) and `/mnt/zurg/shows` (section 4)
9. Install cron jobs (see the cron table above)
10. Set timezone: `timedatectl set-timezone America/Chicago`
11. Configure UFW firewall: allow SSH, 32400 (Plex)
