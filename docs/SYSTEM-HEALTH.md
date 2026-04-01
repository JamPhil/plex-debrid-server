# System Health Definitions

## Overall System Health

A healthy system means: **A user adds a show/movie to their Plex Watchlist (or requests via Seerr/Discord), and it appears in Plex ready to watch — without any manual intervention.**

The secondary function is: **The system monitors itself and alerts via Discord when something goes wrong.**

---

## Component Health Definitions

### 1. Plex

**What it does**: Serves media to the Roku TV.

**Healthy means**:
- Container running and responding on port 32400
- Libraries (Movies section 3, TV section 4) contain content that matches what's in `/mnt/plex/Movies/` and `/mnt/plex/TV/`
- Auto-scan is detecting new files when they appear (FSEvent scanning enabled)
- Content is actually playable from the Roku app (not just listed)

**Connections to verify**:
- Plex can read files through the `/mnt/zurg/` FUSE mount (rclone -> Zurg -> RD)
- Plex library counts match what Sonarr/Radarr think they've delivered
- Seerr can communicate with Plex (for availability status and watchlist sync)
- Tautulli can communicate with Plex (for monitoring)

---

### 2. Zurg + rclone (Storage Layer)

**What it does**: Zurg exposes Real-Debrid content as WebDAV. rclone FUSE-mounts that to `/mnt/zurg/`.

**Healthy means**:
- Both containers running
- `/mnt/zurg/__all__/` is listable and contains content
- Files within the mount are actually readable (not just listed — can stat/read them)
- When new torrents are added to RD, they appear on the mount within a reasonable time

**Connections to verify**:
- rclone is connected to Zurg's WebDAV endpoint
- Zurg is authenticated with a valid RD API token
- Blackhole can find torrent content on the mount after adding to RD
- Plex can read video files through the mount for playback

---

### 3. Blackhole

**What it does**: Bridges between Sonarr/Radarr and Real-Debrid. Receives .magnet files, checks RD cache, adds torrents, creates symlinks in `/mnt/plex/`.

**Healthy means**:
- Container running
- Processing .magnet files from `/mnt/symlinks/sonarr/` and `/mnt/symlinks/radarr/`
- Successfully adding torrents to RD
- Finding the downloaded content on the Zurg mount
- Creating valid symlinks in `/mnt/plex/TV/` and `/mnt/plex/Movies/` that point to real files
- Reporting completed downloads back to Sonarr/Radarr (so they mark episodes as downloaded)
- Not stuck in grab/fail loops on specific content

**Connections to verify**:
- Blackhole can reach the RD API (`REALDEBRID_HOST` correct with `/rest/1.0/`)
- Blackhole's watch folders match what Sonarr/Radarr are configured to write to
- Blackhole's completed folder matches what Sonarr/Radarr are configured to read from
- Symlinks blackhole creates are valid (target files exist on the mount)

---

### 4. Sonarr

**What it does**: Manages TV show library. Monitors for missing episodes, searches for releases, sends downloads to blackhole.

**Healthy means**:
- Container running and responding on port 8989
- Connected to Prowlarr (receiving indexer results)
- Using the correct quality profile (WEB-2160p, id=7)
- Monitored shows have `monitorNewItems=all` so new seasons auto-monitor
- `upgradeAllowed=True` on the active profile so it doesn't reject upgrades
- `removeCompletedDownloads=True` so the queue doesn't clog
- Missing episodes are being searched for (either via RSS, automatic search, or the nightly cron)
- When releases are found, .magnet files are being written to `/mnt/symlinks/sonarr/`
- When blackhole completes, Sonarr detects the file in the completed folder and imports it
- Episode count in Sonarr matches what's actually on disk

**Connections to verify**:
- Sonarr receives indexer results from Prowlarr
- Sonarr writes .magnet files that blackhole picks up
- Sonarr reads completed downloads from blackhole
- Seerr pushes new TV requests to Sonarr
- The quality profile and custom formats Sonarr uses match what we configured

---

### 5. Radarr

**What it does**: Same as Sonarr but for movies.

**Healthy means**:
- Same criteria as Sonarr but for movies
- Connected to Prowlarr, using WEB-2160p profile (id=7)
- Writing .magnet files to `/mnt/symlinks/radarr/`
- Reading completed downloads from blackhole
- Movie count matches what's on disk

**Connections to verify**:
- Same as Sonarr but on port 7878 with Radarr paths

---

### 6. Prowlarr

**What it does**: Manages indexers (TPB, LimeTorrents, YTS) and syncs them to Sonarr/Radarr.

**Healthy means**:
- Container running and responding on port 9696
- All configured indexers are enabled and responding (not erroring)
- Indexers are synced to both Sonarr and Radarr as download sources
- When Sonarr/Radarr trigger a search, Prowlarr returns results
- A manual search in Prowlarr for known content returns results

**Connections to verify**:
- Prowlarr -> each indexer (TPB, LimeTorrents, YTS): Can reach them, getting results
- Prowlarr -> Sonarr: Indexers appear in Sonarr's indexer list
- Prowlarr -> Radarr: Indexers appear in Radarr's indexer list

---

### 7. Seerr

**What it does**: Web UI for requesting content. Also syncs Plex Watchlist.

**Healthy means**:
- Container running and responding on port 5055
- Connected to Plex (can show availability status)
- Connected to Sonarr and Radarr (can push requests)
- Using the correct quality profiles (WEB-2160p for both)
- Plex Watchlist sync is functioning (items added to watchlist create requests)
- User permissions allow requests to flow through (admin has appropriate permissions, default permissions allow new users to request if applicable)

**Connections to verify**:
- Seerr -> Plex: authenticated, can read library and watchlist
- Seerr -> Sonarr: correct profile, correct root folder (`/mnt/plex/TV`)
- Seerr -> Radarr: correct profile, correct root folder (`/mnt/plex/Movies`)
- A request made in Seerr actually appears in Sonarr/Radarr

---

### 8. Doplarr

**What it does**: Discord bot for media requests.

**Healthy means**:
- Container running
- Connected to Discord (bot online in the server)
- Connected to Seerr (can route requests)
- A request made via Discord creates a request in Seerr, which flows to Sonarr/Radarr

**Connections to verify**:
- Doplarr -> Discord: Bot token valid, bot appears online
- Doplarr -> Seerr: Can create requests via Seerr API

---

### 9. Tautulli

**What it does**: Monitors Plex activity and sends notifications to Discord.

**Healthy means**:
- Container running on port 8181
- Connected to Plex (can see library and activity)
- Discord webhook configured and working (agent_id=20)
- Sending notifications for new content added

**Connections to verify**:
- Tautulli -> Plex: authenticated, receiving activity data
- Tautulli -> Discord: webhook delivers notifications

---

### 10. Monitoring Stack (Prometheus + Grafana + cAdvisor + Node Exporter)

**What it does**: Collects metrics, visualizes them, alerts on problems.

**Healthy means**:
- All four containers running
- Prometheus is scraping all targets (cAdvisor, Node Exporter, and itself) successfully
- Grafana dashboards are loading with data (not "no data")
- All alert rules are in a valid state (either "inactive" or legitimately "firing")
- For any firing alert: the underlying condition is real and actionable
- Discord webhook is configured in Grafana contact points

**Connections to verify**:
- cAdvisor -> Prometheus: scrape target up
- Node Exporter -> Prometheus: scrape target up
- Prometheus -> Grafana: datasource configured and working
- Grafana -> Discord: webhook delivers alert notifications

---

### 11. Autoheal

**What it does**: Restarts unhealthy containers automatically.

**Healthy means**:
- Container running
- Has access to Docker socket
- Successfully restarting containers when their healthchecks fail

---

## End-to-End Pipeline Health Test

The ultimate test of system health is tracing a single request through every step:

1. **Request** -> Does it reach Sonarr/Radarr?
2. **Search** -> Does Prowlarr find releases?
3. **Download** -> Does blackhole receive the .magnet, add to RD, and create symlinks?
4. **Mount** -> Does the content appear on `/mnt/zurg/` and link correctly to `/mnt/plex/`?
5. **Library** -> Does Plex detect the new file and add it to the library?
6. **Playback** -> Can it be played on the Roku?

---

## Connection Map

```
Plex Watchlist
     |
     v
   Seerr <-----> Plex <-----> Tautulli ---> Discord
   ^   |            ^
   |   v            |
Doplarr  Sonarr/Radarr <---> Prowlarr ---> TPB / LimeTorrents / YTS
              |
              v
         Blackhole ---> Real-Debrid API
              |              |
              v              v
        /mnt/symlinks    Zurg (WebDAV)
         /mnt/plex           |
              |              v
              |         rclone (FUSE)
              |         /mnt/zurg/
              |              |
              +--------------+
                     |
                     v
                Plex Libraries

Prometheus <--- cAdvisor + Node Exporter
     |
     v
  Grafana ---> Discord

Autoheal ---> Docker Socket (restarts unhealthy containers)
```
