# Shader Glass Report Hero Contract

## Design intent

Open analytical reports with a bright Blue Sky Shader and one unified translucent panel that combines orientation copy with four concise scope facts.

## Dependencies and asset order

The Hero must be used with the report typography foundation. Load assets in this order:

```html
<link rel="stylesheet" href="components/report-foundation.css" />
<link rel="stylesheet" href="components/report-hero.css" />
```

Load `report-hero.js` after the Hero markup. Copy all selected component assets into the delivered report; do not link back to the installed Skill directory.

## Required anatomy

Use `../../assets/components/hero-reference.html` as the structural source of truth:

1. `<header class="hero" data-report-hero data-shader-status="loading">`
2. `.hero-background[aria-hidden="true"]`
3. `.hero-background__shader` canvas
4. `.shell.hero-grid.hero-panel`
5. `.hero-intro` with exactly one `h1` and one `.hero-copy`
6. `.hero-meta[aria-label]` with four `.meta-row` items
7. A following opaque `.hero-cover` that wraps navigation and main content

The component must not include an Original/Shader switch or any other background controls.

## Content rules

- The title must name the report subject directly.
- The description must be one concise sentence that states the comparison scope or reader value.
- Metadata must contain four short, high-value facts such as objects, business, states/scenarios, and date.
- Internal reasoning, execution notes, collection status, and progress reporting must not appear.
- Metadata labels should be 2–5 Chinese characters or similarly concise in another language.
- Long values must wrap at tablet/mobile widths. Desktop values should remain one line when space permits.

## Visual contract

### Background

- The default and only standard background must be the bundled Blue Sky Shader.
- Shader colors must remain `#E6F2FF`, `#B3D9FF`, `#80B3FF`, and `#6699E6`.
- The component must expose `data-shader-status="ready"` after successful initialization and `fallback` when WebGL is unavailable.
- The compact CSS background is fallback-only and should not replace the Shader during normal operation.

### Glass panel

- Desktop width must be `min(1066px, calc(100% - 40px))`.
- Desktop minimum height must be 237px.
- Desktop padding must be `40px 40px 80px`.
- Corner radius must be 40px.
- The panel must use a translucent gradient, 24px backdrop blur, restrained border highlights, and no text shadow.
- Title, description, values, and labels must remain readable white or translucent-white text.

### Internal layout

- Desktop uses one flex row with a 20px gap.
- `.hero-intro` flexes and may wrap; `.hero-meta` remains a compact 2×2 grid.
- Title uses `--font-display`; description uses `--font-body`; metadata uses `--font-caption`.
- Intro title-to-description spacing must be 12px.
- The Hero must not contain the former small uppercase English eyebrow.

## Desktop overlap contract

Apply above 1080px:

- Hero height must be 360px.
- Panel must be bottom-anchored at `-39px`, placing its lower edge at 399px so 39px continues below the Hero.
- The panel height must remain content-driven, with its required top and bottom padding intact. If its copy wraps or grows, it expands upward; it must not push the following navigation down.
- At the 237px minimum panel height, its top is 162px. With taller content, its top moves upward while its bottom anchor remains unchanged.
- `.hero-cover` must have `z-index: 20` and an opaque report background.
- The following layer must cover the panel's lower overflow, including its bottom radii and shadow.
- The panel must not float above the following navigation or report content.

The overlap is a stacking relationship, not negative margin. Do not raise the Hero or panel above `.hero-cover`.

## Responsive behavior

At 1080px or below:

- The Hero must return to normal document flow with 72px vertical padding.
- The panel must become a one-column grid.
- Panel width must be `min(100% - 40px, 1066px)`.
- Panel padding must be 40px and radius 32px.
- Metadata must use two equal columns.
- Metadata values must wrap safely.
- The intentional desktop overlap must disappear.

At 760px or below:

- Hero vertical padding must be 52px.
- Panel width must use 12px page gutters.
- Panel padding must be `32px 24px` and radius 24px.
- Heading must use `--font-display-mobile`.

## Motion and fallback behavior

- The Shader may animate continuously only when `prefers-reduced-motion` is not `reduce`.
- With reduced motion, the component must render a stable Shader frame.
- If WebGL, Canvas 2D, compilation, or required nodes are unavailable, the canvas must be hidden and the CSS fallback must remain visible.
- Failure must not remove or obscure the Hero content.
- The runtime must not require a framework, network request, or build step.

## Accessibility acceptance

- The component must use a semantic `<header>` and exactly one page `h1`.
- `.hero-background` and its canvas must be hidden from assistive technology with `aria-hidden="true"` on the wrapper.
- `.hero-meta` must have a descriptive accessible label.
- All title, description, and metadata content must remain real text.
- White text must meet WCAG 2.2 AA contrast against the rendered glass/background combination.
- At 200% browser zoom, content must not overlap or create horizontal page scrolling.
- The component contains no interactive control and therefore adds no tab stop.

## QA checklist

- No Original/Shader switch is visible or present in the DOM.
- `data-shader-status` becomes `ready` in a WebGL-capable browser.
- Browser console has no errors.
- At 1846px viewport width: Hero is 360px high; the panel is 1066px wide, bottom-anchored 39px behind the following layer, and has at least 237px height. The 237px baseline panel begins at 162px; taller content expands upward.
- Desktop title and description never run behind metadata.
- Top and bottom content spacing inside each side of the panel appear balanced.
- The `.hero-cover` hides the panel's lower radii and shadow.
- At 1080px and below, the panel is in normal flow and nothing is clipped.
- At 760px and below, title and metadata wrap without overflow.
- Reduced-motion mode shows a stable background frame.
- Forced fallback leaves a readable Hero.

## Prohibited implementations

- Background mode switch or preview controls
- Static CSS replacing the Shader during normal operation
- Small uppercase English eyebrow
- Text shadow
- Text rendered into canvas or an image
- Glass panel floating above the following content
- Negative-margin overlap
- External font, framework, or runtime dependency
