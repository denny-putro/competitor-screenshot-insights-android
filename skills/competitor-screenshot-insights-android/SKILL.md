---
name: competitor-screenshot-insights-android
description: Operate and research an app on a connected physical Android device with Agent Device over adb, then return verified viewport screenshots, bounded long screenshots, or an ordered viewport evidence pack. Use when the user says “开启快速截屏” or an English fast-screenshot-mode equivalent; while that modal session is active for loose screenshot commands such as “截图”, “长截图”, “全截图”, or English equivalents; when a screenshot-only request needs the fast mode activated first; for directed Android journeys; and for open-ended app research or competitor evidence collection. This is the Android counterpart of `competitor-screenshot-insights`; prefer that skill when the target is an iPhone.
---

# Competitor Screenshot Insights (Android)

Use modal fast capture for screenshot-only commands. For app journeys, analysis, or evidence collection, follow the research workflow: plan at the business level, obtain one scope confirmation, operate the connected Android device, and preserve useful evidence even when a long composite fails.

Android needs no XCTest runner, no signing identity, and no Xcode. Transport is adb over USB, so wherever the iOS skill prepares or recovers a Runner, this skill verifies an adb device instead.

## Installation gate

1. Run `sh scripts/preflight.sh` before planning any workflow. This fast check is local-only and must not contact the phone.
2. On exit `0` with `status: ready`, reuse the verified installation and do not read `INSTALL.md`.
3. On exit `10` with `status: setup_required`, read `INSTALL.md` completely, follow its setup flow, and record the successful installation as instructed there. Resume the original request after setup; do not make the user repeat it.
4. On exit `2` or malformed output, stop and report the preflight error. Do not operate the phone.
5. Do not reinstall or reconfigure dependencies without evidence that they are missing, stale, or incompatible.

For modal fast capture, let `scripts/fast-capture-mode.sh` perform this preflight for `start` and `capture`. Do not run a duplicate preflight before the wrapper.

The cached marker covers local installation readiness, not live phone readiness. Do not issue an Agent Device command that connects to, observes, controls, or changes the physical phone until the installation gate passes and the user has approved the relevant setup or research scope. Preflight probes only local executables; it never runs `adb devices` or otherwise reaches the phone.

## Non-negotiable gates

- Do not issue an Agent Device command that interacts with the phone before the user approves either the journey or discovery scope, except for an activation phrase matched by the fast-mode router or an explicitly approved setup or health step from `INSTALL.md`. Treat fast-mode activation as approval only for a read-only USB transport check (`adb devices -l`), a content-free device-enumeration warm-up and keepalive, and session-only rebinding to the current foreground app identity. The rebinding command must contain no app name, bundle ID, or URL and must not relaunch or switch apps. Treat an accepted capture command while that mode is active as approval only for its fixed capture behavior and repair of that same foreground-following session when a daemon restart or adb reconnect removed it.
- For every explicitly named app, launch only through `sh scripts/open-mapped-app.sh`. It is the mandatory name → registry → package → foreground package → visible-brand gate. A registry miss triggers only the script's exact installed-name discovery; direct `agent-device apps`, the active session, and manual package selection are never launch fallbacks. After `agent-device-env.sh` is sourced, raw `agent-device open` is blocked.
- Require the gate's launch screenshot and target manifest before capturing any journey evidence. A uniquely exact installed-name match may be automatically registered only after its installed name, foreground package, and visible application label agree. If discovery is absent or ambiguous, or any identity check mismatches, stop. Do not choose a likely app, use a sibling brand, manually edit the mapping, or use discovery to replace an existing mapping during research.
- Treat the visible foreground app plus the requested app as the target. Never trust the persistent session binding by itself. Stop before app-scoped observation when the package and visible screen disagree.
- Enter a payment page only for screenshots, read-only scrolling, back, or close. Never enter payment data, choose or save a payment method, confirm a purchase, use a wallet or balance, or trigger biometric payment. Record `payment_page_reached` and end the journey there.
- The approved scope authorizes reversible in-app creation or editing that the plan explicitly names, such as creating and saving a trip, document, draft, list, project, or test record. Execute these planned actions without another confirmation at save time, and leave the created result in place unless the approved plan includes cleanup.
- Confirm immediately before an unplanned or externally consequential submission, such as placing a commercial order, sending or publishing content to another person, logging in, changing account security or permissions, deleting data, or making a change outside the approved scope.
- Run only one Agent Device workflow at a time. Leave the Agent Device session and daemon active after normal work; the daemon self-exits after its idle window.

## Route the request

1. When the message might activate, exit, or use modal fast capture—or the conversation indicates that mode is active—run `sh scripts/fast-capture-mode.sh route '<complete user message>'` first. Follow **Modal fast-capture mode** when it returns a matched action. Exit `10` means the mode did not claim the request.
2. Use **research mode / directed route** when the user identifies an app, function, page, journey, navigation step, analysis, or any other semantic work in addition to a screenshot.
3. Use **research mode / discovery route** when the user asks to “look at this app,” collect research screenshots, identify functions, or research a theme whose app structure is unknown. Read `references/discovery-mode.md` completely.
4. For either research route, read `references/capture-modes.md`. Default to `fast`. Use `verified` only when the user explicitly requires formal-report fidelity, pixel accuracy, or a seamless composite.
5. Choose a viewport for a single state, modal, control, or result. Choose a long screenshot when ordered vertical context adds material evidence. For long capture, read `references/long-screenshot.md`; read `references/video-long-screenshot.md` only when recording is relevant.
6. For every explicitly named app, use `sh scripts/open-mapped-app.sh`; it seeds and validates a private per-user registry from `references/app-bundle-ids.md` automatically and, only when the target is absent, performs exact installed-name discovery plus post-launch registration. Read `references/automated-checks.md` only before running bundled checks, and `references/runner-recovery.md` only after a device or daemon failure. Do not preload recovery or verified-mode material on the normal fast path.

## Modal fast-capture mode

- Activate on the router's `start` action by immediately running `sh scripts/fast-capture-mode.sh start`. Before warm-up, the wrapper requires the configured Android device to appear in `adb devices -l` in state `device` with a `usb:` transport token. An adb-over-network serial (`host:port`) carries no `usb:` token and is rejected: fast mode is wired-only by design. A device reported `unauthorized` means the USB debugging prompt has not been accepted on the phone — stop and ask the user to accept it, exactly as the iOS flow pauses for certificate trust. An `offline`, ambiguous, or missing device must stop activation with a USB-connect message. After that gate, the wrapper performs a read-only device enumeration as warm-up, releases only the prior Agent Device session record when necessary, creates a session with no app target so it follows the current foreground app, verifies that the session returns an app identity, and starts a content-free heartbeat. Do not report the mode active until all gates pass. The wrapper's session-only `open` is the sole fast-mode exception to the raw-open guard: it must contain no app name, bundle ID, URL, or relaunch flag. Repeated activation reuses the verified session generation.
- On `inactive_capture`, do not operate the phone; reply: `请先说“开启快速截屏”。`
- While active, accept only the router's `capture`, `stop`, or repeated `start` actions. For `blocked`, do not operate the phone or answer the semantic request; reply exactly: `当前处于快速截屏模式，请先说“退出快速截屏”。`
- On `capture`, run `sh scripts/fast-capture-mode.sh capture --message '<complete user message>' --output <absolute-unique.png>` immediately. Add a fresh `--work-dir` for long or full capture. Before capture, the wrapper verifies the recorded session generation; if a daemon restart or adb reconnect removed or replaced it, the wrapper recreates the same app-target-free foreground-following session under the device lock. Return the resulting image without analysis. The router deliberately accepts concise natural Chinese and English variants inside this mode, including `截屏`, `截图`, `长截屏`, `长截图`, `全截屏`, `全截图`, `screenshot`, `long screenshot`, `scrolling screenshot`, and `full screenshot`.
- Interpret `viewport` as the current visible screen, `long` as downward capture from the current position, and `full` as top-to-bottom capture. Do not pass an app target, open or relaunch a named app, navigate, inspect page content, analyze, compare, or research.
- On `stop`, run `sh scripts/fast-capture-mode.sh stop`, stop the heartbeat, and report that normal routing has resumed. Exiting does not close or alter the foreground app.
- The mode and heartbeat expire after 10 minutes without an accepted activation or capture. Each accepted capture refreshes the idle timer. Heartbeats use a content-free `agent-device devices --platform android` enumeration: it names no app, opens nothing, cannot switch or relaunch the foreground app, saves no screenshot or page content, does not inspect accessibility, and shares the device-workflow lock with captures.

## Plan and confirm

Skip this section entirely for modal fast-capture mode.

- Start from the user's research question and the product decision the evidence should support. Summarize the intended understanding in one sentence; do not turn a focused request into a generic app tour.
- Before writing the confirmation, build a compact UX coverage map for the approved goal:
  1. entry and starting context;
  2. the primary task path;
  3. information, choices, and commitment points that shape a decision;
  4. the outcome, system feedback, and immediate next step;
  5. only the alternative paths or edge states that materially change the experience, such as login, permission, empty, error, paywall, or unavailable states.
- Treat coverage as comprehensive when every materially distinct stage and approved variant has usable evidence, not when every tap or visually similar screen is captured. Prefer states that explain discoverability, comprehension, decision-making, action, feedback, recovery, or trust.
- Identify meaningful coverage dimensions before proposing the plan, such as new versus returning user, logged-in versus logged-out, free versus paid, entry channel, content type, or user-selected scenario. Include dimensions named by the user or central to the research goal as separate journeys. If an unstated dimension would materially change the evidence, surface one bounded assumption instead of silently sampling it.
- In discovery mode, briefly search the web first to understand what the app is and its main purpose, then use that context when planning the exploration.
- Translate the coverage map into user-level journeys and milestones. Describe what the user accomplishes or what UX question is being examined, not predicted page names or tap sequences. Group related states into one milestone while keeping materially different scenarios separate.
- When a milestone creates or edits reversible app content, name the intended artifact and saved outcome in the plan. User approval of that plan authorizes the action; do not add a blanket statement that creation or saving will not be performed.
- For each milestone choose `viewport` or `long screenshot`. Use long capture `auto` by default: soft target 4 and hard limit 6 viewport-equivalents. Use a number or `full` only when explicitly requested.
- State a concise completion criterion: what entry, decision, outcome, variant, or blocker evidence must be present for the approved journey to count as covered. Name any deliberate exclusion or representative sampling; never hide it inside execution.
- Keep the confirmation easy to scan: present only the research intent, one necessary assumption when needed, a short numbered journey or milestone list with capture types and any planned create/edit outcome, the completion criterion, and the payment or high-impact-action boundary. Do not expose filenames, internal checks, fallback mechanics, or device setup.
- Ask the user to confirm the research goal, coverage, evidence depth, and safety boundary in one explicit confirmation. Do not ask them to validate guessed interface structure.
- Before any phone operation, treat every later user instruction that adds, removes, or changes an app, journey, page or subpage, capture type, extent, evidence depth, or safety boundary as a plan amendment. Merge it into one complete revised plan, retaining every earlier item not explicitly removed or replaced; update the completion criterion; then obtain a new explicit confirmation before starting or resuming execution. Do not execute the latest instruction as an untracked side request.
- After approval, adapt to renamed, merged, split, or reordered pages without reconfirming only while the business goal, approved variants, coverage, evidence depth, capture mode, extent, and safety boundary remain unchanged.

## Preserve approved journey coverage

- Treat every user-requested scenario or combination as an independent journey unless the user explicitly accepts sampling or representative coverage.
- Execution order, navigation, tools, and presentation may be optimized, but these optimizations must not reduce the approved coverage or completion depth.
- Evidence organization determines how captured evidence is presented; it must not be used to reduce what gets captured.
- If a journey cannot reach the approved endpoint, preserve what was captured and report the actual blocker. Do not silently treat an incomplete journey as intentionally complete.

## Execute the approved scope

For modal fast-capture mode, use only the wrapper specified above and return its artifact. For research mode, continue with the steps below.

1. Source `scripts/agent-device-env.sh`. Use `$AGENT_DEVICE_SESSION` for every stateful command. Confirm the Android device is visible to adb in state `device` and the phone is unlocked. A black screenshot is a failed capture.
2. For an explicitly named app, run `sh scripts/open-mapped-app.sh --app <requested name> --screenshot <absolute launch.png> --manifest <absolute target.json>` before every journey. The command is the only allowed app-opening path: it resolves a registered target or performs exact installed-name discovery, opens only its selected package, captures the visible screen, and verifies foreground package plus visible application label. The latter path automatically appends a new mapping only after all checks pass. Keep its manifest with the evidence set.
3. If the target gate fails, stop before any app-scoped observation or interaction. Do not use the session binding, a manually run installed-app lookup, a manually supplied package, a similar brand, or a manual registry edit to recover. Report whether the deterministic result was not installed, ambiguous, an identity mismatch, or an existing-mapping conflict; request a separately authorized mapping-maintenance task only to correct an existing mapping.
4. Take a semantic snapshot only when navigation, scroll planning, or state verification needs it. Prefer mutation commands with `--settle`; reuse an unambiguous settle result instead of immediately taking another full snapshot. Never reuse stale refs after a material UI change.
5. Capture to explicit absolute paths. In fast viewport mode, run `sh scripts/check-viewport.sh` and visually confirm the correct readable state. Retry once only after a hard failure.
6. For fast long capture, preserve the target-gate screenshot and call `sh scripts/capture-long-fast.sh` with the verified package, a fresh work directory, and the approved extent. Do not issue concurrent device commands. The versioned `run.json` records stages, failure code, command counts, fallbacks, extent, and final outcome.
7. Allow one targeted fallback only after changing a causal condition. Stop a single screenshot repair at about 90 seconds. Do not replay an unchanged action after the same failure signature.

## Preserve and hand off evidence

- A readable fast composite may ship with soft warnings such as a small seam, repeated fixed chrome, dynamic banner, limited extent, or lower stitch confidence. Reject wrong-app, undecodable, near-black, locked/loading, unreadable, missing, reversed, or grossly corrupted evidence.
- If long capture fails hard quality, return the generated `evidence-pack.json` when it contains valid ordered viewports. State its order, captured extent, and stop reason. Do not let a failed composite erase readable source viewports.
- Report whether each long capture reached the page bottom or stopped at an approved/runtime limit. Preserve the target manifest alongside absolute paths, app, scenario, capture order, findings, and long/viewport type. Do not present evidence without a verified target manifest as belonging to a named app.
- When the user requests an HTML report, use `build-competitor-report-html`. Let that skill select narrative evidence while retaining all useful non-raw screenshots; do not copy its HTML components here.
