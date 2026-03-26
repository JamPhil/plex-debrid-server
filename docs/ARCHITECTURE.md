# Architecture

## Data Flow

```
Plex Watchlist (RSS)
       |
       v
watchlist-sync.py (polls every 60s)
       |
       v
Torrentio API (via IPRoyal HTTP proxy)
       |  Returns torrent streams ranked by quality
       v
watchlist-sync.py (scores, picks best, validates title)
       |
       v
Real-Debrid API (adds magnet, selects files)
       |  RD caches or downloads the torrent
       v
Zurg (polls RD every 10s, exposes via WebDAV)
       |
       v
rclone (FUSE mounts WebDAV to /mnt/zurg/)
       |
       v
Plex (scans /mnt/zurg/shows/ and /mnt/zurg/movies/)
       |
       v
User watches on Plex client (TV, phone, etc.)
```

## Removal Flow

```
User removes from Plex Watchlist
       |
       v
watchlist-sync.sh (runs at noon + midnight CT)
       |  Compares watchlist RSS vs RD inventory
       |  24-hour grace period before deletion
       v
Real-Debrid API (deletes torrent)
       |
       v
Zurg/rclone (files disappear from mount)
       |
       v
Plex (next scan + empty trash removes from library)
```

## Monitoring Flow

```
mount-watchdog.sh (every 5 min)
  - Checks FUSE mount on host AND inside Plex container
  - Auto-restarts rclone and/or Plex if mount drops
  - Discord alert on failure

healthcheck.sh (every 15 min)
  - Checks all 5 containers running + healthy
  - Checks watchlist-sync container specifically
  - Checks disk (alert >85%) and memory (alert >90%)
  - Discord alert on any issue

daily-report.py (9am CT)
  - Pipeline status: watchlist vs debrid vs plex counts
  - Server health: containers, disk, memory, FUSE mount
  - Debrid/Torrentio: proxy, RD premium, errors, duplicates, blocked items
  - Plex: scan status, missing items with reason (not in RD vs pending scan)
```

## Container Dependencies

```
zurg (starts first, healthcheck: curl WebDAV)
  └─> rclone (waits for zurg healthy, healthcheck: ls /data/movies)
        ├─> plex (waits for rclone healthy, healthcheck: curl /identity)
        └─> watchlist-sync (waits for rclone healthy, healthcheck: heartbeat file)
autoheal (independent, monitors all containers)
```

## Network

- Plex uses `network_mode: host` (required for DLNA/discovery)
- All other containers use Docker default bridge network
- Zurg listens on port 9999 (internal only)
- Plex listens on port 32400 (exposed via host network)
- UFW firewall allows: SSH, 32400 (Plex), 8080 (legacy), 9696 (legacy)

## Volumes

- `plex-config` — Plex database and settings (persist across restarts)
- `watchlist-data` — Watchlist manager state file (tracks what's been added)
- `/mnt/zurg` — FUSE mount point (not a Docker volume, host path)

## Key Design Decisions

1. **Custom watchlist-sync.py instead of Riven** — Riven created massive duplicates in RD by scraping at show/season/episode levels independently. Our script sends exactly one torrent per show to RD.

2. **Torrentio via HTTP proxy instead of Prowlarr** — Torrentio has the largest catalog. Prowlarr's public indexers were mostly Cloudflare-blocked from datacenter IPs. IPRoyal static residential proxy ($4/mo) solves this cleanly.

3. **rslave mount propagation for Plex** — Using `rshared` caused mount disconnections inside the Plex container. `rslave` inherits mount changes from the host. Combined with mount-watchdog.sh checking inside the Plex container.

4. **Plex libraries at /mnt/zurg/shows and /mnt/zurg/movies** — Originally used /media/shows and /media/movies, but these broke when the FUSE mount dropped. Mounting the parent `/mnt/zurg` with rslave is more resilient.
