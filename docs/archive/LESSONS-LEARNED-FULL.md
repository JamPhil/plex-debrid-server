# Lessons Learned — What We Tried and Why

This document captures every significant problem encountered during setup, what was tried, what failed, and the final solution. Read this before making changes to avoid repeating mistakes.

---

## 1. Torrentio Blocked from Datacenter IPs

**Problem:** Torrentio (the primary torrent scraper) returns 403 Forbidden from DigitalOcean server IPs. Cloudflare blocks datacenter IP ranges.

**What we tried:**
- Direct access from server → 403
- FlareSolverr (Cloudflare bypass) → Added complexity, timed out on indexer additions, didn't reliably solve challenges
- Different User-Agent headers → Still 403 (IP-level block, not UA)
- SSH tunnel from user's home PC → Worked but requires PC to be on 24/7

**Solution:** IPRoyal static residential HTTP proxy (~$4/month). Routes Torrentio requests through a residential IP. Configured in docker-compose.yml as `TORRENTIO_PROXY` env var.

**Key insight:** This is an HTTP proxy, not SOCKS5. Python's `urllib.request.ProxyHandler` works for HTTP proxies. SOCKS5 requires the `pysocks` library.

---

## 2. Riven Created Massive Duplicates in Real-Debrid

**Problem:** Riven (the automation tool we initially used) scraped content at three levels independently: show, season, and episode. Each level could add its own torrent to RD. Result: 100+ torrents for 18 watchlist items, with 11 copies of the same Bob's Burgers 148GB torrent.

**What we tried:**
- `bucket_limit: 1` in Riven settings → Didn't help because each scrape level is independent
- Quality ranking adjustments → Reduced duplicates slightly but didn't fix root cause
- Post-hoc RD cleanup scripts → Complex, error-prone, accidentally deleted season packs

**Solution:** Replaced Riven entirely with a custom `watchlist-sync.py` script (~640 lines). This script:
- Queries Torrentio once per show (not per episode)
- Picks a single best result using our scoring logic
- Checks if content already exists in RD before adding
- Result: exactly one torrent per show, no duplicates

**Key insight:** The problem was architectural, not configurational. Riven's multi-level scraping is by design. No amount of setting tweaks could fix it. A simpler, custom solution gave us complete control.

---

## 3. FUSE Mount Drops Inside Plex Container

**Problem:** The rclone FUSE mount at `/mnt/zurg/` would periodically disconnect inside the Plex container, showing "Transport endpoint is not connected." The host mount remained fine.

**What we tried:**
- `rshared` mount propagation → Mount still dropped on container restarts
- Mounting subdirectories (`/mnt/zurg/movies`, `/mnt/zurg/shows`) → Same issue
- Plex's `FSEventLibraryUpdatesEnabled` → Doesn't work with FUSE mounts

**Solution (multi-part):**
1. Changed Plex mount to parent directory `/mnt/zurg:/mnt/zurg:rslave` (slave propagation inherits from host)
2. Updated mount-watchdog.sh to check mount INSIDE the Plex container, not just on host
3. Watchdog auto-restarts Plex when its mount drops (rclone restart only if host mount is broken)
4. Runs every 5 minutes via cron

**Key insight:** Docker containers get a snapshot of the mount namespace at creation time. If the FUSE mount is remounted (rclone restart), the container doesn't see the new mount. `rslave` propagation helps but isn't perfect. The watchdog is the safety net.

---

## 4. Plex Library Section IDs Changed

**Problem:** When we recreated Plex libraries with new paths, the section IDs changed from 1/2 to 3/4. Scripts referencing old IDs silently failed (scans triggered on nonexistent sections).

**Solution:** Updated all references in watchlist-sync.py, watchlist-sync.sh, and daily-report.py.

**Key insight:** Plex section IDs auto-increment and never reuse deleted IDs. After deleting and recreating libraries, always verify the new IDs via the API: `curl http://localhost:32400/library/sections?X-Plex-Token=TOKEN`

---

## 5. Torrentio Returns Wrong Shows (Title Mismatch)

**Problem:** Torrentio returned "Building Bad" for IMDB ID `tt11691774` (Only Murders in the Building). The torrent was incorrectly tagged in Torrentio's database.

**Solution:** Added title validation to `find_best_torrent()` in watchlist-sync.py. Before accepting a result, the script checks that at least 50% of the expected show name's significant words appear in the torrent filename. Mismatches are logged and skipped.

**Key insight:** Never trust scraper results blindly, even when using the correct IMDB ID. Always validate the torrent name against the expected title.

---

## 6. Zilean Had an Empty Database

**Problem:** Zilean (a shared hashlist scraper) synced IMDB data but imported 0 actual torrent hashes. Every search returned "No streams found."

**What we tried:**
- Waited for DMM sync to complete → It finished but the hashlist was empty
- Checked database directly → `SELECT count(*) FROM "Torrents"` returned 0

**Original solution (March 2026):** Removed Zilean. It depends on other DebridMediaManager users sharing their hashlists, which wasn't populated enough to be useful at the time.

**Update (April 2026):** After migrating to DUMB v2.3.0, Zilean was re-deployed and the DMM hashlist is now fully populated (107 results for "Breaking Bad"). Set to priority 1 in Prowlarr so Sonarr/Radarr prefer its results — since DMM content comes from other RD users, it's highly likely to already be cached.

---

## 7. Prowlarr Indexers Blocked by Cloudflare

**Problem:** Most useful torrent indexers (1337x, EZTV, TPB, RARBG) are behind Cloudflare and block datacenter IPs — the same problem as Torrentio.

**What we tried:**
- Added FlareSolverr as a proxy in Prowlarr → Timed out adding indexers
- Used non-Cloudflare indexers (LimeTorrents, YTS, RuTor) → Very limited catalog, mostly foreign content
- FlareSolverr with tag-based routing → Indexer additions timed out

**Solution:** Removed Prowlarr entirely. Torrentio (via residential proxy) has a larger catalog than all Prowlarr indexers combined and doesn't need per-indexer configuration.

---

## 8. Discord Webhook 403 from Python urllib

**Problem:** Discord webhooks returned 403 when called from Python's `urllib.request` but worked fine with `curl`. Error code 1010 (Cloudflare block).

**Solution:** Switched Discord webhook calls to use `subprocess.run(["curl", ...])` instead of `urllib.request`. Curl has a different TLS fingerprint that isn't blocked.

**Key insight:** Cloudflare fingerprints TLS clients. Python's urllib gets flagged as bot traffic from datacenter IPs. Curl doesn't. Use curl for any Cloudflare-protected endpoint.

---

## 9. Plex Scan Stuck on Specific Folders

**Problem:** Plex scan would hang at 35% when processing "PLUR1BUS" (stylized name with number substitution). All other shows queued behind it couldn't scan.

**Cause:** Combination of: (a) Plex metadata agent struggling to match the stylized name, (b) files on FUSE mount timing out during media analysis.

**Solution:** Deleted the problematic torrent from RD, let watchlist-sync pick a different version with a more standard naming convention. Plex scanned the replacement without issues.

**Key insight:** Torrent naming affects Plex's ability to match metadata. Season packs from well-known release groups (e.g., `-FLUX`, `-NTb`) have standardized naming that Plex handles well. Avoid obscure release groups with non-standard naming.

---

## 10. RD 451 "Unavailable For Legal Reasons"

**Problem:** Some content (e.g., "The Agency") returns HTTP 451 when adding the magnet to Real-Debrid. This is a legal takedown — RD refuses to host it.

**Solution:** No fix. This is a legal restriction on RD's end. The watchlist-sync script logs these as "blocked by RD" and the daily report lists them. User needs to find alternative sources or accept that some content isn't available via RD.

---

## 11. Intro/Credits Detection Overloads Small Server

**Problem:** Plex's intro/credits marker detection caused high CPU usage on the 2GB droplet, slowing down library scans significantly.

**Solution:** Disabled during initial setup: `GenerateIntroMarkerBehavior=never`, `GenerateCreditsMarkerBehavior=never`. Can be re-enabled later with `scheduled` after the library is fully built.

---

## 12. Stack Complexity vs. Simplicity

**Original stack (10 containers):** Zurg, rclone, Plex, Riven backend, Riven frontend, PostgreSQL, Prowlarr, FlareSolverr, Zilean, autoheal

**Final stack (5 containers):** Zurg, rclone, Plex, watchlist-sync, autoheal

**Key insight:** Every additional service added failure modes, memory usage, and configuration complexity without proportional benefit. The custom watchlist-sync.py replaced 5 services (Riven backend/frontend, PostgreSQL, Prowlarr, Zilean) with 640 lines of Python and no external dependencies beyond `pysocks`. Memory usage dropped from ~1.5GB to ~700MB, freeing headroom on the 2GB droplet.

---

## 13. Blackhole REALDEBRID_HOST Must Include /rest/1.0/ Path

**Problem:** Blackhole (westsurname/scripts) returned 404 errors on `torrents/availableHosts` endpoint. Torrents were never being checked against RD cache.

**What we tried:**
- Set `REALDEBRID_HOST=https://api.real-debrid.com` → 404 on all API calls
- Checked Blackhole logs → requests going to `/torrents/availableHosts` without the base path

**Solution:** Set `REALDEBRID_HOST=https://api.real-debrid.com/rest/1.0/` (trailing slash required). The Blackhole script appends endpoint paths directly to this base URL, so the full REST API path must be included.

**Key insight:** Always check what a script does with its base URL config. Some tools append `/rest/1.0/` themselves; Blackhole does not. The trailing slash matters too — without it, paths get concatenated incorrectly.

---

## 14. Grafana Alert Rules Require A->B(Reduce)->C(Threshold) Pattern

**Problem:** All Grafana alert rules showed "Error" state immediately after creation. No alerts were firing despite conditions being met.

**What we tried:**
- Verified Prometheus datasource connection → working fine
- Tested Prometheus queries directly → returned valid data
- Checked Grafana logs → "input data must be a wide series but got type not" errors

**Solution:** Every Grafana alert rule needs three expressions in sequence:
- **A**: Prometheus query (returns time-series data)
- **B**: Reduce expression (converts time-series to single value using `last()`, `mean()`, etc.)
- **C**: Threshold expression (compares reduced value against threshold)

Skipping the Reduce step (B) and going directly from A to C causes the "not wide series" error because the Threshold expression cannot operate on raw time-series data.

**Key insight:** Grafana's alert evaluation pipeline is strict about data types. Time-series data must be reduced to a single number before threshold comparison. This isn't obvious from the UI, which lets you skip the Reduce step without warning.

---

## 15. Tautulli Discord Notification Agent ID is 20

**Problem:** Tautulli Discord notifications were configured but never sent. No errors in Tautulli logs, but Discord webhook was never called.

**What we tried:**
- Verified Discord webhook URL → worked with manual curl test
- Checked Tautulli notification settings → agent appeared configured

**Solution:** The Tautulli notification agent_id for Discord is **20**, not 18. Agent 18 is "Join" (a different notification service). When configuring via API or scripts, using the wrong agent_id creates a notification agent for the wrong service that silently accepts the webhook URL but never sends to Discord.

**Key insight:** Tautulli agent IDs are not documented prominently. The correct IDs can be found in the Tautulli API docs or by inspecting the notification agents page source. Discord = 20, Slack = 14, Join = 18.

---

## 16. Seerr Watchlist Sync Needs AUTO_REQUEST User Permissions

**Problem:** Plex Watchlist items were not being automatically requested in Seerr (fork of Overseerr). Users could browse and manually request, but watchlist sync did nothing.

**Solution:** The Seerr user account linked to Plex needs AUTO_REQUEST permissions enabled. Without this, Seerr sees the watchlist items but won't create automatic requests for them. Configure in Seerr → Users → Edit user → Permissions → enable "Auto Request" for both movies and TV.

**Key insight:** Watchlist sync is a two-step process: (1) Seerr reads the watchlist (requires Plex connection), (2) Seerr creates requests for new items (requires AUTO_REQUEST permission). Step 1 works without the permission, making it look like sync is working when it's actually silently skipping the request creation.

---

## 17. cAdvisor and Prometheus Tuning for Low-Resource Servers

**Problem:** On a 2 vCPU / 4GB RAM server running 15 containers, cAdvisor and Prometheus consumed noticeable CPU, competing with Plex for resources during media playback.

**What we tried:**
- Default cAdvisor settings → high CPU from per-CPU metrics and frequent housekeeping
- Default Prometheus 15s scrape interval → excessive scraping for a non-critical monitoring setup

**Solution (multi-part):**
1. **cAdvisor tuning:**
   - `--housekeeping_interval=30s` (default 1s — reduces CPU sampling frequency)
   - `--docker_only=true` (ignores non-Docker cgroups)
   - Disabled metrics: `--disable_metrics=percpu,sched,tcp,udp` (not needed for our alerting)
2. **Prometheus tuning:**
   - Scrape interval: 60s (up from default 15s — sufficient for alerting on 2m evaluation intervals)
   - Retention: 30 days (adequate for trend analysis without filling disk)
3. **Grafana tuning:**
   - Alert evaluation interval: 2m (fast enough to catch outages, slow enough to not waste CPU)

**Key insight:** Monitoring tools are designed for large infrastructure and default to aggressive collection intervals. On a small server, tuning these intervals down significantly reduces overhead with no practical impact on alert responsiveness. A 60s scrape with 2m alert evaluation still catches any outage within 3 minutes.

---

## 18. Tautulli API: Config is in `[PMS]` Section, Not `[General]`

**Problem:** When querying Tautulli's `config.ini` for PMS connection settings (`pms_ip`, `pms_port`, `pms_token`, etc.), all values appeared as "NOT SET" — leading to a false conclusion that Tautulli wasn't connected to Plex, when it was actually working perfectly and actively sending Discord notifications.

**Root cause:** Two compounding errors:
1. The Tautulli API command `server_info` does not exist — the correct command is `get_server_info`. The wrong command returned an "Unknown command" error that was misinterpreted as a connection failure.
2. PMS settings in `config.ini` are stored under the `[PMS]` section, not `[General]`. Reading from `[General]` returns nothing.

**Config file structure:**
```ini
[General]
# General Tautulli settings (http_port, api_key, etc.)
# Does NOT contain PMS settings

[PMS]
# All Plex Media Server connection settings live here
pms_ip = 172.17.0.1
pms_port = 32400
pms_token = <token>
pms_identifier = <machine-id>
pms_name = <server-name>
pms_url = http://172.17.0.1:32400

[Advanced]
pms_timeout = 15

[Monitoring]
monitor_pms_updates = 0
```

**How to properly verify Tautulli-Plex connection:**
```bash
# Correct API command (not "server_info")
curl "http://localhost:8181/api/v2?apikey=KEY&cmd=get_server_info"

# Check connection status
curl "http://localhost:8181/api/v2?apikey=KEY&cmd=server_status"
# Returns: {"connected": true}

# If reading config.ini directly, use [PMS] section
python3 -c "import configparser; c=configparser.ConfigParser(); c.read('/config/config.ini'); print(c['PMS']['pms_ip'])"
```

**Key insight:** When diagnostics contradict observable behavior (notifications ARE being sent), question the diagnostic method before concluding something is broken. Cross-reference multiple signals: container health, uptime, active notification agents, and actual notification delivery.

---

## 19. Sonarr/Radarr Blackhole: `removeCompletedDownloads` Must Be `True`

**Problem:** The Sonarr queue kept filling with 22+ blocked Bob's Burgers S15 entries that had to be manually cleared every few hours. They reappeared after every RSS sync.

**Root cause:** `removeCompletedDownloads` was set to `False` on the Torrent Blackhole download client. After blackhole processed a torrent and placed the completed symlinks in `/mnt/symlinks/sonarr/completed/`, Sonarr imported the files but never cleaned up the completed directory. On the next scan, Sonarr re-detected the same completed directory, tried to re-import, found the episodes were already imported, and blocked — creating duplicate queue entries.

**Fix:** Set `removeCompletedDownloads: True` via the Sonarr/Radarr API:
```bash
# Get current config, change the flag, PUT it back
curl -s http://localhost:8989/api/v3/downloadclient/1 \
  -H "X-Api-Key: <key>" | \
  jq '.removeCompletedDownloads = true' | \
  curl -s -X PUT http://localhost:8989/api/v3/downloadclient/1 \
  -H "X-Api-Key: <key>" -H "Content-Type: application/json" -d @-
```

**Why this was missed:** The Sonarr UI defaults `removeCompletedDownloads` to `true` for most download clients, but when configured via API/automation the default can vary. Always verify this setting after programmatic setup.

**Key insight:** With the blackhole download client, `removeCompletedDownloads` is critical because the watch folder acts as both input and output. Without cleanup, every successfully imported download becomes a permanent re-import trigger.

---

## 20. symlink-import.sh Was Creating Duplicate Plex Entries

**Problem:** `/mnt/plex/TV/` had 45 directories for 16 shows. Each torrent season pack got its own raw-named directory (e.g., `Bobs.Burgers.S01.1080p.WEB-DL.x265.HEVC.OPUS-TCZ`) alongside the clean Sonarr-managed folder (`Bob's Burgers`). This caused Plex to sometimes show duplicate entries and confused Seerr's availability tracking.

**Root cause:** The `symlink-import.sh` cron script used the raw torrent folder name as the directory name in `/mnt/plex/TV/`, rather than mapping to Sonarr's clean folder. It was also redundant because Plex already scans `/mnt/zurg/shows/` directly as a second library location.

**Fix:** Disabled the symlink-import cron job entirely and removed the 34 orphan directories. The content pipeline now works as:
- **New content:** Blackhole → Sonarr import → `/mnt/plex/TV/CleanName/` (with `removeCompletedDownloads: True`)
- **Pre-existing RD content:** Plex scans `/mnt/zurg/shows/` directly (already configured as a library location)

**Key insight:** Before writing a script to bridge two systems, check whether the target system (Plex) already has a built-in mechanism (multiple library locations). The symlink-import script was solving a problem that didn't exist — Plex was already configured to scan Zurg's organized directories.

---

## 21. Sonarr SeasonSearch Only Finds Season Packs, Not Individual Episodes

**Problem:** Content existed on TPB as individual episodes (e.g., `Shrinking.S03E08.1080p.WEB.h264-ETHEL` with 1179 seeders), but Sonarr's `SeasonSearch` command returned 0 results because no season pack existed. Shows appeared stuck as "partially available" indefinitely.

**Root cause:** Sonarr's `SeasonSearch` command queries indexers for season packs only (e.g., `Shrinking S03 COMPLETE`). When no pack exists, it returns nothing — it does NOT fall back to searching for individual episodes. `EpisodeSearch` is a separate command that finds individual episodes and works correctly.

**How the automation gap manifested:**
1. User adds show to Plex Watchlist → Seerr sends to Sonarr → Sonarr does `SeriesSearch` → may find season packs for some seasons, but misses individual episodes for others
2. RSS sync (every 15 min) catches NEW episodes as they air, but doesn't search for OLD missing episodes
3. Old missing episodes sit unfound until someone manually triggers `EpisodeSearch`

**Fix:** Added `scripts/search-missing.sh` as a daily cron job (3am CT) that:
1. Queries Sonarr's `wanted/missing` API for all aired but missing episodes
2. Triggers `EpisodeSearch` for each in batches of 10
3. Rate-limits to avoid flooding indexers

```bash
# Cron entry
0 3 * * * /opt/plex-server/scripts/search-missing.sh >> /var/log/search-missing.log 2>&1
```

**Key insight:** Sonarr has three distinct search types with different behaviors:
- `SeriesSearch` — searches for everything (season packs + individual episodes) — used on initial add
- `SeasonSearch` — season packs ONLY — does NOT fall back to individual episodes
- `EpisodeSearch` — individual episodes — most reliable for finding content that exists as singles
