# Capture Modes

Use `fast` by default. Screenshot tasks favor a promptly usable artifact over seam perfection.

Use `verified` only when the user explicitly asks for high quality, seamless stitching, exact comparison, pixel fidelity, or an artifact intended for a formal report. A failed fast attempt does not silently escalate into an unlimited verified repair loop.

## Capture extent

For an approved long screenshot, `auto` is the default extent:

- four delivered viewport-equivalents is the soft target;
- six delivered viewport-equivalents is the hard maximum;
- a known bounded page whose complete estimated height is at most six viewports may continue to its natural bottom;
- a known page longer than six viewports and a virtualized or unknown-height page target about four viewports;
- a positive user-approved viewport count or `full` coverage overrides `auto`.

A viewport-equivalent is based on the delivered image height relative to the initial device screenshot, not on the number of swipe gestures. An automatic result may pass the four-viewport soft target by the height of its last useful overlapping segment, but it must remain within the six-viewport hard maximum. Do not add a semantic snapshot, look-ahead gesture, or repair loop merely to find a prettier boundary at the soft target.

An extent-limited long screenshot is not a complete-page screenshot. Preserve `capture_extent`, `captured_viewports`, `page_complete`, and `stop_reason` from `run.json` in the completion report. Use key viewport screenshots only after a non-negotiable long-screenshot failure, or when the approved plan explicitly asks for them.

## Fast mode

Non-negotiable checks:

- the requested or actual foreground app is the target before semantic observation;
- every delivered image decodes and is not near-black;
- long-screenshot frames remain in chronological top-to-bottom order and show meaningful vertical progress;
- the final long image has no gross missing area or gross height inconsistency.

Accept with a warning when the image remains readable but contains a repeated fixed header, changing banner, countdown, GIF frame, folded navigation state, bottom action bar, low-confidence seam, or a small duplicated region. Do not build animation masks or repeatedly tune seams for these soft artifacts in fast mode.

For a normal viewport, capture once after the target is ready, run `scripts/check-viewport.sh`, and make one quick visual glance for the correct page, lock screen, transition, or obstruction. Retry once only on a hard failure. Do not take a semantic snapshot solely to validate a normal screenshot.

For a long screenshot, use `scripts/capture-long-fast.sh` after the foreground-app gate and top-position check. It applies the approved capture extent, records a bounded batch when semantic height is reliable, and reports whether the result reaches the page bottom. When a virtualized list exposes no reliable total height, it instead runs a continuous still loop with a conservative overlap, provisional-frame validation, extent termination or two-frame no-progress termination, stitching, and fast QA. Perform one final top/bottom/order/black-block glance. Make at most one targeted retry.

Safety gestures are diagnostic. Exclude their frames when the base sequence already covers the expected scroll progress. If coverage is short, accept a safety frame only when it has a strong matched overlap with the last accepted frame. The pipeline may automatically remove one trailing safety frame and restitch once when QA identifies a duplicate/repeated-tail problem; it does not enter an open-ended repair loop.

Treat 5–15 seconds for a viewport and 30–60 seconds for a straightforward long screenshot as operating targets, not hard-coded waits. Stop repair work around 90 seconds and deliver the readable result with a concise warning unless a non-negotiable check failed.

## Verified mode

Use the stricter probe and stitched-output defaults, inspect every flagged seam, and recapture weak positions. Preserve the existing two-second settle-and-retry behavior when animation or loading could affect fidelity. Reject repeated chrome, text discontinuities, or other material stitching defects instead of downgrading them to warnings.
