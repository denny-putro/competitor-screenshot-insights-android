(() => {
  "use strict";

  const STORAGE_KEY = "codex-report-locale";
  const root = document.documentElement;
  const navigation = document.querySelector("[data-report-navigation]");
  const translations = window.reportTranslations || {};
  const supportedLocales = Object.keys(translations).filter((locale) => locale === "zh-CN" || locale === "en");

  if (!navigation || supportedLocales.length === 0) return;

  const lookup = (locale, key) => key.split(".").reduce((value, part) => value && value[part], translations[locale]);
  const translate = (key, locale = root.dataset.reportLocale) => lookup(locale, key) || lookup(navigation.dataset.defaultLocale, key) || key;
  const translateLegacy = (value, locale = root.dataset.reportLocale) => {
    if (locale !== "en" || typeof value !== "string") return value;
    return Object.entries(translations.legacy || {})
      .sort(([left], [right]) => right.length - left.length)
      .reduce((translated, [source, target]) => translated.split(source).join(target), value);
  };
  const originalText = new WeakMap();
  const originalAttributes = new WeakMap();

  function applyLegacyDocument(locale) {
    if (!translations.legacy) return;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        return parent && !parent.closest("script, style") && node.nodeValue.trim()
          ? NodeFilter.FILTER_ACCEPT
          : NodeFilter.FILTER_REJECT;
      }
    });
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
    textNodes.forEach((node) => {
      if (!originalText.has(node)) originalText.set(node, node.nodeValue);
      node.nodeValue = translateLegacy(originalText.get(node), locale);
    });
    document.querySelectorAll("[alt], [title], [aria-label], [data-screenshot-title], [data-screenshot-label]").forEach((element) => {
      let originals = originalAttributes.get(element);
      if (!originals) { originals = {}; originalAttributes.set(element, originals); }
      ["alt", "title", "aria-label", "data-screenshot-title", "data-screenshot-label"].forEach((attribute) => {
        if (!element.hasAttribute(attribute)) return;
        if (!(attribute in originals)) originals[attribute] = element.getAttribute(attribute);
        element.setAttribute(attribute, translateLegacy(originals[attribute], locale));
      });
    });
  }

  function applyStatic(locale) {
    document.querySelectorAll("[data-i18n]").forEach((element) => { element.textContent = translate(element.dataset.i18n, locale); });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => { element.setAttribute("aria-label", translate(element.dataset.i18nAriaLabel, locale)); });
    document.querySelectorAll("[data-i18n-title]").forEach((element) => { element.setAttribute("title", translate(element.dataset.i18nTitle, locale)); });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => { element.setAttribute("placeholder", translate(element.dataset.i18nPlaceholder, locale)); });
    const title = lookup(locale, "report.title");
    if (title) document.title = title;
  }

  function setLocale(locale, { persist = true } = {}) {
    if (!supportedLocales.includes(locale)) return;
    root.lang = locale;
    root.dataset.reportLocale = locale;
    navigation.querySelectorAll("[data-report-locale]").forEach((button) => {
      const active = button.dataset.reportLocale === locale;
      button.setAttribute("aria-pressed", String(active));
    });
    applyStatic(locale);
    applyLegacyDocument(locale);
    if (persist) {
      try { localStorage.setItem(STORAGE_KEY, locale); } catch (_) {}
    }
    document.dispatchEvent(new CustomEvent("reportlocalechange", { detail: { locale } }));
  }

  navigation.querySelectorAll("[data-report-locale]").forEach((button) => {
    button.addEventListener("click", () => setLocale(button.dataset.reportLocale));
  });

  let savedLocale;
  try { savedLocale = localStorage.getItem(STORAGE_KEY); } catch (_) {}
  setLocale(supportedLocales.includes(savedLocale) ? savedLocale : navigation.dataset.defaultLocale || supportedLocales[0], { persist: false });
  const observer = new MutationObserver((mutations) => {
    if (mutations.some((mutation) => mutation.addedNodes.length)) applyLegacyDocument(root.dataset.reportLocale);
  });
  observer.observe(document.body, { childList: true, subtree: true });
  window.ReportI18n = { get locale() { return root.dataset.reportLocale; }, setLocale, t: translate, tLegacy: translateLegacy, applyStatic };
})();
