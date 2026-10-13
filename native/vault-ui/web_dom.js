// Runs only in Qt's isolated ApplicationWorld; never accepts executable model text.
(() => {
  const visible = e => e && e.isConnected && !e.disabled && e.getClientRects().length &&
    getComputedStyle(e).visibility === 'visible' && getComputedStyle(e).display !== 'none';
  const label = e => (e.getAttribute('aria-label') ||
    Array.from(e.labels || []).map(x => x.innerText).join(' ') ||
    (e.tagName === 'INPUT' ? e.getAttribute('placeholder') || '' : e.innerText) || '').trim().slice(0, 160);
  const shape = e => JSON.stringify([e.tagName, e.type, e.getAttribute('role'), label(e),
    e.getAttribute('autocomplete'), e.getAttribute('href'), e.form?.action, e.form?.method]);
  const elements = Array.from(document.querySelectorAll('input,textarea,button,select,a[href],[role="button"]'))
    .filter(e => visible(e) && e.type !== 'hidden').slice(0, 80);
  const ids = new Map(elements.map((e, i) => [String(i + 1), {e, shape: shape(e)}]));
  const state = {snapshot: SNAPSHOT, ids, visible, shape};
  globalThis.__lumenVault = state;
  // Clone only for text extraction: no live input values, scripts, frames, or hidden content.
  const parts = [];
  const walk = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
  let n, length = 0, visited = 0;
  while ((n = walk.nextNode()) && visited++ < 20000 && length < 12000) {
    const p = n.parentElement;
    if (!p || p.closest('script,style,noscript,input,textarea,select,iframe,[hidden],[aria-hidden="true"]') || !visible(p)) continue;
    const text = n.textContent.trim();
    if (text) { parts.push(text); length += text.length; }
  }
  return JSON.stringify({snapshot: SNAPSHOT, text: parts.join('\n').slice(0, 12000),
    truncated: length >= 12000 || visited >= 20000 || elements.length >= 80,
    nodes: elements.map((e, i) => ({node: String(i+1), tag: e.tagName.toLowerCase(),
      type: e.type || '', role: e.getAttribute('role') || '', label: label(e),
      autocomplete: e.getAttribute('autocomplete') || ''}))});
})()
