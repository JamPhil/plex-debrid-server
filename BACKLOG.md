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

### [INVESTIGATE] Re-establish missing episode search mechanism after DUMB migration
- **Found**: 2026-04-07 during Andor/Paradise missing episode investigation
- **Context**: The old stack had `search-missing.sh` cron job (daily 3am CT) that queried Sonarr's `wanted/missing` API and triggered `EpisodeSearch` in batches. This was lost during DUMB v2.3.0 migration. See LESSONS-LEARNED.md #7 for the original problem and fix.
- **Symptoms**: 3 episodes sat missing indefinitely (Andor S01E01, S02E05, Paradise S01E02) because Sonarr's initial SeriesSearch missed them and RSS sync only catches new releases. No backfill mechanism exists.
- **Additional anomaly**: Sonarr's `wanted/missing` API returned 0 records despite 3 episodes having `hasFile=False` and `monitored=True`. This was not investigated — needs root cause analysis before re-implementing the search script (the script depends on this API).
- **Suggested fix**: Determine the correct approach for DUMB stack — could be a cron on the host, a DUMB built-in feature, or Sonarr config. Check if DUMB has a built-in mechanism before creating external scripts. If a script is needed, adapt the old `search-missing.sh` logic for the new stack.
- **Priority**: High — without this, any episode missed by the initial search will stay missing forever
- **Status**: Open

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
  1. Checks Seerr logs for repeated watchlist sync failures on the same item (logs at `/opt/dumb/log/` in DUMB stack)
  2. Alerts via Discord webhook when a single item has failed N consecutive times (e.g. 3+)
  3. Optionally auto-resolves by removing the blocking item from the Seerr watchlist and logging it for manual follow-up
- **Priority**: Medium
- **Status**: Open

---

### [INVESTIGATE] Verify Plex FSEvent auto-detection works in DUMB container
- **Found**: 2026-04-02 during scripts audit
- **Context**: In DUMB, Plex runs inside the same container as the rclone mount, eliminating the cross-container mount propagation issues of the old stack. Library folders are at `/mnt/debrid/decypharr_symlinks/`. No Sonarr/Radarr -> Plex notification connections configured. `ScheduledLibraryUpdatesEnabled=False`.
- **Symptoms**: Unknown — FSEvent detection was never tested in isolation in the DUMB environment. The old cross-container FUSE mount concern no longer applies, but inotify behavior on symlink directories inside the container is untested.
- **Suggested fix**: Test by adding a show/movie through Sonarr/Radarr and checking if Plex picks it up within 1-2 minutes without manual scan. If FSEvent works, notification connections are unnecessary. If not, add Plex connections to Sonarr and Radarr.
- **Priority**: Medium
- **Status**: Open

---

### [INVESTIGATE] Anime content issues — import blocking and indexer coverage
- **Found**: 2026-04-02 during Phase 4 Seerr testing
- **Context**: Tested Akira (1988 movie) and Cowboy Bebop (1998 TV) through Seerr pipeline
- **Symptoms**:
  - Akira: Grabbed from TPB, but Radarr import blocked with "release was matched to movie by ID. Manual Import required." Filename doesn't follow standard naming.
  - Cowboy Bebop: Sonarr search returned zero results — no grab events in history at all. 1998 anime likely has poor coverage on current indexers (TPB, TorrentLeech, YTS).
- **Suggested fix**:
  1. Akira: Force manual import via Radarr API, or investigate Custom Format / naming settings for anime
  2. Cowboy Bebop: Check Prowlarr interactive search results. May need an anime-specific indexer (Nyaa, AnimeTosho) added to Prowlarr
  3. Consider adding anime-focused indexer to Prowlarr for better coverage
- **Priority**: Medium
- **Status**: Open
