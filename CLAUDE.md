# Plex + Real-Debrid Streaming Server (DUMB Stack)

## Project Overview
Automated Plex media server that streams content via Real-Debrid. Users request shows/movies through Seerr (web UI) or Plex Watchlist. Content is automatically found via Prowlarr indexers, checked against RD cache by Decypharr, and appears in Plex within minutes.

## Architecture
- **DigitalOcean droplet**: 174.138.35.189 (4GB RAM, 2 vCPU, Ubuntu 24.04)
- **SSH key**: "robotrader" key (shared with another project)
- **Server path**: `/opt/dumb/`
- **Old server path**: `/opt/plex-server/` (backups preserved, stack decommissioned 2026-04-06)
- **Platform**: DUMB v2.3.0 (Debrid Unlimited Media Bridge) -- single Docker container bundling all services
- **Mount point**: `/mnt/debrid/decypharr/` (Decypharr internal rclone mount -> Real-Debrid content)
- **Symlinks**: `/mnt/debrid/decypharr_symlinks/` (Decypharr working directories)

## Data Flow
```
Request -> Plex Watchlist / Seerr -> Sonarr/Radarr -> Prowlarr (indexers)
    -> Decypharr (check RD cache, add torrent, create symlinks)
    -> Real-Debrid -> rclone FUSE mount -> Plex

Quality Profiles: Profilarr (TRaSH Guides) -> Sonarr/Radarr
Metadata Cache: Zilean + PostgreSQL
Plex Monitoring: Tautulli -> Discord (agent_id=20)
```

## Tech Stack (1 DUMB container, all services embedded)

### Storage Layer
- **Decypharr** -- RD bridge: qBittorrent API emulation, RD cache checking, WebDAV server, embedded rclone mount
- **rclone** -- Internal to Decypharr, FUSE mounts WebDAV to `/mnt/debrid/decypharr/`

### Media Server
- **Plex** ("James Streaming Server") -- Embedded inside DUMB container (eliminates mount propagation issues)

### Media Management (*Arr Stack)
- **Prowlarr** -- Indexer manager (needs TPB + YTS configured; 1337x/EZTV CloudFlare-blocked from datacenter)
- **Sonarr** -- TV show library manager
- **Radarr** -- Movie library manager
- **Profilarr** -- TRaSH Guides quality profile sync (auto-configured for Sonarr + Radarr)

### Request Layer
- **Seerr** -- Web UI for browsing/requesting + Plex Watchlist integration. User needs AUTO_REQUEST permissions for watchlist sync.

### Monitoring & Tools
- **Tautulli** -- Plex monitoring (Discord webhook, agent_id=20)
- **Zilean** -- Metadata cache for torrent lookups
- **PostgreSQL** -- Database for Zilean
- **pgAdmin** -- Database admin UI (port 5050)

### Infrastructure
- **DUMB API** -- Backend API for dashboard
- **DUMB Frontend** -- Web dashboard with embedded service UIs (port 3005)
- **DUMB built-in** -- ffprobe monitoring (detects/unsticks frozen Sonarr/Radarr scans), auto-updates, symlink repair

## Key Files
- `/opt/dumb/docker-compose.yml` -- DUMB container definition
- `/opt/dumb/config/` -- All service configurations (managed by DUMB)
- `/opt/dumb/log/` -- Service logs
- `/opt/dumb/data/` -- Service data
- `.env` -- Secrets (NOT in git)
- `.env.example` -- Template with all required variables

## Credentials / Services
- **Real-Debrid**: API token configured in Decypharr via DUMB onboarding, expires ~Sept 2026
- **Plex**: Claim token (one-time), ongoing token configured in DUMB
- **Discord webhook**: For Tautulli alerts
- **DUMB Dashboard**: Username `Jam_Phil`, password in `.env`
- **Seerr API key**: `MTc3NTUxMDAyNzE2NWQyZjhlYzgwLTBhNWQtNDc0Yy1iMGI2LTAyYWIxMDA0MjQ3Yg==`
- **Sonarr API key**: `107342f2750149ce94bcaff5e84ea544`
- **Radarr API key**: `a063e2c4e6eb4f268ff1d08bf2097938`
- **Prowlarr API key**: `37660125fc724bf7806cc7656e648854`

## DUMB Dashboard Access
- **URL**: `http://174.138.35.189:3005`
- **Login**: `Jam_Phil` / (password stored securely)
- All service UIs accessible via embedded iframes in dashboard
- Individual service ports still available for direct access if needed

## Service Ports
| Service | Port | Access |
|---------|------|--------|
| DUMB Dashboard | 3005 | Primary admin UI |
| Plex | 32400 | Media streaming |
| Seerr | 5055 | User requests |
| Sonarr | 8989 | Admin (or via DUMB dashboard) |
| Radarr | 7878 | Admin (or via DUMB dashboard) |
| Prowlarr | 9696 | Admin (or via DUMB dashboard) |
| Tautulli | 8181 | Admin (or via DUMB dashboard) |
| Decypharr | 8282 | Internal |
| Profilarr | 6868 | Admin (or via DUMB dashboard) |
| Zilean | 8182 | Internal |
| PostgreSQL | 5432 | Internal |
| pgAdmin | 5050 | Admin |

## Plex Configuration (CRITICAL)
- **Plex server name**: "James Streaming Server"
- **Plex section IDs**: Movies = 1, TV Shows = 2 (created fresh during DUMB migration 2026-04-06)
- **Library paths**: `/mnt/debrid/decypharr_symlinks/radarr-debrid` (Movies), `/mnt/debrid/decypharr_symlinks/sonarr-debrid` (TV)
- **Quality Profile**: WEB-2160p (alternative) — via Profilarr, scales 2160p -> 1080p -> 720p
- IMPORTANT: All Plex analysis MUST be disabled to avoid excessive RD API calls:
  - Video preview thumbnails: Never
  - Credits detection: Never
  - Ad detection: Disabled
  - Voice activity detection: Never
- `autoEmptyTrash` unchecked (prevents library loss during partial scans)

## Known Architectural Constraints
- **Sonarr ffprobe issue**: Sonarr's hardcoded sample detection runs ffprobe on every imported file. In a debrid setup, each probe triggers an RD API call through the FUSE mount. DUMB's built-in ffprobe monitoring mitigates this, but bulk additions (20+ shows) can still overwhelm RD's ~5-6 concurrent download link limit.
- **Mitigation**: Add content in small batches (3-5 items), never bulk. DUMB's ffprobe monitoring detects and unsticks frozen scans.
- **CloudFlare-blocked indexers**: 1337x, EZTV, Torrentio blocked from datacenter IPs. Use TPB and YTS in Prowlarr.

## Cron Jobs
- None currently -- DUMB handles service health internally
- MissingEpisodeSearch cron may need to be re-established after pipeline verification

## Bug Discovery Protocol
When you discover a bug or issue that is **outside your current task scope**:
1. Do NOT fix it -- stay focused on your assigned task
2. Add an entry to `BACKLOG.md` at the top of the list (newest first), using the template in that file
3. Include: what you observed, what's currently running/configured, and your best guess at a fix
4. Mention it briefly to the user: "Logged an issue to BACKLOG.md -- out of scope for this session"
5. Note the backlog entry in `docs/DEVLOG.md` so there's a trail

When starting a new session with no specific task, check `BACKLOG.md` for open items.

## Working Rules
1. **Trace the causal chain before acting.** When encountering an error, ask "why?" at least twice before taking any action. Fix root causes, not symptoms.
2. **Generate 3 solutions, choose the best.** Never lock onto the first fix that comes to mind. Consider at least three approaches, evaluate tradeoffs, and pick the best one. This applies to debugging, architecture decisions, and recommendations.
3. **Prefer in-stack settings over workarounds.** Check if there's a config or setting change that prevents the problem before reaching for scripts, cron jobs, or manual cleanup.
4. **Verify before concluding.** Never state unverified claims as fact. If a claim is load-bearing, check it first. Fetch docs, query APIs, read configs — then form conclusions.
5. **Save as you go.** After completing any fix, config change, or significant decision, immediately:
   - Save to memory (if it's context future chats need)
   - Append to `docs/DEVLOG.md` (chronological record of what changed, why, and the outcome)
   - Do not wait until end of chat — save after each significant action
6. **Commit and push meaningful changes.** After completing a body of work (fixes, config updates, new docs), commit to git and push to GitHub so all agents work from the same state.

## Common Issues
1. **ffprobe rate limit floods** -- DUMB's built-in ffprobe monitoring should detect and unstick frozen scans. If RD rate limits hit, stop adding content and wait for current imports to complete. Add in batches of 3-5.
2. **Seerr not syncing with Plex** -- Re-authenticate Plex connection in Seerr settings. Ensure user has AUTO_REQUEST permissions for watchlist sync. Both `plex-watchlist-sync` job AND AUTO_REQUEST bits must be enabled.
3. **RD 451 error** -- Content blocked by Real-Debrid for legal reasons. Nothing to do.
4. **Tautulli Discord notifications not working** -- Verify agent_id is 20 (Discord), not 18 (Join).
5. **CloudFlare-blocked indexers** -- 1337x, EZTV, Torrentio are blocked from datacenter IPs. Use TPB and YTS in Prowlarr instead.
6. **Seerr watchlist 20-item limit** -- Seerr only fetches first 20 watchlist items per sync. New items appear at position 1 and get processed. Backlog items need manual requesting.
7. **Seerr watchlist not syncing** -- TWO gates must both be enabled: (1) Admin permissions: AUTO_REQUEST + AUTO_REQUEST_MOVIE + AUTO_REQUEST_TV bits on the user (permissions value 28674), AND (2) User-level DB toggles: `watchlistSyncMovies=1` and `watchlistSyncTv=1` in the `user_settings` table. If the user_settings row doesn't exist, watchlist sync silently does nothing.

## Migration History
- **2026-03-27**: Initial 15-container build (Zurg + rclone + blackhole)
- **2026-04-01**: Replaced Zurg+rclone+blackhole with Decypharr (3→1 containers)
- **2026-04-05**: Full system purge after RD rate limit flood (8,870 errors)
- **2026-04-06**: Migrated to DUMB v2.3.0 (15→1 container). Old stack preserved at `/opt/plex-server/backups/`
