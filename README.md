# Competitor Screenshot Insights

**English** | [简体中文](README.zh-CN.md)

> Turn a real iPhone into a reliable competitor-research assistant.

**Public Beta · v0.2**

Competitor Screenshot Insights explores apps on a physical device, reconstructs important user journeys, and delivers clear viewport screenshots, long screenshots, and ordered evidence packs. Whether you want to examine a specific feature or explore an unfamiliar product, it turns “take a look at this competitor” into a verifiable, reusable research process.

It is designed for product managers, designers, researchers, and growth teams working on competitive analysis, experience comparisons, design reviews, opportunity discovery, and strategic reporting.

## Quick Start

In Codex, ask the Agent to install the Skill from GitHub with the built-in `skill-installer`:

> Install `competitor-screenshot-insights` from `fengjunnan-web/competitor-screenshot-insights`, path `skills/competitor-screenshot-insights`.

On first use, the Skill runs a local preflight. The Agent reads and follows the [installation guide](skills/competitor-screenshot-insights/INSTALL.md) only when dependencies are missing or the configuration has changed. After a successful setup, it reuses a machine-local cache instead of repeating installation checks on every run.

Good starting requests include:

- “Research this app’s membership-purchase journey and capture the key screens.”
- “Explore how this app handles monetization and advertising.”
- “Compare search and filtering in two apps and preserve the complete evidence.”

## Fast Screenshot Mode

When you only want to capture the phone’s current screen repeatedly, say `start fast screenshot mode`. The Skill first confirms that the configured iPhone is available over USB, warms the Runner, and binds to the current foreground app. It does not open or switch apps for you.

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

It can also work with the optional `build-competitor-report-html` Skill to generate a default HTML report that organizes selected screenshots into a clear research narrative:

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

The current beta targets macOS, a physical iPhone, a compatible Xcode version, Node.js 22.12+, Agent Device 0.20.x, and Python 3.12+. Some iOS and Xcode combinations may require Runner configuration described in the installation guide.

Device names, Team IDs, Bundle IDs, machine paths, installation caches, and app mappings learned at runtime remain in the user’s private configuration directory. They are not stored in the Skill or repository. Research screenshots may still contain account or business information, so users should review and redact them before sharing.

## License

This project is available under the [MIT License](LICENSE). Third-party runtime components retain their respective licenses.

## Start with Screenshots, Keep the Insight Open

Competitor Screenshot Insights does more than “take a few screenshots.”

It handles the most time-consuming and failure-prone parts of real-app research so you receive ordered, contextual, verifiable evidence that remains open to further analysis—leaving more time for the insights and decisions that matter.
