# BUG: FUSE Mount Timing — Sonarr FileNotFoundException on Import

## Status: FIXED — `RCLONE_DIR_CACHE_TIME=10s` env var in docker-compose.yml (2026-04-02)

## Summary

When Decypharr adds a torrent to Real-Debrid and creates symlinks, Sonarr sometimes tries to import the symlinked files before the rclone FUSE mount inside the container has refreshed. This causes `System.IO.FileNotFoundException` errors and leaves queue items stuck at `importPending/warning`.

The issue self-resolves when Sonarr retries (usually within 30-60 seconds), or when a manual `DownloadedEpisodesScan` is triggered. It does NOT cause data loss — just delayed imports.

## Observed Behavior

- Decypharr successfully adds torrent to RD, creates symlinks in `/mnt/symlinks/sonarr/`
- Symlinks point to files under `/mnt/decypharr/realdebrid/__all__/<torrent-name>/`
- Sonarr immediately tries to import, follows the symlink, but gets `FileNotFoundException` on the target
- The files ARE on RD and the WebDAV server knows about them — it's the rclone VFS directory cache serving stale data
- After the cache refreshes (or on retry), import succeeds

### Shows affected during testing (2026-04-02):
- **Severance S02** (season pack, 10 episodes) — all 10 failed initially, succeeded on retry ~30s later
- **Shrinking S02** (season pack, 12 episodes) — all 12 failed initially, succeeded on `DownloadedEpisodesScan`
- **Shrinking S03E09, S03E10** (individual episodes) — failed initially, succeeded on retry
- **Shrinking S01**, **Severance S01**, **Rooster S01** — imported successfully on first attempt (no timing issue)

### Pattern: Season packs processed second are more likely to fail. The first season pack imports fine because rclone has time to refresh while Decypharr processes it. The second pack is processed ~25 seconds later, and the FUSE mount hasn't refreshed yet.

## Root Cause

### Primary: rclone DirCacheTime = 5 minutes (default)

Decypharr runs rclone internally as a remote-control daemon (`rclone rcd`). The rclone VFS layer caches directory listings for `DirCacheTime`, which defaults to **5 minutes** (300 seconds).

The old Zurg+rclone setup had `--dir-cache-time 10s` explicitly set. When we migrated to Decypharr, this setting was lost because Decypharr manages rclone internally and doesn't expose `DirCacheTime` as a config option.

**Current rclone VFS settings inside Decypharr:**
```
DirCacheTime:      300,000,000,000 ns  (5 minutes — THIS IS THE PROBLEM)
CachePollInterval:  60,000,000,000 ns  (60 seconds)
PollInterval:       60,000,000,000 ns  (60 seconds)
CacheMode:          0 (off — no file caching, but dir listings ARE cached)
```

**Timeline of a failed import:**
1. `T+0s` — Decypharr adds torrent to RD, WebDAV server updates internally
2. `T+0.1s` — Decypharr creates symlinks in `/mnt/symlinks/sonarr/`
3. `T+0.1s` — Decypharr notifies Sonarr (via qBit API emulation) that download is complete
4. `T+0.5s` — Sonarr tries to import, follows symlink to `/mnt/decypharr/realdebrid/__all__/<name>/`
5. `T+0.5s` — rclone VFS serves cached directory listing that DOESN'T include the new torrent → **FileNotFoundException**
6. `T+30-300s` — rclone cache expires or refreshes → files become visible → retry succeeds

### Secondary: rclone unmount/remount cycling every 5 minutes

Decypharr logs show rclone unmounting and remounting every ~5 minutes:
```
[rclone] Unmount completed provider=realdebrid
...
[rclone] Successfully mounted realdebrid WebDAV at /mnt/decypharr/realdebrid via RC
```

This cycling could cause transient `FileNotFoundException` if Sonarr accesses the mount during the brief unmount window. This is a separate issue from the DirCacheTime problem.

## Architecture Context

```
Decypharr container:
  ├── WebDAV server (port 8282) — serves RD content, updates immediately on torrent add
  ├── rclone rcd (port 5572) — FUSE mounts WebDAV to /mnt/decypharr/realdebrid/
  │   └── VFS dir cache: 5 min (STALE DATA SOURCE)
  ├── Symlink creator — creates symlinks in /mnt/symlinks/sonarr/
  └── qBit API emulator — notifies Sonarr of completed downloads

Sonarr container:
  └── /mnt bind mount (rshared propagation) — sees FUSE mount from Decypharr
      ├── /mnt/symlinks/sonarr/ — finds the symlink (OK)
      └── /mnt/decypharr/realdebrid/__all__/ — follows symlink target (STALE CACHE)
```

Mount propagation (`rshared`) is correctly configured on both containers. The issue is entirely within rclone's VFS directory cache.

## Relevant Config Files

### Decypharr config (`/app/config.json` inside container, `decypharr-config` Docker volume):
```json
{
  "rclone": {
    "enabled": true,
    "mount_path": "/mnt/decypharr",
    "uid": 1000,
    "gid": 1000
  }
}
```
No `dir_cache_time` or VFS tuning options available in Decypharr's config schema.

### rclone config (`/app/rclone/rclone.conf` inside container):
```ini
[realdebrid]
type = webdav
pacer_min_sleep = 0
url = http://localhost:8282/webdav/realdebrid/
vendor = other
```

### rclone process (inside Decypharr container):
```
rclone rcd --rc-addr :5572 --rc-no-auth --config /app/rclone/rclone.conf --log-file /app/logs/rclone.log --log-level INFO
```
Mount is created via RC API call, not command-line flags. No `--dir-cache-time` flag.

### Old rclone config (for reference — what worked before):
```
--dir-cache-time 10s --poll-interval 30s --vfs-cache-mode off
```

## Fix Applied

### Environment variable: `RCLONE_DIR_CACHE_TIME=10s`

Added to the Decypharr service in `docker-compose.yml`:
```yaml
environment:
  - RCLONE_DIR_CACHE_TIME=10s
  - RCLONE_VFS_CACHE_POLL_INTERVAL=10s
```

**Why this works:** Decypharr launches rclone as `rclone rcd` internally. The rclone process inherits container environment variables. `RCLONE_DIR_CACHE_TIME` maps to rclone's `--dir-cache-time` flag and is respected globally by the rcd daemon — including across Decypharr's 5-minute unmount/remount cycling.

**What didn't work:**
- `RCLONE_VFS_DIR_CACHE_TIME=10s` — wrong env var name; rclone doesn't use the `VFS_` prefix for `dir-cache-time`
- RC API `options/set` via mount-watchdog.sh — worked temporarily but got reset every 5 minutes when Decypharr cycled the mount (unmount destroys the rclone rcd process and restarts it with defaults)
- Decypharr config.json — no VFS configuration options exposed

**Verified:** DirCacheTime=10s persists across Decypharr's 5-minute remount cycles. Tested 2026-04-02.

**Remaining note:** Decypharr still cycles the mount every ~5 minutes (unmount + remount in ~2 seconds). This is a Decypharr design choice, not configurable. During the ~2s window, file access may fail. This is separate from the DirCacheTime issue and is unlikely to cause problems in practice since Sonarr retries quickly.

## Previous Fix Attempts (historical)

### Option 1: Use rclone RC API to set DirCacheTime
Since rclone runs as `rcd` inside Decypharr, you can call the RC API to change VFS options at runtime:
```bash
docker exec decypharr curl -s -X POST http://localhost:5572/options/set \
  -H "Content-Type: application/json" \
  -d '{"vfs": {"DirCacheTime": 10000000000}}'
```
This sets `DirCacheTime` to 10 seconds (in nanoseconds). Would need to be applied after every container restart (startup script or cron).

**Verify current value:**
```bash
docker exec decypharr curl -s http://localhost:5572/options/get | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('vfs',{}).get('DirCacheTime','not found'))"
```

### Option 2: Use rclone RC API to force VFS refresh after torrent add
```bash
docker exec decypharr curl -s -X POST http://localhost:5572/vfs/forget \
  -H "Content-Type: application/json" \
  -d '{"dir": "/__all__/"}'
```
This invalidates the cache for the `__all__` directory, forcing rclone to re-read from WebDAV on next access. Would need to be triggered after each Decypharr torrent add (harder to automate).

### Option 3: Decypharr config or environment variable
Check if Decypharr supports passing rclone flags via environment variable (e.g., `RCLONE_VFS_DIR_CACHE_TIME=10s` or `RCLONE_FLAGS`). Check Decypharr docs/GitHub issues.

### Option 4: Accept the current behavior
The issue self-resolves on retry. Sonarr retries automatically. The delay is 30-60 seconds in practice. If this is acceptable, no fix needed — just document it as expected behavior.

## Diagnostic Commands

```bash
# Check current DirCacheTime
docker exec decypharr curl -s http://localhost:5572/options/get | python3 -c "
import sys,json
d=json.load(sys.stdin)
vfs = d.get('vfs',{})
print(f'DirCacheTime: {vfs.get(\"DirCacheTime\",\"?\")} ns ({vfs.get(\"DirCacheTime\",0)/1e9:.0f}s)')
print(f'CachePollInterval: {vfs.get(\"CachePollInterval\",\"?\")} ns')
print(f'PollInterval: {d.get(\"main\",{}).get(\"PollInterval\",\"?\")} ns')
"

# Check if files are visible on the mount (from host)
ls "/mnt/decypharr/realdebrid/__all__/<torrent-name>/"

# Check if files are visible inside Sonarr container
docker exec sonarr ls "/mnt/decypharr/realdebrid/__all__/<torrent-name>/"

# Force rclone to forget cached directory listing
docker exec decypharr curl -s -X POST http://localhost:5572/vfs/forget \
  -d '{"dir": "/__all__/"}'

# Check Sonarr import errors
docker logs sonarr --since 10m 2>&1 | grep "FileNotFoundException\|Could not find file"

# Trigger Sonarr to retry imports
source /opt/plex-server/.env
curl -s -X POST "http://localhost:8989/api/v3/command" \
  -H "X-Api-Key: $SONARR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "DownloadedEpisodesScan"}'

# Check rclone unmount/remount cycling
docker logs decypharr --since 30m 2>&1 | grep -i "unmount\|mount"
```

## Error Log Examples

```
[Warn] ImportApprovedEpisodes: Couldn't import episode /mnt/symlinks/sonarr/Severance (2022) S02 (...)/Severance (2022) S02E08 (...).mkv
[v4.0.17.2952] System.IO.FileNotFoundException: Could not find file '/mnt/decypharr/realdebrid/__all__/Severance (2022) S02 (...)/Severance (2022) S02E08 (...).mkv'.
File name: '/mnt/decypharr/realdebrid/__all__/Severance (2022) S02 (...)/Severance (2022) S02E08 (...).mkv'
   at NzbDrone.Core.MediaFiles.EpisodeImport.ImportDecisionMaker.GetDecision(...)
```

Note: The symlink at `/mnt/symlinks/sonarr/` exists and is correct. The error is on the symlink TARGET at `/mnt/decypharr/realdebrid/__all__/` — rclone's cached directory listing doesn't include the new torrent yet.
