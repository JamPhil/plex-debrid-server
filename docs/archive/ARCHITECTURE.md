# Architecture

## Media Request Flow

```
User -> Seerr (web UI) / Doplarr (Discord bot) / Plex Watchlist
       |
       v
Seerr (routes request to appropriate *arr app)
       |  (User needs AUTO_REQUEST permissions for Plex Watchlist sync)
       v
Sonarr (TV) / Radarr (Movies)
       |  Searches via Prowlarr for matching torrents
       v
Prowlarr (The Pirate Bay + YTS indexers)
       |  NOTE: Torrentio, 1337x, EZTV are CloudFlare-blocked from datacenter IPs
       |  Returns results ranked by quality profile
       v
Sonarr/Radarr sends .magnet to Blackhole download client
       |
       v
Blackhole script (westsurname/scripts)
       |  1. Checks if torrent is cached on Real-Debrid
       |  2. If cached: adds to RD, waits for mount, creates symlinks
       |  3. If not cached: fails the download (BLACKHOLE_FAIL_IF_NOT_CACHED=true)
       |  CRITICAL: REALDEBRID_HOST must be https://api.real-debrid.com/rest/1.0/
       |            (trailing slash required, /rest/1.0/ path required)
       v
Real-Debrid (cloud torrent cache)
       |
       v
Zurg (polls RD every 10s, exposes via WebDAV on port 9999)
       |
       v
rclone (FUSE mounts WebDAV to /mnt/zurg/)
       |
       v
Blackhole creates symlinks: /mnt/symlinks/*/completed/ -> /mnt/zurg/__all__/
       |
       v
Sonarr/Radarr import to /mnt/plex/TV/ or /mnt/plex/Movies/
       |
       v
Plex (scans /mnt/plex/ and /mnt/zurg/ libraries -> user watches on TV)
```

## Monitoring Flow

```
cAdvisor (container CPU, memory, network, disk metrics)
  Tuned: --housekeeping_interval=30s, --docker_only=true
  Disabled: percpu, sched, tcp, udp metrics (reduces CPU on 2 vCPU server)
  + Node Exporter (host OS metrics)
       |
       v
Prometheus (scrapes every 60s, stores 30 days)
       |
       v
Grafana (dashboards + 5 alert rules, 2m evaluation interval)
       |  Alert rule pattern: A (Prometheus query) -> B (Reduce) -> C (Threshold)
       |  Missing the Reduce step (B) causes all alerts to error
       |  Alerts: container down, high CPU/memory/disk, mount failure
       v
Discord webhook

Tautulli (monitors Plex directly)
       |  Alerts: new content added, server down, scan issues
       |  Discord notifier agent_id = 20 (NOT 18/Join)
       v
Discord webhook
```

## Container Dependencies

```
zurg (starts first, healthcheck: curl WebDAV)
  └─> rclone (waits for zurg healthy, healthcheck: ls /data/__all__)
        ├─> plex (waits for rclone healthy, healthcheck: curl /identity)
        └─> blackhole (waits for rclone + sonarr + radarr healthy)

prowlarr (independent, healthcheck: curl /ping)
  ├─> sonarr (waits for prowlarr healthy)
  └─> radarr (waits for prowlarr healthy)

plex + sonarr + radarr
  └─> seerr (waits for all three healthy)
        └─> doplarr (waits for seerr healthy)

plex
  └─> tautulli (waits for plex healthy)

cadvisor + node-exporter
  └─> prometheus
        └─> grafana

autoheal (independent, monitors all containers)
```

## Network

- Plex uses `network_mode: host` (required for DLNA/discovery)
- All other containers use Docker default bridge network
- Containers communicate by service name (e.g., `http://sonarr:8989`)
- UFW firewall allows: SSH (22), Plex (32400), Seerr (5055), Grafana (3000)

## Volumes

| Volume | Purpose |
|--------|---------|
| `plex-config` | Plex database and settings |
| `zurg-data` | Zurg state data |
| `prowlarr-config` | Prowlarr indexer configuration |
| `sonarr-config` | Sonarr library database and settings |
| `radarr-config` | Radarr library database and settings |
| `seerr-config` | Seerr request database |
| `tautulli-config` | Tautulli monitoring data |
| `prometheus-data` | Prometheus time-series metrics (30 day retention) |
| `grafana-data` | Grafana dashboards, users, alert state |
| `/mnt/zurg` | FUSE mount point (host path, not Docker volume) |
| `/mnt/symlinks` | Blackhole working directories (host path) |
| `/mnt/plex` | Organized library (host path, symlinks to mount) |

## Key Design Decisions

1. **Blackhole script instead of Decypharr** -- More proven, simpler, explicitly checks RD cache before committing. Better for hands-off reliability.

2. **TPB + YTS in Prowlarr** -- Torrentio is CloudFlare-blocked from datacenter IPs. 1337x and EZTV are also blocked. The Pirate Bay and YTS work without proxy from DigitalOcean. Eliminates IPRoyal proxy dependency.

3. **Prometheus + Grafana instead of custom scripts** -- Purpose-built monitoring with proper alerting thresholds, dashboards, and Discord integration. Replaces fragile shell scripts. Prometheus scrapes at 60s intervals; Grafana evaluates alerts every 2 minutes. cAdvisor tuned with 30s housekeeping and disabled unnecessary metrics to reduce CPU load on 2 vCPU server.

4. **Tautulli for Plex monitoring** -- Knows Plex's API natively, provides rich media notifications (new content, server health).

5. **Symlink-based library** -- Plex reads from `/mnt/plex/` (symlinks organized by Sonarr/Radarr) rather than directly from `/mnt/zurg/` (raw torrent names). This gives proper media naming and organization.

6. **rslave mount propagation for Plex** -- Using `rshared` caused mount disconnections inside the Plex container. Combined with mount-watchdog.sh checking inside the Plex container every 5 minutes.

7. **Seerr over Overseerr** -- Seerr (v3.1.0) is an actively maintained fork of Overseerr with continued development. Provides the same functionality with ongoing updates and bug fixes.

8. **Plex analysis fully disabled** -- All analysis features disabled via environment variables (GenerateBIFBehavior, LoudnessAnalysisBehavior, GenerateIntroMarkerBehavior, GenerateCreditsMarkerBehavior all set to `never`). Prevents excessive RD API calls that can cause bans, and reduces CPU load on the 2 vCPU server.
