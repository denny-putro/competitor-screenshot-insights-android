# Screenshot viewer contract

## Include

```html
<link rel="stylesheet" href="components/screenshot-viewer.css" />
<!-- page content -->
<script src="components/screenshot-viewer.js"></script>
```

For standalone HTML opened through `file://`, keep the CSS link but inline the complete contents of `assets/screenshot-viewer.js` in a normal `<script>` block. Local report browsers may display external CSS while declining to execute a local external script, leaving screenshots visible but non-interactive.

## Image markup

```html
<img
  src="assets/example.png"
  alt="Trip.com 航班搜索结果首屏"
  loading="lazy"
  data-screenshot-viewer
  data-screenshot-title="Trip.com · 结果首屏"
  data-screenshot-label="结果首屏"
/>
```

For a known long screenshot, add:

```html
data-screenshot-long="true"
```

The script upgrades marked images into the complete component. It also observes later DOM insertions, so marked images added by a report's rendering script receive the same component.

## Fixed behavior

- Outer width: `258px`; use available container width only when it is narrower.
- Ordinary screenshot: show the full image at its natural aspect ratio.
- Long screenshot: use a `558px`-high internally scrollable preview, begin at the top, keep a subtle bottom fade until the scroll reaches the end, and display `长截图`.
- Opening: clicking the image surface, pressing Enter/Space on it, or clicking `查看大图` opens one shared dialog.
- Focused dialog: use a `375px` width, shrink only when the viewport is narrower, reset its scroll position to the top, show the original image first, and place the title, actions, and status below the image.
- Actions: `复制图片`, `下载`, and close. Copy targets the image bitmap rather than the URL. When the browser blocks bitmap clipboard access, show a clear failure message and keep Download available.
- Closing: close button, Escape, or a true backdrop click.

Do not modify the bundled CSS or JS per report. Change the skill assets only when the component specification itself changes.

## Bilingual reports

When a report provides `window.ReportI18n.tLegacy`, the viewer uses it for its built-in controls and labels. Provide Chinese and English equivalents for `截图查看器`, `截图`, `关闭`, `复制图片`, `下载`, `长截图`, `查看完整长截图`, `查看大图`, `复制中…`, `已复制`, `图片已复制到剪贴板`, `复制失败`, and `当前浏览器无法复制图片，请使用下载`.
