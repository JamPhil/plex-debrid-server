#!/bin/bash
# Watchlist Sync - removes RD torrents not on Plex Watchlist after 24h grace period
LOGFILE="/opt/plex-server/logs/watchlist-sync.log"
STATE_FILE="/opt/plex-server/scripts/.watchlist-sync-state.json"
WEBHOOK_URL=$(grep DISCORD_WEBHOOK_URL /opt/plex-server/.env | cut -d= -f2-)
RD_TOKEN=$(grep REAL_DEBRID_API_TOKEN /opt/plex-server/.env | cut -d= -f2-)
PLEX_TOKEN=$(grep PLEX_TOKEN /opt/plex-server/.env | cut -d= -f2-)

python3 << PYEOF
import urllib.request, json, xml.etree.ElementTree as ET, re, os, time
from datetime import datetime, timedelta

RD_TOKEN = "$RD_TOKEN"
PLEX_TOKEN = "$PLEX_TOKEN"
STATE_FILE = "$STATE_FILE"
LOGFILE = "$LOGFILE"
WEBHOOK_URL = "$WEBHOOK_URL"
GRACE_HOURS = 24

def log(msg):
    with open(LOGFILE, 'a') as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")

def send_discord(msg):
    try:
        data = json.dumps({"content": msg}).encode()
        req = urllib.request.Request(WEBHOOK_URL, data=data,
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req)
    except:
        pass

state = {}
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        state = json.load(f)

# Get Plex Watchlist RSS
try:
    with open('/var/lib/docker/volumes/plex-server_riven-data/_data/settings.json') as f:
        d = json.load(f)
    rss_url = d.get('content',{}).get('plex_watchlist',{}).get('rss','')
    if isinstance(rss_url, list):
        rss_url = rss_url[0] if rss_url else ''
except:
    rss_url = ''

if not rss_url:
    log("ERROR - No RSS URL found")
    exit(1)

with urllib.request.urlopen(urllib.request.Request(rss_url)) as resp:
    root = ET.fromstring(resp.read())

watchlist_keys = []
for item in root.findall('.//item'):
    title = item.find('title').text if item.find('title') is not None else ''
    clean = re.sub(r'\s*\(\d{4}\)\s*', ' ', title).strip().lower()
    watchlist_keys.append(clean)

def normalize(s):
    s = s.lower()
    s = re.sub(r'[.\-_\[\](){}]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def matches_watchlist(filename):
    fn = normalize(filename)

    for title in watchlist_keys:
        words = [w for w in title.split() if len(w) > 2]
        small_words = {'the', 'and', 'of', 'in', 'on', 'at', 'to', 'for', 'a', 'an'}
        significant = [w for w in words if w not in small_words]

        # Direct: all significant words in filename
        if significant and all(w in fn for w in significant):
            return True

        # Also try with 1<->i substitution (plur1bus <-> pluribus)
        alt_title = title.replace('1', 'i')
        if alt_title != title:
            alt_words = [w for w in alt_title.split() if len(w) > 2 and w not in small_words]
            if alt_words and all(w in fn for w in alt_words):
                return True

        alt_fn = fn.replace('i', '1')
        if alt_fn != fn:
            if significant and all(w in alt_fn for w in significant):
                return True

    return False

# Get RD Torrents
req = urllib.request.Request('https://api.real-debrid.com/rest/1.0/torrents?limit=100',
    headers={'Authorization': f'Bearer {RD_TOKEN}'})
with urllib.request.urlopen(req) as resp:
    torrents = json.loads(resp.read())

now = datetime.now().isoformat()
new_state = {}
to_delete = []
kept = 0

for t in torrents:
    tid = t['id']
    fname = t['filename']

    if matches_watchlist(fname):
        kept += 1
        continue

    if tid in state:
        first_seen = datetime.fromisoformat(state[tid])
        if datetime.now() - first_seen > timedelta(hours=GRACE_HOURS):
            to_delete.append((tid, fname))
        else:
            new_state[tid] = state[tid]
            hours_left = GRACE_HOURS - (datetime.now() - first_seen).total_seconds() / 3600
            log(f"GRACE - {fname[:60]} ({hours_left:.1f}h remaining)")
    else:
        new_state[tid] = now
        log(f"FLAGGED - {fname[:60]} (not on watchlist, 24h grace started)")

deleted_names = []
for tid, fname in to_delete:
    try:
        req = urllib.request.Request(
            f'https://api.real-debrid.com/rest/1.0/torrents/delete/{tid}',
            method='DELETE',
            headers={'Authorization': f'Bearer {RD_TOKEN}'})
        urllib.request.urlopen(req)
        log(f"DELETED - {fname[:60]}")
        deleted_names.append(fname[:50])
        time.sleep(0.5)
    except Exception as e:
        log(f"ERROR deleting {tid}: {e}")
        new_state[tid] = state.get(tid, now)

with open(STATE_FILE, 'w') as f:
    json.dump(new_state, f, indent=2)

if deleted_names:
    try:
        urllib.request.urlopen(urllib.request.Request(
            f'http://localhost:32400/library/sections/3/refresh?X-Plex-Token={PLEX_TOKEN}',
            method="POST"))
        urllib.request.urlopen(urllib.request.Request(
            f'http://localhost:32400/library/sections/4/refresh?X-Plex-Token={PLEX_TOKEN}',
            method="POST"))
    except:
        pass
    msg = f"🧹 **Watchlist Sync**: Removed {len(deleted_names)} items from RD:\n"
    for name in deleted_names:
        msg += f"  • {name}\n"
    send_discord(msg)

log(f"SUMMARY - Kept: {kept}, Grace: {len(new_state)}, Deleted: {len(deleted_names)}")
PYEOF
