# Phase 5 — Scripts & Automation Rebuild

Created: 2026-04-02
Context: The Decypharr migration (Phases 1-4) replaced Zurg + rclone + blackhole with a single Decypharr container. All scripts written for the v1 architecture were deprecated and moved to `scripts/deprecated/`. This doc outlines what needs to be rebuilt for the new architecture.

## Current State

### Active scripts (no changes needed)
| Script | Purpose |
|--------|---------|
| `scripts/discord-notify.sh` | Generic Discord webhook sender. Used by other scripts. |
| `scripts/update-stack.sh` | `docker compose pull && up -d`. Architecture-independent. |
| `scripts/trash_cfs.py` | One-time TRaSH Guide custom format setup. Already applied, kept as reference. |

### Active cron jobs
| Schedule | Command | Status |
|----------|---------|--------|
| `17 */6 * * *` | Sonarr `MissingEpisodeSearch` via curl | OK — architecture-independent |

### Deprecated scripts (in `scripts/deprecated/`)
All moved 2026-04-02. These were written for the Zurg+rclone+blackhole architecture and reference dead paths (`/mnt/zurg/`), dead containers (`blackhole`, `zurg`, `rclone`), or deleted Plex library sections (3/4, now 7/6).

## Scripts to Rebuild

### 1. Mount Watchdog (replace `mount-watchdog.sh`)

**Old behavior**: Checked `/mnt/zurg/__all__/` on host and inside Plex container every 5 min. Restarted rclone/Decypharr/Plex if broken. Sent Discord alerts.

**What's changed**: Docker healthcheck + autoheal now handles restarts:
- Decypharr healthcheck: `ls /mnt/decypharr/realdebrid/__all__`
- Autoheal restarts unhealthy containers automatically
- Plex `depends_on: decypharr: condition: service_healthy`
- Mount propagation via `rshared` on `/mnt`

**Decision needed**: Is a separate watchdog still needed, or is Docker health infra sufficient?
- **Pro rebuild**: Discord notifications on mount failure (autoheal is silent), can verify Plex specifically sees the mount (not just Decypharr), catches edge cases Docker healthcheck misses
- **Pro skip**: Adds complexity, risk of the exact bug we just had (wrong path = restart loop). Grafana alerts (Phase 4c) can cover Discord notifications instead
- **Recommendation**: Skip for now. Revisit only if mount drops are observed that autoheal doesn't catch. If rebuilt, must check `/mnt/decypharr/realdebrid/__all__/` and should NOT restart Plex (only Decypharr).

### 2. Deploy Script (replace `deploy.sh`)

**Old behavior**: Validated .env, wrote Zurg config, started Zurg -> rclone -> blackhole -> all services in sequence. Verified health. Printed first-time setup instructions.

**What's changed**: Decypharr replaces 3 containers. Seerr replaces Overseerr. Monitoring stack is optional. Mount paths changed.

**Rebuild scope**:
- Validate .env (update required vars for Decypharr: `REAL_DEBRID_API_TOKEN`, `PLEX_CLAIM`, `DISCORD_WEBHOOK_URL`)
- Start Decypharr first (it creates its own rclone mount internally)
- Wait for Decypharr healthy, then start remaining stack
- Update first-time setup instructions for Seerr, Decypharr, new Plex library paths
- Reference correct ports and section IDs

**Priority**: Medium — only needed for fresh deployments or disaster recovery

### 3. Bootstrap Script (replace `bootstrap.sh`)

**Old behavior**: System setup (apt, Docker, firewall, fuse, timezone), created directory structure, generated .env template.

**What's changed**: Mount directory is `/mnt/decypharr/realdebrid/` (but Decypharr creates this itself). Symlinks dir unchanged. Plex library dir unchanged.

**Rebuild scope**:
- Change mount path references (though Decypharr may handle this via Docker volumes)
- Update .env template: remove `OVERSEERR_API_KEY`, add `SEERR_API_KEY`
- Verify directory creation matches docker-compose volume mounts
- Keep: system packages, Docker, firewall rules, timezone, fuse config

**Priority**: Low — only needed for fresh server setup

### 4. Backup/Restore Scripts (replace `backup-configs.sh` + `restore-configs.sh`)

**Old behavior**: Tarball of `docker-compose.yml`, `.env`, `zurg/config.yml`, `rclone/rclone.conf`, `scripts/`.

**What's changed**: Zurg and rclone configs no longer exist. Decypharr config lives inside its Docker volume.

**Rebuild scope**:
- Backup: `docker-compose.yml`, `.env`, `scripts/`, `prometheus/`, `grafana/`
- Consider backing up Decypharr config from its volume (`/var/lib/docker/volumes/...`)
- Consider backing up Sonarr/Radarr/Prowlarr SQLite DBs for faster recovery
- Restore: reverse of above, `docker compose down && extract && up -d`

**Priority**: Medium — important for disaster recovery but not urgent

### 5. Plex Metrics Exporter (replace `plex-metrics.sh`)

**Old behavior**: Prometheus textfile exporter writing to `/var/lib/node-exporter/plex_custom.prom`. Metrics: Plex library counts (sections 3/4), blackhole success/fail, zurg mount health.

**What's changed**: Sections 3/4 -> 7/6. Blackhole -> Decypharr. Zurg mount -> Decypharr mount.

**Decision needed**: Is this script needed at all?
- cAdvisor already provides container-level metrics
- Node Exporter provides host metrics
- Plex library counts could be a useful custom metric
- Decypharr health is covered by Docker healthcheck
- **Recommendation**: Defer to Phase 4c (monitoring re-enablement). Only rebuild if Grafana dashboards need Plex-specific metrics that aren't available from standard exporters.

### 6. Diagnose Missing Content (replace `diagnose-missing.sh`)

**Old behavior**: 5-step pipeline diagnosis: Prowlarr search -> Sonarr match -> Sonarr releases -> Zurg content check -> Plex content check.

**What's changed**: Steps 1-3 (Prowlarr/Sonarr/Radarr APIs) are unchanged. Step 4 path changed. Step 5 path unchanged.

**Rebuild scope**:
- Update Step 4: check `/mnt/decypharr/realdebrid/__all__/` instead of `/mnt/zurg/shows/`
- Consider adding a Step 4b: check Decypharr download client queue via Sonarr/Radarr API
- Consider adding RD API check: is the torrent actually in the user's RD account?

**Priority**: Medium — useful diagnostic tool but not blocking anything

## Plex Configuration Fixes (not scripts, but discovered during audit)

These should be addressed before or alongside Phase 5:

1. **`autoEmptyTrash=True`** — Dangerous with FUSE mounts. If a scan runs during a mount hiccup, Plex permanently deletes library entries. Should be set to `False`.

2. **No Sonarr/Radarr -> Plex notification connections** — Both return empty `[]` from `/api/v3/notification`. After each import, Sonarr/Radarr should trigger a targeted Plex library refresh (single show/movie, not full library scan). This is the proper way to keep Plex in sync without relying on filesystem events or full scans.

3. **`ScheduledLibraryUpdatesEnabled=False`** — Intentionally disabled to avoid excessive RD API calls, but with no notifications AND no scheduled scans, Plex has no way to discover new content. The notification connections (item 2) are the correct fix.

4. **Plex library rebuild needed** — The watchdog restart loop + auto-empty-trash degraded the TV library from 18 shows to 2. After fixing the above, a careful rescan is needed.
