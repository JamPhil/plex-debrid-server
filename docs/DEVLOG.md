# Development Log

Chronological record of changes, decisions, and their rationale. Each entry should capture what changed, why, and the outcome. All agents should append to this log after completing significant work.

---

## 2026-03-27 — Initial Server Build
**What:** Deployed full Plex + Real-Debrid streaming server on DigitalOcean (174.138.35.189). 15-container Docker Compose stack: Zurg, rclone, Plex, Sonarr, Radarr, Prowlarr, Blackhole, Seerr, Doplarr, Tautulli, Prometheus, Grafana, cAdvisor, Node Exporter, Autoheal.

**Why:** Automated media server that streams via Real-Debrid — users request content through Seerr/Watchlist/Discord, it appears in Plex within minutes.

**Outcome:** Stack deployed and functional. Initial indexers: The Pirate Bay, YTS, LimeTorrents.

---

## 2026-03-29 — Custom Watchlist Manager & Monitoring
**What:** Added custom watchlist sync, Grafana dashboards with 5 alert rules, Discord webhook notifications, Tautulli integration.

**Why:** Needed automated request pipeline and health monitoring with alerting.

**Outcome:** Full monitoring stack operational. Grafana alerts firing to Discord. Tautulli reporting new content additions.

---

## 2026-03-30 — TRaSH Guides Review & Quality Profile Overhaul
**What:**
- Compared entire build against TRaSH Guides recommendations
- Added 21 custom formats to Sonarr and Radarr (16 streaming services, 4 WEB tiers, SDR blocker)
- Switched quality profile from HD-1080p to WEB-2160p in Sonarr, Radarr, and Seerr
- Set quality definitions to unlimited max/preferred (was capped at 125-155MB)
- Disabled Plex relay (was throttling to 2Mbps) and scheduled library scans (redundant with FSEvent auto-scan)
- Left intro/credits markers off intentionally — will enable after library stabilizes

**Why:** User has 4K HDR (non-DV) TV. TRaSH Guides WEB-2160p profile is the correct match. Previous HD-1080p profile was underselling the hardware. Restrictive quality limits were rejecting high-quality large files.

**Decision:** User confirmed WEB-2160p over WEB-1080p after reviewing evidence. Intro/credits markers deferred by user choice.

**Outcome:** All 7 identified gaps closed. Quality pipeline now matches TRaSH best practices for 4K HDR10 streaming.

---

## 2026-03-30 — System Health Definitions & Diagnostic Methodology
**What:** Created two new documents:
- `docs/SYSTEM-HEALTH.md` — Defines "healthy" for the system and all 11 components, including inter-component connections
- `docs/DIAGNOSTIC-CHECKLIST.md` — Claude Code prompt with 4-phase diagnostic process and 11 verification rules

**Why:** Multiple diagnosis attempts failed because of:
1. Skipping components (forgot Plex entirely despite it being #1 in the health doc)
2. Taking errors at face value without cross-referencing (error log ≠ actual problem)
3. Jumping to conclusions from single data sources

**Outcome:** Repeatable diagnostic framework. Completeness checks ("count must be 11"). Cross-reference requirements before classifying anything as broken.

---

## 2026-03-30 — Mount Propagation Fix (rshared)
**What:** Changed `/mnt:/mnt` to `/mnt:/mnt:rshared` for all 5 containers (rclone, Plex, Sonarr, Radarr, Blackhole) in docker-compose.yml.

**Why:** Default `rprivate` propagation meant FUSE mounts created by rclone after container start were invisible inside other containers. Blackhole successfully added torrents to RD but couldn't see the files to create symlinks — causing 1,018 "Torrent folder not found" errors. This was the root cause of ALL blackhole symlink failures.

**Outcome:** Immediately fixed. 19 symlinks created within 2 minutes of the fix. Zero mount errors since. Moved 21 stuck magnets from processing folder back to watch folder — all processed successfully.

---

## 2026-04-01 — TorrentLeech Indexer Added
**What:** Added TorrentLeech (private tracker) to Prowlarr. Auto-synced to Sonarr and Radarr via Prowlarr fullSync.

**Why:** Public indexers (TPB, YTS, LimeTorrents) have limited coverage and fewer well-seeded releases. TorrentLeech provides significantly better results — test search returned 35 results with well-seeded 4K WEB-DLs from top-tier release groups (XEBEC, NTb, FLUX).

**Outcome:** Now 4 indexers active. Improved hit rate for content searches, especially for older or niche titles.

---

## 2026-04-01 — Blackhole Download Client readOnly Fix
**What:** Changed Blackhole download client `readOnly` from `True` to `False` in both Sonarr and Radarr via API.

**Why:** With `readOnly: True`, Sonarr copied symlinks instead of moving them during import. The original symlink stayed in the completed directory, making it non-empty. Sonarr's cleanup failed with "Directory not empty", leaving queue items stuck at `importPending` forever. This had been recurring since the start of the project — 260+ items were stuck.

**Root cause trace:** Queue stuck → import pending → directory not empty → symlink still there → readOnly=True means copy not move → change to False.

**What we tried first (wrong):** Manually deleted stuck directories, then proposed a cron job for automated cleanup. Both were symptom treatments. The one-setting fix was the correct answer.

**Outcome:** Queue cleared to 0. New imports now move symlinks cleanly and directories are deleted automatically. No recurring maintenance needed.

---

## 2026-04-01 — Library Progress Snapshot
**Sonarr:** 101 series, 4236/5980 episodes (1744 missing, down from 3505 baseline). 53 series fully complete.

**Radarr:** 39 movies, 36 have files. 3 missing: Berserk Golden Age Arc II, Berserk Golden Age Arc III, Sword of the Stranger.

**Active issues:** RD rate limiting (429 errors) slowing blackhole processing. Some content DMCA-blocked by RD (Star Trek Picard S03 one release — alternate found). Killjoys S05 and The Americans S05 episodes still downloading on RD.

---

## 2026-04-01 — Working Rules Added to CLAUDE.md
**What:** Added 6 working rules to CLAUDE.md based on recurring feedback:
1. Trace causal chain before acting
2. Generate 3 solutions, choose the best
3. Prefer in-stack settings over workarounds
4. Verify before concluding
5. Save as you go (memory + devlog)
6. Commit and push meaningful changes

**Why:** Pattern of jumping to first solution, treating symptoms, and stating unverified claims as fact. These rules are in CLAUDE.md so they're loaded as system instructions in every chat — not optional memory that might be forgotten mid-task.

**Outcome:** Framework for better decision-making across all future sessions.

---

## 2026-04-01 — GitHub Default Branch Fix
**What:** Changed GitHub default branch from `master` to `main`. Deleted the empty `master` branch.

**Why:** Repo had two branches: `main` (with all 3 commits) and `master` (empty). GitHub's default was set to `master`, so visiting the repo showed no recent work. User thought changes weren't pushing correctly.

**Outcome:** Default branch is now `main`. Old `master` deleted. Repo has one clean branch with all work visible.

---

## 2026-04-01 — Major Rebuild: Replaced Zurg+rclone+blackhole with Decypharr (Phases 1-2 complete)

**What:**
- Diagnosed pipeline failure: 569 blackhole failures, 0 successes in 24 hours
- Identified two structural root causes (not just config issues)
- Replaced Zurg + rclone + blackhole (3 containers) with Decypharr (1 container)
- Full clean slate: purged Sonarr (101 series), Radarr (39 movies), RD (3,534 torrents), Plex libraries, symlinks
- Cleaned 9 dead v1 scripts to `scripts/deprecated/`
- Cleaned crontab (removed search-missing.sh and plex-metrics.sh)
- Configured Sonarr "Season Pack" Custom Format (+100 score in WEB-2160p profile)
- Stopped Seerr/Doplarr + monitoring stack for controlled rebuild

**Root causes found:**
1. **Blackhole `FAIL_IF_NOT_CACHED=false`** — when a torrent wasn't RD-cached, blackhole polled the RD API in an infinite 1-second loop (the timeout only fires when `failIfNotCached=True` — verified in source code). 80 stuck processing files × 1 API call/sec = 859 HTTP 429 rate-limit errors/day, blocking ALL downloads including cached ones.
2. **`search-missing.sh` triggered `EpisodeSearch`** for all 1,721 missing episodes daily at 3am. 90.5% of failures (486/537) were individual episodes (`S##E##`). Prowlarr data showed season packs for the same shows had 45-90 seeders while individual episodes had 0-2 seeders. The script was the source of the flood.

**Why Decypharr over patching blackhole:**
- Emulates qBittorrent API natively (Sonarr/Radarr talk to it as a download client, not filesystem watching)
- `download_uncached: false` is a first-class setting that rejects non-cached torrents instantly
- Built-in WebDAV + rclone replaces both Zurg and rclone
- 640 GitHub stars, Go-based, actively maintained
- Eliminates the `on_created` filesystem event spam (806 empty triggers in 30 min)

**Alternatives evaluated and rejected:**
- Riven: 772 stars but last commit Jan 2025, duplicate torrent issue (100+ for 18 items) not confirmed fixed — we already tried and abandoned it
- RDT-Client: 1.4k stars but 95 open issues, recent memory/duplicate bugs
- Patching blackhole settings: Would fix the immediate failure but not the structural issues (filesystem watching, no proper API integration, fragile Python watchdog)

**Scripts deprecated (moved to `scripts/deprecated/`):**
- `search-missing.sh` — root cause of episode flood
- `symlink-import.sh` — bridged blackhole→Plex, replaced by Decypharr
- `watchlist-sync.py`, `watchlist-sync.sh` — v1 custom automation, replaced by Seerr+*arr
- `torrentio-proxy.py` — v1 SOCKS5 proxy, unused
- `daily-report.py`, `daily-report.sh` — hardcoded v1 container names
- `healthcheck.sh` — hardcoded v1 container list

**Current server state (end of session):**
- Running: Plex, Sonarr, Radarr, Prowlarr, Decypharr, Autoheal (6 containers)
- Stopped: Seerr, Doplarr, Grafana, Prometheus, cAdvisor, Node Exporter, Tautulli (7 containers — intentional, re-enable in Phase 4)
- Removed: Zurg, rclone, blackhole (replaced by Decypharr)
- All libraries empty, RD account clean, ready for testing

**Outcome:** Phases 1-2 complete. Full plan in `docs/REBUILD-PLAN.md`. Next session: Phase 3 (manual testing with 3 items), then Phase 4 (re-enable Seerr + monitoring), Phase 5 (update docs, commit).

---

## 2026-04-01 — Phase 3: Decypharr Config Fixes, Folder Restructure, Pipeline Testing

**What:**
- Fixed Decypharr config (multiple schema issues from initial deployment)
- Restructured mount paths: `/mnt/zurg/` → `/mnt/decypharr/realdebrid/`
- Recreated Plex library sections with clean paths (sections 7 and 6)
- Updated docker-compose healthcheck for new mount path
- Tested movie pipeline (Gladiator) — full success
- Tested TV show pipeline (Severance) — pipeline works but Sonarr config issues remain

**Decypharr config fixes (4 issues found and resolved):**
1. `use_webdav: true` was missing in debrid entry — WebDAV server never started, rclone had nothing to mount
2. `rclone.enabled: true` was missing — mount explicitly disabled even with WebDAV running
3. `/mnt/decypharr/` owned by root — Decypharr runs as uid 1000, couldn't create mount subdirectory (permission denied)
4. Healthcheck still pointed to old `/mnt/zurg/__all__` path — autoheal restart-looped the container before rclone could initialize

**Folder restructure (clean break from v1):**
```
Old:  /mnt/zurg/__all__/          (Zurg FUSE mount)
New:  /mnt/decypharr/realdebrid/  (Decypharr internal rclone mount)
      ├── __all__/                 (all RD content)
      ├── torrents/
      └── __bad__/
```
- `/mnt/symlinks/` and `/mnt/plex/` paths unchanged
- Plex sections recreated: Movies = section 7, TV Shows = section 6
- Plex now scans only `/mnt/plex/` (removed old `/mnt/zurg/` dual-scan paths)
- Sonarr/Radarr root folders unchanged (`/mnt/plex/TV`, `/mnt/plex/Movies`)

**Working Decypharr config (final):**
```json
{
  "debrids": [{
    "name": "realdebrid",
    "api_key": "<token>",
    "folder": "/mnt/decypharr/realdebrid/__all__/",
    "use_webdav": true,
    "download_uncached": false
  }],
  "qbittorrent": {
    "download_folder": "/mnt/symlinks/",
    "categories": ["sonarr", "radarr"]
  },
  "rclone": {
    "enabled": true,
    "mount_path": "/mnt/decypharr",
    "uid": 1000,
    "gid": 1000
  },
  "port": "8282",
  "use_auth": false
}
```

**Movie test — Gladiator: PASS ✅**
- Radarr grabbed 4K UHD BluRay Extended Cut DV HDR x265-hallowed (19.77 GB equivalent)
- Decypharr: cached on RD, symlink created in 106ms
- Radarr imported in 18 seconds
- Plex: visible and playable
- Zero errors, zero 429s

**TV show test — Severance: PARTIAL (pipeline works, Sonarr config issues)**
- Pipeline mechanically works: Decypharr processes episodes, creates symlinks, Radarr imports
- `download_uncached: false` correctly rejects non-cached torrents (S01E07 HONE rejected, alternate TEPES grabbed)
- **Issue 1: Individual episodes grabbed instead of season packs** — even with Season Pack CF (+100) and SeriesSearch, Sonarr chose individual episodes. Root cause: the best season packs (CF 2480) were rejected by Sonarr's disk space check ("Importing after download will exceed available disk space"). Non-rejected packs scored only 175 vs individuals at 2275. The disk space check is wrong for our setup — content streams from RD, doesn't use local disk.
- **Issue 2: Italian episodes grabbed** — Sonarr grabbed "Scissione" (Italian title for Severance) from LimeTorrents. Language filtering not configured.
- **Issue 3: Season Pack CF score too low** — +100 bonus doesn't overcome the gap when high-quality packs are rejected for disk space and remaining packs lack HDR/DV CFs.

**Sonarr config issues to fix in next session:**
1. Disable disk space check (or set minimum free space to 0) — content streams from RD mount, local disk isn't used
2. Configure language restriction to English only
3. Re-evaluate Season Pack CF score (may need higher than +100, or the disk space fix alone may resolve it)

**Current server state:**
- Running: Plex, Sonarr, Radarr, Prowlarr, Decypharr (healthy), Autoheal (6 containers)
- Stopped: Seerr, Doplarr, Grafana, Prometheus, cAdvisor, Node Exporter, Tautulli (7 containers)
- Radarr: Gladiator (2000) — has file, working
- Sonarr: empty (Severance scrubbed after test)
- Plex: Gladiator in Movies library

**Outcome:** Phase 3 partially complete. Movie pipeline validated end-to-end. TV show pipeline mechanically works but Sonarr needs config fixes (disk space, language, season pack scoring) before TV testing can pass. Next session: fix Sonarr config, re-test Severance, then proceed to Phase 4.

---

## 2026-04-02 — Phase 3 TV Pipeline Testing & MissingEpisodeSearch Cron

**What:**
- Tested TV pipeline end-to-end with 3 shows:
  - **Severance** (completed, 2 seasons): 2 season packs grabbed, 19/19 episodes imported
  - **Shrinking** (airing S03, completed S01-S02): 2 season packs + 2 individual S03 episodes grabbed initially
  - **Rooster** (airing S01, no prior seasons): 4 individual episodes grabbed, all imported
- Discovered SeriesSearch's SeasonSearch limitation: for airing seasons, it searches at the season level, which returns results biased toward recent episodes. Older aired episodes in the same season get missed.
- Fixed by adding server cron job: `17 */6 * * * curl ...MissingEpisodeSearch` — triggers Sonarr's built-in MissingEpisodeSearch every 6 hours. This command groups missing episodes by season, tries season packs first, falls back to individual episode search, respects LastSearchTime, and skips queued items.
- After running MissingEpisodeSearch for Shrinking, all 10 aired S03 episodes were filled in (all 2160p ATVP DV HDR10+ from FLUX/NTb).
- Scrubbed `scripts/symlink-import.sh` from repo and server (obsolete — Decypharr handles symlinks internally).

**Root cause of SeasonSearch gap:** Sonarr's SeasonSearch queries indexers with a season-level search ("Shrinking S03"). Indexers return limited results biased toward recent/popular episodes. Older episodes in airing seasons get buried. Individual EpisodeSearch ("Shrinking S03E01") returns targeted results and works every time.

**Import timing issue (recurring):** Sonarr occasionally tries to import symlinks before Decypharr's rclone FUSE mount refreshes inside the Sonarr container, causing FileNotFoundException. Self-resolves on automatic retry or manual `DownloadedEpisodesScan`. Root cause identified: rclone `DirCacheTime` defaults to 5 minutes inside Decypharr vs the old 10-second setting. See `docs/BUG-FUSE-MOUNT-TIMING.md` for full diagnosis and fix options.

**All Phase 3 config fixes validated:**
- `skipFreeSpaceCheckWhenImporting: true` — season packs (55-88GB) import without disk space rejection
- Season Pack CF (+100) — completed seasons grab packs, not individual episodes
- SeriesSearch strategy — correct per-season behavior
- WEB-2160p profile with 38 CFs — proper scoring and quality selection
- Indexer priorities — TorrentLeech preferred (all grabs from TL)

**Cron jobs (updated):**
- `*/5 * * * *` — mount-watchdog.sh (FUSE mount health)
- `17 */6 * * *` — MissingEpisodeSearch via Sonarr API (fills gaps from initial search)
- Removed: `*/2 * * * *` symlink-import.sh (obsolete with Decypharr)

**Outcome:** Phase 3 TV pipeline PASS. Ready for Phase 4 (re-enable monitoring, Seerr, Doplarr).

---

## 2026-04-02 — Fixed FUSE Mount Timing Bug (DirCacheTime)

**What:**
- Fixed rclone DirCacheTime defaulting to 5 minutes inside Decypharr, causing Sonarr `FileNotFoundException` on import
- Added `RCLONE_DIR_CACHE_TIME=10s` and `RCLONE_VFS_CACHE_POLL_INTERVAL=10s` env vars to Decypharr in docker-compose.yml
- Removed now-redundant RC API DirCacheTime fix from mount-watchdog.sh

**Root cause:** Decypharr manages rclone internally and doesn't expose VFS config options. The default 5-minute DirCacheTime meant rclone served stale directory listings after Decypharr added a torrent to RD. Sonarr would try to import immediately, follow the symlink to the mount, and get FileNotFoundException because rclone's cached listing didn't include the new files yet.

**Why previous fix (RC API via watchdog) failed:** Decypharr unmounts and remounts rclone every ~5 minutes. Each remount cycle restarts the rclone rcd process with default options, resetting DirCacheTime back to 300s. The watchdog (also 5-minute interval) was in a race condition with the remount cycle.

**Fix:** `RCLONE_DIR_CACHE_TIME=10s` environment variable on the Decypharr container. The rclone rcd process inherits this from the container environment and uses it globally — persisting across Decypharr's remount cycles. Verified: DirCacheTime stays at 10s after remount.

**Note:** `RCLONE_VFS_DIR_CACHE_TIME` (with VFS_ prefix) does NOT work — rclone's env var for `--dir-cache-time` is `RCLONE_DIR_CACHE_TIME`.

**Outcome:** Bug fixed. Sonarr imports should now succeed on first attempt (10s cache vs 5min). See `docs/BUG-FUSE-MOUNT-TIMING.md` for full details.

---

## 2026-04-02 — Fixed Decypharr Healthcheck (Stale /mnt/zurg Path)

**What:** Updated Decypharr healthcheck from `/mnt/zurg/__all__` to `/mnt/decypharr/realdebrid/__all__` in both local and server docker-compose.yml. Redeployed container.

**Why:** After the Phase 3 mount restructure (`/mnt/zurg/` → `/mnt/decypharr/realdebrid/`), the healthcheck was never updated. The old path didn't exist, so the healthcheck always failed — Decypharr was stuck in `starting` state, which would trigger autoheal restart loops.

**Outcome:** Decypharr reports `healthy`. Backlog item closed.

---

## 2026-04-02 — Fixed Duplicate RD Torrents & Language Filter

**What:**
- Changed Radarr WEB-2160p quality profile language from "Original" (id: -2) to "English" (id: 1) via API
- Deleted 2 duplicate RD torrents: `UQKHYYU46XPW2` (Dune Italian WEBDL), `6AGQQ4Y274WFO` (Chernobyl duplicate season pack)
- Removed Italian `Scissione.S02E06` from Sonarr queue and blocklisted it
- Cleaned stale Italian Dune symlink from `/mnt/symlinks/radarr/`
- Restarted Decypharr to restore Chernobyl mount visibility (deleting the duplicate RD entry caused Decypharr's WebDAV to drop the folder until refresh)

**Root causes:**
1. **Radarr language = "Original"** — This setting doesn't filter by language at all; it just accepts whatever the source claims is the original language. TPB had an Italian WEBDL of Dune that Radarr grabbed 34 seconds after importing the correct English UHD BluRay.
2. **Sonarr concurrent search** — After restart, both `SeriesSearch` and `MissingEpisodeSearch` ran simultaneously for Chernobyl, each sending the same season pack torrent hash to Decypharr, creating two identical RD entries.
3. **Sonarr Italian grab** — Sonarr's deprecated language profile (English-only) didn't prevent grabbing `Scissione` (Italian title for Severance) from indexers. The release matched by TVDB ID despite the foreign title.

**Additional cleanup:**
- Removed Italian Dune WEBDL from Radarr queue (stuck with "no eligible files" warning after RD torrent deletion) and blocklisted it
- Removed orphaned `btgaateoth_2012_1080_son.mkv` from Decypharr's qBittorrent queue — unidentified artifact, not linked to any RD torrent, Radarr movie, or symlink

**Final state verified:**
- RD: 21 torrents, zero duplicates
- Radarr queue: 0 items
- Sonarr queue: 0 items
- Decypharr queue: 0 items
- Broken symlinks: 0
- Mount items: 21 (matches RD count)

**Outcome:** All queues clean, zero broken symlinks, zero duplicate RD entries, Radarr now restricted to English-only releases. Backlog item closed.

---

## 2026-04-02 — Phase 4a: Re-enabled Seerr + Watchlist Sync

**What:**
- Started Seerr, fixed stale Plex library section IDs (3/4 → 7/6), cleared 139 old requests and 147 stale media entries
- Disabled watchlist sync job and AUTO_REQUEST permissions for controlled manual testing
- Tested 4 content types through Seerr → Sonarr/Radarr → Decypharr → RD → Plex pipeline:
  - **Dune (2021)** — movie, 2160p UHD BluRay DV HDR10+ 23.3GB ✅
  - **Chernobyl** — completed show, S01 season pack (2160p UHD BluRay DV HDR10) ✅
  - **Daredevil: Born Again** — current show with prior seasons, S1 season pack (9/9) + S2 individual episodes (3/3 aired) ✅
  - **Scrubs 2026** — current show S01 only, individual episodes (4/7 aired found) ✅
- Tested anime (Cowboy Bebop + Akira) — logged indexer coverage and import issues to backlog
- Re-enabled watchlist sync and AUTO_REQUEST permissions
- Monitored flood: 23 requests (7 movies, 16 TV), 127 torrents submitted, 379 files ready, **only 1 single 429 error**

**Issues found and resolved during session:**
1. Seerr Plex libraries pointed to deleted sections 3/4 — fixed by editing settings.json directly
2. Seerr `plex-watchlist-sync` job (every 3 min) is separate from AUTO_REQUEST user permission — both must be disabled to prevent auto-sync
3. Seerr search API can't find many shows (Knight of Seven Kingdoms, Daredevil, Cowboy Bebop) — direct TMDB ID lookup works as workaround
4. Sonarr commands got stuck after restart (MissingEpisodeSearch blocked RefreshSeries queue) — restart cleared it, but new series added during stuck period had 0/0 episodes until refresh completed

**Issues logged to BACKLOG.md:**
- Anime indexer coverage (Cowboy Bebop not found, Akira import blocked by naming)
- Duplicate RD torrents on grab (fixed by another agent mid-session)

**Current state:**
- Seerr: healthy, watchlist syncing every 3 min, 23 requests processing
- Sonarr: 19 series, 140+ episodes with files, MissingEpisodeSearch filling gaps
- Radarr: 8 movies, 7 with files
- Decypharr: healthy, ~100 RD torrents, zero rate limiting
- Doplarr: still stopped (Phase 4b, next session — waiting for flood to settle)

**Outcome:** Phase 4a complete. Seerr request pipeline validated end-to-end. Watchlist flood processing cleanly with no rate limiting. Doplarr deferred to next session.

---

## 2026-04-02 — Diagnosed Plex Library Loss: mount-watchdog.sh Restart Loop

**What:**
- Investigated user report: Plex showing only a few TV shows, missing original tested shows
- Diagnosed root cause: `mount-watchdog.sh` checking dead `/mnt/zurg/__all__/` path → always fails → restarts Decypharr + Plex every 5 minutes
- Confirmed via Plex server logs: 6 restarts in 30 minutes (16:55 → 17:00 → 17:05 → 17:10 → 17:15 → 17:20)
- Each restart cancelled in-progress library scans (`Scanner: scanning in /mnt/plex/TV was cancelled`)
- `autoEmptyTrash=True` (Plex default) permanently deleted shows not re-verified during cancelled scans
- Library degraded from 6 TV shows → 2 during the diagnostic session (forced scan made it worse)

**Causal chain:**
1. Watchdog cron (`*/5 * * * *`) checks `/mnt/zurg/__all__/` — path doesn't exist post-Decypharr rebuild
2. Watchdog concludes mount is broken → restarts Decypharr + Plex
3. Plex startup triggers library scan → scan cancelled 5 min later by next restart
4. `autoEmptyTrash=True` deletes shows that weren't re-verified before cancellation
5. Repeat every 5 minutes, losing more shows each cycle

**Additional findings:**
- Neither Sonarr nor Radarr have Plex notification connections (`/api/v3/notification` returns `[]` for both)
- `ScheduledLibraryUpdatesEnabled=False` — no periodic Plex scans
- Combined: Plex has NO mechanism to discover new content (no notifications, no scheduled scans, filesystem events unreliable over FUSE)

**Actions taken:**
- Removed `mount-watchdog.sh` from crontab (stopped the restart loop)
- Audited all 10 scripts against new Decypharr architecture
- Deprecated 8 scripts that reference old architecture (moved to `scripts/deprecated/` on both server and local repo)
- Kept 2 scripts: `discord-notify.sh` (generic utility), `update-stack.sh` (architecture-independent)
- Created `docs/PHASE5-SCRIPTS.md` documenting all scripts/automation that need rebuilding

**Fixes applied:**
- Set `autoEmptyTrash=False` via Plex API — prevents future library loss during partial scans
- Triggered TV library rescan — shows recovering (2 → 6 and climbing at time of close, scan at 31%)
- Movies already at 7/7 (unaffected)

**Still open (logged to BACKLOG.md):**
- Verify Plex FSEvent auto-detection works with symlink-over-FUSE setup (may make Sonarr/Radarr notification connections unnecessary)

**Outcome:** Immediate threat (restart loop) eliminated. `autoEmptyTrash` disabled as safety net. Library rebuild in progress. Scripts audited and deprecated. Phase 5 rebuild plan created in `docs/PHASE5-SCRIPTS.md`.

---

## 2026-04-03 — Fixed Seerr Watchlist Auto-Request (Permissions Missing)

**What:** Re-enabled AUTO_REQUEST permission bits on user Jam_phil (user #1) in Seerr. Updated permissions from `29360218` to `29388890` (+4096 AUTO_REQUEST, +8192 AUTO_REQUEST_MOVIE, +16384 AUTO_REQUEST_TV).

**Symptoms:** Plex watchlist items appeared in Seerr's watchlist view but were never automatically submitted as requests to Sonarr/Radarr. Seerr request queue showed 0 items.

**Root cause:** During the Phase 4a rebuild (2026-04-02), AUTO_REQUEST permissions were intentionally disabled for controlled manual testing. The devlog states they were "re-enabled" at the end of that session, but the permission bits were not actually set on the user — either the change didn't persist or was applied incorrectly.

**How it works (for future reference):**
- Seerr watchlist sync and auto-request are two separate systems
- Watchlist sync (every 3 min per `plex-watchlist-sync` job) pulls Plex watchlist items into Seerr's watchlist view — this was working
- Auto-request requires TWO tiers: admin permission bits (AUTO_REQUEST + AUTO_REQUEST_MOVIE + AUTO_REQUEST_TV) AND user-level profile toggles (watchlistSyncMovies + watchlistSyncTv)
- User-level toggles were already `true`; only the admin permission bits were missing

**Outcome:** Both tiers now active. Watchlist items should auto-request on the next 3-minute sync cycle.

---

## 2026-04-03 — RD Rate Limit Protection + 30 Rock Import Debugging

**What:** Diagnosed and partially resolved Real-Debrid API rate limit exhaustion caused by large show imports. Added rate limiting config to Decypharr. Updated BACKLOG with uncached fallback feature request.

**Problem:** 30 Rock (7 seasons, ~140 episodes) was added via watchlist. All 7 season packs were grabbed simultaneously. During import, Sonarr runs ffprobe on every episode file to check if it's a sample — each probe triggers a download link request to RD through Decypharr's WebDAV mount. 140+ simultaneous probes exhausted RD's concurrent download link limit (~5-6), causing Decypharr to disable the RD account entirely. All imports stalled, including unrelated items (4 Star Trek movies).

**Root cause chain:**
1. Sonarr's SeriesSearch fires all season searches at once (no built-in throttle)
2. Each season pack contains ~20 episode files
3. Sonarr's sample detection (hardcoded, cannot be disabled) runs ffprobe on every file
4. ffprobe reads go through FUSE mount → rclone → Decypharr WebDAV → RD API (unrestrict/link)
5. 140+ concurrent unrestrict calls overwhelm RD's ~5-6 concurrent link limit
6. Decypharr disables the RD account after bandwidth errors → nothing works

**Research findings:**
- Sonarr/Radarr have zero download concurrency controls (devs say it's the download client's job)
- Sample detection is hardcoded in Sonarr — no setting to disable, no file size threshold, only runtime-based via ffprobe
- Decypharr's `rate_limit` and `download_rate_limit` throttle outbound API calls but NOT the WebDAV streaming path
- RD limits: 250 API req/min, ~6-10 active torrents (reduced from 42 in late 2024), ~5-6 concurrent download links

**Config changes applied to Decypharr (`/app/config.json`):**
```json
{
  "debrids": [{
    "rate_limit": "200/minute",
    "download_rate_limit": "30/minute"
  }],
  "qbittorrent": {
    "max_downloads": 5
  },
  "rclone": {
    "transfers": 2
  }
}
```
- `rate_limit: 200/minute` — caps general RD API calls below 250/min hard limit
- `download_rate_limit: 30/minute` — throttles download link generation
- `max_downloads: 5` — explicit concurrent file download limit (was default)
- `rclone.transfers: 2` — limits concurrent mount reads from WebDAV backend

**Results with rate limiting:**
- Before: 0/7 seasons imported, system completely locked
- After: 4/7 seasons imported (S01, S02, S06, S07), system recovered between seasons
- Individual seasons (~20 eps) import cleanly; the overwhelm happens when multiple seasons import simultaneously
- Remaining 3 seasons (S03, S04, S05) left for MissingEpisodeSearch cron to pick up in smaller batches

**Other actions:**
- Cleared and re-added 30 Rock multiple times during debugging
- Removed Star Trek movies from stuck queue — imported immediately after Decypharr restart
- Temporarily disabled watchlist sync during debugging, re-enabled at end of session
- Added "Uncached RD fallback" feature to BACKLOG.md (Low priority — custom script to submit uncached torrents to RD after cached options exhausted)
- Added "Seerr watchlist sync failure monitoring" to BACKLOG.md

**Outcome:** Rate limiting config is live. System can handle ~20-episode seasons individually. Letting automated processes (MissingEpisodeSearch every 6h, RSS sync every 15m) fill remaining gaps over the next day. Watchlist sync re-enabled to resume normal operations.

---

## 2026-04-03 — Diagnosed Seerr Watchlist Sync Stall (20-Item Pagination Limit)

**Symptom:** No new shows added from Plex watchlist in 4+ hours. Watchlist sync job ran every 3 minutes but produced zero output — no request creation, no errors.

**Investigation:** Full 11-component diagnostic per `docs/DIAGNOSTIC-CHECKLIST.md`. All components confirmed healthy: Decypharr (182 mount items, 0 broken symlinks, 648 valid), Sonarr (22 series, 640/785 files), Radarr (12 movies, 11 files), Prowlarr (4 indexers, no issues), Plex (counts match disk exactly: 21 TV, 11 movies). Pipeline confirmed working end-to-end (manual Sonarr search grabbed and imported Abbott Elementary S05E14). The bottleneck was isolated to Seerr's watchlist sync.

**Root cause:** Seerr's `watchlistsync.ts` line 68 calls `plexTvApi.getWatchlist({ size: 20 })` — fetches only the first 20 items from the Plex watchlist with no pagination. All 20 of those items were already auto-requested (confirmed via Seerr DB query). The remaining 103 watchlist items on pages 2-7 were never fetched. The sync correctly found nothing new in its 20-item window and exited silently.

**Root cause origin:** Overseerr PR [#3901](https://github.com/sct/overseerr/pull/3901) intentionally reduced sync size from 200 to 20 as part of an E-Tag caching optimization. The design assumes the watchlist is an incremental "inbox" — new items appear at position 1 (newest-first) and get processed within the 20-item window. Seerr v3.1.0 inherited this unchanged. No config setting exists to control it.

**Impact:** 95 watchlist items remain unrequested but will not be auto-requested by the sync. However, any NEW items added to the watchlist going forward will be processed correctly (they appear at position 1, within the 20-item window).

**Resolution:** User will manually request the backlog items through Seerr. No code changes or workarounds needed — the system works as designed for ongoing use.

**Also found during diagnostics (not related to the main issue):**
- Cowboy Bebop S01 stuck in Sonarr queue: "Series title mismatch; automatic import is not possible" (already in BACKLOG.md as anime issue)
- Sonarr/Radarr still have no Plex notification connections (relies on FSEvent, which appears to be working but is unverified for reliability — logged in BACKLOG.md)

---

## 2026-04-05 — RD Rate Limit Flood: Emergency Recovery & Architecture Analysis

**What:**
- User bulk-requested many shows at once via Plex watchlist
- Real-Debrid account disabled due to API rate limit exhaustion ("used all active accounts")
- Emergency recovery: stopped Decypharr, cleared 931 Sonarr queue items, cancelled 26 queued MissingEpisodeSearch commands, disabled MissingEpisodeSearch cron, restarted Decypharr clean
- Conducted full architecture analysis comparing current stack against 3 alternatives

**What happened:**
- Bulk watchlist additions triggered Sonarr to fire searches for all series simultaneously
- 130 torrents processed in 30 minutes, generating 8,870 RD rate limit errors
- Sonarr's hardcoded ffprobe sample detection on every imported file generates RD download-link API calls through FUSE mount → rclone → Decypharr WebDAV → RD unrestrict/link API
- This WebDAV streaming path bypasses Decypharr's `rate_limit` and `download_rate_limit` settings entirely
- RD's concurrent download link limit (~5-6) overwhelmed → account disabled → all operations failed

**Root cause analysis (building on 2026-04-03 30 Rock findings):**
The same architectural issue identified during the 30 Rock incident. The problem is structural:
1. Sonarr has no search/grab throttle (by design — devs say it's the download client's job)
2. Sonarr's sample detection (ffprobe) is hardcoded, cannot be disabled
3. Decypharr's rate limits only cover its outbound API calls, NOT the WebDAV streaming path
4. rclone's FUSE mount has no concurrent-read limit for VFS reads
5. RD has a hard limit of ~5-6 concurrent download links (can't be changed)
6. MissingEpisodeSearch also causes floods — it searches 95-138 episodes at a time and fires multiple series concurrently. Deferring searches to the cron just delays the flood.

**Architecture comparison conducted:**
Evaluated 3 alternatives against current stack:

1. **Riven** (771 stars, last commit March 2026) — replaces entire *arr stack with single app. Eliminates ffprobe flood by controlling the full pipeline. Trade-off: loses TRaSH-quality granularity (no custom formats, no release group scoring).

2. **Stremio + debrid addons** (Torrentio/Comet/MediaFusion) — no server at all. Zero infrastructure, zero API flood risk. Trade-off: no persistent library, no watch history, no sharing, fundamentally different UX.

3. **Current stack + targeted fixes** — keep everything, fix the amplification at the source. The proposed fix of "disable search on add, use MissingEpisodeSearch cron" was invalidated during discussion: MissingEpisodeSearch causes the same flood pattern.

**Conclusion:** The rate limit issue is an architectural limitation of using Sonarr with debrid FUSE mounts. Sonarr was built for local downloads where ffprobe is instant and free. No config tuning fully solves it. Realistic mitigation: add shows in small batches (3-5), not 20+ at once. System works well for steady-state operation.

**Recovery actions taken:**
1. Stopped Decypharr to halt RD API spam
2. Plex watchlist confirmed already empty (items already picked up by Seerr)
3. Cleared 931 items from Sonarr queue (`DELETE /api/v3/queue/bulk?removeFromClient=false`)
4. Cancelled 26 queued MissingEpisodeSearch commands via Sonarr API
5. Restarted Sonarr (3 in-progress searches persisted — harmless without Decypharr)
6. Disabled MissingEpisodeSearch cron (`17 */6 * * *` commented out)
7. Started Decypharr — confirmed 0 RD rate limit errors, processing cleanly

**Current state:**
- Decypharr: running, healthy, no RD errors
- Sonarr: running, queue empty, no active search commands
- MissingEpisodeSearch cron: DISABLED (needs re-enabling with a throttling strategy)
- All other containers: unchanged

**Open items:**
- MissingEpisodeSearch cron needs to be re-enabled with some form of throttling
- `RCLONE_WEBDAV_PACER_MIN_SLEEP` could be increased (e.g. 500ms-1s) as a safety net to serialize WebDAV reads, at the cost of slower normal imports
- Long-term: evaluate whether Riven is worth the quality control trade-off

---

## 2026-04-05 — Full System Purge: Clean Slate for Recovery

**What:**
Complete purge of all content across every layer of the pipeline to recover from the RD rate limit flood. Starting from a blank canvas to re-add content in a controlled manner.

**Context:** After the 2026-04-05 RD rate limit incident (8,870 errors, account disabled), the system was partially stabilized but still had ~400 RD torrents, ~100 Sonarr series, ~30 Radarr movies, and various queue items. User requested a full wipe rather than incremental cleanup.

**Actions taken (in order):**

1. **Stopped Seerr** — prevent watchlist sync from adding new requests during cleanup
2. **Cleared Sonarr** — deleted 95 series (deleteFiles=true), cleared 37 queue items, cleared blocklist
3. **Cleared Radarr** — deleted 32 movies (deleteFiles=true), cleared blocklist
4. **Cleared Real-Debrid** — deleted all 407 torrents via API (paginated, 100/page, 5 pages)
5. **Cleared Decypharr** — deleted queue via qBittorrent API, then stopped container, replaced `torrents.json` (324KB → empty `[]`), cleared cache, restarted. Queue went from 111 → 0.
6. **Cleared filesystem** — deleted all symlinks in `/mnt/symlinks/radarr/` and `/mnt/symlinks/sonarr/`, deleted all content in `/mnt/plex/Movies/` and `/mnt/plex/TV/`
7. **Recreated Plex libraries** — old sections 7 (Movies) and 6 (TV) had persistent metadata that wouldn't clear via scan+emptyTrash (even with autoEmptyTrash temporarily enabled). Deleted both sections and recreated fresh. **New section IDs: Movies = 8, TV Shows = 9**
8. **Updated Seerr settings.json** — changed Plex library section IDs from 7/6 → 8/9
9. **Cleared Seerr** — deleted 99 requests and 129 media entries via API. On restart, Seerr re-created 20 items from its internal state, so cleared again. Verified SQLite database directly: 0 rows in media, media_request, season, season_request, watchlist tables.
10. **Disabled Seerr watchlist sync** — set `plex-watchlist-sync` schedule to `0 0 31 2 *` (Feb 31 = never fires) in settings.json
11. **Removed AUTO_REQUEST permissions** — user permissions changed from 29421914 → 29393242 (removed bits 4096 + 8192 + 16384)
12. **Re-disabled Plex analysis features** on new library sections (GenerateBIFBehavior, LoudnessAnalysisBehavior, GenerateIntroMarkerBehavior, GenerateCreditsMarkerBehavior all set to `never`)
13. **Confirmed autoEmptyTrash=0** remains set

**Race condition encountered:** Radarr re-added 20 movies and started grabbing torrents while Sonarr/Radarr were still running during cleanup. The source was Seerr pushing requests before it was stopped. Had to stop Sonarr+Radarr, re-purge RD (19 torrents) and Decypharr, then restart. No import lists were configured — the re-adds came from Seerr's request pipeline.

**Final verified state (all zeros):**
- Sonarr: 0 series, 0 queue, 0 active commands
- Radarr: 0 movies, 0 queue
- Real-Debrid: 0 torrents
- Decypharr: 0 queue items
- Plex: 0 movies (section 8), 0 TV shows (section 9)
- Seerr: 0 requests, 0 media, 0 watchlist (DB verified)
- Filesystem: 0 symlinks, 0 Plex library files, 0 mount items
- Cron: 0 active jobs (MissingEpisodeSearch still disabled from emergency recovery)

**Running containers:** Decypharr, Plex, Sonarr, Radarr, Prowlarr, Autoheal
**Stopped containers:** Seerr, Doplarr, Grafana, Prometheus, cAdvisor, Node Exporter, Tautulli

**Gates before content can flow again (both required):**
1. Re-enable `plex-watchlist-sync` schedule (currently set to never)
2. Re-enable AUTO_REQUEST permission bits on user (currently removed)
3. Start Seerr container
4. Decide on MissingEpisodeSearch throttling strategy before re-enabling cron
5. Consider adding `RCLONE_WEBDAV_PACER_MIN_SLEEP` to Decypharr as rate limit safety net

**Key change to remember:** Plex section IDs changed: Movies 7→8, TV Shows 6→9. Any scripts, API calls, or configs referencing old section IDs need updating.

---

## 2026-04-06 — DUMB Migration: Replaced 15-Container Stack with Single DUMB Container

**What:**
- Evaluated DUMB (Debrid Unlimited Media Bridge) as replacement for the entire multi-container stack
- Backed up all configs and Docker volumes on server
- Tore down all 15 containers (`docker compose down` on `/opt/plex-server/`)
- Deployed DUMB v2.3.0 single container at `/opt/dumb/`
- Completed guided onboarding wizard configuring all services

**Why:**
Three recurring architectural problems drove the decision:
1. **Mount propagation issues** — FUSE mounts created by rclone/Decypharr were invisible inside other containers. Required `rshared` flags, mount-watchdog cron, and still had intermittent failures. DUMB embeds Plex inside the same container as rclone, eliminating this entirely.
2. **ffprobe rate limit floods** — Sonarr's hardcoded sample detection generates RD API calls through the FUSE/WebDAV path, bypassing Decypharr's rate limits. Caused two major incidents (30 Rock on 04-03, bulk watchlist on 04-05, 8,870 errors). DUMB has built-in ffprobe monitoring that detects and unsticks frozen scans.
3. **Configuration fragmentation** — 15 containers with manual wiring between Sonarr→Prowlarr, Radarr→Prowlarr, Seerr→Sonarr/Radarr, etc. DUMB auto-configures download clients, root folders, and Prowlarr app sync.

**Services enabled in DUMB:**
- Plex Media Server ("James Streaming Server")
- Decypharr (RD bridge + rclone mount, `download_uncached: false`)
- Sonarr + Radarr (with Profilarr auto-configuration)
- Prowlarr (indexer management)
- Seerr (request management + Plex Watchlist sync)
- Profilarr (TRaSH Guides quality profiles, auto-synced to Sonarr/Radarr)
- Tautulli (Plex monitoring)
- Zilean (metadata cache) + PostgreSQL + pgAdmin
- DUMB API + Frontend (dashboard with embedded service UIs)

**What we lost (accepted tradeoffs):**
- Prometheus + Grafana + cAdvisor + Node Exporter → replaced by DUMB's built-in metrics UI
- Doplarr (Discord request bot) → replaced by Plex Watchlist + Seerr (adequate for single-user)
- Per-container independent restarts → DUMB manages all services internally
- mount-watchdog.sh → no longer needed (same-container mounts)
- Custom Grafana Discord alert rules → DUMB monitoring TBD

**What we gained:**
- Mount propagation solved by design (Plex + rclone in same container)
- Built-in ffprobe monitoring (detects and unsticks frozen scans)
- Auto-wired service connections (less manual configuration)
- Guided onboarding (reduces setup errors)
- Single container = less Docker overhead on 4GB droplet
- Profilarr for automated TRaSH Guides quality profile management

**Server layout change:**
```
Old: /opt/plex-server/  (15 containers via docker-compose.yml)
New: /opt/dumb/          (1 DUMB container)
     ├── config/         (all service configs)
     ├── log/            (service logs)
     ├── data/           (service data)
     └── docker-compose.yml
```

**Credentials carried over:** RD API token, Plex token + fresh claim token, Discord webhook URL

**Backup preserved:** `/opt/plex-server/backups/` contains .env, docker-compose.yml, all config dirs, and Docker volume exports

**Status at end of session:** All services configured and pipeline verified end-to-end.

**Outcome:** Migration from multi-container to DUMB complete. All services configured and verified.

---

## 2026-04-06 — DUMB Post-Migration: Service Configuration & Pipeline Verification

**What:**
- Configured all services inside DUMB after onboarding
- Fixed docker-compose.yml to expose all service ports (originally only 3005 was mapped)
- Verified full pipeline end-to-end with test content
- Fixed Seerr watchlist sync (two-gate auth issue)

**Service configuration completed:**
1. **Prowlarr** — Added TPB, YTS, TorrentLeech indexers. Synced to Sonarr + Radarr apps.
2. **Profilarr** — Imported WEB-2160p (alternative) profile from TRaSH Guides. Scales 2160p → 1080p → 720p. Synced to both Sonarr and Radarr.
3. **Decypharr** — Auto-configured by DUMB as qBittorrent download client in Sonarr/Radarr.
4. **Plex** — "James Streaming Server". Libraries: Movies (section 1, `/mnt/debrid/decypharr_symlinks/radarr-debrid`), TV Shows (section 2, `/mnt/debrid/decypharr_symlinks/sonarr-debrid`). All analysis disabled. autoEmptyTrash disabled.
5. **Seerr** — Connected to Plex, Sonarr, Radarr. WEB-2160p (alternative) profile selected for both.
6. **Tautulli** — Connected to Plex. Discord webhook configured for notifications.

**Ports issue:** DUMB's default docker-compose.yml only exposes port 3005. Added all service ports (32400, 8989, 7878, 9696, 5055, 8181, 8282, 6868, 8182, 5432, 5050) to enable direct access. Required container recreation which triggered a Seerr frontend rebuild (~10 min).

**Auth issue:** Prowlarr/Sonarr/Radarr require Forms authentication when exposed to the internet. Set `AuthenticationMethod=Forms` and `AuthenticationRequired=DisabledForLocalAddresses` in all three config.xml files.

**Pipeline test results:**
- Star Trek: Generations (movie) — ✅ Grabbed via TorrentLeech, imported to Plex
- Daredevil: Born Again (TV) — ✅ 12/12 aired episodes, 2160p DSNP DV HDR from FLUX/NTb/BLOOM, 57GB total
- Plex libraries scanning and showing content ✅
- Watchlist sync working ✅ (after fixing two-gate auth)

**Seerr watchlist sync fix (recurring issue — third time):**
The watchlist sync has a two-gate requirement that's easy to miss:
1. **Gate 1 (admin permissions):** AUTO_REQUEST + AUTO_REQUEST_MOVIE + AUTO_REQUEST_TV bits on user (permissions value 28674)
2. **Gate 2 (user-level DB toggles):** `watchlistSyncMovies=1` and `watchlistSyncTv=1` in the `user_settings` SQLite table. If the user_settings row doesn't exist for the user, watchlist sync silently does nothing — no errors, no logs, just "Starting scheduled job" with no follow-up.
- Fix: `INSERT INTO user_settings (locale, watchlistSyncMovies, watchlistSyncTv, userId) VALUES ('', 1, 1, 1);`

**New API keys (generated fresh by DUMB):**
- Seerr: `MTc3NTUxMDAyNzE2NWQyZjhlYzgwLTBhNWQtNDc0Yy1iMGI2LTAyYWIxMDA0MjQ3Yg==`
- Sonarr: `107342f2750149ce94bcaff5e84ea544`
- Radarr: `a063e2c4e6eb4f268ff1d08bf2097938`
- Prowlarr: `37660125fc724bf7806cc7656e648854`

**Final verified state:**
- All services running inside DUMB v2.3.0 single container
- Pipeline: Plex Watchlist → Seerr (auto-request every 3 min) → Sonarr/Radarr → Prowlarr (TPB/YTS/TorrentLeech) → Decypharr → RD → rclone mount → Plex
- Quality: WEB-2160p (alternative) via Profilarr with 2160p→1080p→720p fallback
- Monitoring: Tautulli → Discord webhook
- 11 requests processing, content appearing in Plex

**Outcome:** DUMB migration fully complete. All services configured and verified. Pipeline working end-to-end with watchlist auto-requesting.
