> ### Fork note — Android port
>
> Derived from [`fengjunnan-web/competitor-screenshot-insights`](https://github.com/fengjunnan-web/competitor-screenshot-insights)
> (MIT), which targets a physical **iPhone**. This fork replaces that Skill with an
> **Android** port: `skills/competitor-screenshot-insights/` is gone and
> `skills/competitor-screenshot-insights-android/` takes its place. The rename is
> required — `validate_skill.py` enforces that a Skill's `name:` matches its folder.
>
> The upstream commit history is intact, so the port is one reviewable diff:
> `git log --oneline` shows it directly above upstream's own commits.
>
> **Known limitation.** The app-identity gate is weaker than upstream's. iOS confirms
> a human-readable brand from the accessibility layer's `Application` node; Android
> exposes no such value, so the gate instead cross-checks the package across two
> independent CLI surfaces (`appstate` and `snapshot`) plus the registry. The bundled
> registry ships **empty** on purpose: Android package names are not derivable from
> iOS bundle identifiers, and a guess would defeat the wrong-app gate.
>
> Validated on a physical Huawei P30 (`ELE-L29`): 103 tests, plus a full journey from
> app launch through search, results, fare selection, and the booking form.
>
> `AGENTS.md` is inherited from upstream and still designates *that* repository as the
> canonical source for public Skill code; read it as upstream's policy, not this fork's.

# Competitor Research Skills

> Capture competitor journeys on a real Android device, then turn the evidence into a clear HTML gallery.

**Public Beta · v0.2**

This repository contains two installable Claude Code Skills: `competitor-screenshot-insights-android` explores apps on a physical Android device and captures ordered evidence; `build-competitor-report-html` turns screenshot evidence into a neutral, bilingual HTML gallery. Install either Skill independently or use them together as an end-to-end research workflow.

It is designed for product managers, designers, researchers, and growth teams working on competitive analysis, experience comparisons, design reviews, opportunity discovery, and strategic reporting.

## Quick Start

These are Claude Code Skills. Claude Code loads them from `~/.claude/skills/<skill-name>/`,
and the folder name must match the `name:` in the Skill's frontmatter.

**Option A — ask Claude Code to install from GitHub:**

> Install `competitor-screenshot-insights-android` from `denny-putro/competitor-screenshot-insights-android`, path `skills/competitor-screenshot-insights-android`.

> Install `build-competitor-report-html` from `denny-putro/competitor-screenshot-insights-android`, path `skills/build-competitor-report-html`.

**Option B — clone and deploy (keeps this repo as the source of truth):**

```sh
git clone https://github.com/denny-putro/competitor-screenshot-insights-android.git
cd competitor-screenshot-insights-android
sh deploy.sh          # copy the Skill into ~/.claude/skills/
sh deploy.sh --check   # report drift between repo and installed copy
```

Do not symlink the Skill into `~/.claude/skills/`: Claude Code does not discover
symlinked Skills, and the linked Skill is silently absent from the Skill list.
`deploy.sh` copies instead, and re-records the install fingerprint — which covers
file paths, so any relocation needs `preflight.sh --record` again.

The report Skill is self-contained: its typography, Hero, navigation, test-criteria, and screenshot-viewer components are bundled as private modules. No additional component Skills are required. It can use evidence from `competitor-screenshot-insights` or screenshots collected elsewhere.

On first use, the Skill runs a local preflight. The Agent reads and follows the [installation guide](skills/competitor-screenshot-insights-android/INSTALL.md) only when dependencies are missing or the configuration has changed. After a successful setup, it reuses a machine-local cache instead of repeating installation checks on every run.

Good starting requests include:

- “Research this app’s membership-purchase journey and capture the key screens.”
- “Explore how this app handles monetization and advertising.”
- “Compare search and filtering in two apps and preserve the complete evidence.”

## Fast Screenshot Mode

When you only want to capture the phone’s current screen repeatedly, say `start fast screenshot mode`. The Skill first confirms that the configured Android device is visible to `adb` over a USB cable, warms the device transport, and binds to the current foreground app. Wired only: an adb-over-network target is rejected. It does not open or switch apps for you.

Once the mode is active, use concise English or Chinese commands:

- `screenshot` / `截图`: capture the currently visible screen;
- `long screenshot` / `长截图`: capture downward from the current position;
- `full screenshot` / `全截图`: return to the top, then capture the full page;
- `exit fast screenshot mode` / `退出快速截屏`: leave the mode and resume normal conversation.

Fast Screenshot Mode accepts only capture, repeated activation, and exit commands. Exit the mode before asking for page analysis, app navigation, or ordinary conversation. The mode expires automatically after 10 minutes without an accepted command.

## Two Research Modes

### Directed research for a defined goal

When you already know which app, feature, or journey you want to study, the Skill follows a directed route and collects evidence around that goal.

You can ask it to:

- capture the complete path from the home screen to a membership-purchase page;
- study search, filtering, and result presentation;
- compare product-detail pages across apps;
- collect the important states of a core feature.

It stays focused on the task while adapting to changes in entry points, labels, and page order. You do not need to describe every tap in advance.

### Guided discovery for an open question

When you have only a broad direction—such as “take a look at this app” or “research its monetization design”—the Skill enters discovery mode.

It maps the product structure, core capabilities, and important experience paths; identifies screens worth preserving; and gradually builds evidence that can support deeper analysis. You can begin with the real product experience even before you know the exact research question.

## Why Screenshots Are the Core Deliverable

Screenshots are intentionally the primary output instead of locking every result into a fixed report format.

They are universal, reusable product-research evidence. You can analyze product strategy, information architecture, conversion paths, interaction details, or visual style from your own perspective. You can also pass the material directly to another AI, research tool, or teammate without migrating data or changing your workflow.

The Skill preserves scenario, order, and context wherever possible so each screenshot supports judgment rather than merely looking presentable.

It can also work with the included `build-competitor-report-html` Skill to generate a default HTML report that organizes selected screenshots into a clear research narrative:

- Use the HTML report for quick review and sharing.
- Use the original screenshot evidence for analysis with your own framework.
- Reuse the same material in an existing team reporting workflow.

This supports both an out-of-the-box deliverable and open-ended analysis.

## What We Optimized

Real apps contain many situations that people understand instantly but automation often mishandles. We turned those details into explicit, reliable behaviors.

### Pop-ups and advertisements

Launch ads, campaign pop-ups, permission prompts, and promotional overlays often cover the target content.

The Skill uses the research goal to decide whether an overlay is an obstruction to close or valuable product evidence to preserve, reducing accidental taps without losing meaningful monetization patterns.

### Horizontal containers

Product cards, content recommendations, channel navigation, and carousels are easily mistaken for ordinary vertical pages.

The Skill improves direction detection and gesture strategy for horizontal containers, reducing incorrect swipes, duplicate screenshots, and missing content.

### Dynamic pages

Real pages often contain delayed loading, rotating banners, recommendation modules, sticky navigation, and continuously changing promotional content.

The workflow evaluates the current visible state instead of relying on stale page structure, allowing it to adapt when modules appear, entry points move, or layouts are reordered.

### Fixed interface elements

Bottom navigation, floating buttons, and sticky headers may repeat throughout a long screenshot and interfere with reading or stitching.

The Skill tries to reduce their impact on long captures and evidence organization while preserving authentic page context.

### From mechanical gestures to goal-aware decisions

The Skill does not simply repeat taps at fixed coordinates. It continually checks whether the current page still serves the approved research goal.

This allows it to adapt when a page is redesigned, an entry point moves, or a flow is split into multiple steps while preserving the intended scope and evidence depth.

## How Reliability Is Protected

### Device and target-app verification

Each run checks whether the device is usable, the phone is unlocked, the screen is readable, and the foreground app matches the research target. It stops instead of continuing in the wrong app or an invalid state.

### One device workflow at a time

Only one device workflow runs at a time, preventing taps, scrolling, page loading, and captures from interfering with each other. Every piece of evidence retains a clear operational context.

### Waiting for stable UI state

The Skill gives the interface enough time to finish transitions and avoids reusing page elements that became stale after a change, reducing mistakes caused by animation, refreshes, and layout shifts.

### Screenshot quality checks

Black, locked, loading, unreadable, wrong-app, or severely corrupted screenshots are not delivered as valid evidence.

When a problem is recoverable, the Skill retries only after changing the condition that caused it, avoiding unproductive loops.

### Long-screenshot fallback

Long-screenshot stitching does not always succeed, especially on pages with dynamic banners, fixed navigation, or complex scroll containers.

Fallback is therefore a first-class capability: if a valid composite cannot be produced, the Skill preserves and delivers an ordered viewport evidence pack. A failed stitch does not erase the entire research journey.

### Traceable results

Deliverables preserve the app, scenario, capture order, covered extent, and stop reason. You can inspect both the result and how it was produced, then reuse that context for review, collaboration, or further analysis.

## Safety Boundaries

Physical-device research needs enough depth to be useful and clear limits to remain safe.

After reaching a payment page, the Skill may only capture, inspect, scroll, go back, or close. It will not enter payment details, select a payment method, confirm a purchase, or trigger biometric payment.

It also asks for confirmation immediately before placing an order, sending a message, logging in, changing an account, or modifying external data outside the approved scope.

## Compatibility and Privacy

This fork targets macOS or Linux, a physical Android device with Developer options and USB debugging enabled, Android platform-tools (`adb`), Node.js 22.12+, Agent Device 0.20.x, and Python 3.12+. No Xcode, Apple Developer account, signing identity, or XCTest Runner is involved. If the device reports `unauthorized`, accept the USB debugging prompt on the phone; that is a permission state, not a transport fault.

Device names, adb serials, machine paths, installation caches, and app package mappings learned at runtime remain in the user’s private configuration directory. They are not stored in the Skill or repository. Research screenshots may still contain account or business information, so users should review and redact them before sharing.

## License

This project is available under the [MIT License](LICENSE). Third-party runtime components retain their respective licenses.

## Start with Screenshots, Keep the Insight Open

Competitor Screenshot Insights does more than “take a few screenshots.”

It handles the most time-consuming and failure-prone parts of real-app research so you receive ordered, contextual, verifiable evidence that remains open to further analysis—leaving more time for the insights and decisions that matter.
