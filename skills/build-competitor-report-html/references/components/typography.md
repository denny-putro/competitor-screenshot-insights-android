# HTML Report Typography Reference

Use this reference for research, comparison, audit, evidence, and design-review HTML reports.

## Design intent

Create a restrained analytical hierarchy with a native system sans-serif stack and a small, repeatable type scale.

## Font family

Use the operating-system sans-serif stack. Do not load Inter or another web font.

```css
font-family:
  system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
  "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
```

On macOS, English and numbers normally render in SF Pro and Chinese in PingFang SC. On Windows, use Segoe UI and Microsoft YaHei.

## Type tokens

| Token | Font size | Line height | Use |
|---|---:|---:|---|
| `--font-caption` | 12px | 18px | Labels, screenshot captions, footer |
| `--font-small` | 14px | 22px | Navigation, metadata, tables, buttons, normal report copy |
| `--font-body` | 16px | 26px | Hero description, section introduction, important prose |
| `--font-title` | 20px | 28px | App titles, card titles, method titles, metric values |
| `--font-display` | 40px | 1.2 | Page title and section titles |
| `--font-display-mobile` | 32px | 1.2 | Page and section titles at 760px or below |

App titles and card titles must use the same 20px token. Page titles and section titles must use the same 40px token. Do not introduce adjacent one-off sizes such as 11, 13, 15, 17, 19, 22, 30, or 50px. Establish hierarchy with weight, color, spacing, and placement.

## Global foundations

```css
--ink: #101828;
--muted: #667085;
--paper: #ffffff;
--canvas: #f4f5f7;
--radius-md: 18px;
```

- Body copy must use `--ink` on `--canvas`.
- Supporting copy should use `--muted` only when the resulting contrast remains readable.
- The standard content shell must use a 1440px maximum width, with 20px desktop and 12px mobile gutters.
- Buttons must inherit the report font.

## Responsive behavior

At 760px or below, page and section display headings must use `--font-display-mobile`. Other type tokens must remain fixed; do not create local intermediate sizes.

## Accessibility acceptance

- At 200% browser zoom, text must remain readable without horizontal page scrolling caused by typography.
- Text must remain real selectable text.
- Body and heading text must meet WCAG 2.2 AA contrast against their actual rendered backgrounds.
- Keyboard focus indicators must remain visible on all interactive text controls.

## QA checks

- Computed body font starts with the native `system-ui` stack.
- The only standard sizes are 12, 14, 16, 20, 40, and the 32px mobile display override.
- 40px display text uses 1.2 line height.
- 20px titles use 28px line height.
- 16px body text uses 26px line height.
- 14px small text uses 22px line height.
- 12px captions use 18px line height.
- No external font requests are present.

## Prohibited implementations

- Inter or another externally loaded font
- `clamp()` typography for the defined scale
- One-off font sizes that duplicate an existing hierarchy level
- Hidden focus indicators
- Low-contrast muted text
