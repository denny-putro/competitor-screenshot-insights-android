# Test Criteria Card Contract

## Purpose

Present fixed test inputs in one readable card without turning the report into a dashboard or analytical summary.

## Dependencies and asset order

Use the report typography foundation and load the copied component CSS after it:

```html
<link rel="stylesheet" href="components/report-foundation.css" />
<link rel="stylesheet" href="components/test-criteria.css" />
```

Never link a delivered report directly to the skill directory.

## Required anatomy

```html
<section class="test-criteria" id="test-criteria" aria-labelledby="test-criteria-title">
  <div class="test-criteria__header">
    <h2 id="test-criteria-title">测试口径</h2>
  </div>
  <dl class="test-criteria__card">
    <div class="test-criteria__item">
      <dt>单程</dt>
      <dd>上海（所有机场）→ 曼谷，2026-09-16</dd>
    </div>
  </dl>
</section>
```

- Use exactly one `h2` and one `.test-criteria__card`.
- Do not add a subtitle, description, or eyebrow below the heading.
- Represent every criterion as one `.test-criteria__item` containing one `dt` and one `dd`.
- Keep route, date, passenger, cabin, selection-rule, price, device, or environment labels factual and concise.
- Omit the component when the source contains no explicit test criteria.

## Visual contract

- The component uses one white card with an 18px report radius and a restrained border.
- Rows use a 128px label column, a flexible content column, a 20px gap, and 14px vertical padding.
- Adjacent rows use a subtle top divider; individual rows must not look like separate cards.
- The heading uses the report `--font-title` and `--line-title` tokens.
- Row text uses `--font-small` and `--line-small` tokens.
- At 760px or below, each row becomes one column with a 4px label-to-content gap and 16px card side padding.

## Bilingual reports

Translate the heading, row labels, and row values through the report's established localization mechanism. Keep both locales equivalent and leave source screenshots unchanged.

## Acceptance checks

- One card contains every criterion row.
- No small introductory text appears beneath the heading.
- Labels align on desktop and stack above values on mobile.
- Long routes and caveats wrap without horizontal page overflow.
- All text remains selectable and meets the report foundation's contrast requirements.
