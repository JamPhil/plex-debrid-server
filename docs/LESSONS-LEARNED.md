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

**Solution:** Removed Zilean. It depends on other DebridMediaManager users sharing their hashlists, which wasn't populated enough to be useful. Torrentio replaced this functionality entirely.

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
