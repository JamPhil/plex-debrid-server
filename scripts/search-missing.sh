#!/bin/bash
# =============================================================================
# Search Missing Episodes
# =============================================================================
# Triggers individual episode searches for all aired but missing episodes.
# Sonarr's SeasonSearch only finds season packs; this script ensures
# individual episodes are also searched.
# Runs daily via cron.
# =============================================================================

SONARR_API_KEY="${SONARR_API_KEY:-00769b3d70044bcbb66eee2f50c2c116}"
SONARR_HOST="http://localhost:8989"
LOG_PREFIX="[search-missing]"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $LOG_PREFIX $1"; }

log "Starting missing episode search..."

python3 << 'PYEOF'
import json, urllib.request, time
from datetime import datetime, timezone

API_KEY = "00769b3d70044bcbb66eee2f50c2c116"
HOST = "http://localhost:8989"

# Get all missing aired episodes
req = urllib.request.Request(
    f"{HOST}/api/v3/wanted/missing?page=1&pageSize=500&sortKey=airDateUtc&sortDirection=descending&monitored=true",
    headers={"X-Api-Key": API_KEY}
)
d = json.loads(urllib.request.urlopen(req).read())
records = d.get("records", [])

now = datetime.now(timezone.utc).isoformat()
aired = [r for r in records if r.get("airDateUtc", "") and r["airDateUtc"] < now]

if not aired:
    print(f"No missing aired episodes found")
    exit(0)

# Group by series
series = {}
for r in aired:
    stitle = r.get("series", {}).get("title", "unknown")
    series.setdefault(stitle, []).append(r["id"])

total = len(aired)
print(f"Found {total} missing aired episodes across {len(series)} shows")

# Trigger episode searches in batches of 10
searched = 0
for stitle, ep_ids in sorted(series.items()):
    for i in range(0, len(ep_ids), 10):
        batch = ep_ids[i:i+10]
        data = json.dumps({"name": "EpisodeSearch", "episodeIds": batch}).encode()
        req2 = urllib.request.Request(
            f"{HOST}/api/v3/command",
            data=data,
            headers={"X-Api-Key": API_KEY, "Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req2)
        searched += len(batch)
        time.sleep(2)  # Don't flood the indexers
    print(f"  {stitle}: {len(ep_ids)} episodes queued")

print(f"Triggered searches for {searched} episodes")
PYEOF

log "Search complete"
