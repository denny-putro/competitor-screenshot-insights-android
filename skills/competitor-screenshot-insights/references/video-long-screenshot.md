# Recording-Assisted Native iOS Long Screenshots

Use this fast path only after `long-screenshot.md` selects it. Record controlled vertical scrolling, discover stable video intervals from the actual media timeline, extract one verified frame per settled page position, and pass those frames through the same probe, stitch, and QA checks as still screenshots.

## Preferred fast entrypoint

After the foreground-app visual gate has passed and the intended container is at the top, run the continuous pipeline:

```bash
scripts/capture-long-fast.sh \
  --expected-bundle com.example.app \
  --before-screenshot /absolute/path/target-before.png \
  --work-dir /absolute/path/detail-full.fast-run \
  --output /absolute/path/detail-full.png
```

Use a fresh work directory. When semantic height is bounded, the script owns the sequence from one local observation through bounded recording, confirmed stop, dynamic extraction, provisional-frame checks, safety-frame exclusion, stitching, and fast QA. When height is virtualized or unknown, the same entrypoint routes to adaptive still capture before recording begins. Do not issue screenshots, snapshots, or visual inspections while it runs. Its `run.json` contains strategy, per-stage timings, geometry, accepted/excluded frames, coverage or terminal evidence, QA, and any automatic repair.

The remaining sections describe the internal contract and the manual fallback. Do not manually repeat them after a successful unified run.

## Guardrails

- Verify the target app and move the intended container to the top before recording. Capture and inspect the normal initial screenshot. Take one semantic snapshot only when container discovery, height planning, or bottom evidence needs it.
- Use one vertical scroll container. Keyboards, maps, carousels, sheets, active video, or content blanked by the OS still favor still frames. A local countdown, GIF, mascot, banner, folding header, or bottom action is acceptable in fast mode.
- Treat nested galleries and auto-advancing media as dynamic regions for the target-continuity check, not as content to delete. Exclude a recognized top gallery from that one comparison crop while preserving it in the capture and stitch sequence.
- Use high-quality recording without touch overlays. Do not assume the requested FPS equals the encoded FPS; physical-device recordings may be variable-frame-rate or may emit relatively few frames while a gesture runs.
- Preserve the initial screenshot as a lossless fallback. Never use a black, loading, transitional, motion-blurred, wrong-page, or weak-overlap video frame.

## Record controlled positions

1. Create task-specific paths for the video, extracted candidates, and accepted `segment-NNN.png` files.
2. At the top of the page, use one semantic snapshot when needed to obtain the total scrollable content height and the container's visible height. Choose the planned per-gesture scroll distance, then calculate the number of gestures with `scripts/plan-scroll-count.sh`:

   ```bash
   scripts/plan-scroll-count.sh \
     --content-height 4075 \
     --visible-height 844 \
     --scroll-distance 400 \
     --safety-gestures 1
   ```

   The script computes the ceiling-based base count after clamping negative remaining distance to zero. Fast mode adds one safety gesture; a duplicate result is expected at the bottom and must be excluded rather than treated as a task failure. Use the container's visible height, not the whole screen height, when fixed chrome reduces the viewport.
3. Finish all setup and verification before recording. Run the planned gestures as one bounded recording batch:

   ```bash
   scripts/record-scroll-batch.sh \
     --output /absolute/path/scroll.mp4 \
     --count 9 \
     --x 195 --y 650 --dx 0 --dy -400 \
     --duration-ms 800 --pause-seconds 0.7
   ```

   The wrapper starts high-quality recording without touch overlays, performs exactly `--count` gestures, and stops before returning. Its exit trap attempts `record stop` when a gesture or command fails.
4. Treat the interval inside the wrapper from `record start` through `record stop` as a critical section. Do not run the wrapper in the background. While it is active, execute no separate screenshot, semantic snapshot, decoder, QA, user-input wait, or visual inspection.
5. Scroll about 60–70% of the visible content height per gesture, preserving roughly 30–40% overlap. Use a controlled pan rather than a momentum-heavy fling. After each gesture, allow the scrolling body—not the whole screen—to settle. The wrapper also preserves a final post-gesture candidate window. Gesture telemetry and observed frames determine extraction; the configured cadence is not an extraction timestamp.
6. Let the wrapper stop recording immediately after the planned final gesture. Its cleanup owns at most one necessary stop. Do not repeat `record stop` after the result says the recorder is inactive or the Runner lost the recording state. In the unified pipeline, a finalization/state-loss failure uses the remaining budget to capture one target-verified endpoint and returns the ordered start/end viewport evidence pack; it does not retry recording. Never leave a recorder active across a visual inspection or tool boundary.
7. Only after `record stop` succeeds, verify that the MP4 exists, opens, has nonzero duration, and has the expected orientation and dimensions. Then capture or inspect the bottom screenshot and request a fresh semantic snapshot only if bottom confirmation is needed.
8. If semantic and visual bottom evidence do not yet agree, start a new short continuation recording after analysis; do not keep the previous recorder open. If semantics are unavailable or degraded, capture enough continuation positions to establish two successive no-progress comparisons after extraction, then exclude duplicate positions from stitching.

## Discover stable intervals dynamically

Never seek fixed times such as `1.5s`, assume constant FPS, or select a fixed frame number after each gesture. Run the bundled extractor after recording has stopped:

```bash
scripts/extract-scroll-frames.sh \
  --video /absolute/path/scroll.mp4 \
  --telemetry /absolute/path/scroll.gesture-telemetry.json \
  --output-dir /absolute/path/probes \
  --base-gesture-count 8 \
  --top-crop 240 --bottom-crop 492 --x-margin 40
```

It reads actual decoded presentation timestamps, builds each settled interval from gesture telemetry, derives a stability threshold from the observed neighbor differences, and selects a sharp interior non-black frame. It writes `extraction.json`; no fixed time or requested FPS determines the selected frames.

1. Decode frames with their presentation timestamps. Preserve media order.
2. Exclude fixed top/bottom chrome and side margins, then calculate visual change between adjacent body crops. Combine pixel or perceptual difference with timestamp gaps and optional gesture telemetry.
3. Group or score consecutive low-motion frames within the telemetry-derived candidate intervals. Let observed frame timestamps and visual stability determine the result; gesture timestamps only bound the search.
4. Reject clusters that are too brief to establish stability, overlap a transition, are near-black, show loading/obstruction, or disagree with neighboring frames. Derive sufficiency from the observed sampling density and repeated visual agreement rather than a fixed absolute timestamp.
5. Within each remaining cluster, score interior frames. Prefer high sharpness, low black-pixel ratio, strong agreement with nearby frames, correct page identity, and strong overlap with the last accepted segment. Avoid first/last boundary frames when an interior equivalent exists.
6. For the first position, prefer the verified lossless initial screenshot when its dimensions and crop geometry match the extracted frames. Otherwise use the best verified frame from the first stable cluster.

## Validate before accepting

Treat every selected video frame as a provisional probe:

1. Run `scripts/validate-probe.sh --mode <fast|verified>` against the last accepted segment with crops that exclude fixed chrome when practical.
2. Accept and number the frame on exit `0`, including fast warnings, after confirming the correct page/container. On exit `11`, recapture the position or use the still-frame fallback. On exit `10`, exclude it; a no-progress safety frame normally confirms the bottom.
3. In fast mode, do not tune around moving local elements or low-confidence-but-usable overlap. If no minimally usable frame exists, make one targeted still recapture when recoverable; otherwise use the still-frame fallback. Verified mode retains the stricter cluster search and seam requirements.
4. Stop adding frames as soon as semantic bottom evidence and the accepted visual sequence agree. Discard repeated terminal clusters and all no-progress probes.

In the unified fast path, base gestures and safety gestures have different roles. Base frames are the planned capture sequence. Safety frames are diagnostic and are excluded immediately when the sum of accepted pair offsets already covers the estimated `content_height - visible_height` within the bounded tolerance. When coverage is incomplete, a safety frame may enter the stitch only if probe validation reports a strong matched overlap; a merely readable fallback match is insufficient. If final QA still identifies a repeated tail and the sequence remains covered without the last accepted safety frame, the pipeline drops that frame and restitches once. No second automatic repair is allowed.

Semantic height can overestimate the real page. When at least one frame has established positive vertical progress, a later extracted no-progress position and an independently captured no-progress bottom screenshot together confirm the visual bottom even if measured coverage is below the semantic estimate. Do not apply this override when the initial frame never moved or when only the bottom screenshot is duplicate.

## Stitch and verify

Run `scripts/stitch-long-screenshot.sh` over accepted segments in chronological order, then run `scripts/qa-stitched-output.sh --mode <fast|verified>`. Follow the mode-specific rules in `long-screenshot.md` and `automated-checks.md`.

In fast mode, open the final image once for a top/bottom/order/black-block glance; animation discontinuities and minor seams are acceptable. In verified mode, inspect the middle and every flagged seam as well. Video compression may soften text, so use still frames when the user explicitly requires source-pixel fidelity.

## Performance interpretation

Measure capture, decode/selection, pair validation, stitch, and QA separately. Report recorded-media duration separately from command wall time. Do not promise the Trip.com test timing on another app: page length, rendering latency, recorder behavior, and recovery attempts dominate the result.
