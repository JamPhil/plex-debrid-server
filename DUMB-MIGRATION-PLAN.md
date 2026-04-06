# DUMB Migration Plan — Plex + Real-Debrid Server

## Context

We're migrating from a 15-container *arr stack (recently rebuilt with Decypharr) to DUMB (Debrid Unlimited Media Bridge) — a single-container solution that bundles all services internally. The server is currently at a clean slate after a full purge (April 5, 2026), making this the ideal time to migrate.

**Why:** Mount propagation issues, ffprobe rate limit floods, and configuration fragmentation have been recurring operational headaches. DUMB solves all three by embedding services in a single container with built-in coordination and ffprobe monitoring.

**Server:** DigitalOcean droplet 174.138.35.189 (4GB RAM, 2 vCPU, Ubuntu 24.04)

---

## Phase 1: Backup Current State

Before touching anything, preserve the current setup for rollback.

1. **SSH into server** and back up critical files:
   - `.env` (all API keys, tokens, passwords)
   - `docker-compose.yml` (current config)
   - `zurg/config.yml`, `rclone/rclone.conf`
   - `prometheus/prometheus.yml`
   - `grafana/provisioning/` and `grafana/dashboards/`
   - All docs (`docs/`, `CLAUDE.md`, `BACKLOG.md`, `REBUILD-PLAN.md`)

2. **Export Docker volumes** (Plex, Sonarr, Radarr, Prowlarr, Seerr configs):
   ```bash
   mkdir -p /opt/plex-server/backups
   for vol in plex-config sonarr-config radarr-config prowlarr-config seerr-config tautulli-config decypharr-config; do
     docker run --rm -v ${vol}:/data -v /opt/plex-server/backups:/backup alpine tar czf /backup/${vol}.tar.gz -C /data .
   done
   ```

3. **Record current credentials** from `.env`:
   - `REAL_DEBRID_API_TOKEN`
   - `PLEX_TOKEN`
   - `DISCORD_WEBHOOK_URL`
   - `TIMEZONE` (America/Chicago)

---

## Phase 2: Tear Down Current Stack

1. **Stop all containers**: `docker compose down`
2. **Verify nothing is running**: `docker ps`
3. **Unmount FUSE**: Ensure `/mnt/decypharr/` is cleanly unmounted
4. **Keep Docker volumes** intact for potential rollback — do NOT prune

---

## Phase 3: Deploy DUMB

1. **Create DUMB directory structure**:
   ```bash
   mkdir -p /opt/dumb/{config,log,data}
   mkdir -p /mnt/debrid
   ```

2. **Download DUMB docker-compose.yml**:
   ```bash
   cd /opt/dumb
   curl -O https://raw.githubusercontent.com/I-am-PUID-0/DUMB/master/docker-compose.yml
   ```

3. **Configure environment variables** in docker-compose.yml:
   - `TZ=America/Chicago`
   - `PUID=1000`
   - `PGID=1000`

4. **Start DUMB**:
   ```bash
   docker compose up -d
   ```

5. **Access DUMB frontend** at `http://174.138.35.189:3005`

---

## Phase 4: Guided Onboarding (via DUMB Web UI)

Walk through DUMB's onboarding to configure each service:

### 4a. Storage Layer — Decypharr + rclone
- Input Real-Debrid API token
- Configure `download_uncached: false` (reject non-cached)
- Mount point: `/mnt/debrid/`

### 4b. Media Server — Plex
- Use existing `PLEX_TOKEN` (NOT a new claim token — we want to reconnect to the existing Plex server identity)
- Verify Plex sees the debrid mount path
- **Disable all analysis features** (critical for RD API quota):
  - `GenerateBIFBehavior=never`
  - `LoudnessAnalysisBehavior=never`
  - `GenerateIntroMarkerBehavior=never`
  - `GenerateCreditsMarkerBehavior=never`

### 4c. Indexers — Prowlarr
- Add indexers:
  - The Pirate Bay (TPB)
  - YTS
- Sync to Sonarr + Radarr

### 4d. TV Management — Sonarr
- Quality Profile: WEB-2160p (or configure custom)
- Root folder: wherever DUMB maps the organized TV library
- Download client: should auto-configure to Decypharr
- Recreate custom format for season pack preference if applicable

### 4e. Movie Management — Radarr
- Quality Profile: WEB-2160p
- Root folder: wherever DUMB maps the organized Movies library
- Download client: auto-configured

### 4f. Request Management — Seerr
- Connect to Plex (authenticate with Plex account)
- Connect to Sonarr + Radarr (internal URLs)
- Enable Plex Watchlist sync
- Grant user AUTO_REQUEST permissions
- Set up Discord webhook notifications (for "content ready" alerts)

### 4g. Monitoring — Tautulli
- Connect to Plex
- Set up Discord webhook (agent_id=20)
- Configure new content notifications

---

## Phase 5: Verify Pipeline (End-to-End Test)

### Test 1: Movie Request
1. Add a popular movie to Plex Watchlist from Plex app
2. Wait for Seerr to detect and create request
3. Confirm Radarr picks up request and searches Prowlarr
4. Confirm Decypharr finds cached torrent on RD
5. Confirm movie appears in Plex library
6. Play movie — verify streaming works

### Test 2: TV Show Request
1. Add a currently-airing show to Plex Watchlist
2. Same verification chain as above through Sonarr
3. Confirm episodes appear in Plex

### Test 3: Resource Check
1. Check DUMB's built-in monitoring for CPU/memory usage
2. Verify 4GB RAM is sufficient with all services running
3. Watch for any RD rate limit warnings

### Test 4: ffprobe Monitoring
1. Verify DUMB's built-in ffprobe detection is active
2. Add 3-5 items at once (not bulk) and watch for ffprobe issues

---

## Phase 6: Cleanup

1. **Remove old stack** (only after DUMB is verified working):
   ```bash
   cd /opt/plex-server
   docker compose down
   docker volume prune  # Remove old volumes (after confirming backups)
   ```
2. **Keep backup directory** (`/opt/plex-server/backups/`) for 30 days
3. **Disable old cron jobs**: mount-watchdog, MissingEpisodeSearch

---

## What We Lose (Accepted Tradeoffs)

| Feature | Current | DUMB | Impact |
|---------|---------|------|--------|
| Grafana dashboards | Custom dashboards + 5 alert rules | Built-in metrics UI | Medium — less customizable but adequate |
| Prometheus + cAdvisor | Full metrics stack | Built-in monitoring | Medium — lose historical metrics depth |
| Discord alerts | Grafana → Discord webhook | DUMB monitoring TBD | Need to verify DUMB alerting capabilities |
| Doplarr | Discord request bot | Not included | Low — Plex Watchlist + Seerr covers single-user |
| Per-container control | Independent restarts | All-in-one | Low — DUMB handles health internally |
| mount-watchdog.sh | Custom FUSE health script | Eliminated (same-container mounts) | Win — problem solved by design |

---

## What We Gain

- **No more mount propagation issues** — Plex + rclone in same container
- **Built-in ffprobe monitoring** — detects and unsticks frozen scans
- **Auto-wired services** — no manual download client / indexer / root folder configuration
- **Guided onboarding** — reduces setup errors
- **Single container** — less Docker overhead on 4GB droplet
- **Easier updates** — one image to pull instead of 15

---

## Post-Migration Documentation

Once migration is verified, create `docs/DUMB-MIGRATION.md` documenting:
- Why we migrated (mount issues, ffprobe floods, complexity)
- DUMB version deployed
- Services enabled and their configuration
- Credentials carried over
- What changed (paths, ports, monitoring)
- How to access each service
- Rollback procedure (restore from `/opt/plex-server/backups/`)

Also update:
- `CLAUDE.md` — reflect new architecture
- `docs/DEVLOG.md` — log the migration
- Memory files — update project state

---

## Rollback Plan

If DUMB doesn't work out:
1. Stop DUMB: `docker compose -f /opt/dumb/docker-compose.yml down`
2. Restore old stack: `cd /opt/plex-server && docker compose up -d`
3. Restore volumes from backups if needed
4. Old stack is fully preserved in `/opt/plex-server/` with all configs
