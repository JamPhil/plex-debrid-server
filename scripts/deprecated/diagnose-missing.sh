#!/bin/bash
# =============================================================================
# Diagnose Missing Content
# =============================================================================
# Run this BEFORE assuming content isn't available on indexers.
# Compares Prowlarr direct search results vs Sonarr's view to identify
# where in the pipeline content is being lost.
#
# Usage: ./diagnose-missing.sh "show name" [season] [episode]
# Example: ./diagnose-missing.sh "shrinking" 3 8
# =============================================================================

set -euo pipefail

QUERY="${1:?Usage: $0 \"show name\" [season] [episode]}"
SEASON="${2:-}"
EPISODE="${3:-}"

SONARR_API_KEY="${SONARR_API_KEY:-00769b3d70044bcbb66eee2f50c2c116}"
RADARR_API_KEY="${RADARR_API_KEY:-2125f84876a04d97ad63abe3304967f6}"
PROWLARR_API_KEY=$(grep -oP '(?<=<ApiKey>)[^<]+' /var/lib/docker/volumes/plex-server_prowlarr-config/_data/config.xml)

# Build search term
SEARCH="$QUERY"
if [ -n "$SEASON" ] && [ -n "$EPISODE" ]; then
    SEARCH="$QUERY s$(printf '%02d' $SEASON)e$(printf '%02d' $EPISODE)"
elif [ -n "$SEASON" ]; then
    SEARCH="$QUERY s$(printf '%02d' $SEASON)"
fi

echo "=== STEP 1: Prowlarr Direct Search ==="
echo "Query: $SEARCH"
PROWLARR_RESULTS=$(curl -s "http://localhost:9696/api/v1/search?query=$(echo "$SEARCH" | sed 's/ /+/g')&type=search" -H "X-Api-Key: $PROWLARR_API_KEY")
PROWLARR_COUNT=$(echo "$PROWLARR_RESULTS" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
echo "Results: $PROWLARR_COUNT"
if [ "$PROWLARR_COUNT" -gt "0" ]; then
    echo "$PROWLARR_RESULTS" | python3 -c "
import json, sys
results = json.load(sys.stdin)
indexers = {}
for r in results:
    idx = r.get('indexer','?')
    indexers[idx] = indexers.get(idx, 0) + 1
for idx, count in sorted(indexers.items()):
    print(f'  {idx}: {count} results')
for r in results[:3]:
    print(f'  {r.get(\"title\",\"?\")[:70]} seeders={r.get(\"seeders\",0)}')
" 2>/dev/null
fi

echo ""
echo "=== STEP 2: Sonarr Series Match ==="
SERIES=$(curl -s "http://localhost:8989/api/v3/series" -H "X-Api-Key: $SONARR_API_KEY" | python3 -c "
import json, sys
query = '$QUERY'.lower()
for s in json.load(sys.stdin):
    if query in s['title'].lower():
        print(f'Match: {s[\"title\"]} (id={s[\"id\"]})')
        stats = s.get('statistics',{})
        print(f'  Episodes: {stats.get(\"episodeFileCount\",0)}/{stats.get(\"totalEpisodeCount\",0)}')
        print(f'  Monitored: {s[\"monitored\"]}')
        print(f'  Quality Profile: {s.get(\"qualityProfileId\",\"?\")}')
" 2>/dev/null)
if [ -z "$SERIES" ]; then
    echo "  NOT IN SONARR — show hasn't been added"
else
    echo "$SERIES"
fi

echo ""
echo "=== STEP 3: Sonarr Release Search ==="
SERIES_ID=$(curl -s "http://localhost:8989/api/v3/series" -H "X-Api-Key: $SONARR_API_KEY" | python3 -c "
import json, sys
query = '$QUERY'.lower()
for s in json.load(sys.stdin):
    if query in s['title'].lower():
        print(s['id'])
        break
" 2>/dev/null)

if [ -n "$SERIES_ID" ] && [ -n "$SEASON" ]; then
    SONARR_RESULTS=$(curl -s "http://localhost:8989/api/v3/release?seriesId=$SERIES_ID&seasonNumber=$SEASON" -H "X-Api-Key: $SONARR_API_KEY")
    SONARR_COUNT=$(echo "$SONARR_RESULTS" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    echo "Sonarr sees: $SONARR_COUNT releases"

    if [ "$PROWLARR_COUNT" -gt "0" ] && [ "$SONARR_COUNT" -eq "0" ]; then
        echo ""
        echo "*** MISMATCH DETECTED ***"
        echo "Prowlarr found $PROWLARR_COUNT results but Sonarr sees 0."
        echo "Likely causes:"
        echo "  1. SeasonSearch only finds season packs — try EpisodeSearch instead"
        echo "  2. Quality profile rejecting all results"
        echo "  3. Releases are blocklisted"
        echo "  4. Sonarr categories don't match indexer categories"
    fi

    if [ "$SONARR_COUNT" -gt "0" ]; then
        echo "$SONARR_RESULTS" | python3 -c "
import json, sys
results = json.load(sys.stdin)
approved = [r for r in results if r.get('approved')]
rejected = [r for r in results if r.get('rejected')]
print(f'  Approved: {len(approved)}')
print(f'  Rejected: {len(rejected)}')
if rejected:
    r = rejected[0]
    reasons = [rr.get('reason','') if isinstance(rr,dict) else str(rr) for rr in r.get('rejections',[])]
    print(f'  Top rejection reasons:')
    for reason in reasons[:3]:
        print(f'    - {reason}')
" 2>/dev/null
    fi
else
    echo "  Skipped (no series ID or season number)"
fi

echo ""
echo "=== STEP 4: Zurg Content Check ==="
echo "Zurg has:"
ls /mnt/zurg/shows/ 2>/dev/null | grep -i "$(echo "$QUERY" | sed 's/ /./g')" || echo "  Nothing matching in Zurg"

echo ""
echo "=== STEP 5: Plex Content Check ==="
echo "Plex has:"
ls /mnt/plex/TV/ 2>/dev/null | grep -i "$QUERY" || echo "  Nothing matching in /mnt/plex/TV/"
