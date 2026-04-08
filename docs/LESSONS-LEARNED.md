# Lessons Learned — Current Stack (DUMB v2.3.0)

These lessons still apply to the current architecture. For the full history (including v1/v2 issues), see `docs/archive/LESSONS-LEARNED-FULL.md`.

---

## 1. CloudFlare Blocks Datacenter IPs for Torrent Indexers

**Problem:** Torrentio, 1337x, EZTV, and other torrent sites return 403 from DigitalOcean server IPs. Cloudflare blocks datacenter IP ranges at the IP level (not User-Agent).

**Solution:** Use indexers that aren't CloudFlare-blocked (TPB, YTS, TorrentLeech). For Torrentio access, IPRoyal static residential HTTP proxy (~$4/month) routes requests through a residential IP.

**Key insight:** This is an IP-level block. No amount of header manipulation, FlareSolverr, or User-Agent changes will fix it. Either use a residential proxy or use different indexers.

---

## 2. ffprobe Rate Limiting on Debrid Mounts

**Problem:** Sonarr's hardcoded sample detection runs ffprobe on every imported file. Each probe triggers an RD API call through the FUSE/WebDAV mount path, bypassing Decypharr's rate limits. Bulk additions caused two major incidents (30 Rock on Apr 3, bulk watchlist on Apr 5 with 8,870 errors).

**Current mitigation:** DUMB v2.3.0 has built-in ffprobe monitoring that detects and unsticks frozen scans. This reduces the severity but doesn't eliminate the root cause.

**Rule:** Add content in small batches (3-5 items at a time). Never bulk-add 20+ shows simultaneously.

---

## 3. Zilean (DMM Hashlist) Should Be Priority 1 in Prowlarr

**Problem:** Zilean indexes torrents from other Real-Debrid users' shared hashlists (DebridMediaManager). These torrents are highly likely to already be cached on RD, meaning faster grabs and fewer wasted API calls.

**Current config:** Zilean at priority 1, TorrentLeech at 10, public indexers (TPB, YTS, StremThru) at 25. Sonarr/Radarr prefer Zilean results first.

**Key insight:** During the original build (March 2026), Zilean had an empty database and was removed. After DUMB re-deployed it (April 6), the DMM hashlist populated correctly (107 results for "Breaking Bad"). Always check if Zilean is populated before concluding it's useless.

---

## 4. Plex Analysis MUST Be Disabled

**Problem:** Plex's video analysis features (preview thumbnails, intro/credits detection, voice activity) generate heavy I/O. On a debrid FUSE mount, each file access triggers an RD API call, causing rate limit floods.

**Required settings:**
- Video preview thumbnails: **Never**
- Credits detection: **Never**
- Ad detection: **Disabled**
- Voice activity detection: **Never**
- `GenerateIntroMarkerBehavior=never`
- `GenerateCreditsMarkerBehavior=never`

**Key insight:** These settings must be checked after every Plex container recreation or update. They can silently revert to defaults.

---

## 5. Seerr Watchlist Sync Has a 20-Item Limit

**Problem:** Seerr only fetches the first 20 items from a Plex Watchlist per sync cycle (every 3 minutes). Items are processed from position 1 (newest), so new additions get picked up quickly, but older backlog items beyond position 20 sit indefinitely.

**Workaround:** For large initial imports, manually request items through the Seerr web UI rather than relying on watchlist sync.

---

## 6. Plex autoEmptyTrash Must Be Disabled

**Problem:** With `autoEmptyTrash=True` (Plex default), any partial library scan that doesn't find all files will permanently delete the "missing" entries. On a FUSE mount where temporary disconnections can make files invisible, this causes catastrophic library loss.

**Incident:** During v2, a mount-watchdog restart loop caused Plex to scan during mount reconnection, and autoEmptyTrash deleted shows (6 -> 2 TV shows in one session).

**Rule:** `autoEmptyTrash` must always be **unchecked/false**. Empty trash manually only after confirming the mount is healthy.

---

## 7. Sonarr SeasonSearch vs EpisodeSearch vs SeriesSearch

**Problem:** Sonarr has three distinct search types with different behaviors:
- **SeriesSearch** — searches for everything (season packs + individual episodes) — used on initial add
- **SeasonSearch** — season packs ONLY — does NOT fall back to individual episodes
- **EpisodeSearch** — individual episodes — most reliable for finding content that exists as singles

**Impact:** After initial SeriesSearch, any missed episodes stay missing forever unless EpisodeSearch is triggered. RSS sync only catches NEW episodes, not old missing ones.

**Current gap:** The old `search-missing.sh` cron job (daily EpisodeSearch on wanted/missing episodes) was lost during the DUMB migration. This needs to be re-established — see BACKLOG.md.

---

## 8. Seerr Watchlist Sync Requires Two Gates

**Problem:** Seerr watchlist sync silently does nothing if either gate is missing:

1. **Gate 1 (admin permissions):** AUTO_REQUEST + AUTO_REQUEST_MOVIE + AUTO_REQUEST_TV bits on user (permissions value 28674)
2. **Gate 2 (user-level DB toggles):** `watchlistSyncMovies=1` and `watchlistSyncTv=1` in the `user_settings` SQLite table

If the `user_settings` row doesn't exist for the user, watchlist sync silently skips — no errors, no logs.

**Fix:** `INSERT INTO user_settings (locale, watchlistSyncMovies, watchlistSyncTv, userId) VALUES ('', 1, 1, 1);`

---

## 9. Tautulli Discord Agent ID is 20

**Problem:** Tautulli notification agent IDs are not prominently documented. Using the wrong ID (e.g., 18 for "Join") creates a notification agent that silently accepts the Discord webhook URL but never sends.

**Correct IDs:** Discord = **20**, Slack = 14, Join = 18.
