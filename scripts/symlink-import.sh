#!/bin/bash
# =============================================================================
# Symlink Import Script
# =============================================================================
# Monitors blackhole's completed directories and creates proper symlinks
# in the Plex library folders. This bridges the gap between blackhole
# (which adds content to RD and creates symlinks in /mnt/symlinks/*/completed/)
# and Plex (which reads from /mnt/plex/Movies/ and /mnt/plex/TV/).
#
# Also notifies Radarr/Sonarr to rescan so they track the files.
#
# Runs as a cron job every 2 minutes.
# =============================================================================

set -euo pipefail

LOG_PREFIX="[symlink-import]"
RADARR_COMPLETED="/mnt/symlinks/radarr/completed"
SONARR_COMPLETED="/mnt/symlinks/sonarr/completed"
PLEX_MOVIES="/mnt/plex/Movies"
PLEX_TV="/mnt/plex/TV"
ZURG_ALL="/mnt/zurg/__all__"

RADARR_API_KEY="${RADARR_API_KEY:-}"
SONARR_API_KEY="${SONARR_API_KEY:-}"
RADARR_HOST="http://localhost:7878"
SONARR_HOST="http://localhost:8989"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $LOG_PREFIX $1"
}

# Process completed radarr downloads
process_radarr() {
    if [ ! -d "$RADARR_COMPLETED" ]; then
        return
    fi

    for dir in "$RADARR_COMPLETED"/*/; do
        [ -d "$dir" ] || continue
        dirname=$(basename "$dir")

        # Skip if already processed (marker file exists)
        if [ -f "$dir/.imported" ]; then
            continue
        fi

        log "Processing movie: $dirname"

        # Find the main video file (largest file)
        main_file=$(find "$dir" -type l -o -type f | head -1)
        if [ -z "$main_file" ]; then
            log "  No files found in $dirname, skipping"
            continue
        fi

        # Get the actual target of the symlink
        if [ -L "$main_file" ]; then
            target=$(readlink -f "$main_file")
        else
            target="$main_file"
        fi

        if [ ! -f "$target" ]; then
            log "  Target file not accessible: $target"
            continue
        fi

        filename=$(basename "$main_file")

        # Create movie folder in Plex library
        # Try to extract a clean movie name from the filename
        movie_dir="$PLEX_MOVIES/$dirname"
        mkdir -p "$movie_dir"
        chown 1000:1000 "$movie_dir"

        # Create symlink to the actual file on Zurg
        if [ ! -L "$movie_dir/$filename" ] && [ ! -f "$movie_dir/$filename" ]; then
            ln -sf "$target" "$movie_dir/$filename"
            chown -h 1000:1000 "$movie_dir/$filename"
            log "  Created symlink: $movie_dir/$filename -> $target"
        fi

        # Mark as imported
        touch "$dir/.imported"

        # Notify Radarr to rescan
        if [ -n "$RADARR_API_KEY" ]; then
            curl -sf -X POST "$RADARR_HOST/api/v3/command" \
                -H "X-Api-Key: $RADARR_API_KEY" \
                -H "Content-Type: application/json" \
                -d '{"name": "RefreshMovie"}' > /dev/null 2>&1 || true
            log "  Notified Radarr to rescan"
        fi
    done
}

# Process completed sonarr downloads
process_sonarr() {
    if [ ! -d "$SONARR_COMPLETED" ]; then
        return
    fi

    for dir in "$SONARR_COMPLETED"/*/; do
        [ -d "$dir" ] || continue
        dirname=$(basename "$dir")

        # Skip if already processed
        if [ -f "$dir/.imported" ]; then
            continue
        fi

        log "Processing show: $dirname"

        # Find all video files (episodes)
        found_files=0
        while IFS= read -r file; do
            [ -n "$file" ] || continue
            found_files=1

            if [ -L "$file" ]; then
                target=$(readlink -f "$file")
            else
                target="$file"
            fi

            if [ ! -f "$target" ]; then
                log "  Target not accessible: $target"
                continue
            fi

            filename=$(basename "$file")

            # Create show folder in Plex library
            show_dir="$PLEX_TV/$dirname"
            mkdir -p "$show_dir"
            chown 1000:1000 "$show_dir"

            if [ ! -L "$show_dir/$filename" ] && [ ! -f "$show_dir/$filename" ]; then
                ln -sf "$target" "$show_dir/$filename"
                chown -h 1000:1000 "$show_dir/$filename"
                log "  Created symlink: $show_dir/$filename"
            fi
        done < <(find "$dir" -type l -o -type f 2>/dev/null)

        if [ "$found_files" -eq 0 ]; then
            log "  No files found in $dirname, skipping"
            continue
        fi

        # Mark as imported
        touch "$dir/.imported"

        # Notify Sonarr to rescan
        if [ -n "$SONARR_API_KEY" ]; then
            curl -sf -X POST "$SONARR_HOST/api/v3/command" \
                -H "X-Api-Key: $SONARR_API_KEY" \
                -H "Content-Type: application/json" \
                -d '{"name": "RefreshSeries"}' > /dev/null 2>&1 || true
            log "  Notified Sonarr to rescan"
        fi
    done
}

# Also scan Zurg's organized directories and create symlinks for any new content
sync_zurg_to_plex() {
    # Sync movies from Zurg
    if [ -d "/mnt/zurg/movies" ]; then
        for item in /mnt/zurg/movies/*/; do
            [ -d "$item" ] || continue
            dirname=$(basename "$item")
            target_dir="$PLEX_MOVIES/$dirname"

            if [ ! -d "$target_dir" ]; then
                mkdir -p "$target_dir"
                # Symlink all video files
                find "$item" -maxdepth 1 \( -name "*.mkv" -o -name "*.mp4" -o -name "*.avi" -o -name "*.m4v" \) -print0 2>/dev/null | while IFS= read -r -d '' vfile; do
                    fname=$(basename "$vfile")
                    [ -L "$target_dir/$fname" ] || ln -sf "$vfile" "$target_dir/$fname"
                done
            fi
        done
    fi
}

# Main
log "Starting import scan..."
process_radarr
process_sonarr
log "Import scan complete"
