# System Diagnostic Prompt

You are diagnosing the health of a Plex + Real-Debrid streaming server. Your goal is to determine what is working, what is broken, and what is unknown — then recommend next steps.

## Your source of truth

The file `docs/SYSTEM-HEALTH.md` defines what "healthy" means for this system. It contains 11 numbered components, each with specific "Healthy means" criteria and "Connections to verify" between components.

Before doing anything else, read `docs/SYSTEM-HEALTH.md` in full. Every check you perform must trace back to a specific criterion in that document.

## Rules you must follow

### Completeness

1. **Do not skip components.** There are 11 components in `SYSTEM-HEALTH.md`. You must check all 11. Before presenting findings, count the components you checked and confirm the count is 11.

2. **Check every criterion, not just some.** For each component, verify every bullet under "Healthy means" AND every bullet under "Connections to verify." If a criterion cannot be checked remotely (e.g., "content is playable on Roku"), note it as "cannot verify remotely" rather than silently skipping it.

3. **Gather all facts before interpreting any of them.** Complete all 11 component checks first. Only after all data is collected should you categorize findings or draw conclusions.

### Classification

4. **Categorize findings into exactly three buckets:**
   - **Confirmed working**: You checked it, and the evidence shows it meets the health definition.
   - **Confirmed broken**: You checked it, and the evidence shows it does NOT meet a specific criterion. State which criterion failed and what the evidence is.
   - **Unknown**: You either could not check it, or the result was ambiguous. State what you don't know and what additional check would resolve it.

5. **Do not put anything in "confirmed broken" without citing the specific health criterion that failed and the specific evidence.** "It looks wrong" is not evidence.

6. **Do not put anything in "confirmed working" unless you actually verified it.** If you saw the container was running but didn't check its connections, it is "unknown," not "confirmed working."

7. **Do not interpret unknowns.** An unknown is not a problem and not a non-problem. It is an unknown. Say what you would need to check to resolve it.

### Verification and cross-referencing

These rules exist because single data points are unreliable. An error log might say a download failed, but the content might already be in Plex from a different source. A metric might say "failures = 5" but those failures might have been retried and succeeded. You must cross-reference before concluding anything is broken.

8. **Never treat a single data source as proof of a problem.** A log entry, a metric value, a queue status, or an API response is one data point. Before classifying something as broken, corroborate it with at least one other independent source. Examples:
   - Blackhole logs say an episode failed → check whether that episode is actually in Sonarr's library AND on disk AND in Plex before calling it broken.
   - A Grafana alert is firing → check the underlying metric, then check whether the condition it's alerting on is actually causing a user-facing problem.
   - Sonarr history shows `downloadFailed` → check whether a subsequent grab succeeded, whether the episode is now on disk, and whether Plex has it.

9. **Trace errors to their actual impact.** The question is not "did an error occur?" but "is content missing from Plex that should be there?" Work backwards from the user-facing outcome:
   - Is the content in Plex? If yes, any upstream errors for that content are resolved — not broken.
   - Is the content NOT in Plex? Then trace forward through the pipeline to find where it's stuck: Is it in Sonarr? Was it grabbed? Did blackhole process it? Is it on the mount? Is the symlink valid?

10. **Distinguish between active problems and historical noise.** Logs accumulate errors over time. A failure from 6 hours ago that was retried and succeeded 5 hours ago is not a current problem. When checking logs, always check whether the error state persists NOW, not just whether an error occurred at some point.

11. **For any item you are about to classify as "confirmed broken," ask yourself these questions before finalizing:**
    - Have I checked the downstream system to see if this actually matters? (e.g., is the content in Plex despite the error?)
    - Have I checked whether this was a transient issue that resolved itself?
    - Am I looking at one data source, or have I cross-referenced with at least one other?
    - Could there be a simpler explanation I haven't checked?
    If the answer to any of these is "no," reclassify the item as "unknown" and state what additional check is needed.

## Diagnostic procedure

Execute these phases in order.

### Phase 1: Data collection

Check each component against its health definition. Run checks in parallel where the components are independent, but ensure you cover all 11:

1. **Plex** — container, library sections, library item counts vs files on disk, auto-scan settings, connections to Seerr and Tautulli
2. **Zurg + rclone** — containers, mount listable, mount readable (stat a file, not just ls), Zurg RD token validity, rclone WebDAV connection
3. **Blackhole** — container, recent completions vs failures, error patterns, symlink validity, grab/fail loops
4. **Sonarr** — container, quality profile settings, download client settings, monitorNewItems, queue, recent history (grabs vs imports vs failures), episode counts vs disk
5. **Radarr** — same as Sonarr but for movies
6. **Prowlarr** — container, indexer status, indexer sync to Sonarr and Radarr, test search for known content
7. **Seerr** — container, Sonarr/Radarr profile config, Plex connection, watchlist sync status, user permissions
8. **Doplarr** — container, Discord connection status, Seerr connection status
9. **Tautulli** — container, Plex connection status, Discord webhook config
10. **Monitoring stack** — all 4 containers, Prometheus scrape targets, Grafana alert states (for any firing alert: verify the underlying metric), contact points
11. **Autoheal** — container, Docker socket access

### Phase 1b: Cross-reference check

After collecting data from all 11 components, perform these cross-reference checks before moving to Phase 2. These catch cases where one system reports an error but another system shows the issue is resolved.

- **For any content that blackhole logs show as "Failed"**: Check whether that specific content (show/episode/movie) exists in Sonarr/Radarr as downloaded, exists as a file on disk, and exists in the Plex library. If all three say yes, the failure was transient and is not a current problem.
- **For any Grafana alert that is "firing"**: Check the raw metric value, then check whether the condition the alert describes is actually causing missing content or a user-facing issue right now.
- **For any Sonarr/Radarr history showing "downloadFailed"**: Check whether a later grab for the same content succeeded, and whether the content is now on disk.
- **Compare library counts across systems**: Sonarr episode file count vs files on disk vs Plex library item count. Mismatches between any pair indicate a real problem. Agreement across all three indicates health even if logs show historical errors.

### Phase 2: Completeness verification

Before moving on:
- List all 11 component names.
- Next to each, write how many "Healthy means" criteria you checked vs how many exist in `SYSTEM-HEALTH.md`.
- Next to each, write how many "Connections to verify" you checked vs how many exist.
- If any counts don't match, go back and check what you missed.

### Phase 3: Compile findings

Organize results into the three buckets: confirmed working, confirmed broken, unknown. Follow the rules above strictly.

### Phase 4: Analysis and recommendations

Only after Phase 3 is complete:

- For each **confirmed broken** item: propose possible root causes. There must be more than one unless the evidence conclusively rules out alternatives. State what evidence supports or contradicts each cause.
- For each **unknown** item: state the specific check that would resolve it.
- Present **multiple options** for next steps, including the option that nothing needs to change.
- State your **recommendation** with reasoning. Cite the evidence that supports it.

## Output format

Present your findings in this structure:

```
## Completeness Check
[11 components listed with criteria counts]

## Confirmed Working
[Component — criteria met — evidence summary]

## Confirmed Broken
[Component — specific criterion that failed — evidence — possible causes]

## Unknown
[Component — what you couldn't determine — what check would resolve it]

## Recommendations
[Options with tradeoffs, then your recommendation with reasoning]
```
