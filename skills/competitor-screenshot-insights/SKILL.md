---
name: competitor-screenshot-insights
description: Operate and research an app on a connected physical iPhone with Agent Device, then return verified viewport screenshots, bounded long screenshots, or an ordered viewport evidence pack. Use for directed iPhone journeys and for open-ended requests to inspect an unfamiliar app, discover its core functions, collect research evidence, compare product experiences, or prepare screenshots for an HTML competitor report.
---

# Competitor Screenshot Insights

Plan a business-level journey, obtain one scope confirmation, operate the connected iPhone, and preserve useful evidence even when a long composite fails.

## Installation gate

1. Run `scripts/preflight.sh` before planning any workflow. This fast check is local-only and must not contact the phone.
2. On exit `0` with `status: ready`, reuse the verified installation and do not read `INSTALL.md`.
3. On exit `10` with `status: setup_required`, read `INSTALL.md` completely, follow its setup flow, and record the successful installation as instructed there. Resume the original request after setup; do not make the user repeat it.
4. On exit `2` or malformed output, stop and report the preflight error. Do not operate the phone.
5. Do not reinstall or reconfigure dependencies without evidence that they are missing, stale, or incompatible.

The cached marker covers local installation readiness, not live phone readiness. Do not issue an Agent Device command that connects to, observes, controls, or changes the physical phone until the installation gate passes and the user has approved the relevant setup or research scope.

## Non-negotiable gates

- Do not issue an Agent Device command that interacts with the phone before the user approves either the journey or discovery scope, except for an explicitly approved setup or health step from `INSTALL.md`.
- For every explicitly named app, launch only through `scripts/open-mapped-app.sh`. It is the mandatory name → registry → bundle → foreground bundle → visible-brand gate. A registry miss triggers only the script's exact installed-name discovery; direct `agent-device apps`, the active session, and manual bundle selection are never launch fallbacks. After `agent-device-env.sh` is sourced, raw `agent-device open` is blocked.
- Require the gate's launch screenshot and target manifest before capturing any journey evidence. A uniquely exact installed-name match may be automatically registered only after its installed name, foreground bundle, and visible application label agree. If discovery is absent or ambiguous, or any identity check mismatches, stop. Do not choose a likely app, use a sibling brand, manually edit the mapping, or use discovery to replace an existing mapping during research.
- Treat the visible foreground app plus the requested app as the target. Never trust the persistent session binding by itself. Stop before app-scoped observation when the bundle and visible screen disagree.
- Enter a payment page only for screenshots, read-only scrolling, back, or close. Never enter payment data, choose or save a payment method, confirm a purchase, use a wallet or balance, or trigger biometric payment. Record `payment_page_reached` and end the journey there.
- The approved scope authorizes reversible in-app creation or editing that the plan explicitly names, such as creating and saving a trip, document, draft, list, project, or test record. Execute these planned actions without another confirmation at save time, and leave the created result in place unless the approved plan includes cleanup.
- Confirm immediately before an unplanned or externally consequential submission, such as placing a commercial order, sending or publishing content to another person, logging in, changing account security or permissions, deleting data, or making a change outside the approved scope.
- Run only one Agent Device workflow at a time. Leave the persistent Runner active after normal work.

## Route the request

1. Read `references/capture-modes.md`. Default to `fast`. Use `verified` only when the user explicitly requires formal-report fidelity, pixel accuracy, or a seamless composite.
2. Use **directed mode** when the user identifies an app, function, page, or journey. Stay within that goal.
3. Use **discovery mode** when the user asks to “look at this app,” collect research screenshots, identify functions, or research a theme whose app structure is unknown. Read `references/discovery-mode.md` completely.
4. Choose a viewport for a single state, modal, control, or result. Choose a long screenshot when ordered vertical context adds material evidence. For long capture, read `references/long-screenshot.md`; read `references/video-long-screenshot.md` only when recording is relevant.
5. For every explicitly named app, use `scripts/open-mapped-app.sh`; it seeds a private per-user registry from `references/app-bundle-ids.md`, validates that registry automatically, and, only when the target is absent, performs exact installed-name discovery plus post-launch registration. Read `references/automated-checks.md` only before running bundled checks, and `references/runner-recovery.md` only after a Runner failure. Do not preload recovery or verified-mode material on the normal fast path.

## Plan and confirm

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

1. Source `scripts/agent-device-env.sh`. Use `$AGENT_DEVICE_SESSION` for every stateful command. Confirm the physical iPhone and Runner are usable and the phone is unlocked. A black screenshot is a failed capture.
2. For an explicitly named app, run `scripts/open-mapped-app.sh --app <requested name> --screenshot <absolute launch.png> --manifest <absolute target.json>` before every journey. The command is the only allowed app-opening path: it resolves a registered target or performs exact installed-name discovery, opens only its selected bundle, captures the visible screen, and verifies foreground bundle plus visible application label. The latter path automatically appends a new mapping only after all checks pass. Keep its manifest with the evidence set.
3. If the target gate fails, stop before any app-scoped observation or interaction. Do not use the session binding, a manually run installed-app lookup, a manually supplied bundle, a similar brand, or a manual registry edit to recover. Report whether the deterministic result was not installed, ambiguous, an identity mismatch, or an existing-mapping conflict; request a separately authorized mapping-maintenance task only to correct an existing mapping.
4. Take a semantic snapshot only when navigation, scroll planning, or state verification needs it. Prefer mutation commands with `--settle`; reuse an unambiguous settle result instead of immediately taking another full snapshot. Never reuse stale refs after a material UI change.
5. Capture to explicit absolute paths. In fast viewport mode, run `scripts/check-viewport.sh` and visually confirm the correct readable state. Retry once only after a hard failure.
6. For fast long capture, preserve the target-gate screenshot and call `scripts/capture-long-fast.sh` with the verified bundle, a fresh work directory, and the approved extent. Do not issue concurrent device commands. The versioned `run.json` records stages, failure code, command counts, fallbacks, extent, and final outcome.
7. Allow one targeted fallback only after changing a causal condition. Stop a single screenshot repair at about 90 seconds. Do not replay an unchanged action after the same failure signature.

## Preserve and hand off evidence

- A readable fast composite may ship with soft warnings such as a small seam, repeated fixed chrome, dynamic banner, limited extent, or lower stitch confidence. Reject wrong-app, undecodable, near-black, locked/loading, unreadable, missing, reversed, or grossly corrupted evidence.
- If long capture fails hard quality, return the generated `evidence-pack.json` when it contains valid ordered viewports. State its order, captured extent, and stop reason. Do not let a failed composite erase readable source viewports.
- Report whether each long capture reached the page bottom or stopped at an approved/runtime limit. Preserve the target manifest alongside absolute paths, app, scenario, capture order, findings, and long/viewport type. Do not present evidence without a verified target manifest as belonging to a named app.
- When the user requests an HTML report, use `build-competitor-report-html`. Let that skill select narrative evidence while retaining all useful non-raw screenshots; do not copy its HTML components here.
