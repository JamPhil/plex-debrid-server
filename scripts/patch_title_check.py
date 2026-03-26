"""Patch watchlist-sync.py to add title validation with logging."""
import re

with open("/opt/plex-server/scripts/watchlist-sync.py", "r") as f:
    content = f.read()

# Find the find_best_torrent function and check if title validation exists
if "expected_title" not in content:
    print("ERROR: expected_title not found in code")
    exit(1)

if "TITLE REJECT" in content:
    print("Already patched with logging")
    exit(0)

# Replace the title check block to add logging
old = '                    continue  # Skip mismatched result'
new = '''                    log(f"TITLE REJECT: {parsed.get('title','')[:50]} (match {matches}/{len(expected_words)})")
                    continue  # Skip mismatched result'''

content = content.replace(old, new, 1)

with open("/opt/plex-server/scripts/watchlist-sync.py", "w") as f:
    f.write(content)
print("Patch applied with logging")
