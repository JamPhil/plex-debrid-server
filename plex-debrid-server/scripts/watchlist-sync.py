#!/usr/bin/env python3
"""
Watchlist Sync — monitors Plex Watchlist, finds best torrents via Torrentio,
adds them to Real-Debrid, and triggers Plex library scans.

Designed to add ONE torrent per show/movie, preferring season packs over
individual episodes, and 4K over 1080p.
"""

import json
import os
import re
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

# --- Config from environment ---
RD_TOKEN = os.environ["RD_API_TOKEN"]
PLEX_TOKEN = os.environ.get("PLEX_TOKEN", "")
PLEX_URL = os.environ.get("PLEX_URL", "http://localhost:32400")
WATCHLIST_RSS = os.environ["WATCHLIST_RSS"]
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
TORRENTIO_PROXY = os.environ.get("TORRENTIO_PROXY", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))
GRACE_HOURS = int(os.environ.get("GRACE_HOURS", "24"))

DATA_DIR = Path("/app/data")
STATE_FILE = DATA_DIR / "state.json"
HEARTBEAT_FILE = DATA_DIR / "heartbeat"
LOG_FILE = DATA_DIR / "watchlist-sync.log"

# --- IMDB ID cache: title -> imdb_id ---
IMDB_CACHE_FILE = DATA_DIR / "imdb_cache.json"

# --- Torrentio base URL ---
TORRENTIO_BASE = "https://torrentio.strem.fun"
# Filter: sort by quality+size, exclude cam/screener/480p
TORRENTIO_FILTER = "sort=qualitysize|qualityfilter=480p,scr,cam,unknown"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except:
        pass


def discord(msg):
    if not DISCORD_WEBHOOK:
        return
    try:
        data = json.dumps({"content": msg}).encode()
        req = urllib.request.Request(
            DISCORD_WEBHOOK, data=data,
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
    except:
        pass


def touch_heartbeat():
    HEARTBEAT_FILE.touch()


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"managed": {}, "removed": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_imdb_cache():
    if IMDB_CACHE_FILE.exists():
        with open(IMDB_CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_imdb_cache(cache):
    with open(IMDB_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


# --- HTTP helpers ---
_proxy_handler = None


def _setup_proxy():
    """Configure HTTP proxy for Torrentio requests."""
    global _proxy_handler
    if not TORRENTIO_PROXY:
        return
    _proxy_handler = urllib.request.ProxyHandler({
        "http": TORRENTIO_PROXY,
        "https": TORRENTIO_PROXY,
    })
    log(f"HTTP proxy configured: {TORRENTIO_PROXY.split('@')[-1] if '@' in TORRENTIO_PROXY else TORRENTIO_PROXY}")


def http_get(url, headers=None, use_proxy=False, timeout=30):
    default_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    if headers:
        default_headers.update(headers)
    req = urllib.request.Request(url, headers=default_headers)
    if use_proxy and _proxy_handler:
        opener = urllib.request.build_opener(_proxy_handler)
        with opener.open(req, timeout=timeout) as resp:
            return resp.read()
    else:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()


def http_post(url, data=None, headers=None, timeout=30):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_delete(url, headers=None, timeout=30):
    req = urllib.request.Request(url, method="DELETE", headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


import urllib.parse


# --- Plex Watchlist ---
def fetch_watchlist():
    """Fetch Plex Watchlist RSS, return list of {title, year, type, guid}."""
    items = []
    try:
        data = http_get(WATCHLIST_RSS)
        root = ET.fromstring(data)
        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el = item.find("link")
            category_el = item.find("category")
            if title_el is None:
                continue
            raw_title = title_el.text.strip()
            # Extract year from title like "Shogun (2024)"
            m = re.match(r"^(.*?)\s*\((\d{4})\)$", raw_title)
            if m:
                title = m.group(1).strip()
                year = int(m.group(2))
            else:
                title = raw_title
                year = None
            media_type = "show"
            if category_el is not None and "movie" in (category_el.text or "").lower():
                media_type = "movie"
            guid = ""
            if link_el is not None and link_el.text:
                guid = link_el.text.strip()
            items.append({
                "title": title,
                "year": year,
                "type": media_type,
                "guid": guid,
                "raw_title": raw_title,
            })
    except Exception as e:
        log(f"ERROR fetching watchlist: {e}")
    return items


# --- IMDB lookup ---
def get_imdb_id(title, year, media_type):
    """Look up IMDB ID using Plex's metadata search."""
    cache = load_imdb_cache()
    cache_key = f"{title}_{year}_{media_type}"
    if cache_key in cache:
        return cache[cache_key]

    # Try searching via a public metadata API
    try:
        query = urllib.parse.quote(f"{title} {year or ''}")
        # Use IMDB suggestions API
        clean_title = re.sub(r"[^a-zA-Z0-9 ]", "", title).strip().lower()
        first_word = clean_title.split()[0] if clean_title else title[0]
        url = f"https://v2.sg.media-imdb.com/suggestion/{first_word[0]}/{urllib.parse.quote(clean_title)}.json"
        data = json.loads(http_get(url))
        for result in data.get("d", []):
            rid = result.get("id", "")
            if not rid.startswith("tt"):
                continue
            rtitle = result.get("l", "").lower()
            ryear = result.get("y", 0)
            if rtitle == title.lower() or title.lower() in rtitle:
                if year and ryear and abs(ryear - year) <= 1:
                    cache[cache_key] = rid
                    save_imdb_cache(cache)
                    return rid
                elif not year:
                    cache[cache_key] = rid
                    save_imdb_cache(cache)
                    return rid
        # Fallback: take first tt result
        for result in data.get("d", []):
            rid = result.get("id", "")
            if rid.startswith("tt"):
                cache[cache_key] = rid
                save_imdb_cache(cache)
                return rid
    except Exception as e:
        log(f"IMDB lookup failed for {title}: {e}")

    return None


# --- Torrentio ---
def search_torrentio(imdb_id, media_type, season=None, episode=None):
    """Query Torrentio for streams. Returns list of stream dicts."""
    if media_type == "movie":
        url = f"{TORRENTIO_BASE}/{TORRENTIO_FILTER}/stream/movie/{imdb_id}.json"
    elif season and episode:
        url = f"{TORRENTIO_BASE}/{TORRENTIO_FILTER}/stream/series/{imdb_id}:{season}:{episode}.json"
    else:
        # For shows, search for S01E01 first to get season pack results
        url = f"{TORRENTIO_BASE}/{TORRENTIO_FILTER}/stream/series/{imdb_id}:1:1.json"

    try:
        data = json.loads(http_get(url, use_proxy=True))
        return data.get("streams", [])
    except Exception as e:
        log(f"Torrentio search failed for {imdb_id}: {e}")
        return []


def parse_torrentio_stream(stream):
    """Parse a Torrentio stream into structured info."""
    title = stream.get("title", "") or ""
    name = stream.get("name", "") or ""
    info_hash = stream.get("infoHash", "")

    # If no infoHash, try to extract from URL
    if not info_hash:
        url = stream.get("url", "")
        m = re.search(r"[a-fA-F0-9]{40}", url)
        if m:
            info_hash = m.group(0)

    if not info_hash:
        return None

    full_text = f"{name} {title}".lower()

    # Detect type
    is_complete = bool(re.search(r"complete|s\d+\s*-\s*s\d+|all\s+season", full_text))
    is_season_pack = bool(re.search(r"season|s\d{1,2}(?!\s*e\d)", full_text)) and not is_complete
    is_episode = bool(re.search(r"s\d{1,2}e\d{1,2}", full_text))

    if is_complete:
        pack_type = "complete"
    elif is_season_pack and not is_episode:
        pack_type = "season"
    elif is_episode:
        pack_type = "episode"
    else:
        pack_type = "unknown"

    # Quality
    resolution = "unknown"
    if "2160p" in full_text or "4k" in full_text:
        resolution = "2160p"
    elif "1080p" in full_text:
        resolution = "1080p"
    elif "720p" in full_text:
        resolution = "720p"

    # Size (Torrentio puts size in title like "15.2 GB")
    size_gb = 0
    size_match = re.search(r"([\d.]+)\s*GB", title, re.IGNORECASE)
    if size_match:
        size_gb = float(size_match.group(1))

    # Language penalty
    is_foreign = bool(re.search(
        r"\bita\b|\brus\b|\bfrench\b|\brutor\b|\brutracker\b|\bselen\b|\bcastell",
        full_text
    ))
    has_english = bool(re.search(r"\beng\b|\benglish\b", full_text))

    return {
        "info_hash": info_hash.lower(),
        "title": title[:100],
        "pack_type": pack_type,
        "resolution": resolution,
        "size_gb": size_gb,
        "is_foreign": is_foreign,
        "has_english": has_english,
    }


def score_stream(parsed):
    """Score a parsed stream. Higher = better."""
    score = 0

    # Pack type: complete > season > episode
    pack_scores = {"complete": 2000, "season": 1000, "episode": 0, "unknown": 0}
    score += pack_scores.get(parsed["pack_type"], 0)

    # Resolution: 4K > 1080p > 720p
    res_scores = {"2160p": 1000, "1080p": 500, "720p": 100, "unknown": 0}
    score += res_scores.get(parsed["resolution"], 0)

    # Language: penalize foreign, boost English
    if parsed["is_foreign"] and not parsed["has_english"]:
        score -= 500
    if parsed["is_foreign"]:
        score -= 100

    # Size tiebreaker (bigger usually = better quality, but capped)
    score += min(parsed["size_gb"], 100)

    return score


def find_best_torrent(imdb_id, media_type, season=None, episode=None, expected_title=None):
    """Search Torrentio and return the single best stream."""
    streams = search_torrentio(imdb_id, media_type, season, episode)
    if not streams:
        return None

    parsed_streams = []
    for s in streams:
        parsed = parse_torrentio_stream(s)
        if parsed and parsed["info_hash"]:
            # Title validation: reject results that don't match expected show
            if expected_title:
                torrent_name = parsed.get("title", "").lower()
                expected_words = [w for w in re.sub(r"[^a-z0-9 ]", "", expected_title.lower()).split() if len(w) > 2]
                # At least half of significant title words must appear in torrent name
                matches = sum(1 for w in expected_words if w in torrent_name)
                if expected_words and matches < len(expected_words) / 2:
                    log(f"TITLE REJECT: {parsed.get('title','')[:50]} (match {matches}/{len(expected_words)})")
                    continue  # Skip mismatched result
            parsed["score"] = score_stream(parsed)
            parsed_streams.append(parsed)

    if not parsed_streams:
        return None

    # Sort by score descending
    parsed_streams.sort(key=lambda x: x["score"], reverse=True)
    return parsed_streams[0]


# --- Real-Debrid ---
def rd_headers():
    return {"Authorization": f"Bearer {RD_TOKEN}"}


def rd_get_torrents():
    """Get all torrents in RD account."""
    try:
        data = json.loads(http_get(
            "https://api.real-debrid.com/rest/1.0/torrents?limit=100",
            headers=rd_headers()
        ))
        return data
    except:
        return []


def rd_has_hash(info_hash):
    """Check if a hash is already in RD."""
    torrents = rd_get_torrents()
    for t in torrents:
        # RD doesn't expose hash directly, but we track in state
        pass
    return False


def rd_add_magnet(info_hash):
    """Add a magnet to RD. Returns torrent ID, 'blocked' for 451, or None."""
    magnet = f"magnet:?xt=urn:btih:{info_hash}"
    try:
        data = urllib.parse.urlencode({"magnet": magnet}).encode()
        req = urllib.request.Request(
            "https://api.real-debrid.com/rest/1.0/torrents/addMagnet",
            data=data,
            headers=rd_headers()
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result.get("id")
    except urllib.error.HTTPError as e:
        if e.code == 451:
            log(f"RD BLOCKED (451): {info_hash[:16]}... — content unavailable for legal reasons")
            return "blocked"
        log(f"RD addMagnet failed: {e}")
        return None
    except Exception as e:
        log(f"RD addMagnet failed: {e}")
        return None


def rd_select_files(torrent_id):
    """Select all files in a torrent."""
    try:
        data = urllib.parse.urlencode({"files": "all"}).encode()
        req = urllib.request.Request(
            f"https://api.real-debrid.com/rest/1.0/torrents/selectFiles/{torrent_id}",
            data=data,
            headers=rd_headers()
        )
        urllib.request.urlopen(req, timeout=30)
        return True
    except Exception as e:
        log(f"RD selectFiles failed: {e}")
        return False


def rd_delete_torrent(torrent_id):
    """Delete a torrent from RD."""
    try:
        http_delete(
            f"https://api.real-debrid.com/rest/1.0/torrents/delete/{torrent_id}",
            headers=rd_headers()
        )
        return True
    except:
        return False


# --- Plex ---
def plex_scan():
    """Trigger Plex library scan for both sections."""
    if not PLEX_TOKEN:
        return
    try:
        for section in ["3", "4"]:
            req = urllib.request.Request(
                f"{PLEX_URL}/library/sections/{section}/refresh?X-Plex-Token={PLEX_TOKEN}",
                method="POST"
            )
            urllib.request.urlopen(req, timeout=10)
    except:
        pass


def plex_empty_trash():
    """Empty trash in both Plex library sections."""
    if not PLEX_TOKEN:
        return
    try:
        for section in ["3", "4"]:
            req = urllib.request.Request(
                f"{PLEX_URL}/library/sections/{section}/emptyTrash?X-Plex-Token={PLEX_TOKEN}",
                method="PUT"
            )
            urllib.request.urlopen(req, timeout=10)
    except:
        pass


# --- Main logic ---
def process_watchlist_item(item, state):
    """Process a single watchlist item. Returns True if new content was added."""
    title = item["title"]
    raw_title = item["raw_title"]
    media_type = item["type"]
    year = item["year"]

    # Already managed?
    state_key = raw_title.lower()
    if state_key in state.get("managed", {}):
        return False

    # Blocked by RD (451)?
    if state_key in state.get("blocked", {}):
        return False

    # Get IMDB ID
    imdb_id = get_imdb_id(title, year, media_type)
    if not imdb_id:
        log(f"SKIP {title} — no IMDB ID found")
        return False

    if media_type == "movie":
        best = find_best_torrent(imdb_id, "movie", expected_title=title)
        if not best:
            log(f"SKIP {title} — no streams found")
            return False

        log(f"ADDING {title}: {best['resolution']} {best['pack_type']} (score: {best['score']:.0f})")
        torrent_id = rd_add_magnet(best["info_hash"])
        if torrent_id == "blocked":
            state.setdefault("blocked", {})[state_key] = {
                "title": title, "reason": "451", "blocked_at": datetime.now().isoformat()
            }
            discord(f"⛔ **Blocked by RD**: {title} — unavailable for legal reasons")
            return False
        if torrent_id:
            rd_select_files(torrent_id)
            state["managed"][state_key] = {
                "imdb_id": imdb_id,
                "type": media_type,
                "info_hash": best["info_hash"],
                "rd_id": torrent_id,
                "added_at": datetime.now().isoformat(),
                "title": title,
            }
            discord(f"🎬 **Added movie**: {title} [{best['resolution']}]")
            return True

    elif media_type == "show":
        # Strategy: search S01E01 first — Torrentio returns season packs too
        best = find_best_torrent(imdb_id, "show", expected_title=title)
        if not best:
            log(f"SKIP {title} — no streams found")
            return False

        log(f"ADDING {title}: {best['resolution']} {best['pack_type']} (score: {best['score']:.0f}) — {best['title'][:60]}")
        torrent_id = rd_add_magnet(best["info_hash"])
        if torrent_id == "blocked":
            state.setdefault("blocked", {})[state_key] = {
                "title": title, "reason": "451", "blocked_at": datetime.now().isoformat()
            }
            discord(f"⛔ **Blocked by RD**: {title} — unavailable for legal reasons")
            return False
        if torrent_id:
            rd_select_files(torrent_id)
            state["managed"][state_key] = {
                "imdb_id": imdb_id,
                "type": media_type,
                "info_hash": best["info_hash"],
                "rd_id": torrent_id,
                "added_at": datetime.now().isoformat(),
                "title": title,
                "pack_type": best["pack_type"],
            }
            pack_label = {"complete": "complete series", "season": "season pack", "episode": "episode"}.get(best["pack_type"], "")
            discord(f"📺 **Added show**: {title} [{best['resolution']} {pack_label}]")
            return True

    return False


def cleanup_removed(watchlist_titles, state):
    """Remove RD torrents for items no longer on watchlist (with grace period)."""
    now = datetime.now()
    managed = state["managed"]
    removed = state.get("removed", {})
    to_delete = []

    for state_key, info in list(managed.items()):
        if state_key in watchlist_titles:
            # Still on watchlist — remove from removed tracking if present
            removed.pop(state_key, None)
            continue

        # Not on watchlist
        if state_key not in removed:
            removed[state_key] = now.isoformat()
            log(f"FLAGGED for removal: {info.get('title', state_key)} (24h grace started)")
        else:
            flagged_at = datetime.fromisoformat(removed[state_key])
            if now - flagged_at > timedelta(hours=GRACE_HOURS):
                to_delete.append(state_key)

    deleted_names = []
    for state_key in to_delete:
        info = managed.get(state_key, {})
        rd_id = info.get("rd_id", "")
        title = info.get("title", state_key)
        if rd_id:
            rd_delete_torrent(rd_id)
        managed.pop(state_key, None)
        removed.pop(state_key, None)
        deleted_names.append(title)
        log(f"DELETED: {title}")

    state["removed"] = removed

    if deleted_names:
        plex_scan()
        time.sleep(15)
        plex_empty_trash()
        msg = f"🧹 **Removed {len(deleted_names)} items** (off watchlist >24h):\n"
        for name in deleted_names:
            msg += f"  • {name}\n"
        discord(msg)


def main_loop():
    log("Watchlist Sync starting")
    _setup_proxy()
    log("Sending startup Discord..."); discord("🚀 **Watchlist Sync** started"); log("Discord sent, loading state...")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    log("State loaded, entering main loop...")
    cycle = 0

    while True:
        log(f"Cycle {cycle+1} starting...")
        try:
            touch_heartbeat()
            cycle += 1

            # Fetch watchlist
            watchlist = fetch_watchlist()
            if not watchlist:
                log("WARNING: empty watchlist or fetch failed")
                time.sleep(POLL_INTERVAL)
                continue

            watchlist_titles = {item["raw_title"].lower() for item in watchlist}

            # Process new items
            added = 0
            for item in watchlist:
                try:
                    if process_watchlist_item(item, state):
                        added += 1
                        save_state(state)
                        time.sleep(2)  # Rate limit RD
                except Exception as e:
                    log(f"ERROR processing {item['title']}: {e}")

            # Trigger Plex scan if we added anything
            if added > 0:
                log(f"Added {added} new items, triggering Plex scan")
                time.sleep(10)  # Wait for Zurg to pick up new RD content
                plex_scan()

            # Cleanup items removed from watchlist
            try:
                cleanup_removed(watchlist_titles, state)
                save_state(state)
            except Exception as e:
                log(f"ERROR in cleanup: {e}")

            # Periodic heartbeat log
            if cycle % 60 == 0:  # Every ~60 minutes
                rd_count = len(rd_get_torrents())
                log(f"HEARTBEAT: {len(state['managed'])} managed items, {rd_count} RD torrents, {len(watchlist)} watchlist items")

        except Exception as e:
            log(f"ERROR in main loop: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main_loop()
