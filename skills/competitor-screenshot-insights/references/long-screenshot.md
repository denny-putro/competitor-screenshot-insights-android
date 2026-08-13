# Native iOS Long Screenshots

Use this procedure when the user requests a full-page or long screenshot, or proactively when continuous multi-screen evidence adds material value to the task. Agent Device's native `--full` support is for web content, so capture overlapping physical-device frames and stitch them deterministically.

## Decide

Use the mode selected by `capture-modes.md`. Fast is the default and tolerates readable seam artifacts; verified is opt-in.

Prefer a long screenshot for bounded detail pages, reviews, search results, settings, checkout flows, terms, or research evidence that loses meaning when split across isolated frames. Also use it when the final report benefits from showing continuous vertical context. Prefer the long screenshot despite small readable seam artifacts; key viewport screenshots are the fallback after a non-negotiable long-screenshot failure.

Keep a normal viewport screenshot when one screen contains the relevant state or the task only needs a specific control or confirmation. An unbounded or dynamic feed may still use an extent-limited long screenshot when several consecutive results form useful evidence; do not describe it as complete coverage. Do not collect additional sensitive content merely to make an image longer.

## Limit capture extent

Use the approved plan's extent:

- `auto` is the default: target about four viewport-equivalents and never exceed six;
- when a bounded semantic page is no more than six viewport-equivalents, capture it to the natural bottom;
- when a bounded page is longer than six viewport-equivalents, capture about four;
- when height is virtualized or unknown, capture about four and stop without an extra semantic boundary search;
- use a positive viewport count or `full` only when the user explicitly approved it.

Calculate viewport-equivalents from final output height divided by the initial device screenshot height. This is independent of swipe count and automatically accounts for overlap. The soft target may be exceeded by one accepted overlapping segment, but the auto hard maximum remains six viewports.

Do not silently claim full-page coverage when a limit stops capture. Report `page_complete: false` and the applicable `soft_viewport_limit_reached`, `hard_viewport_limit_reached`, or `user_approved_limit_reached` stop reason. A visual no-progress end or a known bounded bottom may report `page_complete: true`.

Choose the capture path before scrolling:

- Prefer the recording-assisted fast path for a bounded page that spans several viewports, scrolls mainly in one vertical container, and does not require lossless source pixels. A local countdown, GIF, mascot, banner, folding header, or bottom action does not disqualify it. Read `video-long-screenshot.md` completely before using it.
- Prefer the still-frame path for short pages, pixel-critical text or design inspection, secure/blanked recording surfaces, active video or animation, complex nested scrolling, or a virtualized list whose semantic tree exposes no reliable total height.
- Treat recording as an optimization, not a requirement. Fall back to still frames as soon as recording quality, page continuity, or bottom detection becomes unreliable; do not force a hybrid result with questionable video frames.

In fast mode, `scripts/capture-long-fast.sh` makes this capability decision from structural and height evidence. It also applies the approved extent without taking another semantic snapshot. If the semantic snapshot times out, contains no nodes, or returns a `0×0` root, it records that reason and switches to a generic coordinate plan for the configured device rather than an app/page profile. Its adaptive still path uses a conservative vertical gesture, preserves overlap, accepts only visually verified vertical progress, stops at the approved progress target, and otherwise requires two successive no-progress probes when semantics cannot prove the bottom. Use the manual still procedure below only for diagnosis or a targeted fallback.

Default vertical gestures begin at the horizontal center shared by the app viewport and the selected scroll container, outside the iOS edge-gesture zones. For recording-assisted capture, an accepted positive scroll followed by both a no-progress extracted position and a no-progress bottom screenshot may establish the actual bottom when the semantic height estimate is too large.

## Capture still frames

1. Move the target native page to its top and create a task-specific segment directory. Take one semantic snapshot only when the page/container is uncertain or terminal/bottom signals are needed; screenshots remain the routine observation.
2. Capture and lightly inspect the initial frame, then accept it as `segment-000.png`. Add the two-second stability wait only in verified mode or when the whole page is visibly transitioning/loading.
3. Scroll the main vertical container by roughly 60–70% of its visible content height, leaving 30–40% overlap. Scale the gesture to the current viewport and adjust when the app has large fixed bars.
4. After each routine scroll, wait only until the scrolling body has settled enough to capture; do not wait for unrelated animated regions. Capture to a provisional path outside the final `segment-*.png` glob, such as `probe-001.png`. Treat the screenshot as the primary post-scroll observation; do not immediately request a full semantic snapshot.
5. Inspect the probe immediately and compare its scrollable body with the last accepted segment. Ignore fixed status/navigation/tab/reservation bars, clocks, animated media, and other non-scrolling changes when deciding whether the body contains new vertical content.
6. Run `scripts/validate-probe.sh --mode <fast|verified>` with the last accepted segment, the probe, and the applicable fixed-chrome crops. Promote the probe on exit `0`, including fast warnings, after confirming the correct page/container. Exclude exit `10` probes; inspect or recapture exit `11` probes.
7. Take a fresh full semantic snapshot only when the scroll target or page state is ambiguous, a probe shows no progress, visual content suggests the page is near its end, or bottom confirmation is required. Do not snapshot after every accepted segment.
8. Stop without capturing another formal segment when semantic and visual evidence agree that the end is reached:
   - semantics show no content below, the scroll position is at the end, or a known terminal element is present; and
   - the latest accepted frame visibly contains that terminal region, or a settled probe adds no new scrollable-body content.
9. If semantic and visual evidence disagree, wait for lazy loading once and retry the probe or snapshot. If semantics are unavailable or degraded, require two successive settled probes with no new scrollable-body content, exclude both probes from stitching, and report that the stop used the visual fallback.

Avoid nested maps, carousels, sheets, and horizontally scrolling elements. If a scroll targets the wrong container, recover the page position before capturing the next segment.

## Stitch

Source `scripts/agent-device-env.sh`, then run:

```bash
scripts/stitch-long-screenshot.sh \
  --profile generic \
  -o /absolute/path/detail-full.png \
  /absolute/path/segments/segment-*.png
```

Preserve capture order; never sort by image content. The wrapper rejects different input dimensions and near-black frames, then writes:

- the stitched PNG;
- `<output>.stitch.log` with pair-level matching diagnostics;
- `<output>.stitch.json` with dimensions, warnings, and low-confidence pair numbers.

Profiles:

| Profile | Top crop | Bottom crop | Use |
|---|---:|---:|---|
| `generic` | CLI default | CLI default | Unknown native apps; tune after the first result |
| `airbnb` | 240 px | 492 px | Airbnb on the configured 1170×2532-pixel iPhone; verified 2026-07-15 |

Override a profile with `--top-crop`, `--bottom-crop`, or `--x-margin` when fixed UI differs.

After stitching, run `scripts/qa-stitched-output.sh --mode <fast|verified>` with the stitched PNG and its `.stitch.json` report. Do not deliver an exit `10` result. In fast mode, exit-`0` warnings do not trigger repair; in verified mode, resolve every exit `11` reason.

## Interpret diagnostics

- `mode=matched` with confidence at or above 0.5 is a strong automatic overlap.
- In fast mode, `mode=fallback`, lower confidence, or `STITCH_QA_REQUIRED=yes` is a warning when the overall image remains readable and ordered.
- In verified mode, inspect every fallback or flagged pair and accept it only when the seam is visually correct.

## Verify

In fast mode, open the final PNG once and glance at its top, bottom, overall order, and any obvious black or grossly missing block. Repeated headers, changing animated content, folded navigation, bottom bars, small duplicated regions, and minor text discontinuities are acceptable warnings when the image is readable. Make at most one targeted retry and stop perfection work around 90 seconds.

In verified mode, inspect the top, middle, bottom, and every flagged pair. Reject repeated headers or reservation bars, missing sections, black blocks, reversed ordering, text discontinuities, and accidental nested-scroll content.

If automatic overlap remains incorrect after one tuned retry, use deterministic per-segment pixel crops and vertical stacking. Never use generative image editing, OCR reconstruction, or content-aware filling for a product screenshot.
