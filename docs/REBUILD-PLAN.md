# Rebuild Plan: Replace Bridge Layer + Fix Search Strategy

**Created:** 2026-04-01
**Status:** Phases 1-3 executed in initial session. Phases 4-5 pending for next session.

## Context

The pipeline is broken: **569 failures, 0 successes in 24 hours**. The root cause is structural, not a single setting:

1. **westsurname/scripts blackhole** with `FAIL_IF_NOT_CACHED=false` polls RD API in an infinite loop for non-cached torrents, causing 859 rate-limit errors/day and blocking everything
2. **Sonarr's search strategy** grabs individual episode torrents for older shows (90.5% of failures are `S##E##`), which are poorly seeded and never RD-cached. Season packs for the same shows have 45-90 seeders and are likely cached.
3. **Accumulated damage**: 80 stuck processing files, 38 stalled RD downloads, 1,933 Sonarr blocklist entries, 3,534 RD torrents (many stale)
4. **Dead v1 scripts** on the server that could interfere with the new architecture

The fix needs to be structural: replace the fragile bridge tool, fix the search approach, clean out legacy scripts, and validate on a clean slate.

## Execution Phases

### Phase 1: Stop the Bleeding + Clean Slate

**Goal:** Halt all automation, purge accumulated state, remove legacy scripts, create a blank canvas.

**1a. Stop automation + monitoring containers:**
```
docker stop seerr doplarr blackhole grafana prometheus cadvisor node-exporter tautulli
```
- Seerr stopped to prevent watchlist auto-sync (36 movies, 102 shows would flood Sonarr/Radarr)
- Doplarr stopped (depends on Seerr)
- Blackhole stopped (no more RD API spam)
- Grafana/Prometheus/cAdvisor/Node Exporter/Tautulli stopped to prevent false alerts during rebuild
- Seerr and Doplarr stay stopped until Phase 4
- Monitoring stack stays stopped until Phase 4 (re-enabled after pipeline is validated)

**1b. Purge Sonarr/Radarr:**
- Delete ALL series from Sonarr (API: delete each series, files=false since symlinks are disposable)
- Delete ALL movies from Radarr (same approach)
- Clear Sonarr blocklist (1,933 entries)
- Clear Radarr blocklist
- Clear download queues and history

**1c. Purge Real-Debrid:**
- Delete all 3,534 torrents from RD account (API: loop through and delete)
- This cleans up stale/duplicate/stuck torrents from the blackhole spam

**1d. Purge Plex libraries:**
- Empty Movies and TV Shows libraries (Plex API: remove all items, or just let them disappear when symlinks are gone)
- Delete all symlinks from `/mnt/plex/Movies/` and `/mnt/plex/TV/`
- Delete contents of `/mnt/symlinks/sonarr/` and `/mnt/symlinks/radarr/`

**1e. Clean crontab:**
- Remove `search-missing.sh` entry (script being deleted)
- Remove `plex-metrics.sh` entry (needs rewrite for Decypharr, re-add in Phase 4)
- Keep `mount-watchdog.sh` entry (will be updated in Phase 2)

**1f. Remove dead v1 scripts:**

| Script | Why Remove |
|--------|-----------|
| `search-missing.sh` | Root cause of individual-episode flood. Sonarr's built-in search + Custom Formats handle this natively. |
| `symlink-import.sh` | Bridged blackhole -> Plex. Decypharr handles symlinks directly via qBittorrent API. |
| `watchlist-sync.py` | v1 custom script (Torrentio scraping, RD adding). Replaced by Seerr + *arr stack. |
| `watchlist-sync.sh` | Companion to watchlist-sync.py — deletes RD torrents not on watchlist. Would conflict with Sonarr/Radarr's torrent management. |
| `.watchlist-sync-state.json` | State file for dead watchlist-sync.py. |
| `torrentio-proxy.py` | SOCKS5 proxy for Torrentio. From v1, not used anymore. |
| `daily-report.py` + `daily-report.sh` | Hardcoded to check v1 components. Would report false information. |
| `healthcheck.sh` | Hardcoded v1 container list (`zurg rclone plex autoheal`). Superseded by Grafana alerting. |

**Action:** Move all dead scripts to `/opt/plex-server/scripts/deprecated/` (not delete -- preserves history in case we need to reference them).

### Phase 2: Replace Bridge Layer (Zurg + rclone + blackhole -> Decypharr)

**Goal:** Single container replaces 3, with proper qBittorrent API emulation and built-in cache checking.

**Why Decypharr:**
- Emulates qBittorrent API -- Sonarr/Radarr talk to it like a real download client (no filesystem-watching)
- Built-in RD cache check: `download_uncached: false` rejects non-cached torrents cleanly
- Built-in WebDAV server + embedded rclone -- replaces both Zurg and rclone
- Instant file availability (no Zurg 10-second polling delay)
- 640 GitHub stars, Go-based, actively maintained
- Eliminates the `on_created` filesystem spam entirely

**What gets removed:** `zurg`, `rclone`, `blackhole` containers
**What gets added:** `decypharr` container
**Net result:** 15 containers -> 13 containers (Seerr/Doplarr still exist, just stopped for now)

**2a. Update docker-compose.yml:**
- Comment out (don't delete) zurg, rclone, blackhole service definitions
- Add decypharr service:
```yaml
decypharr:
  image: cy01/blackhole:latest
  container_name: decypharr
  ports:
    - "8282:8282"
  volumes:
    - decypharr-config:/app
    - /mnt:/mnt:rshared
  devices:
    - /dev/fuse
  cap_add:
    - SYS_ADMIN
  security_opt:
    - apparmor:unconfined
  restart: unless-stopped
```
- Update Plex, Sonarr, Radarr `depends_on` to reference decypharr instead of rclone
- Add `decypharr-config` to volumes section

**2b. Create Decypharr config:**
```json
{
  "debrids": [{
    "name": "realdebrid",
    "api_key": "<RD_TOKEN>",
    "folder": "/mnt/zurg/__all__/",
    "use_webdav": true
  }],
  "qbittorrent": {
    "download_folder": "/mnt/symlinks/",
    "categories": ["sonarr", "radarr"]
  },
  "port": "8282",
  "download_uncached": false
}
```

**2c. Deploy and verify Decypharr:**
- `docker compose up -d decypharr`
- Verify WebDAV UI accessible at `:8282`
- Verify `/mnt/zurg/__all__/` is mounted and shows RD content (should be empty since we purged RD)

**2d. Switch Sonarr/Radarr download client:**
- Remove existing Blackhole (TorrentBlackhole) download client via API
- Add qBittorrent download client via API:
  - Host: `decypharr`, Port: `8282`
  - Category: `sonarr` / `radarr`
  - Username/Password: as configured
- Test connection from Sonarr/Radarr UI

**2e. Update mount-watchdog.sh:**
- Check Decypharr's mount health instead of rclone container
- Restart `decypharr` instead of `rclone` on mount failure

### Phase 3: Fix Search Strategy + Test

**Goal:** Validate the full pipeline with 3 hand-picked test items before opening the floodgates.

**3a. Configure Sonarr season pack preference:**
- Create "Season Pack" Custom Format in Sonarr (via API)
- Assign +100 score in the quality profile
- This makes Sonarr prefer season packs when both individual and pack releases exist
- Sonarr's built-in search already searches for both packs and individual episodes -- the Custom Format ensures it picks the pack when available

**3b. Manual test -- add 3 items directly to Sonarr/Radarr:**

| Test Case | What to Add | Why |
|-----------|------------|-----|
| Completed older show | e.g. The League (7 seasons, finished) | Should grab season packs, all RD-cached |
| Currently airing show | e.g. a show with new episodes weekly | Should grab individual episodes as they air |
| Movie | e.g. a popular movie | Simple case, verify Radarr->Decypharr->Plex |

**3c. Verify for each test item:**
- Sonarr/Radarr finds releases via Prowlarr
- Sonarr sends torrent to Decypharr (not blackhole)
- Decypharr checks RD cache, rejects non-cached, accepts cached
- Symlink created in `/mnt/plex/`
- Plex sees the content and can play it
- Zero 429 errors in Decypharr logs
- For the completed show: season pack grabbed (not 10+ individual episodes)

### Phase 4: Re-enable Request Pipeline + Monitoring (NEXT SESSION)

**Goal:** Layer Seerr, monitoring, and alerting back on once the pipeline is validated.

**4a. Re-enable monitoring stack:**
```
docker start prometheus cadvisor node-exporter grafana tautulli
```
- Monitoring comes back first so we can observe the Seerr flood
- Verify Grafana dashboards load, Prometheus scraping, alerts not firing spuriously

**4b. Update plex-metrics.sh:**
- Replace blackhole event counting with Decypharr metrics
- Re-add to crontab: `*/2 * * * *`

**4c. Start Seerr:**
```
docker start seerr
```
- Watchlist sync will auto-add 36 movies + 102 shows to Radarr/Sonarr
- With `download_uncached: false` + season pack preference, the flood is handled correctly

**4d. Monitor the flood:**
- Watch Decypharr logs for cache-check behavior
- Watch Sonarr/Radarr queues -- items should process quickly (cached) or fail fast (not cached)
- Verify no 429 rate limiting
- Verify season packs being preferred for completed shows
- Check Grafana for container health during high load

**4e. Start Doplarr:**
```
docker start doplarr
```

### Phase 5: Update Docs + Commit (NEXT SESSION)

- Update `docker-compose.yml` (already done in Phase 2)
- Update `CLAUDE.md` -- architecture, container list (13 not 15), data flow, common issues, remove references to zurg/rclone/blackhole configs
- Update `docs/ARCHITECTURE.md`
- Update `.env.example`
- Update `scripts/deploy.sh` and `scripts/backup-configs.sh`
- Append to `docs/DEVLOG.md`
- Commit and push

## Scripts Summary (final state)

| Script | Status | Notes |
|--------|--------|-------|
| `mount-watchdog.sh` | **UPDATED** | Checks decypharr mount, not rclone |
| `plex-metrics.sh` | **UPDATED** | Decypharr metrics instead of blackhole (Phase 4) |
| `deploy.sh` | **UPDATED** | New architecture deployment (Phase 5) |
| `backup-configs.sh` | **UPDATED** | Decypharr config instead of zurg/rclone (Phase 5) |
| `bootstrap.sh` | **KEEP** | Generic server init |
| `restore-configs.sh` | **KEEP** | Generic tarball restore |
| `update-stack.sh` | **KEEP** | Generic docker compose pull |
| `discord-notify.sh` | **KEEP** | Generic webhook helper |
| `diagnose-missing.sh` | **KEEP** | Prowlarr vs Sonarr diagnostic tool |
| `search-missing.sh` | **REMOVED** | Sonarr native search + Custom Formats |
| `symlink-import.sh` | **REMOVED** | Decypharr handles symlinks |
| `watchlist-sync.py` | **REMOVED** | Replaced by Seerr + *arr stack |
| `watchlist-sync.sh` | **REMOVED** | Would conflict with new architecture |
| `torrentio-proxy.py` | **REMOVED** | v1 artifact, unused |
| `daily-report.py/.sh` | **REMOVED** | Hardcoded v1 assumptions |
| `healthcheck.sh` | **REMOVED** | Hardcoded v1 container list |

## What Does NOT Change (structurally)

- Plex (still reads from `/mnt/plex/` and `/mnt/zurg/`)
- Prowlarr (still manages indexers)
- Sonarr/Radarr (still manage libraries -- different download client, same role)
- Monitoring stack (temporarily stopped during Phases 1-3, re-enabled Phase 4 -- no config changes except plex-metrics.sh)
- Autoheal

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Decypharr doesn't work | Old containers commented out, not deleted. Rollback = uncomment + restart. |
| RD purge loses content user was watching | User confirmed clean slate. Plex watchlist preserved on Plex account. |
| Seerr flood after re-enable | Decypharr rejects non-cached instantly. No infinite polling. Fast fail = fast retry with next release. |
| Mount path compatibility | Decypharr mounts to same `/mnt/zurg/` path -- Plex config unchanged |
| Season pack Custom Format doesn't work as expected | Test with manual items first (Phase 3) before enabling automation |
| Dead scripts interfere | All v1 scripts moved to deprecated/ dir in Phase 1, crontab cleaned |

## Rollback

If Decypharr doesn't work:
1. `docker stop decypharr`
2. Uncomment zurg/rclone/blackhole in docker-compose.yml
3. `docker compose up -d zurg rclone blackhole`
4. Switch Sonarr/Radarr download client back to Blackhole via API
5. Re-add content to Sonarr/Radarr (Seerr watchlist sync handles this)
6. Move deprecated scripts back if needed
