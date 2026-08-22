/* extension/airlock.js — the interceptor.
 *
 * Runs at document_start, in all frames, in the ISOLATED world. Everything here is
 * arranged around one hard constraint: the paste handler must call preventDefault()
 * SYNCHRONOUSLY. There is no await above that line and there never can be — the
 * default action of a trusted paste event is performed the moment the handler
 * returns, so a single await hands the payload to the page.
 */
(() => {
  if (window.__AIRLOCK__) return;
  window.__AIRLOCK__ = true;

  const MAX_EDGE = 1024;          // B → A: the latency sweep must use this exact edge
  const JPEG_Q = 0.82;
  const CLIENT_TIMEOUT_MS = 2500;

  const log = (...a) => console.debug('[airlock]', ...a);
  const rid = () => 'r_' + Math.random().toString(16).slice(2, 8);

  // ======================================================================= transport
  // Two routes, in this order:
  //   viaWorker() — fetch happens in the service worker, which is exempt from Local
  //                 Network Access. This is the route that works on an https page.
  //   direct()    — content-script fetch with targetAddressSpace:'local'. Only viable
  //                 when the SW is gone (extension reloaded under an open tab) or on a
  //                 loopback page where LNA is not involved at all.
  function orphaned() {
    // Reading chrome.runtime.id throws once the extension context is invalidated.
    try { return !(chrome && chrome.runtime && chrome.runtime.id); } catch (_) { return true; }
  }

  function viaWorker(type, body) {
    return new Promise((resolve, reject) => {
      if (orphaned()) return reject(new Error('extension context invalidated'));
      let settled = false;
      try {
        chrome.runtime.sendMessage(Object.assign({ type }, body), (res) => {
          // lastError MUST be read, or Chrome logs an unchecked-error warning and the
          // promise silently never settles.
          const err = chrome.runtime.lastError;
          if (settled) return;
          settled = true;
          if (err) return reject(new Error(err.message));
          if (res === undefined) return reject(new Error('no response from service worker'));
          resolve(res);
        });
      } catch (e) {
        if (!settled) { settled = true; reject(e); }
      }
    });
  }

  async function direct(path, init) {
    const opts = Object.assign({
      credentials: 'omit',
      cache: 'no-store',
      // Chrome's LNA opt-in. Harmless where it is not needed, required where it is.
      targetAddressSpace: 'local',
    }, init || {});
    const res = await fetch('http://127.0.0.1:8787' + path, opts);
    return res.json();
  }

  function withTimeout(promise, ms, tag) {
    return new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error((tag || 'operation') + ' exceeded ' + ms + ' ms')), ms);
      promise.then((v) => { clearTimeout(t); resolve(v); },
                   (e) => { clearTimeout(t); reject(e); });
    });
  }

  // An MV3 service worker is killed after ~30 s idle. The first paste after that has to
  // wake it, and the wake occasionally loses the message — "Could not establish
  // connection. Receiving end does not exist." Measured on the box: a paste into a page
  // that had been sitting idle fail-closed in 0 ms with nothing reaching :8787, while the
  // very next paste succeeded. One retry after a short pause turns that into a hiccup
  // instead of a BLOCK card on the first paste of the demo.
  async function inspect(payload) {
    try {
      return await viaWorker('INSPECT', { payload });
    } catch (first) {
      log('service-worker route failed, retrying once after wake:', first.message);
      try {
        await new Promise((r) => setTimeout(r, 250));
        return await viaWorker('INSPECT', { payload });
      } catch (e) {
        log('service-worker route failed twice, falling back to direct fetch:', e.message);
        return direct('/v1/inspect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      }
    }
  }

  // One long-lived port for the things that stream: the console feed and the
  // sanctioned answer. Opened lazily so a page that never pastes never wakes the SW.
  let port = null;
  const answerHandlers = new Map();
  const wsSubscribers = new Set();

  function getPort() {
    if (port || orphaned()) return port;
    try {
      port = chrome.runtime.connect({ name: 'airlock' });
      port.onDisconnect.addListener(() => { port = null; });
      port.onMessage.addListener((msg) => {
        if (!msg) return;
        if (msg.type === 'WS') { wsSubscribers.forEach((fn) => fn(msg.frame)); return; }
        const h = answerHandlers.get(msg.rid);
        if (!h) return;
        if (msg.type === 'ANSWER_DELTA') h.onDelta && h.onDelta(msg.text);
        if (msg.type === 'ANSWER_DONE') { h.onDone && h.onDone(); answerHandlers.delete(msg.rid); }
        if (msg.type === 'ANSWER_ERROR') { h.onError && h.onError(msg.error); answerHandlers.delete(msg.rid); }
      });
    } catch (e) {
      log('connect failed', e.message);
      port = null;
    }
    return port;
  }

  window.__AIRLOCK_NET__ = {
    inspect,
    health: () => viaWorker('HEALTH', {}).catch(() => direct('/healthz').catch(() => null)),
    policy: () => viaWorker('POLICY', {}).catch(() => null),
    decisions: (limit) => viaWorker('DECISIONS', { limit }).catch(() => null),
    report: () => viaWorker('REPORT', {}).catch(() => null),
    feedback: (body) => viaWorker('FEEDBACK', { body }).catch(() => ({ ok: false })),
    lockdown: (on) => viaWorker('LOCKDOWN', { on }).catch(() => null),
    lockdownState: () => viaWorker('LOCKDOWN_STATE', {}).catch(() => ({ on: false })),
    onFrame(fn) { wsSubscribers.add(fn); const p = getPort(); if (p) p.postMessage({ type: 'STREAM_ON' }); },
    answer(prompt, decisionId, handlers) {
      const p = getPort();
      const id = rid();
      if (!p) { handlers.onError && handlers.onError('service worker unavailable'); return; }
      answerHandlers.set(id, handlers);
      p.postMessage({ type: 'ANSWER', rid: id, prompt, decision_id: decisionId });
    },
  };

  // ================================================================ image downscale
  // Long edge <= 1024 px, JPEG q=0.82, base64 without the data-URI prefix. Done here
  // rather than server-side so that the bytes never exist at full resolution outside
  // this tab, and so A's latency sweep can use an identical input distribution.
  async function shrinkToB64(file, maxEdge) {
    const edge = maxEdge || MAX_EDGE;
    const bmp = await createImageBitmap(file);
    const scale = Math.min(1, edge / Math.max(bmp.width, bmp.height));
    const w = Math.max(1, Math.round(bmp.width * scale));
    const h = Math.max(1, Math.round(bmp.height * scale));
    const canvas = new OffscreenCanvas(w, h);
    const ctx = canvas.getContext('2d');
    ctx.drawImage(bmp, 0, 0, w, h);
    bmp.close();
    const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality: JPEG_Q });
    const buf = new Uint8Array(await blob.arrayBuffer());
    // Chunked btoa: String.fromCharCode.apply over a megabyte-scale array blows the
    // argument limit and throws RangeError.
    let bin = '';
    const CHUNK = 0x8000;
    for (let i = 0; i < buf.length; i += CHUNK) {
      bin += String.fromCharCode.apply(null, buf.subarray(i, i + CHUNK));
    }
    return { mime: 'image/jpeg', w, h, b64: btoa(bin) };
  }

  // ==================================================================== replay path
  // Never assign .value directly: React installs a value setter on the instance and
  // reads its own shadow copy, so a direct assignment updates the DOM and not the
  // component, and the next render wipes it.
  function setNativeValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }

  let replaying = false;

  function replayText(target, text) {
    if (!text) return;
    replaying = true;
    try {
      // execCommand is deprecated and is still the only thing that produces a real
      // insertion the page's own framework observes. Synthetic ClipboardEvents are
      // isTrusted:false, perform no default action, and fail silently.
      const ok = document.execCommand('insertText', false, text);
      if (!ok && target && ('value' in target)) {
        const start = target.selectionStart != null ? target.selectionStart : target.value.length;
        const end = target.selectionEnd != null ? target.selectionEnd : start;
        setNativeValue(target, target.value.slice(0, start) + text + target.value.slice(end));
        const caret = start + text.length;
        try { target.setSelectionRange(caret, caret); } catch (_) {}
      }
    } catch (e) {
      log('replay failed', e);
    } finally {
      // Give the page's own input handling a turn before we re-arm.
      setTimeout(() => { replaying = false; }, 0);
    }
  }

  // ======================================================================== the gate
  function failClosed(requestId, why) {
    return {
      schema: 'airlock.error.v1',
      error: 'policy_denied',
      action: 'block',
      label: 'airlock_unavailable',
      severity: 'HIGH',
      reason: why || 'Inspector unreachable — deny by default',
      request_id: requestId,
      evidence_spans: [],
      evidence_verified: false,
      p_block: 1,
      threshold: 0.55,
      tier: 'T0',
      model: 'none',
      latency_ms: 0,
      bytes_egressed: 0,
      policy_clause_id: 'NONE',
      policy_clause_text: '',
      decision_id: null,
      score_details: null,
    };
  }

  function currentMode() {
    return (window.__AIRLOCK_MODE__ && window.__AIRLOCK_MODE__.mode) || 'balanced';
  }

  async function gate({ text, html, images, modality }) {
    const requestId = rid();
    const t0 = performance.now();
    const payload = {
      schema: 'airlock.inspect.v1',
      request_id: requestId,
      ts: Date.now(),
      origin: location.origin,
      url: location.href,
      text: text || '',
      html: html || '',
      images: images || [],
      mode: currentMode(),
      threshold: null,
    };
    try {
      const v = await withTimeout(inspect(payload), CLIENT_TIMEOUT_MS, 'inspect');
      if (!v || !v.action) return failClosed(requestId, 'Inspector returned no verdict — deny by default');
      if (v.latency_ms == null) v.latency_ms = Math.round(performance.now() - t0);
      v.modality = v.modality || modality;
      return v;
    } catch (e) {
      // Every throw lands here and every throw is a BLOCK. Deny-by-default is the
      // product, so it has to be the failure mode too.
      return failClosed(requestId, e && e.name === 'AbortError'
        ? 'Inspector exceeded 2500 ms — deny by default'
        : (e && e.message) || 'Inspector unreachable — deny by default');
    }
  }

  function show(v, extra) {
    const ui = window.__AIRLOCK_UI__;
    if (!ui) { log('verdict (no ui):', v); return; }
    ui.verdict(v, Object.assign({ origin: location.origin, host: location.host }, extra || {}));
  }

  // ==================================================================== paste handler
  async function handle(target, text, html, files, modality) {
    window.__AIRLOCK_UI__ && window.__AIRLOCK_UI__.scanning({ modality });

    let images = [];
    if (files && files.length) {
      try {
        // One image. --limit-mm-per-prompt caps the server side too; this is the
        // client-side half of the same rule.
        images = [await shrinkToB64(files[0], MAX_EDGE)];
      } catch (e) {
        log('image downscale failed', e);
        const v = failClosed(rid(), 'Image could not be decoded — deny by default');
        show(v, { payloadText: text || '' });
        return;
      }
    }

    const v = await gate({ text, html, images, modality });
    show(v, { payloadText: text || '', images });

    if (v.action !== 'block') {
      replayText(target, text);
    }
    // On block we simply never replay. The characters were removed from the event by
    // preventDefault() and were never handed to the page: bytes_egressed is 0 and
    // that is literally true, not a claim.
  }

  function onPaste(e) {
    if (replaying) return;
    const dt = e.clipboardData;
    if (!dt) return;

    // --- everything above the preventDefault must be synchronous ------------------
    const text = dt.getData('text/plain') || '';
    const html = dt.getData('text/html') || '';
    const files = [];
    if (dt.items) {
      for (const item of dt.items) {
        if (item.kind === 'file' && item.type.startsWith('image/')) {
          const f = item.getAsFile();
          if (f) files.push(f);
        }
      }
    }
    if (!text && !files.length) return;

    e.preventDefault();
    e.stopImmediatePropagation();
    // --- from here on, async is fine ---------------------------------------------

    handle(e.target, text, html, files, files.length ? 'image' : 'text');
  }

  // Second net. If a site's framework somehow gets a paste through — a synthetic
  // insertion, a shadow-root retarget, a composition path — beforeinput still fires
  // with insertFromPaste and we can still stop the characters from landing.
  function onBeforeInput(e) {
    if (replaying) return;
    if (e.inputType !== 'insertFromPaste' && e.inputType !== 'insertFromPasteAsQuotation') return;
    const text = (e.data != null ? e.data : '') ||
                 (e.dataTransfer && e.dataTransfer.getData('text/plain')) || '';
    if (!text) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    handle(e.target, text, '', [], 'text');
  }

  function onDrop(e) {
    if (replaying) return;
    const dt = e.dataTransfer;
    if (!dt) return;
    const text = dt.getData('text/plain') || '';
    const files = [];
    for (const f of (dt.files || [])) if (f.type.startsWith('image/')) files.push(f);
    if (!text && !files.length) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    handle(e.target, text, dt.getData('text/html') || '', files, files.length ? 'image' : 'text');
  }

  function onChange(e) {
    const el = e.target;
    if (!el || el.tagName !== 'INPUT' || el.type !== 'file') return;
    const files = [];
    for (const f of (el.files || [])) if (f.type.startsWith('image/')) files.push(f);
    if (!files.length) return;
    // A file input cannot be un-set from here without clobbering the page's state,
    // so on a block we clear it — that is the only way to stop the upload.
    handleFileInput(el, files);
  }

  async function handleFileInput(el, files) {
    window.__AIRLOCK_UI__ && window.__AIRLOCK_UI__.scanning({ modality: 'image' });
    let images = [];
    try {
      images = [await shrinkToB64(files[0], MAX_EDGE)];
    } catch (_) {
      show(failClosed(rid(), 'Image could not be decoded — deny by default'), {});
      el.value = '';
      return;
    }
    const v = await gate({ text: '', html: '', images, modality: 'image' });
    show(v, { payloadText: '', images });
    if (v.action === 'block') {
      el.value = '';
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  // Bind to `document`, in the capture phase, at document_start. Never to a selector:
  // ProseMirror, Lexical and every React composer rebuild their nodes constantly, and
  // a selector-bound listener is attached to a node that no longer exists by the time
  // a human pastes into it.
  document.addEventListener('paste', onPaste, true);
  document.addEventListener('beforeinput', onBeforeInput, true);
  document.addEventListener('drop', onDrop, true);
  document.addEventListener('change', onChange, true);

  // MAIN-world bridge: mainworld.js patches window.fetch and asks us for a verdict
  // over postMessage. See mainworld.js for why the answer has to come from here.
  window.addEventListener('message', async (e) => {
    if (e.source !== window) return;
    const d = e.data;
    if (!d || d.__airlock !== 'req') return;
    const v = await gate({ text: d.text || '', html: '', images: [], modality: 'text' });
    window.postMessage({ __airlock: 'res', id: d.id, action: v.action, verdict: v }, '*');
    if (v.action === 'block') show(v, { payloadText: d.text || '' });
  });

  log('armed at', location.href, '· mode', currentMode());

  // Prove the SW route works the moment the page loads, so a broken transport shows
  // up in the console before a human discovers it mid-demo.
  viaWorker('PING', {}).then((r) => log('sw ping', r)).catch((e) => log('sw ping failed', e.message));
})();
