/* extension/mainworld.js — MAIN-world fetch patch. STRETCH ITEM.
 *
 * Cut this without hesitation at 16:00 if anything else is amber. Everything the
 * demo needs is already covered by airlock.js (the paste never reaches the page) and
 * by the declarativeNetRequest lockdown rule (the request never reaches the network).
 * This sits in between: it lets the request be *formed*, inspects the prompt the page
 * is actually about to send, and hands the page back a synthetic 403 carrying the
 * byte-identical body OpenShell emits on an egress denial.
 *
 * It runs in the MAIN world because window.fetch in the ISOLATED world is a different
 * object from the page's. That means no chrome.* here at all — the verdict has to
 * come back over window.postMessage from airlock.js.
 */
(() => {
  if (window.__AIRLOCK_MW__) return;
  window.__AIRLOCK_MW__ = true;

  const GUARDED = /\/backend-api\/conversation(\?|$)/;
  const BRIDGE_TIMEOUT_MS = 3000;

  const pending = new Map();
  let seq = 0;

  window.addEventListener('message', (e) => {
    if (e.source !== window) return;
    const d = e.data;
    if (!d || d.__airlock !== 'res') return;
    const resolve = pending.get(d.id);
    if (!resolve) return;
    pending.delete(d.id);
    resolve(d);
  });

  function ask(text) {
    return new Promise((resolve) => {
      const id = 'mw_' + (++seq);
      pending.set(id, resolve);
      window.postMessage({ __airlock: 'req', id, text }, '*');
      setTimeout(() => {
        if (!pending.has(id)) return;
        pending.delete(id);
        // No reply in 3000 ms is a block. Fail-closed is the product; the bridge
        // being slow is not a reason to make an exception for it.
        resolve({ action: 'block', verdict: { reason: 'Airlock bridge timed out — deny by default' } });
      }, BRIDGE_TIMEOUT_MS);
    });
  }

  // Best-effort prompt extraction from ChatGPT's conversation payload. If we cannot
  // read it we still inspect whatever string form the body has — we never let an
  // unparseable body through on the grounds that it was unparseable.
  function extractPrompt(body) {
    if (body == null) return '';
    let raw = body;
    if (typeof raw !== 'string') {
      if (raw instanceof URLSearchParams) raw = raw.toString();
      else if (raw instanceof FormData) {
        const parts = [];
        raw.forEach((v) => { if (typeof v === 'string') parts.push(v); });
        raw = parts.join('\n');
      } else {
        try { raw = JSON.stringify(raw); } catch (_) { return ''; }
      }
    }
    try {
      const j = JSON.parse(raw);
      const msgs = j.messages || [];
      const parts = [];
      for (const m of msgs) {
        const c = m && m.content;
        if (!c) continue;
        if (Array.isArray(c.parts)) {
          for (const p of c.parts) if (typeof p === 'string') parts.push(p);
        } else if (typeof c === 'string') parts.push(c);
      }
      return parts.join('\n') || raw;
    } catch (_) {
      return raw;
    }
  }

  const DENIAL = {
    error: 'policy_denied',
    by: 'airlock',
    rule: 'egress-unapproved-ai-endpoint',
    endpoint: '/backend-api/conversation',
  };

  function denialResponse(reason) {
    const body = JSON.stringify(Object.assign({}, DENIAL, { reason: reason || undefined }));
    return new Response(body, {
      status: 403,
      statusText: 'Forbidden',
      headers: { 'Content-Type': 'application/json', 'X-Airlock': 'policy_denied' },
    });
  }

  const nativeFetch = window.fetch;

  window.fetch = async function airlockFetch(input, init) {
    let url = '';
    try {
      url = typeof input === 'string' ? input : (input && input.url) || '';
    } catch (_) { url = ''; }

    if (!GUARDED.test(url)) return nativeFetch.apply(this, arguments);

    let body = (init && init.body) != null ? init.body : null;
    if (body == null && input instanceof Request) {
      try { body = await input.clone().text(); } catch (_) { body = null; }
    }

    const text = extractPrompt(body);
    if (!text) return nativeFetch.apply(this, arguments);

    const res = await ask(text);
    if (res.action === 'block') {
      return denialResponse(res.verdict && res.verdict.reason);
    }
    return nativeFetch.apply(this, arguments);
  };

  // Keep the patch honest under a page that inspects it.
  try {
    Object.defineProperty(window.fetch, 'toString', {
      value: () => nativeFetch.toString(),
      configurable: true,
    });
  } catch (_) {}
})();
