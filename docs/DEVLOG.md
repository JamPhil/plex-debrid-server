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
