# Bilingual Report Navigation Contract

## Required markup

Place the navigation directly inside `.hero-cover`, before `<main>`:

```html
<nav class="report-nav" data-report-navigation data-default-locale="zh-CN" aria-label="Report navigation">
  <div class="shell report-nav__inner">
    <div class="report-nav__links" aria-label="Report sections">
      <a href="#overview" data-i18n="nav.overview">Overview</a>
    </div>
    <div class="report-language-switch" role="group" aria-label="Language">
      <button type="button" data-report-locale="zh-CN">中文</button>
      <button type="button" data-report-locale="en">EN</button>
    </div>
  </div>
</nav>
```

Use `data-i18n`, `data-i18n-aria-label`, `data-i18n-title`, and `data-i18n-placeholder` for static text and attributes. The JavaScript reads `window.reportTranslations` as an object keyed by `zh-CN` and `en`, with dot-separated translation keys.

## Behavior

- Default to `data-default-locale`; restore a prior selection from local storage when available.
- Set `document.documentElement.lang`, update the active control's `aria-pressed`, and dispatch `reportlocalechange` with `{ locale }` after every change.
- Use a `report.title` translation to update the document title when supplied.
- Use `reportlocalechange` to rerender strings created with JavaScript, including screenshot captions and alt text.
- Keep the current locale on internal navigation and refresh. The control must operate without network access or a build step.

## Visual and accessibility requirements

- Keep the switch at the far end of the navigation row on desktop; let it wrap below links on narrow screens.
- Render two compact buttons labeled `中文` and `EN`; make the active option look like a raised white surface inside a subtle rounded track.
- Animate the active state with a short, reduced-motion-safe transition. Do not use decorative flags.
- Use real `button` controls with visible keyboard focus and an `aria-label` on the language group.
- Keep all translated copy as selectable DOM text. Do not translate screenshots or render text into canvas.
- At 200% zoom and on mobile, navigation and the switch must remain usable without horizontal page scrolling.
