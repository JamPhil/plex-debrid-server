# Plex + Real-Debrid Streaming Server

## Project Overview
Automated Plex media server that streams content via Real-Debrid. Users add shows/movies to their Plex Watchlist, and content automatically appears in Plex within minutes.

## Architecture
- **DigitalOcean droplet**: 174.138.35.189 (2GB RAM, 2 vCPU, Ubuntu 24.04)
- **SSH key**: "robotrader" key (shared with another project)
- **Server path**: `/opt/plex-server/`
- **Mount point**: `/mnt/zurg/` (FUSE mount → Real-Debrid content)

## Tech Stack (5 containers)
1. **Zurg** — Real-Debrid WebDAV bridge (exposes RD content as files)
2. **rclone** — FUSE mounts Zurg's WebDAV to `/mnt/zurg/`
3. **Plex** — Media server (libraries at `/mnt/zurg/shows/` and `/mnt/zurg/movies/`)
4. **watchlist-sync** — Custom Python script that monitors Plex Watchlist RSS, finds torrents via Torrentio, sends to RD
5. **autoheal** — Auto-restarts unhealthy containers

## Key Files
- `docker-compose.yml` — All container definitions
- `scripts/watchlist-sync.py` — The "brain" of the system (~640 lines)
- `scripts/daily-report.py` — Comprehensive daily Discord report
- `scripts/healthcheck.sh` — Runs every 15 min, Discord alerts on issues
- `scripts/mount-watchdog.sh` — Runs every 5 min, fixes FUSE mount drops
- `scripts/watchlist-sync.sh` — Watchlist cleanup with 24h grace period (runs 2x daily)
- `zurg/config.yml` — Zurg configuration (RD token, directory structure)
- `rclone/rclone.conf` — rclone WebDAV config pointing to Zurg
- `.env` — Secrets (NOT in git)

## Credentials / Services
- **Real-Debrid**: API token in `.env`, expires ~Sept 2026
- **Plex**: Claim token (one-time), ongoing token in `.env`
- **Discord webhook**: For alerts and reports
- **IPRoyal proxy**: HTTP proxy for Torrentio access (Torrentio blocks datacenter IPs)
- **Plex Watchlist RSS**: RSS feed URL in `.env`

## Plex Library Sections
- Section **3** = Movies (path: `/mnt/zurg/movies`)
- Section **4** = TV Shows (path: `/mnt/zurg/shows`)
- IMPORTANT: These changed from 1/2 to 3/4 during setup. All scripts must use 3/4.

## Cron Jobs (on server, CT timezone)
- `*/5 * * * *` — mount-watchdog.sh
- `*/15 * * * *` — healthcheck.sh
- `0 9 * * *` — daily-report.sh
- `0 0,12 * * *` — watchlist-sync.sh (cleanup)

## Critical Knowledge
See `docs/LESSONS-LEARNED.md` for detailed troubleshooting history.
See `docs/ARCHITECTURE.md` for component diagram and data flow.
See `docs/RESTORE-GUIDE.md` for full rebuild instructions.

## Common Issues
1. **FUSE mount drops inside Plex** — mount-watchdog.sh handles this automatically. If manual: `docker compose restart rclone && sleep 20 && docker compose restart plex`
2. **Torrentio 403** — Means proxy is down. Check IPRoyal subscription.
3. **Wrong show matched** — Title validation in watchlist-sync.py filters mismatches. If a bad one slips through, delete from RD and remove the entry from the state file at `/var/lib/docker/volumes/plex-server_watchlist-data/_data/state.json`
4. **RD 451 error** — Content blocked by Real-Debrid for legal reasons. Nothing we can do.
