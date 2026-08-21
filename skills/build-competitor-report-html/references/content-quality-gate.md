# Neutral Screenshot Page Quality Gate

Apply this gate privately to all visible text before generating or updating the HTML.

## Default content model

The page is a screenshot gallery, not an analytical report. Screenshots carry the content; text only helps the reader identify and navigate them.

Allowed visible text:

- a concise title;
- one or two neutral sentences describing the screenshot set;
- essential factual scope such as apps, flow, route, date, platform, or passenger mix;
- app, journey, page, and state headings;
- a short factual caption and, only when needed, one factual sentence per screenshot;
- a concise limitation note for a blocked, partial, or intentionally stopped journey;
- viewer, navigation, language, and accessibility labels.

## Remove by default

- findings, insights, conclusions, takeaways, executive summaries, or key observations;
- comparison tables, rankings, scores, benchmarks, pros and cons, strengths and weaknesses;
- interpretations of conversion, trust, friction, persuasion, urgency, hierarchy, or business intent;
- implications, opportunities, recommendations, design principles, or next steps;
- price calculations or cross-app synthesis beyond a factual value already visible in a screenshot;
- repeated prose that merely narrates visible screenshot content;
- internal reasoning, progress, capture operations, tool usage, file paths, retries, QA logs, or implementation notes;
- generic filler, decorative metrics, and unsupported claims.

Include analytical content only when the user explicitly asks for it in the current task. Keep it limited to the requested scope.

## Neutral wording

- Name the visible page or state: `Expedia · Review trip`.
- Use direct factual context when necessary: `The total shown on this screen is HK$5,250.`
- Do not label a UI as good, bad, clear, confusing, aggressive, trustworthy, persuasive, or problematic.
- Do not infer why a product chose a pattern or how users will react.
- Do not turn screenshot captions into mini-analyses.

## Bilingual delivery

Default to complete Chinese and English versions of all reader-visible text. Keep the versions equivalent. Screenshot pixels remain unchanged. When the user explicitly requests one language, provide only that language and omit the switch.

## Naming

- Keep the canonical title within 14 Chinese-character equivalents.
- Use matching localized titles for `<title>` and `h1`.
- Move route, date, and detailed scope into the short description or metadata.

## Acceptance checks

- Screenshots are the dominant visible content.
- The introduction is no longer than two sentences.
- Every screenshot has a factual identifying label.
- No default section is titled Findings, Conclusions, Comparison, Insights, Recommendations, or an equivalent translation.
- No visible prose evaluates, ranks, interprets, or advises.
- Necessary limitations are stated neutrally and briefly.
- No internal execution information appears.
- The canonical title stays within the naming limit and matches `<title>` and `h1` in each locale.
