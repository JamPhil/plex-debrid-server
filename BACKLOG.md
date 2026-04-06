# Backlog

Issues discovered during sessions but out of scope for that session's task. Another agent should pick these up.

**Format:** Copy the template below when adding a new item. Place newest items at the top.

---

### Template (copy this)
```
### [BUG/ENHANCE/INVESTIGATE] Title
- **Found**: YYYY-MM-DD during [what you were working on]
- **Context**: What's currently running/configured that matters
- **Symptoms**: What you observed
- **Suggested fix**: Your best guess at what to do (optional)
- **Priority**: High / Medium / Low
- **Status**: Open
```

---

<!-- Add new items below this line, newest first -->

### [ENHANCE] Uncached RD fallback — download torrents not cached on Real-Debrid
- **Found**: 2026-04-03 during pipeline discussion
- **Context**: Decypharr runs with `download_uncached: false`. If no cached torrent exists on RD for a requested title (old/obscure content), Sonarr/Radarr exhaust all Prowlarr results and give up. The content stays permanently "missing."
- **Desired behavior**: Exhaust all cached options first (current behavior), then fall back to submitting the best available torrent to RD for actual downloading from seeders.
- **Research findings (2026-04-03)**:
  1. Decypharr has no built-in "prefer cached, fall back to uncached" mode — `download_uncached` is a binary toggle
  2. Setting `download_uncached: true` would accept the first uncached torrent instead of trying all cached options first — wrong behavior
  3. Sonarr/Radarr v4 don't fall back between download clients; v5 has a PR but isn't released and only handles client-level failures
  4. Decypharr stalls uncached torrents rather than rejecting them, so even fallback mechanisms can't detect failure
- **Suggested fix**: Custom two-phase script that:
  1. Monitors Sonarr/Radarr for items stuck in "missing" after searches fail
  2. After a configurable threshold (e.g., 24 hours), queries Prowlarr API for best available torrent
  3. Submits directly to RD API as an uncached download (bypasses Decypharr)
  4. Alerts via Discord when falling back to uncached
- **Priority**: Low (enable if missing content becomes a recurring problem)
- **Status**: Open

### [ENHANCE] Monitor and auto-resolve Seerr watchlist sync failures
- **Found**: 2026-04-03 during Seerr watchlist diagnosis
- **Context**: Seerr's `plex-watchlist-sync` job processes 1 item per 3-minute cycle. If any item fails (e.g. "Missing TVDB ID from Plex Metadata"), it blocks the entire queue — no subsequent items get processed until the failing item is removed. Battlestar Galactica blocked 124 items for an unknown duration before being caught manually.
- **Symptoms**: Watchlist items appear in Seerr's watchlist view but no requests are created. Seerr logs show the same error repeating every 3 minutes on the same item.
- **Suggested fix**: Build a monitoring script or scheduled task that:
  1. Checks Seerr logs (or the API) for repeated watchlist sync failures on the same item
  2. Alerts via Discord webhook when a single item has failed N consecutive times (e.g. 3+)
  3. Optionally auto-resolves by removing the blocking item from the Seerr watchlist and logging it for manual follow-up
  4. Could be a cron job that parses `docker logs seerr` or a Seerr API poller
- **Priority**: Medium
- **Status**: Open

---

### [INVESTIGATE] Verify Plex FSEvent auto-detection works with symlink-over-FUSE setup
- **Found**: 2026-04-02 during scripts audit
- **Context**: Plex has `FSEventLibraryUpdatesEnabled=True` and `FSEventLibraryPartialScanEnabled=True`. Library folders (`/mnt/plex/`) are on ext4 (inotify should work), symlink targets are on FUSE mount. No Sonarr/Radarr → Plex notification connections configured. `ScheduledLibraryUpdatesEnabled=False`.
- **Symptoms**: Unknown — FSEvent was never tested in isolation. Previous failures were caused by the watchdog restart loop, not necessarily FSEvent. Now that the watchdog is removed, FSEvent may work fine on its own.
- **Suggested fix**: Test by adding a show/movie through Sonarr/Radarr and checking if Plex picks it up within 1-2 minutes without manual scan. If FSEvent works, notification connections are unnecessary. If not, add Plex connections to Sonarr and Radarr.
- **Priority**: Medium
- **Status**: Open

---

### [BUG] mount-watchdog.sh checks dead /mnt/zurg/ path — restarts Plex every 5 minutes, destroying library
- **Found**: 2026-04-02 during Plex library diagnosis
- **Context**: After Decypharr rebuild (Phase 2), mount path changed from `/mnt/zurg/__all__/` to `/mnt/decypharr/realdebrid/__all__/`. The mount-watchdog.sh cron job was never updated.
- **Symptoms**:
  - Plex restarting every 5 minutes (confirmed via log rotation: 16:55 → 17:00 → 17:05 → 17:10 → 17:15 → 17:20)
  - Each restart cancels any in-progress library scan (`Scanner: scanning in /mnt/plex/TV was cancelled`)
  - `autoEmptyTrash=True` (Plex server default) permanently deletes shows not re-verified during cancelled scans
  - Library degraded from 6 TV shows → 2 TV shows during a single diagnostic session
  - Scanner logs show repeated `Killing job`, `Waited over 10 seconds for a busy database; giving up`
- **Suggested fix**:
  1. **Immediate**: Update mount-watchdog.sh to check `/mnt/decypharr/realdebrid/__all__/` instead of `/mnt/zurg/__all__/`
  2. **Immediate**: Set `autoEmptyTrash=False` in Plex preferences (dangerous with FUSE mounts + restarts)
  3. **After stabilization**: Add Sonarr/Radarr → Plex notification connections (currently `[]` for both) so imports trigger targeted Plex refreshes
  4. **After stabilization**: Trigger careful library rescan to rebuild deleted entries
- **Priority**: Critical
- **Status**: FIXED (2026-04-02) — Removed watchdog cron entry. Deprecated the script. Set `autoEmptyTrash=False` via Plex API. Triggered library rescan — shows recovering (2 → 6 and climbing at time of close). See devlog for full details.

---

### [INVESTIGATE] Anime content issues — import blocking and indexer coverage
- **Found**: 2026-04-02 during Phase 4 Seerr testing
- **Context**: Tested Akira (1988 movie) and Cowboy Bebop (1998 TV) through Seerr pipeline
- **Symptoms**:
  - Akira: Grabbed `Akira 1988 BDRip 1080p x264 (Original English) [vLtrz]` from TPB, but Radarr import blocked with "release was matched to movie by ID. Manual Import required." Filename `Akira (Original English Audio).mp4` doesn't follow standard naming.
  - Cowboy Bebop: Sonarr search returned zero results — no grab events in history at all. 1998 anime likely has poor coverage on current indexers (TPB, TorrentLeech, YTS).
- **Suggested fix**:
  1. Akira: Force manual import via Radarr API, or investigate Custom Format / naming settings for anime
  2. Cowboy Bebop: Check Prowlarr interactive search results. May need an anime-specific indexer (Nyaa, AnimeTosho) added to Prowlarr
  3. Consider adding anime-focused indexer to Prowlarr for better coverage
- **Priority**: Medium
- **Status**: Open

---

### [BUG] Duplicate RD torrents on grab — Radarr language filter + Sonarr concurrent search
- **Found**: 2026-04-02 during Phase 4 Seerr testing
- **Context**: Both Dune (movie) and Chernobyl (series) created duplicate entries in Real-Debrid
- **Symptoms**:
  - Dune: Radarr grabbed Italian WEBDL from TPB (`Dune.2021.REPACK.4K.HDR.2160p.WEBDL Ita Eng x265-NAHOM`) 34 seconds after importing the correct English UHD BluRay from TorrentLeech. Language profile is "Original" (id: -2), doesn't block foreign releases.
  - Chernobyl: Same season pack (`F04DA7048...` hash) added to RD twice. After Sonarr restart, both `SeriesSearch` and `MissingEpisodeSearch` ran simultaneously, each sending the same torrent to Decypharr.
- **Suggested fix**:
  1. Change Radarr quality profile language from "Original" (id: -2) to "English" (id: 1) via `PUT /api/v3/qualityprofile/7`
  2. Delete duplicate RD entries: `UQKHYYU46XPW2` (Dune Italian), `6AGQQ4Y274WFO` (Chernobyl dup)
  3. Check for and remove Italian Severance episode (`Scissione`) from Sonarr queue
  4. Clean any stale symlinks from duplicates
- **Priority**: High
- **Status**: FIXED (2026-04-02) — Changed Radarr WEB-2160p language from "Original" to "English". Deleted 2 duplicate RD entries (Dune Italian UQKHYYU46XPW2, Chernobyl dup 6AGQQ4Y274WFO). Removed Italian Scissione S02E06 from Sonarr queue (blocklisted). Removed Italian Dune from Radarr queue (blocklisted). Cleaned stale Italian Dune symlink. Removed orphaned `btgaateoth_2012_1080_son.mkv` from Decypharr queue. Restarted Decypharr to restore Chernobyl mount visibility.

---

### [BUG] Decypharr healthcheck references dead /mnt/zurg/__all__ path
- **Found**: 2026-04-02 during Phase 4 planning
- **Context**: Decypharr mount was restructured in Phase 3 from `/mnt/zurg/` to `/mnt/decypharr/realdebrid/`. The devlog says "Updated docker-compose healthcheck for new mount path" but the local `docker-compose.yml` line 43 still has `["CMD", "ls", "/mnt/zurg/__all__"]`. Server may have been fixed directly via SSH without syncing the local file back.
- **Symptoms**: Local docker-compose.yml healthcheck points to a path that shouldn't exist. If redeployed from local file, autoheal would restart-loop Decypharr.
- **Suggested fix**: SSH in, verify which path the deployed compose uses. Update local `docker-compose.yml` line 43 to `["CMD", "ls", "/mnt/decypharr/realdebrid/__all__"]`. Redeploy if server copy also has the old path.
- **Priority**: High
- **Status**: FIXED (2026-04-02) — Updated healthcheck to `/mnt/decypharr/realdebrid/__all__` in both local and server docker-compose.yml. Redeployed. Decypharr now reports healthy.
