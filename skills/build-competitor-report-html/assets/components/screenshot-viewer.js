(() => {
  "use strict";

  const SELECTOR = "img[data-screenshot-viewer]";
  const localeText = (value) => window.ReportI18n?.tLegacy(value) || value;
  let active = null;
  let dialog = null;
  let dialogImage = null;
  let dialogTitle = null;
  let dialogBody = null;
  let copyButton = null;
  let downloadLink = null;
  let status = null;

  function filenameFromSource(source) {
    try {
      const pathname = new URL(source, window.location.href).pathname;
      return decodeURIComponent(pathname.split("/").pop() || "screenshot.png");
    } catch {
      return "screenshot.png";
    }
  }

  function ensureDialog() {
    if (dialog) return;
    dialog = document.createElement("dialog");
    dialog.className = "sv-dialog";
    dialog.setAttribute("aria-label", localeText("截图查看器"));
    dialog.innerHTML = `
      <div class="sv-dialog__body" tabindex="0">
        <img class="sv-dialog__image" src="" alt="" />
      </div>
      <footer class="sv-dialog__bar">
        <div class="sv-dialog__heading">
          <strong class="sv-dialog__title">${localeText("截图")}</strong>
          <button class="sv-dialog__button sv-dialog__close" type="button" aria-label="${localeText("关闭")}">×</button>
        </div>
        <div class="sv-dialog__actions">
          <button class="sv-dialog__button sv-dialog__copy" type="button">${localeText("复制图片")}</button>
          <a class="sv-dialog__download" href="#" download>${localeText("下载")}</a>
        </div>
        <div class="sv-dialog__status" aria-live="polite"></div>
      </footer>
    `;
    document.body.append(dialog);
    dialogImage = dialog.querySelector(".sv-dialog__image");
    dialogTitle = dialog.querySelector(".sv-dialog__title");
    dialogBody = dialog.querySelector(".sv-dialog__body");
    copyButton = dialog.querySelector(".sv-dialog__copy");
    downloadLink = dialog.querySelector(".sv-dialog__download");
    status = dialog.querySelector(".sv-dialog__status");
    const closeButton = dialog.querySelector(".sv-dialog__close");

    closeButton.addEventListener("click", () => dialog.close());
    copyButton.addEventListener("click", copyActiveImage);
    dialog.addEventListener("click", (event) => {
      if (event.target !== dialog) return;
      const bounds = dialog.getBoundingClientRect();
      const outside =
        event.clientX < bounds.left ||
        event.clientX > bounds.right ||
        event.clientY < bounds.top ||
        event.clientY > bounds.bottom;
      if (outside) dialog.close();
    });
    dialog.addEventListener("close", () => {
      status.textContent = "";
      copyButton.disabled = false;
      copyButton.textContent = localeText("复制图片");
      if (active?.frame) active.frame.focus({ preventScroll: true });
      active = null;
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && dialog.open) dialog.close();
    });
  }

  function setLongState(component, isLong) {
    component.figure.dataset.svLong = String(isLong);
    component.label.textContent = isLong
      ? localeText("长截图")
      : component.image.dataset.screenshotLabel || localeText("截图");
    component.frame.setAttribute(
      "aria-label",
      `${localeText(isLong ? "查看完整长截图" : "查看大图")}：${component.title}`,
    );
    updateFade(component);
  }

  function updateFade(component) {
    if (component.figure.dataset.svLong !== "true") {
      component.figure.classList.remove("sv-at-end");
      return;
    }
    const remaining =
      component.scroll.scrollHeight -
      component.scroll.scrollTop -
      component.scroll.clientHeight;
    component.figure.classList.toggle("sv-at-end", remaining <= 3);
  }

  function openComponent(component) {
    ensureDialog();
    active = component;
    const source = component.image.currentSrc || component.image.src;
    dialogTitle.textContent = component.title;
    dialogImage.src = source;
    dialogImage.alt = component.image.alt || component.title;
    downloadLink.href = source;
    downloadLink.download = filenameFromSource(source);
    status.textContent = "";
    copyButton.disabled = false;
    copyButton.textContent = localeText("复制图片");
    dialogBody.scrollTop = 0;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function mount(image) {
    if (!(image instanceof HTMLImageElement) || image.closest(".sv-viewer")) return;

    const title =
      image.dataset.screenshotTitle ||
      image.alt ||
      filenameFromSource(image.currentSrc || image.src);
    const figure = document.createElement("figure");
    figure.className = "sv-viewer";
    const frame = document.createElement("div");
    frame.className = "sv-viewer__frame";
    frame.setAttribute("role", "button");
    frame.setAttribute("tabindex", "0");
    const scroll = document.createElement("div");
    scroll.className = "sv-viewer__scroll";
    const fade = document.createElement("span");
    fade.className = "sv-viewer__fade";
    fade.setAttribute("aria-hidden", "true");
    const toolbar = document.createElement("figcaption");
    toolbar.className = "sv-viewer__toolbar";
    const label = document.createElement("span");
    label.className = "sv-viewer__label";
    const openButton = document.createElement("button");
    openButton.className = "sv-viewer__open";
    openButton.type = "button";
    openButton.textContent = localeText("查看大图");
    openButton.setAttribute("aria-label", `${localeText("查看大图")}：${title}`);

    image.before(figure);
    image.classList.add("sv-viewer__image");
    image.removeAttribute("data-screenshot-viewer");
    scroll.append(image);
    frame.append(scroll, fade);
    toolbar.append(label, openButton);
    figure.append(frame, toolbar);

    const component = { figure, frame, scroll, image, label, title };
    const explicitLong = image.dataset.screenshotLong;
    const resolveLong = () => {
      const automatic =
        image.naturalWidth > 0 && image.naturalHeight / image.naturalWidth > 2.5;
      setLongState(component, explicitLong === "true" || (!explicitLong && automatic));
    };

    resolveLong();
    if (!image.complete) image.addEventListener("load", resolveLong, { once: true });
    scroll.addEventListener("scroll", () => updateFade(component), { passive: true });
    frame.addEventListener("click", () => openComponent(component));
    frame.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      openComponent(component);
    });
    openButton.addEventListener("click", () => openComponent(component));
  }

  function mountAll(root = document) {
    if (root.matches?.(SELECTOR)) mount(root);
    root.querySelectorAll?.(SELECTOR).forEach(mount);
  }

  async function blobFromImage(image, source) {
    try {
      const response = await fetch(source);
      if (response.ok) {
        const sourceBlob = await response.blob();
        if (sourceBlob.type === "image/png") return sourceBlob;
        const bytes = await sourceBlob.arrayBuffer();
        if (source.toLowerCase().split(/[?#]/)[0].endsWith(".png")) {
          return new Blob([bytes], { type: "image/png" });
        }
      }
    } catch {
      // Local file pages may block fetch; canvas is the next option.
    }

    if (!image.complete) await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("canvas-unavailable");
    context.drawImage(image, 0, 0);
    return new Promise((resolve, reject) => {
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error("image-encoding-failed"))),
        "image/png",
      );
    });
  }

  async function legacyCopyImage(source, alt) {
    const staging = document.createElement("div");
    staging.contentEditable = "true";
    staging.style.cssText =
      "position:fixed;left:-10000px;top:0;width:1px;height:1px;overflow:hidden;";
    const image = document.createElement("img");
    image.src = source;
    image.alt = alt;
    staging.append(image);
    document.body.append(staging);
    try {
      await image.decode();
      const range = document.createRange();
      range.selectNode(image);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      const copied = document.execCommand("copy");
      selection.removeAllRanges();
      return copied;
    } finally {
      staging.remove();
    }
  }

  async function copyActiveImage() {
    if (!active) return;
    const source = active.image.currentSrc || active.image.src;
    copyButton.disabled = true;
    copyButton.textContent = localeText("复制中…");
    status.textContent = "";
    try {
      let copied = false;
      if (navigator.clipboard?.write && window.ClipboardItem) {
        try {
          const blob = await blobFromImage(active.image, source);
          await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
          copied = true;
        } catch {
          copied = await legacyCopyImage(source, active.image.alt || active.title);
        }
      } else {
        copied = await legacyCopyImage(source, active.image.alt || active.title);
      }
      if (!copied) throw new Error("copy-not-supported");
      copyButton.textContent = localeText("已复制");
      status.textContent = localeText("图片已复制到剪贴板");
    } catch {
      copyButton.textContent = localeText("复制失败");
      status.textContent = localeText("当前浏览器无法复制图片，请使用下载");
    } finally {
      window.setTimeout(() => {
        if (!dialog?.open) return;
        copyButton.disabled = false;
        copyButton.textContent = localeText("复制图片");
      }, 1600);
    }
  }

  const start = () => {
    ensureDialog();
    mountAll();
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === Node.ELEMENT_NODE) mountAll(node);
        });
      });
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  };

  window.ScreenshotViewer = { mountAll };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
