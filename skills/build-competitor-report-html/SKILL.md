---
name: build-competitor-report-html
description: Build or update a neutral local HTML screenshot gallery from competitor captures, app research, or existing evidence. Use when the user asks to generate, compile, render, or refresh an HTML page for captured product screenshots. Present screenshots with a concise title, one- or two-sentence page description, factual labels, and necessary scope notes; omit analysis, conclusions, comparisons, judgments, and recommendations unless the user explicitly requests them.
---

# Build Competitor Screenshot HTML

Turn captured competitor screenshots into a clean, neutral browsing page. Treat screenshots as the primary content and visible prose as orientation only. This Skill is self-contained: use its bundled references and component assets without requiring separate component Skills.

## Workflow

1. Read `references/content-quality-gate.md`, `references/evidence-organization.md`, `references/component-registry.yaml`, and `references/publishing-metadata.json` completely.
2. Inspect the conversation and existing artifacts. Reuse captured screenshots, app names, page names, scenario facts, and reliable sequence information. When a source contains explicit test criteria, preserve them with the registered test-criteria component instead of reducing them to a prose note. Do not operate the phone or recapture evidence unless explicitly asked.
3. Build a private inventory and map screenshots to the approved journey in actual order. Remove only corrupt, unreadable, irrelevant, or exact-duplicate images at this stage. Never expose the inventory or review process.
4. Keep visible copy minimal:
   - one concise page title;
   - one or two neutral sentences explaining what the screenshots show;
   - one compact test-criteria card when explicit fixed test inputs are available;
   - short app, flow, page, or state labels;
   - at most one factual sentence per screenshot when the image needs context;
   - only material scope notes needed to prevent misinterpretation.
5. Do not add findings, insights, conclusions, comparison tables, rankings, strengths, weaknesses, implications, design judgments, recommendations, or interpretive callouts unless the user explicitly requests analysis in that task.
6. Organize screenshots by app or chronological journey. Preserve one clear image for every substantive journey node so the flow remains complete and understandable. Consolidate only minor variants of the same page and state. Combine different scroll positions of one page into a long screenshot when reliable; otherwise keep the viewport that best identifies the node and its transition, usually the topmost clear view. Preserve source aspect ratios.
7. Resolve applicable entries in `references/component-registry.yaml` in order. Read every selected local component reference completely, then copy its required assets from this Skill into report-local `components/`. Do not install or read sibling component Skills. Keep the bundled component contracts and assets unchanged in each generated report.
8. Default to complete Chinese and English versions of the limited visible copy. Keep screenshot pixels unchanged. If the user explicitly requests one language, omit the language switch and provide that language only.
9. Add the required `competitor-report` metadata from `references/publishing-metadata.json` to the HTML `<head>`. Use a stable lower-case report ID and an ISO generation date.
10. Validate at representative desktop and mobile widths. Check local-file compatibility, missing assets, screenshot interactions, language behavior when present, image aspect ratios, overflow, and content neutrality.

## Presentation Rules

- Make screenshots visually dominant.
- Prefer a simple gallery over dashboards, scorecards, analytical cards, charts, or dense tables.
- Use factual captions such as `Expedia · Fare selection` or `携程 · 乘机人信息`.
- State only what page or state is visible. Do not infer product intent or user impact.
- A blocked, partial, or stopped journey may have one concise neutral note when that limitation affects coverage.
- Do not render capture tooling, retries, file paths, session details, QA logs, or execution history.

## Output Requirements

- Produce a self-contained, usable local HTML page at the requested or current project location.
- Keep all relevant distinct-page screenshots in the main gallery or a compact collapsed source section.
- Apply the registered typography and screenshot-viewer components. Apply Hero, navigation, or test criteria only when the registry says they are useful for the page's content and structure.
- Embed publishing metadata so the page can be published and indexed later.
- Report which registered components were applied and provide a clickable path to the HTML.
- Ask whether the user wants to publish. If confirmed and `$publish-web` is available, invoke that Skill. Publishing is optional and is not required to generate or use the local report.

Explicit user instructions override the neutral-gallery default. If analysis is requested, add only the requested analytical content rather than restoring a generic report template.
