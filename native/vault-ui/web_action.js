(() => {
  const a = ARGUMENTS, s = globalThis.__lumenVault;
  if (!s || s.snapshot !== a.snapshot) return 'stale_snapshot';
  const get = id => { const x = s.ids.get(id); return x && s.visible(x.e) && s.shape(x.e) === x.shape ? x.e : null; };
  const same = url => { try { return new URL(url, location.href).origin === location.origin; } catch { return false; } };
  const set = (e, value) => {
    const proto = e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(e, value);
    e.dispatchEvent(new Event('input', {bubbles:true}));
    e.dispatchEvent(new Event('change', {bubbles:true}));
  };
  if (a.operation === 'web_login') {
    const u = get(a.username_node), p = get(a.password_node), b = get(a.submit_node);
    if (!u || !p || !b) return 'stale_snapshot';
    if (u.tagName !== 'INPUT' || !['text','email'].includes(u.type) ||
        p.tagName !== 'INPUT' || p.type !== 'password' ||
        !(b.tagName === 'BUTTON' || (b.tagName === 'INPUT' && ['submit','button'].includes(b.type)))) return 'invalid_login_controls';
    if (u.form !== p.form || p.form !== b.form || (p.form && !same(b.formAction || p.form.action))) return 'invalid_login_controls';
    // A GET form would put passwords into URLs/history; SPA buttons without forms are supported.
    if (p.form && b.type === 'submit' && (b.getAttribute('formmethod') || p.form.method).toLowerCase() !== 'post') return 'unsafe_login_form';
    const uShape = s.shape(u), pShape = s.shape(p), bShape = s.shape(b);
    set(u, a.username);
    if (!s.visible(p) || s.shape(p) !== pShape || !s.visible(b) || s.shape(b) !== bShape) return 'stale_snapshot';
    set(p, a.password);
    if (!s.visible(u) || s.shape(u) !== uShape || !s.visible(p) || s.shape(p) !== pShape || !s.visible(b) || s.shape(b) !== bShape) return 'stale_snapshot';
    globalThis.__lumenVault = null;
    b.click(); return 'login_submitted';
  }
  const e = get(a.node);
  if (!e) return 'stale_snapshot';
  if (a.operation === 'web_fill') {
    const ac = (e.autocomplete || '').toLowerCase().split(/\s+/);
    if (!['INPUT','TEXTAREA'].includes(e.tagName) ||
        (e.tagName === 'INPUT' && !['text','search','email','url','tel','number'].includes(e.type)) ||
        ac.some(x => ['username','current-password','new-password','one-time-code','cc-number','cc-csc'].includes(x)) ||
        e.form?.querySelector('input[type="password"]') || e.readOnly) return 'credential_field_requires_local_input';
    globalThis.__lumenVault = null; set(e, a.text); return 'text_entered';
  }
  if (e.tagName === 'A' && !same(e.href)) return 'cross_origin_blocked';
  if (e.tagName === 'INPUT' && !['button','submit','checkbox','radio'].includes(e.type)) return 'unsupported_control';
  if (!['A','BUTTON','INPUT'].includes(e.tagName) && e.getAttribute('role') !== 'button') return 'unsupported_control';
  if (e.form?.querySelector('input[type="password"]')) return 'use_web_login';
  globalThis.__lumenVault = null; e.click(); return 'clicked';
})()
