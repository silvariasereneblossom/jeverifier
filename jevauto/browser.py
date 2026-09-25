"""Playwright surface: enumerates interactive elements and acts on them by stable id."""

from __future__ import annotations

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from .model import Action, Element, Observation

# Tags each interactive element with a data-jev-id that persists while the DOM node lives,
# so an id Claude saw a moment ago still points at the same node after re-observation.
_COLLECT_JS = r"""
(maxEls) => {
  const SEL = 'a[href],button,input:not([type=hidden]),select,textarea,summary,' +
    '[role=button],[role=link],[role=checkbox],[role=radio],[role=tab],[role=menuitem],' +
    '[role=option],[role=switch],[role=combobox],[role=textbox],[role=searchbox],' +
    '[contenteditable=""],[contenteditable=true],[onclick],[tabindex]:not([tabindex="-1"])';
  window.__jevNext = window.__jevNext || 1;
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0;
  };
  const inView = el => {
    const r = el.getBoundingClientRect();
    return r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  };
  const nameOf = el => {
    const aria = el.getAttribute('aria-label');
    if (aria) return clean(aria);
    const by = el.getAttribute('aria-labelledby');
    if (by) {
      const t = by.split(/\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ');
      if (clean(t)) return clean(t);
    }
    if (el.labels && el.labels.length) return clean([...el.labels].map(l => l.innerText).join(' '));
    const t = clean(el.innerText || el.textContent);
    if (t) return t.slice(0, 120);
    return clean(el.getAttribute('alt') || el.getAttribute('title') ||
      el.querySelector('img[alt]')?.getAttribute('alt') || el.getAttribute('name') || '');
  };
  const roleOf = el => {
    const r = el.getAttribute('role');
    if (r) return r;
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'input') {
      const t = (el.type || 'text').toLowerCase();
      return ({checkbox: 'checkbox', radio: 'radio', submit: 'button', button: 'button',
               reset: 'button', search: 'searchbox', range: 'slider'})[t] || 'textbox';
    }
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'summary') return 'disclosure';
    if (el.isContentEditable) return 'textbox';
    return tag === 'button' ? 'button' : 'clickable';
  };
  const contextOf = el => {
    const box = el.closest('dialog,[role=dialog],[role=alertdialog],form,nav,header,footer,aside,[role=navigation],[role=search]');
    if (!box) return '';
    const kind = box.getAttribute('role') || box.tagName.toLowerCase();
    const label = box.getAttribute('aria-label') ||
      box.querySelector('h1,h2,h3,legend,[role=heading]')?.innerText || '';
    return clean(`${kind} ${label}`).slice(0, 80);
  };
  const out = [];
  for (const el of document.querySelectorAll(SEL)) {
    if (out.length >= maxEls) break;
    if (!visible(el)) continue;
    if (!el.dataset.jevId) el.dataset.jevId = 'e' + (window.__jevNext++);
    const attrs = {};
    const tag = el.tagName.toLowerCase();
    if (tag === 'input') attrs.type = (el.type || 'text').toLowerCase();
    if (tag === 'a' && el.getAttribute('href')) attrs.href = el.getAttribute('href');
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') attrs.disabled = 'true';
    if ('checked' in el && (el.type === 'checkbox' || el.type === 'radio')) attrs.checked = String(el.checked);
    else if (el.getAttribute('aria-checked')) attrs.checked = el.getAttribute('aria-checked');
    if (el.getAttribute('aria-expanded')) attrs.expanded = el.getAttribute('aria-expanded');
    let value = '';
    if (tag === 'select') value = el.selectedOptions[0]?.text || '';
    else if (tag === 'input' || tag === 'textarea') value = el.value || '';
    out.push({
      id: el.dataset.jevId, role: roleOf(el), name: nameOf(el), value: clean(value).slice(0, 200),
      placeholder: clean(el.getAttribute('placeholder') || ''), context: contextOf(el),
      attrs, in_view: inView(el),
    });
  }
  return {title: document.title, url: location.href,
          text: clean(document.body ? document.body.innerText : '').slice(0, 6000), elements: out};
}
"""


class BrowserSurface:
    kind = "browser"

    def __init__(self, headless: bool = False, max_elements: int = 400) -> None:
        self._pw: Playwright = sync_playwright().start()
        self._browser: Browser = self._pw.chromium.launch(headless=headless)
        self.page: Page = self._browser.new_page()
        self.max_elements = max_elements

    def navigate(self, target: str) -> None:
        if "://" not in target:
            target = "https://" + target
        self.page.goto(target, wait_until="domcontentloaded")
        self._settle()

    def observe(self) -> Observation:
        self._settle()
        raw = self.page.evaluate(_COLLECT_JS, self.max_elements)
        elements = [Element(**e) for e in raw["elements"]]
        return Observation(title=raw["title"], location=raw["url"], elements=elements, text=raw["text"])

    def perform(self, action: Action, element: Element, text: str | None) -> None:
        loc = self.page.locator(f'[data-jev-id="{element.id}"]').first
        if action == "click":
            loc.click(timeout=10_000)
        elif action == "fill":
            loc.fill(text or "", timeout=10_000)
        elif action == "select":
            loc.select_option(label=text, timeout=10_000)
        elif action == "press":
            loc.press(text or "Enter", timeout=10_000)
        elif action == "check":
            loc.check(timeout=10_000)
        elif action == "hover":
            loc.hover(timeout=10_000)
        else:
            raise ValueError(f"unsupported action {action!r}")
        self._settle()

    def _settle(self) -> None:
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10_000)
            self.page.wait_for_load_state("networkidle", timeout=3_000)
        except Exception:
            pass  # long-polling pages never go idle; the DOM is what we need

    def close(self) -> None:
        self._browser.close()
        self._pw.stop()
