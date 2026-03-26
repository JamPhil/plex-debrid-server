#!/usr/bin/env python3
"""Daily Server Report - covers pipeline status, server health, debrid, and plex."""

import urllib.request, json, os, re, subprocess, xml.etree.ElementTree as ET, datetime

# Load config from .env
ENV = {}
with open("/opt/plex-server/.env") as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            ENV[k] = v

WEBHOOK_URL = ENV.get("DISCORD_WEBHOOK_URL", "")
RD_TOKEN = ENV.get("REAL_DEBRID_API_TOKEN", "")
PLEX_TOKEN = ENV.get("PLEX_TOKEN", "")
WATCHLIST_RSS = ENV.get("WATCHLIST_RSS", "")


def run(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception:
        return ""


def api_get(url, headers=None, timeout=10):
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def api_get_raw(url, timeout=10):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def get_watchlist_titles():
    """Fetch watchlist titles from RSS."""
    if not WATCHLIST_RSS:
        return []
    try:
        req = urllib.request.Request(WATCHLIST_RSS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            rss_root = ET.fromstring(resp.read())
        titles = []
        for item in rss_root.findall(".//item"):
            t = item.find("title")
            if t is not None and t.text:
                clean = re.sub(r"\s*\(\d{4}\)\s*", "", t.text).strip()
                titles.append(clean)
        return titles
    except Exception:
        return []


def get_rd_show_movie_count():
    """Count unique shows and movies in RD by grouping torrents."""
    rd_torrents = api_get("https://api.real-debrid.com/rest/1.0/torrents?limit=100",
        headers={"Authorization": f"Bearer {RD_TOKEN}"})
    if rd_torrents is None:
        return None, None, rd_torrents

    shows = set()
    movies = set()
    for t in rd_torrents:
        fn = t["filename"].lower()
        fn_clean = re.sub(r"[.\-_\[\](){}]", " ", fn)
        fn_clean = re.sub(r"^\[.*?\]\s*", "", fn_clean)
        fn_clean = re.sub(r"^www\S+\s+", "", fn_clean).strip()
        # Check if it has season/episode markers
        if re.search(r"s\d{1,2}", fn_clean) or "season" in fn_clean or "complete" in fn_clean:
            m = re.match(r"^(.*?)\s*(?:s\d|season|complete)", fn_clean)
            title = m.group(1).strip() if m else fn_clean[:30]
            title = re.sub(r"\s+", " ", title).strip()
            if len(title) > 2:
                shows.add(title)
        else:
            # Movie
            m = re.match(r"^(.*?)\s+\d{4}\b", fn_clean)
            title = m.group(1).strip() if m else fn_clean[:30]
            title = re.sub(r"\s+", " ", title).strip()
            if len(title) > 2:
                movies.add(title)

    return len(shows), len(movies), rd_torrents


def get_plex_titles():
    """Get show and movie titles from Plex."""
    show_titles = []
    movie_titles = []

    shows_xml = api_get_raw(f"http://localhost:32400/library/sections/4/all?X-Plex-Token={PLEX_TOKEN}")
    if shows_xml:
        root = ET.fromstring(shows_xml)
        show_titles = [d.get("title", "") for d in root.findall(".//Directory")]

    movies_xml = api_get_raw(f"http://localhost:32400/library/sections/3/all?X-Plex-Token={PLEX_TOKEN}")
    if movies_xml:
        root = ET.fromstring(movies_xml)
        movie_titles = [v.get("title", "") for v in root.findall(".//Video")]

    return show_titles, movie_titles


def titles_match(watchlist_title, plex_title):
    wl = watchlist_title.lower()
    pt = plex_title.lower()
    if wl in pt or pt in wl:
        return True
    if wl.replace("1", "i") in pt.replace("1", "i"):
        return True
    # Strip common prefixes
    for prefix in ["the ", "a "]:
        wl2 = wl.removeprefix(prefix)
        pt2 = pt.removeprefix(prefix)
        if wl2 in pt2 or pt2 in wl2:
            return True
    return False


# ========================================
# PIPELINE STATUS (top-level summary)
# ========================================
def check_pipeline_status(wl_titles, rd_shows, rd_movies, plex_shows, plex_movies):
    lines = ["**PIPELINE STATUS**"]

    wl_count = len(wl_titles)
    rd_total = (rd_shows or 0) + (rd_movies or 0)
    plex_total = len(plex_shows) + len(plex_movies)

    lines.append(f"📋 Watchlist: {wl_count} items")

    if rd_shows is not None:
        lines.append(f"📦 Debrid: {rd_shows} shows, {rd_movies} movies")
    else:
        lines.append("📦 Debrid: ❌ unreachable")

    lines.append(f"📺 Plex: {len(plex_shows)} shows, {len(plex_movies)} movies")

    # Compare
    if rd_shows is not None:
        rd_behind = wl_count - rd_total
        if rd_behind > 0:
            lines.append(f"⚠️ Debrid {rd_behind} behind watchlist")

    plex_behind = wl_count - plex_total
    if plex_behind > 0:
        lines.append(f"⚠️ Plex {plex_behind} behind watchlist")
    elif plex_behind == 0 and wl_count > 0:
        lines.append("✅ All synced")

    return "\n".join(lines)


# ========================================
# SERVER HEALTH
# ========================================
def check_server_health():
    lines = ["**SERVER HEALTH**"]

    # Container status
    expected = ["zurg", "rclone", "plex", "watchlist-sync", "autoheal"]
    bad = []
    for c in expected:
        status = run(f"docker inspect --format='{{{{.State.Status}}}}' {c} 2>/dev/null")
        health = run(f"docker inspect --format='{{{{.State.Health.Status}}}}' {c} 2>/dev/null")
        if status != "running":
            bad.append(f"{c}: {status or 'missing'}")
        elif health and health not in ("healthy", ""):
            bad.append(f"{c}: {health}")

    if not bad:
        lines.append("✅ All systems healthy")
    else:
        for b in bad:
            lines.append(f"❌ {b}")

    # Watchlist manager specific check
    wm_status = run("docker inspect --format='{{.State.Status}}' watchlist-sync 2>/dev/null")
    wm_health = run("docker inspect --format='{{.State.Health.Status}}' watchlist-sync 2>/dev/null")
    if wm_status == "running" and wm_health in ("healthy", ""):
        lines.append("✅ Watchlist Manager healthy")
    else:
        lines.append(f"❌ Watchlist Manager: {wm_status}/{wm_health}")

    # Only show disk/memory if there's a warning
    disk_pct_str = run("df / | awk 'NR==2 {print $5}'")
    disk_pct = int(disk_pct_str.replace("%", "")) if disk_pct_str else 0
    mem_total = run("free | awk '/Mem:/ {print $2}'")
    mem_used = run("free | awk '/Mem:/ {print $3}'")
    try:
        mem_pct = int(int(mem_used) * 100 / int(mem_total))
    except Exception:
        mem_pct = 0

    if disk_pct > 70:
        disk_used = run("df -h / | awk 'NR==2 {print $3 \"/\" $2}'")
        icon = "🔴" if disk_pct > 85 else "⚠️"
        lines.append(f"{icon} Disk: {disk_used} ({disk_pct}%)")
    if mem_pct > 75:
        mem_info = run("free -h | awk '/Mem:/ {print $3 \"/\" $2}'")
        icon = "🔴" if mem_pct > 90 else "⚠️"
        lines.append(f"{icon} Memory: {mem_info} ({mem_pct}%)")

    # FUSE mount
    host_ok = run("ls /mnt/zurg/shows/ > /dev/null 2>&1 && echo ok") == "ok"
    plex_ok = run("docker exec plex ls /mnt/zurg/shows/ > /dev/null 2>&1 && echo ok") == "ok"
    if not host_ok:
        lines.append("🔴 FUSE mount broken!")
    elif not plex_ok:
        lines.append("⚠️ FUSE mount broken inside Plex container")

    return "\n".join(lines)


# ========================================
# DEBRID / TORRENTIO
# ========================================
def check_debrid_health(rd_torrents):
    lines = ["**DEBRID / TORRENTIO**"]

    # Torrentio proxy test
    proxy_line = run("grep TORRENTIO_PROXY /opt/plex-server/docker-compose.yml")
    proxy_url = proxy_line.split("=", 1)[1].strip() if "=" in proxy_line else ""
    if proxy_url:
        result = run(f"curl -sf --proxy {proxy_url} 'https://torrentio.strem.fun/manifest.json'")
        if '"Torrentio"' in result:
            lines.append("✅ Torrentio proxy working")
        else:
            lines.append("🔴 Torrentio proxy FAILED")
    else:
        lines.append("⚠️ No proxy configured")

    # RD premium
    rd_user = api_get("https://api.real-debrid.com/rest/1.0/user",
        headers={"Authorization": f"Bearer {RD_TOKEN}"})
    if rd_user:
        expiry = rd_user.get("expiration", "")
        if expiry:
            try:
                exp_date = datetime.datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                days_left = (exp_date - datetime.datetime.now(datetime.timezone.utc)).days
                icon = "🔴" if days_left < 7 else "⚠️" if days_left < 30 else "✅"
                lines.append(f"{icon} RD premium: {days_left} days")
            except Exception:
                lines.append("✅ RD premium active")
    else:
        lines.append("🔴 RD API unreachable")

    # Error state torrents
    if rd_torrents:
        error_torrents = [t for t in rd_torrents if t.get("status") != "downloaded"]
        if error_torrents:
            lines.append(f"⚠️ {len(error_torrents)} torrent(s) in error state:")
            for t in error_torrents[:3]:
                fn_short = t["filename"][:40]
                lines.append(f"  • {fn_short} ({t.get('status', '?')})")

        # Duplicate detection
        titles = {}
        for t in rd_torrents:
            fn_clean = re.sub(r"[.\-_\[\](){}]", " ", t["filename"].lower())
            fn_clean = re.sub(r"^\[.*?\]\s*", "", fn_clean)
            fn_clean = re.sub(r"^www\S+\s+", "", fn_clean).strip()
            m = re.match(r"^(.*?)\s*(?:s\d|season|\d{4})", fn_clean)
            title = m.group(1).strip()[:25] if m else fn_clean[:25]
            titles[title] = titles.get(title, 0) + 1
        dupes = {k: v for k, v in titles.items() if v > 1}
        if dupes:
            lines.append(f"⚠️ {len(dupes)} possible duplicates:")
            for name, count in list(dupes.items())[:3]:
                lines.append(f"  • {name} ({count}x)")
        else:
            lines.append("✅ No duplicates")

    # Watchlist sync activity (last 24h)
    ws_log = run("docker logs --since 24h watchlist-sync 2>&1 | tail -50")
    if ws_log:
        log_lines = ws_log.split("\n")

        # Blocked items (451)
        blocked = set()
        for l in log_lines:
            if "451" in l:
                m = re.search(r"ADDING (.*?):", l)
                if m:
                    blocked.add(m.group(1))
        if blocked:
            lines.append(f"🚫 {len(blocked)} blocked by RD (legal):")
            for b in list(blocked)[:3]:
                lines.append(f"  • {b}")

        # Items added
        added = set()
        for l in log_lines:
            if "ADDING" in l and "451" not in l and "fail" not in l.lower():
                m = re.search(r"ADDING (.*?):", l)
                if m:
                    added.add(m.group(1))
        if added:
            lines.append(f"📥 {len(added)} items added in 24h")

    return "\n".join(lines)


# ========================================
# PLEX
# ========================================
def check_plex_health(wl_titles, plex_shows, plex_movies, rd_torrents):
    lines = ["**PLEX**"]

    # Plex reachable
    identity = api_get_raw("http://localhost:32400/identity")
    if not identity:
        lines.append("🔴 Plex server not responding")
        return "\n".join(lines)
    lines.append("✅ Plex responding")

    # Active scans
    activities_xml = api_get_raw(f"http://localhost:32400/activities?X-Plex-Token={PLEX_TOKEN}")
    if activities_xml:
        root = ET.fromstring(activities_xml)
        scans = []
        for a in root.findall(".//Activity"):
            atype = a.get("type", "")
            if "library" in atype:
                sub = a.get("subtitle", "unknown")
                prog = a.get("progress", "?")
                scans.append(f"{sub[:45]} ({prog}%)")
        if scans:
            lines.append(f"🔄 Scanning: {scans[0]}")
        else:
            lines.append("✅ Idle (no active scans)")

    # Missing from Plex with reason
    if wl_titles:
        all_plex = plex_shows + plex_movies
        # Build set of RD show names for comparison
        rd_names = set()
        if rd_torrents:
            for t in rd_torrents:
                fn = re.sub(r"[.\-_\[\](){}]", " ", t["filename"].lower())
                fn = re.sub(r"^\[.*?\]\s*", "", fn)
                fn = re.sub(r"^www\S+\s+", "", fn).strip()
                rd_names.add(fn[:40])

        missing_items = []
        for wt in wl_titles:
            found_in_plex = any(titles_match(wt, pt) for pt in all_plex)
            if not found_in_plex:
                # Check if it's in RD
                wl_lower = wt.lower()
                in_rd = any(
                    wl_lower.replace("1", "i") in rn.replace("1", "i") or
                    rn.replace("1", "i") in wl_lower.replace("1", "i")
                    for rn in rd_names
                )
                if in_rd:
                    missing_items.append(f"  • {wt} *(in RD, pending scan)*")
                else:
                    missing_items.append(f"  • {wt} *(not in RD)*")

        if missing_items:
            lines.append(f"⚠️ {len(missing_items)} missing from Plex:")
            lines.extend(missing_items[:6])
            if len(missing_items) > 6:
                lines.append(f"  ...+{len(missing_items)-6} more")
        else:
            lines.append("✅ All watchlist items in Plex")

    return "\n".join(lines)


# ========================================
# SEND REPORT
# ========================================
def main():
    # Gather shared data once
    wl_titles = get_watchlist_titles()
    rd_shows, rd_movies, rd_torrents = get_rd_show_movie_count()
    plex_shows, plex_movies = get_plex_titles()

    # Build sections
    pipeline = check_pipeline_status(wl_titles, rd_shows, rd_movies, plex_shows, plex_movies)
    server = check_server_health()
    debrid = check_debrid_health(rd_torrents)
    plex = check_plex_health(wl_titles, plex_shows, plex_movies, rd_torrents)

    msg = f"📊 **Daily Server Report**\n\n{pipeline}\n\n{server}\n\n{debrid}\n\n{plex}"

    if len(msg) > 1900:
        msg = msg[:1900] + "\n...(truncated)"

    payload = json.dumps({"content": msg})
    result = subprocess.run(
        ["curl", "-sf", "-H", "Content-Type: application/json",
         "-d", payload, WEBHOOK_URL],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode == 0:
        print("Report sent to Discord")
    else:
        print(f"Failed to send: {result.stderr[:100]}")


if __name__ == "__main__":
    main()
