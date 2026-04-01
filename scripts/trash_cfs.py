#!/usr/bin/env python3
"""Apply TRaSH Guide recommendations to Sonarr and Radarr."""
import urllib.request, json, sys
import xml.etree.ElementTree as ET

def api_post(port, path, key, data):
    req = urllib.request.Request(
        "http://localhost:{}/api/v3/{}".format(port, path),
        data=json.dumps(data).encode(),
        headers={"X-Api-Key": key, "Content-Type": "application/json"},
        method="POST"
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())

def api_get(port, path, key):
    req = urllib.request.Request("http://localhost:{}/api/v3/{}".format(port, path), headers={"X-Api-Key": key})
    return json.loads(urllib.request.urlopen(req).read())

def api_put(port, path, key, data):
    req = urllib.request.Request(
        "http://localhost:{}/api/v3/{}".format(port, path),
        data=json.dumps(data).encode(),
        headers={"X-Api-Key": key, "Content-Type": "application/json"},
        method="PUT"
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())

SONARR_KEY = "00769b3d70044bcbb66eee2f50c2c116"
RADARR_KEY = "2125f84876a04d97ad63abe3304967f6"

def make_streaming_cf(name, regex, required=True, has_rename=False, rename_regex=None):
    specs = []
    labels = {
        "AMZN": "Amazon", "ATVP": "Apple TV+", "NF": "Netflix",
        "DSNP": "Disney+", "HULU": "Hulu", "PCOK": "Peacock TV",
        "iT": "iTunes", "DCU": "DC Universe", "SYFY": "SYFY",
        "PMTP": "Paramount+", "HBO": "HBO", "MAX": "Max",
        "CC": "Comedy Central", "HMAX": "HBO Max", "SHO": "SHOWTIME",
        "STAN": "Stan",
    }
    if has_rename:
        specs.append({"name": labels.get(name, name), "implementation": "ReleaseTitleSpecification",
                       "negate": False, "required": False,
                       "fields": [{"name": "value", "value": regex}]})
        specs.append({"name": name + " Rename", "implementation": "ReleaseTitleSpecification",
                       "negate": False, "required": False,
                       "fields": [{"name": "value", "value": rename_regex}]})
    else:
        specs.append({"name": labels.get(name, name), "implementation": "ReleaseTitleSpecification",
                       "negate": False, "required": required,
                       "fields": [{"name": "value", "value": regex}]})
    specs.append({"name": "WEBDL", "implementation": "SourceSpecification",
                   "negate": False, "required": False,
                   "fields": [{"name": "value", "value": 3}]})
    specs.append({"name": "WEBRIP", "implementation": "SourceSpecification",
                   "negate": False, "required": False,
                   "fields": [{"name": "value", "value": 4}]})
    return {"name": name, "includeCustomFormatWhenRenaming": True, "specifications": specs}

streaming_cfs = [
    make_streaming_cf("AMZN", r"\b(amzn|amazon(hd)?)\b"),
    make_streaming_cf("ATVP", r"\b(atvp|aptv|Apple TV\+)\b"),
    make_streaming_cf("NF", r"\b(nf|netflix(u?hd)?)\b"),
    make_streaming_cf("DSNP", r"\b(dsnp|dsny|disney|Disney\+)\b"),
    make_streaming_cf("HBO", r"\b(hbo)(?![ ._-]max)\b(?=[ ._-]web[ ._-]?(dl|rip)\b)",
                       required=False, has_rename=True,
                       rename_regex=r"\[(HBO)\b|\b(HBO)\]"),
    make_streaming_cf("MAX", r"\b((?<!hbo[ ._-])max)\b(?=[ ._-]web[ ._-]?(dl|rip)\b)",
                       required=False, has_rename=True,
                       rename_regex=r"\[(MAX)\b|\b(MAX)\]"),
    make_streaming_cf("HULU", r"\b(hulu)\b"),
    make_streaming_cf("PCOK", r"\b(pcok|Peacock TV)\b"),
    make_streaming_cf("iT", r"\b(it|itunes)\b(?=[ ._-]web[ ._-]?(dl|rip)\b)",
                       required=False, has_rename=True,
                       rename_regex=r"\[(iT)(?![+])\b|\b(?<![+])(iT)\]"),
    make_streaming_cf("CC", r"\b(CC)\b[ ._-]web[ ._-]?(dl|rip)?\b",
                       required=False, has_rename=True,
                       rename_regex=r"\[(CC)\b|\b(CC)\]"),
    make_streaming_cf("DCU", r"\b(dcu|DC Universe)\b"),
    make_streaming_cf("HMAX", r"\b(hmax|hbom|hbo[ ._-]?max)\b(?=[ ._-]web[ ._-]?(dl|rip)\b)",
                       required=False, has_rename=True,
                       rename_regex=r"\[(HMAX)\b|\b(HMAX)\]"),
    make_streaming_cf("PMTP", r"\b(pmtp|Paramount\+)\b"),
    make_streaming_cf("SHO", r"\b(sho|showtime)\b[ ._-]web[ ._-]?(dl|rip)?\b",
                       required=False, has_rename=True,
                       rename_regex=r"\[(SHO)\b|\b(SHO)\]"),
    make_streaming_cf("STAN", r"\b(stan)\b[ ._-]web[ ._-]?(dl|rip)?\b",
                       required=False, has_rename=True,
                       rename_regex=r"\[(STAN)\b|\b(STAN)\]"),
    make_streaming_cf("SYFY", r"\b(SYFY)\b"),
]

# WEB Tier custom formats
web_tier_01_groups = "ABBiE|AJP69|APEX|PAXA|PEXA|XEPA|CasStudio|CRFW|CtrlHD|FLUX|HONE|KiNGS|Kitsune|monkee|NOSiViD|NTb|NTG|QOQ|RAWR|RTN|SiC|T6D|TOMMY|ViSUM"
web_tier_02_groups = "3cTWeB|BLUTONiUM|BTW|BYNDR|Chotab|Cinefeel|CiT|CMRG|Coo7|dB|DEEP|END|ETHiCS|FC|Flights|GNOME|iJP|iKA|iT00NZ|JETIX|KHN|KiMCHI|LAZY|MiU|MZABI|NPMS|NYH|orbitron|PHOENiX|playWEB|PSiG|ROCCaT|RTFM|SA89|SbR|SDCC|SIGMA|SMURF|SPiRiT|TEPES|TVSmash|WELP|XEBEC|4KBEC|CEBEX"
web_tier_03_groups = "BLOOM|Dooky|DRACULA|HHWEB|NINJACENTRAL|SLiGNOME|SwAgLaNdEr|T4H|ViSiON"

def make_web_tier(name, groups_regex):
    return {
        "name": name,
        "includeCustomFormatWhenRenaming": False,
        "specifications": [
            {"name": "RlsGrp", "implementation": "ReleaseGroupSpecification",
             "negate": False, "required": True,
             "fields": [{"name": "value", "value": "^({})$".format(groups_regex)}]},
            {"name": "WEBDL", "implementation": "SourceSpecification",
             "negate": False, "required": False,
             "fields": [{"name": "value", "value": 3}]},
            {"name": "WEBRIP", "implementation": "SourceSpecification",
             "negate": False, "required": False,
             "fields": [{"name": "value", "value": 4}]}
        ]
    }

web_tiers = [
    make_web_tier("WEB Tier 01", web_tier_01_groups),
    make_web_tier("WEB Tier 02", web_tier_02_groups),
    make_web_tier("WEB Tier 03", web_tier_03_groups),
    {
        "name": "WEB Scene",
        "includeCustomFormatWhenRenaming": False,
        "specifications": [
            {"name": "DEFLATE", "implementation": "ReleaseGroupSpecification",
             "negate": False, "required": False,
             "fields": [{"name": "value", "value": "^(DEFLATE)$"}]},
            {"name": "INFLATE", "implementation": "ReleaseGroupSpecification",
             "negate": False, "required": False,
             "fields": [{"name": "value", "value": "^(INFLATE)$"}]}
        ]
    }
]

# SDR (no WEBDL) custom format
sdr_no_webdl = {
    "name": "SDR (no WEBDL)",
    "includeCustomFormatWhenRenaming": False,
    "specifications": [
        {"name": "2160p", "implementation": "ResolutionSpecification",
         "negate": False, "required": True,
         "fields": [{"name": "value", "value": 2160}]},
        {"name": "HDR Formats", "implementation": "ReleaseTitleSpecification",
         "negate": True, "required": False,
         "fields": [{"name": "value", "value": r"\bHDR(\b|\d)|\b(dv|dovi|dolby[ .]?v(ision)?)\b|\b(FraMeSToR|HQMUX|SICFoI)\b|\b(PQ)\b|\bHLG(\b|\d)"}]},
        {"name": "SDR", "implementation": "ReleaseTitleSpecification",
         "negate": False, "required": False,
         "fields": [{"name": "value", "value": r"\bSDR\b"}]},
        {"name": "Not WEBDL", "implementation": "SourceSpecification",
         "negate": True, "required": True,
         "fields": [{"name": "value", "value": 3}]},
        {"name": "Not WEBRip", "implementation": "SourceSpecification",
         "negate": True, "required": True,
         "fields": [{"name": "value", "value": 4}]}
    ]
}

all_cfs = streaming_cfs + web_tiers + [sdr_no_webdl]

# ============================================================
# 1. ADD CUSTOM FORMATS TO BOTH SONARR AND RADARR
# ============================================================
for service, port, key in [("SONARR", 8989, SONARR_KEY), ("RADARR", 7878, RADARR_KEY)]:
    print("=== ADDING CFs TO {} ===".format(service))
    for cf in all_cfs:
        try:
            result = api_post(port, "customformat", key, cf)
            print("  OK: {} (id={})".format(result["name"], result["id"]))
        except Exception as e:
            body = e.read().decode()[:200] if hasattr(e, "read") else str(e)
            print("  FAIL {}: {}".format(cf["name"], body))

# ============================================================
# 2. UPDATE QUALITY PROFILES WITH NEW CF SCORES
# ============================================================
print("\n=== UPDATING QUALITY PROFILE SCORES ===")
scores = {}
for name in ["AMZN", "ATVP", "NF", "DSNP", "HBO", "MAX", "HULU", "PCOK",
             "iT", "CC", "DCU", "HMAX", "PMTP", "SHO", "STAN", "SYFY"]:
    scores[name] = 75
scores["WEB Tier 01"] = 1700
scores["WEB Tier 02"] = 1650
scores["WEB Tier 03"] = 1600
scores["WEB Scene"] = 1600
scores["SDR (no WEBDL)"] = -10000

for service, port, key in [("SONARR", 8989, SONARR_KEY), ("RADARR", 7878, RADARR_KEY)]:
    profiles = api_get(port, "qualityprofile", key)
    profile = [p for p in profiles if p["name"] == "WEB-2160p"][0]
    pid = profile["id"]

    all_cf = api_get(port, "customformat", key)
    cf_map = {c["name"]: c["id"] for c in all_cf}

    for fi in profile.get("formatItems", []):
        if fi.get("name", "") in scores:
            fi["score"] = scores[fi["name"]]

    existing_names = {fi["name"] for fi in profile.get("formatItems", [])}
    for name, score in scores.items():
        if name not in existing_names and name in cf_map:
            profile["formatItems"].append({
                "format": cf_map[name],
                "name": name,
                "score": score
            })

    try:
        result = api_put(port, "qualityprofile/{}".format(pid), key, profile)
        print("  {} WEB-2160p profile updated with CF scores".format(service))
    except Exception as e:
        body = e.read().decode()[:300] if hasattr(e, "read") else str(e)
        print("  FAIL {} profile: {}".format(service, body))

# ============================================================
# 3. UPDATE QUALITY DEFINITIONS (unlimited max/preferred)
# ============================================================
print("\n=== UPDATING QUALITY DEFINITIONS ===")
for service, port, key in [("SONARR", 8989, SONARR_KEY), ("RADARR", 7878, RADARR_KEY)]:
    qds = api_get(port, "qualitydefinition", key)
    changed = 0
    for qd in qds:
        title = qd["title"]
        if any(x in title for x in ["720p", "1080p", "2160p", "Remux"]):
            needs_update = False
            if qd.get("maxSize") is not None:
                qd["maxSize"] = None
                needs_update = True
            if qd.get("preferredSize") is not None:
                qd["preferredSize"] = None
                needs_update = True
            if needs_update:
                changed += 1

    try:
        result = api_put(port, "qualitydefinition/update", key, qds)
        print("  {} quality definitions updated ({} changed to unlimited)".format(service, changed))
    except Exception as e:
        body = e.read().decode()[:300] if hasattr(e, "read") else str(e)
        print("  FAIL {} quality defs: {}".format(service, body))

# ============================================================
# 4. DISABLE PLEX RELAY AND SCHEDULED SCAN
# ============================================================
print("\n=== UPDATING PLEX PREFERENCES ===")
plex_prefs = "/var/lib/docker/volumes/plex-server_plex-config/_data/Library/Application Support/Plex Media Server/Preferences.xml"
try:
    tree = ET.parse(plex_prefs)
    root = tree.getroot()
    root.set("RelayEnabled", "0")
    root.set("ScheduledLibraryUpdatesEnabled", "0")
    tree.write(plex_prefs, xml_declaration=True, encoding="utf-8")
    print("  RelayEnabled set to 0")
    print("  ScheduledLibraryUpdatesEnabled set to 0")
except Exception as e:
    print("  FAIL Plex prefs: {}".format(e))

print("\nALL DONE - Plex restart needed for Plex changes to take effect")
