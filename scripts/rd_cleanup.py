import urllib.request, json, re, sys, time

API_KEY = "QMHDXE77L3SOSWHR3YBP2MQ2F2I3RPGMIV7VDCSMOH6IWMQGHQAQ"
DRY_RUN = "--execute" not in sys.argv

req = urllib.request.Request("https://api.real-debrid.com/rest/1.0/torrents?limit=100",
    headers={"Authorization": "Bearer " + API_KEY})
with urllib.request.urlopen(req) as resp:
    torrents = json.loads(resp.read())

print("Total torrents in RD: %d" % len(torrents))

def parse_torrent(t):
    fn = t["filename"]
    fn_lower = fn.lower()
    fn_clean = re.sub(r"[.\-_\[\](){}]", " ", fn_lower)
    fn_clean = re.sub(r"^(www\S+\s+)", "", fn_clean).strip()
    fn_clean = re.sub(r"^\[.*?\]\s*", "", fn_clean).strip()

    info = {
        "id": t["id"],
        "filename": fn,
        "bytes": t.get("bytes", 0),
        "title": "",
        "type": "unknown",
        "seasons": set(),
        "episodes": set(),
    }

    # Multi-season: S01-S14, Season 1 to 7
    m = re.search(r"s(\d{1,2})\s*[-]+\s*s(\d{1,2})", fn_clean)
    if not m:
        m = re.search(r"season\s*(\d+)\s*[-to]+\s*(\d+)", fn_clean)
    if m:
        s_start, s_end = int(m.group(1)), int(m.group(2))
        info["seasons"] = set(range(s_start, s_end + 1))
        info["type"] = "multi_season"
        info["title"] = re.sub(r"\s+", " ", fn_clean[:m.start()]).strip()
        return info

    # Complete/Series pack
    if "complete" in fn_clean or ("series" in fn_clean and "s0" not in fn_clean):
        info["type"] = "complete_series"
        title = re.split(r"complete|series", fn_clean)[0].strip()
        info["title"] = re.sub(r"\s+", " ", title).strip()
        info["seasons"] = set(range(1, 100))
        return info

    # Season pack with episode range: S01E01-08
    m = re.search(r"s(\d{1,2})e(\d{1,2})\s*[-]+\s*(\d{1,2})", fn_clean)
    if m:
        s = int(m.group(1))
        e_start, e_end = int(m.group(2)), int(m.group(3))
        info["seasons"] = {s}
        info["episodes"] = {(s, e) for e in range(e_start, e_end + 1)}
        info["type"] = "season"
        info["title"] = re.sub(r"\s+", " ", fn_clean[:m.start()]).strip()
        return info

    # Single episode: S01E05
    m = re.search(r"s(\d{1,2})e(\d{1,2})", fn_clean)
    if m:
        s, e = int(m.group(1)), int(m.group(2))
        info["seasons"] = {s}
        info["episodes"] = {(s, e)}
        info["type"] = "episode"
        info["title"] = re.sub(r"\s+", " ", fn_clean[:m.start()]).strip()
        return info

    # Single season: S01 (no episode number after)
    m = re.search(r"s(\d{1,2})(?!\d|e\d)", fn_clean)
    if not m:
        m = re.search(r"season\s*(\d+)", fn_clean)
    if m:
        s = int(m.group(1))
        info["seasons"] = {s}
        info["type"] = "season"
        info["title"] = re.sub(r"\s+", " ", fn_clean[:m.start()]).strip()
        return info

    # Movie
    m = re.match(r"^(.*?)\s+\d{4}\b", fn_clean)
    if m and len(m.group(1).strip()) > 2:
        info["title"] = m.group(1).strip()
        info["type"] = "movie"
    else:
        info["title"] = " ".join(fn_clean.split()[:3])
        info["type"] = "movie"
    return info

def normalize_title(title):
    t = title.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\b(the|a|an)\b", "", t).strip()
    t = re.sub(r"\s+", " ", t)
    t = t.replace("1", "i").replace("bobs", "bob s")
    return t

def titles_match(a, b):
    na, nb = normalize_title(a), normalize_title(b)
    if na == nb:
        return True
    if len(na) > 3 and len(nb) > 3:
        if na in nb or nb in na:
            return True
    return False

def score_torrent(info):
    fn = info["filename"].lower()
    score = 0
    if "2160p" in fn or "4k" in fn:
        score += 1000
    elif "1080p" in fn:
        score += 500
    elif "720p" in fn:
        score += 100
    if any(x in fn for x in ["ita ", "ita.", "french", "rus ", "rus.", "rutor", "rutracker", "selen"]):
        score -= 200
    if "web-dl" in fn or "webdl" in fn:
        score += 50
    elif "bluray" in fn:
        score += 70
    elif "webrip" in fn:
        score += 30
    if "hdr" in fn:
        score += 100
    if " dv " in fn or "dolby" in fn or ".dv." in fn:
        score += 80
    if fn.startswith("[") or "www." in fn:
        score -= 100
    score += info["bytes"] / (1024 * 1024 * 1024)
    return score

# Parse all
parsed = [parse_torrent(t) for t in torrents]

# Group by title
title_groups = {}
for p in parsed:
    nt = normalize_title(p["title"])
    found_key = None
    for existing_key in title_groups:
        if titles_match(nt, existing_key):
            found_key = existing_key
            break
    if found_key:
        title_groups[found_key].append(p)
    else:
        title_groups[nt] = [p]

keep_ids = set()
remove_list = []

for title, items in sorted(title_groups.items()):
    print("\n=== %s (%d entries) ===" % (title.upper(), len(items)))

    # Movies: keep best, remove rest
    if all(i["type"] == "movie" for i in items):
        scored = [(score_torrent(i), i) for i in items]
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]
        keep_ids.add(best["id"])
        print("  KEEP:   [%d] %s" % (best_score, best["filename"][:70]))
        for s, i in scored[1:]:
            remove_list.append((i["id"], i["filename"]))
            print("  REMOVE (lower quality): [%d] %s" % (s, i["filename"][:70]))
        continue

    # TV: process from broadest coverage to narrowest, best quality first
    type_priority = {"complete_series": 4, "multi_season": 3, "season": 2, "episode": 1, "movie": 0, "unknown": 0}
    items.sort(key=lambda x: (type_priority.get(x["type"], 0), score_torrent(x)), reverse=True)

    covered_seasons = set()
    covered_episodes = set()
    kept_items = []

    for item in items:
        score = score_torrent(item)
        item_type = item["type"]
        item_seasons = item["seasons"]
        item_episodes = item["episodes"]

        # Check containment
        is_contained = False
        reason = ""

        if item_type == "episode":
            if item_episodes and item_episodes.issubset(covered_episodes):
                is_contained = True
                reason = "episode already in kept season/pack"
            elif item_seasons and item_seasons.issubset(covered_seasons):
                is_contained = True
                reason = "full season already kept"

        elif item_type == "season":
            if item_seasons and item_seasons.issubset(covered_seasons):
                is_contained = True
                reason = "season already in larger pack"

        elif item_type in ("multi_season", "complete_series"):
            if item_seasons and item_seasons.issubset(covered_seasons):
                is_contained = True
                reason = "all seasons already covered"

        if is_contained:
            remove_list.append((item["id"], item["filename"]))
            print("  REMOVE (%s): [%d] %s" % (reason, score, item["filename"][:60]))
            continue

        # Check for exact duplicates (same type, same season coverage, same episodes)
        is_dup = False
        for kept in kept_items:
            if kept["type"] == item_type and kept["seasons"] == item_seasons:
                if item_type == "episode" and kept["episodes"] != item_episodes:
                    continue  # different episodes, not a duplicate
                is_dup = True
                break

        if is_dup:
            remove_list.append((item["id"], item["filename"]))
            print("  REMOVE (duplicate): [%d] %s" % (score, item["filename"][:60]))
            continue

        # Keep this item - it adds new coverage
        keep_ids.add(item["id"])
        kept_items.append(item)
        if item_type in ("complete_series", "multi_season", "season"):
            covered_seasons.update(item_seasons)
            for s in item_seasons:
                for e in range(1, 100):
                    covered_episodes.add((s, e))
        elif item_type == "episode":
            covered_episodes.update(item_episodes)

        if len(item_seasons) > 10:
            seasons_str = "%d-%d" % (min(item_seasons), max(item_seasons))
        else:
            seasons_str = str(sorted(item_seasons))
        print("  KEEP:   [%d] %s [%s, S=%s]" % (score, item["filename"][:60], item_type, seasons_str))

print("\n" + "=" * 60)
print("KEEP: %d torrents" % len(keep_ids))
print("REMOVE: %d torrents" % len(remove_list))

if DRY_RUN:
    print("\nDRY RUN - pass --execute to delete")
else:
    print("\nDeleting...")
    deleted = 0
    for tid, fname in remove_list:
        try:
            dreq = urllib.request.Request(
                "https://api.real-debrid.com/rest/1.0/torrents/delete/" + tid,
                method="DELETE",
                headers={"Authorization": "Bearer " + API_KEY})
            urllib.request.urlopen(dreq)
            deleted += 1
            print("  Deleted: %s" % fname[:60])
            time.sleep(0.5)
        except Exception as e:
            print("  FAILED: %s - %s" % (fname[:60], e))
    print("\nDeleted %d/%d torrents" % (deleted, len(remove_list)))
