# Plex + Real-Debrid Streaming Server

Automated Plex media server that streams content via Real-Debrid. Users add shows/movies to their Plex Watchlist (or request through Seerr), and content appears in Plex within minutes -- found automatically via indexers, verified against RD cache, and mounted via FUSE.

## Current Architecture

**Platform:** [DUMB v2.3.0](https://dumbarr.com/) (Debrid Unlimited Media Bridge) -- a single Docker container bundling all services.

**Server:** DigitalOcean droplet (4GB RAM, 2 vCPU, Ubuntu 24.04) at `/opt/dumb/`

**Data flow:**
```
Plex Watchlist / Seerr (request)
  -> Sonarr / Radarr (media management)
  -> Prowlarr (indexer search: Zilean > TorrentLeech > TPB/YTS)
  -> Decypharr (RD cache check, torrent add, symlink creation)
  -> Real-Debrid (cloud torrent cache)
  -> rclone FUSE mount -> Plex (streaming)
```

## Key Access Points

| Service | URL |
|---------|-----|
| DUMB Dashboard | http://174.138.35.189:3005 |
| Plex | http://174.138.35.189:32400/web |
| Seerr (requests) | http://174.138.35.189:5055 |

## Documentation Guide

| File | Purpose |
|------|---------|
| **CLAUDE.md** | Full system reference -- architecture, credentials, ports, working rules, common issues. **Agents: start here.** |
| **BACKLOG.md** | Open issues and enhancements |
| **docs/DEVLOG.md** | Chronological record of changes (DUMB era, Apr 6+) |
| **docs/LESSONS-LEARNED.md** | Problems encountered and solutions (current stack only) |
| **docs/archive/** | Historical docs from earlier stack versions (v1/v2, pre-DUMB) |
| **legacy/** | Config files and scripts from earlier stack versions |

## GitHub Usage

This repo serves as version-controlled backup and change history. The running server does not pull from GitHub. Agents work on the local folder directly and push to GitHub after major milestones.
