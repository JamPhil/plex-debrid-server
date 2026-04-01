# Plex + Real-Debrid Streaming Server (*Arr Stack)

## Project Overview
Automated Plex media server that streams content via Real-Debrid. Users request shows/movies through Seerr (web UI), Plex Watchlist, or Discord bot (Doplarr). Content is automatically found via Prowlarr indexers, checked against RD cache by Blackhole, and appears in Plex within minutes.

## Architecture
- **DigitalOcean droplet**: 174.138.35.189 (4GB RAM, 2 vCPU, Ubuntu 24.04)
- **SSH key**: "robotrader" key (shared with another project)
- **Server path**: `/opt/plex-server/`
- **Mount point**: `/mnt/zurg/` (FUSE mount -> Real-Debrid content via Zurg WebDAV)
- **Symlinks**: `/mnt/symlinks/` (blackhole working directories)
- **Plex library**: `/mnt/plex/` (organized symlinks, read by Plex)

## Data Flow
```
Request -> Seerr/Doplarr -> Sonarr/Radarr -> Prowlarr (TPB + YTS indexers)
    -> Blackhole (check RD cache, add torrent, create symlinks)
    -> Real-Debrid -> Zurg -> rclone (/mnt/zurg/) -> Plex (/mnt/plex/)

Monitoring: cAdvisor + Node Exporter -> Prometheus (60s scrape) -> Grafana (5 alerts) -> Discord
Plex Monitoring: Tautulli -> Discord (agent_id=20)
```

## Tech Stack (15 containers)

### Storage Layer
1. **Zurg** -- Real-Debrid WebDAV bridge (exposes RD content as files)
2. **rclone** -- FUSE mounts Zurg's WebDAV to `/mnt/zurg/`

### Media Server
3. **Plex** -- Media server (libraries at `/mnt/plex/Movies/` and `/mnt/plex/TV/`, also scans `/mnt/zurg/`)

### Media Management (*Arr Stack)
4. **Prowlarr** -- Indexer manager (The Pirate Bay + YTS; 1337x/EZTV CloudFlare-blocked from datacenter)
5. **Sonarr** -- TV show library manager (quality profiles, episode monitoring)
6. **Radarr** -- Movie library manager (quality profiles)
7. **Blackhole** (westsurname/scripts) -- RD bridge (cache check -> add to RD -> symlink creation). CRITICAL: `REALDEBRID_HOST` must be `https://api.real-debrid.com/rest/1.0/` (trailing slash required, `/rest/1.0/` path required)

### Request Layer
8. **Seerr** (v3.1.0, fork of Overseerr) -- Web UI for browsing/requesting + Plex Watchlist integration. User needs AUTO_REQUEST permissions for watchlist sync.
9. **Doplarr** -- Discord bot for media requests (needs a real Discord bot token to function)

### Monitoring
10. **Tautulli** -- Plex monitoring (new content, server health -> Discord webhook, agent_id=20)
11. **Prometheus** -- Metrics scraper & time-series database (60s scrape interval)
12. **Grafana** -- Dashboards & alerting (5 alert rules, 2m eval interval, A->B(Reduce)->C(Threshold) pattern)
13. **cAdvisor** -- Container metrics collector (tuned: --housekeeping_interval=30s, --docker_only=true, disabled percpu/sched/tcp/udp metrics)
14. **Node Exporter** -- Host OS metrics collector

### Infrastructure
15. **autoheal** -- Auto-restarts unhealthy containers

## Key Files
- `docker-compose.yml` -- All 15 container definitions
- `zurg/config.yml` -- Zurg configuration (RD token, directory structure)
- `rclone/rclone.conf` -- rclone WebDAV config pointing to Zurg
- `prometheus/prometheus.yml` -- Prometheus scrape targets (60s interval)
- `grafana/provisioning/` -- Grafana datasources, dashboards, alert rules
- `grafana/dashboards/server-health.json` -- Server health dashboard
- `scripts/mount-watchdog.sh` -- Runs every 5 min, fixes FUSE mount drops
- `scripts/symlink-import.sh` -- Runs every 2 min, imports existing RD content
- `scripts/deploy.sh` -- Full deployment with setup instructions
- `scripts/bootstrap.sh` -- Fresh server initialization
- `.env` -- Secrets (NOT in git)
- `.env.example` -- Template with all required variables

## Credentials / Services
- **Real-Debrid**: API token in `.env` and `zurg/config.yml`, expires ~Sept 2026
- **Plex**: Claim token (one-time), ongoing token in `.env`
- **Discord webhook**: For Grafana, Tautulli, and Seerr alerts
- **Discord bot token**: For Doplarr media requests (placeholder -- needs real token)
- **Grafana**: Admin credentials in `.env`
- **Seerr**: API key in `.env` (SEERR_API_KEY)

## Plex Library Paths
- **Movies**: `/mnt/plex/Movies` (symlinks created by blackhole), Section ID: 3
- **TV Shows**: `/mnt/plex/TV` (symlinks created by blackhole), Section ID: 4
- Plex also scans `/mnt/zurg/` for direct mount content
- IMPORTANT: All Plex analysis is disabled to avoid excessive RD API calls:
  - `GenerateBIFBehavior=never`
  - `LoudnessAnalysisBehavior=never`
  - `GenerateIntroMarkerBehavior=never`
  - `GenerateCreditsMarkerBehavior=never`

## Mount Structure
```
/mnt/
├── zurg/          (rclone FUSE mount -- all RD content)
│   ├── __all__/   (all torrents, unorganized -- used by blackhole)
│   ├── movies/    (zurg auto-organization)
│   └── shows/     (zurg auto-organization)
├── symlinks/      (blackhole working directories)
│   ├── radarr/    (magnet files + completed symlinks)
│   └── sonarr/    (magnet files + completed symlinks)
└── plex/          (organized library -- symlinks to mount)
    ├── Movies/    (Radarr root folder)
    └── TV/        (Sonarr root folder)
```

## Cron Jobs (on server, CT timezone)
- `*/5 * * * *` -- mount-watchdog.sh (FUSE mount health)
- `*/2 * * * *` -- symlink-import.sh (import existing RD content)

## Service Ports
| Service | Port | External Access |
|---------|------|----------------|
| Plex | 32400 | Yes (host network) |
| Seerr | 5055 | Yes (user requests) |
| Grafana | 3000 | Yes (monitoring) |
| Sonarr | 8989 | Admin only |
| Radarr | 7878 | Admin only |
| Prowlarr | 9696 | Admin only |
| Tautulli | 8181 | Admin only |
| Zurg | 9999 | Internal only |
| Prometheus | 9090 | Internal only |
| cAdvisor | 8080 | Internal only |
| Node Exporter | 9100 | Internal only |

## Working Rules
1. **Trace the causal chain before acting.** When encountering an error, ask "why?" at least twice before taking any action. Fix root causes, not symptoms.
2. **Generate 3 solutions, choose the best.** Never lock onto the first fix that comes to mind. Consider at least three approaches, evaluate tradeoffs, and pick the best one. This applies to debugging, architecture decisions, and recommendations.
3. **Prefer in-stack settings over workarounds.** Check if there's a config or setting change that prevents the problem before reaching for scripts, cron jobs, or manual cleanup.
4. **Verify before concluding.** Never state unverified claims as fact. If a claim is load-bearing, check it first. Fetch docs, query APIs, read configs — then form conclusions.
5. **Save as you go.** After completing any fix, config change, or significant decision, immediately:
   - Save to memory (if it's context future chats need)
   - Append to `docs/DEVLOG.md` (chronological record of what changed, why, and the outcome)
   - Do not wait until end of chat — save after each significant action
6. **Commit and push meaningful changes.** After completing a body of work (fixes, config updates, new docs), commit to git and push to GitHub so all agents work from the same state.

## Common Issues
1. **FUSE mount drops inside Plex** -- mount-watchdog.sh handles automatically. Manual: `docker compose restart rclone && sleep 20 && docker compose restart plex`
2. **Blackhole fails to find cached content** -- Check RD account has active premium. Verify `/mnt/zurg/__all__/` is accessible. Verify `REALDEBRID_HOST` includes `/rest/1.0/` path.
3. **Seerr not syncing with Plex** -- Re-authenticate Plex connection in Seerr settings. Ensure user has AUTO_REQUEST permissions for watchlist sync.
4. **RD 451 error** -- Content blocked by Real-Debrid for legal reasons. Nothing to do.
5. **Grafana alerts not firing** -- Verify Discord webhook URL in Grafana contact points. Ensure alert rules follow A->B(Reduce)->C(Threshold) pattern (missing Reduce step causes all alerts to error).
6. **Tautulli Discord notifications not working** -- Verify agent_id is 20 (Discord), not 18 (Join).
7. **CloudFlare-blocked indexers** -- 1337x, EZTV, Torrentio are blocked from datacenter IPs. Use TPB and YTS in Prowlarr instead.
8. **Blackhole 404 on torrents/availableHosts** -- `REALDEBRID_HOST` is missing the `/rest/1.0/` path segment.
