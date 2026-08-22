/* extension/sw.js — Airlock MV3 service worker.
 *
 * The service worker is the ONLY thing in this extension that touches the network.
 * That is not a style choice: fetch() to 127.0.0.1 from a content script running on
 * an https:// page is subject to Local Network Access; from the service worker it is
 * not. Every rule below exists because breaking it produces a symptom that looks
 * exactly like "the model is slow".
 *
 *   1. Every onMessage listener ends with `return true`. Missing it is the #1 MV3
 *      bug: sendResponse is discarded, the content script times out at 2500 ms and
 *      renders a fail-closed BLOCK that looks like a wedged GPU.
 *   2. Nothing is kept in module scope that matters across a wake. The SW is killed
 *      after ~30 s idle. Anything durable goes to chrome.storage.session.
 */

const BASE = 'http://127.0.0.1:8787';
const WS_URL = 'ws://127.0.0.1:8787/v1/stream';
const INSPECT_TIMEOUT_MS = 2500;

// vLLM Prometheus endpoints. Read-only GETs — B and C consume :8000/:8001 over HTTP
// only, and never start, stop or restart a GPU process (NFR-S1).
const METRICS = {
  kv_cache_text:   'http://127.0.0.1:8000/metrics',
  kv_cache_vision: 'http://127.0.0.1:8001/metrics',
};

// ---------------------------------------------------------------- fail-closed body
function denied(reason, requestId, code) {
  return {
    schema: 'airlock.error.v1',
    error: 'policy_denied',
    code: code || 0,
    label: 'airlock_unavailable',
    action: 'block',
    severity: 'HIGH',
    reason: reason || 'Inspector unreachable — deny by default',
    request_id: requestId || 'r_unknown',
    evidence_spans: [],
    evidence_verified: false,
    p_block: 1,
    threshold: 0.55,
    tier: 'T0',
    model: 'none',
    modality: 'text',
    latency_ms: 0,
    bytes_egressed: 0,
    policy_clause_id: 'NONE',
    policy_clause_text: '',
    decision_id: null,
    score_details: null,
  };
}

// --------------------------------------------------------------------- the hot call
async function inspect(payload) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), INSPECT_TIMEOUT_MS);
  try {
    const res = await fetch(BASE + '/v1/inspect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: ac.signal,
      credentials: 'omit',
      cache: 'no-store',
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      // A block is not an HTTP error, so any non-200 here is a real failure and the
      // server has already shaped it fail-closed. Trust its body if it gave us one.
      return body && body.action ? body
        : denied('Inspector returned HTTP ' + res.status, payload.request_id, res.status);
    }
    if (!body || body.schema !== 'airlock.verdict.v1') {
      return denied('Inspector returned an unrecognised body', payload.request_id, 200);
    }
    return body;
  } catch (e) {
    const why = e && e.name === 'AbortError'
      ? 'Inspector exceeded 2500 ms — deny by default'
      : 'Inspector unreachable — deny by default';
    return denied(why, payload.request_id, 0);
  } finally {
    clearTimeout(timer);
  }
}

async function getJSON(path, ms) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), ms || 1500);
  try {
    const res = await fetch(BASE + path, { signal: ac.signal, credentials: 'omit', cache: 'no-store' });
    return await res.json();
  } catch (_) {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function postJSON(path, body, ms) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), ms || 3000);
  try {
    const res = await fetch(BASE + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ac.signal,
      credentials: 'omit',
    });
    return await res.json();
  } catch (_) {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

// ------------------------------------------------------------------------- warm-up
// Fired on install and on every browser start. Two jobs: prove the LNA-exempt path
// works before a human needs it to, and let the server do its first-call torch
// compile on our time rather than on stage.
async function warm() {
  const h = await getJSON('/healthz', 3000);
  await chrome.storage.session.set({ health: h, healthAt: Date.now() });
  console.log('[airlock][sw] warm →', h);
  return h;
}

chrome.runtime.onInstalled.addListener(() => { warm(); });
chrome.runtime.onStartup.addListener(() => { warm(); });

// -------------------------------------------------------------------- message bus
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    switch (msg && msg.type) {
      case 'PING':
        sendResponse({ ok: true, pong: Date.now(), health: await warm() });
        break;
      case 'INSPECT':
        sendResponse(await inspect(msg.payload));
        break;
      case 'HEALTH':
        sendResponse(await getJSON('/healthz', 1500));
        break;
      case 'POLICY':
        sendResponse(await getJSON('/v1/policy', 1500));
        break;
      case 'DECISIONS':
        sendResponse(await getJSON('/v1/decisions?limit=' + (msg.limit || 50), 2000));
        break;
      case 'REPORT':
        sendResponse(await getJSON('/v1/report', 2000));
        break;
      case 'FEEDBACK':
        sendResponse(await postJSON('/v1/feedback', msg.body, 3000));
        break;
      case 'LOCKDOWN':
        sendResponse(await setLockdown(!!msg.on));
        break;
      case 'LOCKDOWN_STATE':
        sendResponse({ on: await lockdownState() });
        break;
      case 'RELOAD_TABS':          // dev-only helper, see note at the bottom
        sendResponse(await reloadAirlockTabs());
        break;
      default:
        sendResponse({ ok: false, error: 'unknown message type' });
    }
  })();
  return true;               // <-- load-bearing. Do not remove. Do not "tidy".
});

// -------------------------------------------------- long-lived ports: WS + answers
const ports = new Set();

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== 'airlock') return;
  ports.add(port);
  port.onDisconnect.addListener(() => {
    ports.delete(port);
    if (ports.size === 0) { closeStream(); stopMetrics(); }
  });
  port.onMessage.addListener((msg) => {
    if (!msg) return;
    if (msg.type === 'ANSWER') streamAnswer(port, msg);
    if (msg.type === 'STREAM_ON') { openStream(); startMetrics(); }
  });
  openStream();
  startMetrics();
});

function fanout(frame) {
  for (const p of ports) {
    try { p.postMessage({ type: 'WS', frame }); } catch (_) { ports.delete(p); }
  }
}

// ------------------------------------------------------------------ KV cache gauges
// The server-side ConsoleHub can emit {"type":"metric"} frames, but nothing currently
// calls its set_metric() — so left alone the gauges sit at "—" all day. Scrape the two
// vLLM /metrics endpoints ourselves instead. If a real server metric frame ever shows
// up we stand down within 6 s and let it win, so this never fights the server.
let lastServerMetricAt = 0;
let metricTimer = null;

// vLLM renamed this counter: newer builds expose vllm:kv_cache_usage_perc, older ones
// vllm:gpu_cache_usage_perc. Accept either. The box's live :8000 reports the former.
const KV_RE = /^vllm:(?:kv|gpu)_cache_usage_perc\{[^}]*\}\s+([0-9.eE+-]+)/m;

async function scrapeKV(url) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 800);
  try {
    const res = await fetch(url, { signal: ac.signal, cache: 'no-store', credentials: 'omit' });
    if (!res.ok) return null;
    const m = KV_RE.exec(await res.text());
    if (!m) return null;
    const v = Number(m[1]);
    return Number.isFinite(v) ? v : null;
  } catch (_) {
    return null;                 // server not up, or not this one's turn today
  } finally {
    clearTimeout(timer);
  }
}

async function pollMetrics() {
  if (ports.size === 0) return;
  if (Date.now() - lastServerMetricAt < 6000) return;   // the server is doing it
  const [text, vision] = await Promise.all([
    scrapeKV(METRICS.kv_cache_text),
    scrapeKV(METRICS.kv_cache_vision),
  ]);
  const kv = {};
  if (text !== null) kv.kv_cache_text = text;
  if (vision !== null) kv.kv_cache_vision = vision;
  if (Object.keys(kv).length) fanout({ type: 'metric', kv, src: 'scrape' });
}

function startMetrics() {
  if (metricTimer) return;
  metricTimer = setInterval(pollMetrics, 2000);
  pollMetrics();
}

function stopMetrics() {
  clearInterval(metricTimer);
  metricTimer = null;
}

let ws = null;
let wsBackoff = 250;
let wsTimer = null;

function openStream() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  try {
    ws = new WebSocket(WS_URL);
  } catch (_) {
    return scheduleReconnect();
  }
  ws.onopen = () => {
    wsBackoff = 250;
    fanout({ type: 'ws_state', state: 'open' });
  };
  ws.onmessage = (ev) => {
    let frame = null;
    try { frame = JSON.parse(ev.data); } catch (_) { return; }
    if (frame && frame.type === 'metric' && frame.src !== 'scrape') lastServerMetricAt = Date.now();
    fanout(frame);
  };
  ws.onclose = () => { fanout({ type: 'ws_state', state: 'closed' }); scheduleReconnect(); };
  ws.onerror = () => { try { ws.close(); } catch (_) {} };
}

function scheduleReconnect() {
  if (ports.size === 0) return;
  clearTimeout(wsTimer);
  wsTimer = setTimeout(openStream, wsBackoff);
  wsBackoff = Math.min(wsBackoff * 2, 4000);   // 250 ms → 4 s, per the contract
}

function closeStream() {
  clearTimeout(wsTimer);
  if (ws) { try { ws.close(); } catch (_) {} ws = null; }
}

// The sanctioned path. SSE is read here and relayed as deltas over the port, so the
// judge never sees a second browser window and the content script never touches the
// local network directly.
async function streamAnswer(port, msg) {
  const rid = msg.rid;
  try {
    const res = await fetch(BASE + '/v1/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: msg.prompt, decision_id: msg.decision_id || null }),
      credentials: 'omit',
    });
    if (!res.ok || !res.body) throw new Error('HTTP ' + res.status);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf('\n\n')) !== -1) {
        const raw = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 2);
        if (!raw.startsWith('data:')) continue;
        const data = raw.slice(5).trim();
        if (data === '[DONE]') { port.postMessage({ type: 'ANSWER_DONE', rid }); return; }
        try {
          const j = JSON.parse(data);
          // A's /v1/answer emits an airlock.error.v1 object inside a data frame when
          // :8000 is unreachable — no `choices` at all. Without this branch the panel
          // just stops mid-sentence and the operator has nothing to look at.
          if (j && j.error) {
            port.postMessage({ type: 'ANSWER_ERROR', rid, error: j.reason || j.label || j.error });
            return;
          }
          const delta = j.choices && j.choices[0] && j.choices[0].delta;
          const text = (delta && delta.content) || '';
          if (text) port.postMessage({ type: 'ANSWER_DELTA', rid, text });
        } catch (_) { /* keepalive comment or partial frame */ }
      }
    }
    port.postMessage({ type: 'ANSWER_DONE', rid });
  } catch (e) {
    port.postMessage({ type: 'ANSWER_ERROR', rid, error: String(e && e.message || e) });
  }
}

// ------------------------------------------------------------------ the hard floor
// declarativeNetRequest is enforced in the network stack. It works with the service
// worker asleep and the content script broken. It is a switch, not an inspector —
// which is exactly why it is the last line and not the first.
const LOCKDOWN_RULE_ID = 1;

async function setLockdown(on) {
  const rules = on ? [{
    id: LOCKDOWN_RULE_ID,
    priority: 1,
    action: { type: 'block' },
    condition: {
      urlFilter: '||chatgpt.com/backend-api/conversation',
      resourceTypes: ['xmlhttprequest', 'other'],
    },
  }] : [];
  await chrome.declarativeNetRequest.updateSessionRules({
    removeRuleIds: [LOCKDOWN_RULE_ID],
    addRules: rules,
  });
  await chrome.storage.session.set({ lockdown: on });
  return { on };
}

async function lockdownState() {
  const rules = await chrome.declarativeNetRequest.getSessionRules();
  return rules.some((r) => r.id === LOCKDOWN_RULE_ID);
}

// ------------------------------------------------------------------ dev-only helper
// Reloading the extension orphans every content script already in a page ("Extension
// context invalidated"). airlock.js guards against that and falls back to a direct
// fetch, but during the build it is faster to just reload the tabs. Not used on stage:
// rule for 16:30 is reload once, then never touch chrome://extensions again.
async function reloadAirlockTabs() {
  if (!chrome.tabs) return { ok: false, reason: 'no tabs permission' };
  const tabs = await chrome.tabs.query({
    url: ['https://chatgpt.com/*', 'https://chat.openai.com/*', 'http://localhost:5173/*'],
  });
  for (const t of tabs) chrome.tabs.reload(t.id);
  return { ok: true, reloaded: tabs.length };
}
