# Automated Screenshot Checks

Use these deterministic checks to reject bad inputs early. Source `scripts/agent-device-env.sh` indirectly through the shell entrypoints; each command emits JSON.

Exit codes are shared:

| Code | Decision | Required response |
|---:|---|---|
| `0` | `accept` or `accept_with_warnings` | Continue and preserve the mode-appropriate final glance. |
| `10` | `reject` | Do not use the target, frame, or stitched output. Follow `suggested_action`. |
| `11` | `review` | Inspect or recapture before continuing. Never treat review as acceptance. |
| `2` | `error` | Fix the command, dependency, or input artifact. |

## Run the unified fast long-screenshot pipeline

Use this entrypoint for a compatible fast recording-assisted capture after the target-app visual gate has passed and the intended scroll container is at the top:

```bash
scripts/capture-long-fast.sh \
  --expected-bundle com.example.app \
  --before-screenshot /absolute/path/target-before.png \
  --work-dir /absolute/path/detail-full.fast-run \
  --output /absolute/path/detail-full.png
```

The default capture extent is `auto`: about four viewport-equivalents, with six as the hard maximum. A known complete page of at most six viewports may continue to its natural bottom. Pass `--capture-extent 8` for a user-approved eight-viewport target or `--capture-extent full` for explicitly approved complete-page coverage. Do not use either override unless it appeared in the confirmed capture plan.

The work directory must be new or empty so frames from an earlier run cannot enter the sequence. The script takes one semantic snapshot locally to derive the main scroll container, height confidence, crop geometry, scroll distance, gesture point, and capture extent. A bounded height uses the recording-assisted path. A virtualized or unknown height uses one continuous adaptive still loop: perform a conservative vertical gesture, capture and validate each provisional frame, promote only visual progress, stop at the approved extent or after two successive no-progress frames, then stitch and run fast QA. If the semantic snapshot times out, contains no nodes, or returns a `0×0` root, the script records the trigger in `semantic_fallback` and may build a page-agnostic plan from the explicitly configured device coordinate viewport. When no viewport dimensions are configured, coordinate fallback fails safely instead of guessing another device's geometry. This fallback does not infer an app/page profile; it rejects a mismatched screenshot aspect ratio and still requires target continuity, positive visual vertical progress for every accepted frame, and final fast QA. A valid semantic tree with no confidently identifiable main vertical container does not trigger coordinate fallback. The script writes strategy, extent, completeness, stop reason, per-stage timings, per-frame decisions, and QA to `run.json`.

Container and height inference are evidence-weighted. Classify a media-labelled `CollectionView` from its direct-cell structure: a media-only collection is ineligible as the page container; a media-led detail collection remains eligible when multiple vertically separated cells expose readable business content; conflicting evidence becomes `ambiguous_media_container`. Ambiguous selections are written to `geometry.container_role_warning` and use adaptive viewport evidence even when a scrollbar suggests a bounded height. A `CollectionView` is otherwise eligible only when it is substantially full-screen and has vertically distributed direct cells, vertical-scrollbar evidence, or a structural list/container identifier. When the semantic tree exposes no usable scrollbar thumb and only a shallow descendant extent, an accessibility scrollbar label such as `8页` or `8 pages` is a bounded content-height fallback. Otherwise the height remains unknown and routes to adaptive still capture. Inspect `geometry.scroll_candidates`, `geometry.container_role`, `height_estimates`, `height_confidence`, and `capture_strategy` in `run.json` when planning looks suspicious.

A recognized dynamic gallery near the top changes only the crop used for the pre-/post-snapshot target-continuity comparison. It is not removed from the initial segment, extracted frames, stitch inputs, or delivered image. For other dynamic lists, an exact expected bundle plus stable app chrome may accept plausible body churn with a warning; a bundle mismatch or changed chrome remains a hard reject. After the pipeline intentionally scrolls, endpoint recovery requires the exact bundle and stable chrome rather than body similarity. This prevents changing list content from being mistaken for an app replacement without weakening the wrong-app gate.

The caller still owns the hard pre-semantic target gate: a session-sourced bundle that disagrees with the visible screenshot must be rebound and verified before invoking this script. Exit `0` permits one final visual glance. Read `capture_extent`, `captured_viewports`, `page_complete`, and `stop_reason` before describing the result. Exit `10` means the sequence or output failed a non-negotiable check; exit `2` means the invocation or environment is invalid. Use the run report for one targeted fallback instead of rerunning the entire flow without a diagnosis.

## Plan the scroll count

At the verified top of a bounded page, calculate the planned gesture count deterministically:

```bash
scripts/plan-scroll-count.sh \
  --content-height 4075 \
  --visible-height 844 \
  --scroll-distance 400 \
  --safety-gestures 1
```

The command emits the base `ceil((content_height - visible_height) / scroll_distance)`, then adds the requested safety gestures only when scrolling is needed. Fast recording capture normally uses one safety gesture; exclude it later if it produces no new content. Pass the scroll container's visible height rather than the full device height when fixed chrome reduces the usable viewport. Invalid or non-positive dimensions return exit `2`.

## Check a normal viewport

Fast mode uses a deliberately lightweight integrity check:

```bash
scripts/check-viewport.sh --image /absolute/path/current.png
```

It verifies only that the file decodes and is not near-black. Pair it with one quick visual glance for the correct page, lock screen, transition, or obstruction. It does not wait for global stability or inspect animation quality.

## Record a bounded scroll batch

After reading the accepted `scroll_count`, run `scripts/record-scroll-batch.sh` with that count and the chosen pan geometry. The wrapper owns the complete recording lifecycle and performs no duplicate final stop after the recorder reports state loss. If finalization fails, the unified pipeline may use the remaining runtime budget for one target-verified endpoint screenshot and return an ordered start/end evidence pack. It never retries the recording. Do not background it or inspect the screen concurrently.

Use `--dry-run` to validate the batch arguments without touching the device. A zero-count page should not be recorded; return a normal viewport screenshot instead.

## Check target-app consistency

This command never opens an app. It compares an optional expected bundle with `appstate` and can verify that a supposedly read-only observation did not replace the visible page.

For a named target app, capture the verified target before the first semantic snapshot, take the snapshot, capture again, then run:

```bash
scripts/check-target-app.sh \
  --expected-bundle com.example.app \
  --before-screenshot /absolute/path/target-before.png \
  --after-screenshot /absolute/path/target-after.png
```

For a current-screen request, omit `--expected-bundle` and use the two screenshots as visual continuity evidence.

The two screenshot paths must be distinct captures. A result with `state_source: "session"` is not independent proof of the physical foreground app; without visual continuity evidence the command returns `review`. If the screenshot visibly disagrees with a session-sourced bundle, do not take the first semantic snapshot. Rebind the session to the visually identified foreground bundle without relaunching, then run this check with that expected bundle and pre-/post-bind screenshots. The model must still determine the intended app from the user's request.

## Validate a provisional frame

Run this before renaming a probe to `segment-NNN.png`:

```bash
scripts/validate-probe.sh \
  --mode fast \
  --previous /absolute/path/segment-003.png \
  --probe /absolute/path/probe-004.png \
  --top-crop 240 \
  --bottom-crop 492 \
  --x-margin 40
```

Both modes reject near-black, duplicate/no-progress, and frames without a minimally usable overlap. Before overlap matching, fast mode uses combined whole-body pixel and perceptual similarity to reject near-identical frames; this prevents repeated cards or tiles from creating a false offset. `verified` returns `review` for insufficient or low-confidence overlap. `fast` accepts readable progress with a fallback or low-confidence overlap as `accept_with_warnings`; it does not require static banners or fixed chrome to match. Use crop values that exclude fixed chrome when practical.

For recording-assisted capture, apply this command to each dynamically selected video frame exactly as if it were a screenshot probe. In fast mode, do not keep searching a cluster after an exit `0` warning; reserve alternate candidates or recapture for exit `10`/`11`.

The unified fast pipeline delegates this loop to `scripts/select-scroll-segments.sh`. Base-gesture frames must pass fast probe validation. A safety-gesture frame is excluded without validation when base-frame offsets already cover the expected progress; otherwise it must additionally meet the stronger matched-overlap threshold before it can be numbered as a segment.

The default pan begins at the horizontal center shared by the app viewport and the selected scroll container, keeping it away from iOS edge gestures. During recording-assisted selection, a semantic height estimate may be overridden only after at least one positive accepted scroll and two visual terminal signals: a later extracted position has no progress and the final bottom screenshot also has no progress. A duplicate bottom screenshot alone is not enough when measured coverage remains below the estimate.

## QA a stitched output

Use the report produced by `stitch-long-screenshot.sh`:

```bash
scripts/qa-stitched-output.sh \
  --mode fast \
  --stitched /absolute/path/detail-full.png \
  --report /absolute/path/detail-full.png.stitch.json
```

In `verified` mode, the check rejects duplicate inputs, large repeated regions, and inconsistent height, and returns `review` for low-confidence seams. In `fast` mode, duplicate/repeated regions, modest height differences, missing reports, and low-confidence seams become exit-`0` warnings; near-black output and gross height inconsistency still fail.

For a deterministic manual stack without a stitch report, pass the ordered inputs and crop settings. The missing report normally forces `review`; use `--allow-missing-report` only when manual seam inspection is already mandatory:

```bash
scripts/qa-stitched-output.sh \
  --stitched /absolute/path/detail-full.png \
  --segments /absolute/path/segments/segment-*.png \
  --top-crop 240 \
  --bottom-crop 492 \
  --x-margin 40 \
  --allow-missing-report
```

A fast accepted result needs one top/bottom/order/black-block glance. A verified result still requires top, middle, bottom, and flagged-seam inspection.
