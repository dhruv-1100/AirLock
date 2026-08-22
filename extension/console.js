/* extension/console.js — the live console panel.
 *
 * Lives in the SAME shadow root as the block card, bottom-left, collapsible, and it
 * is the one part of the overlay with pointer-events: auto. Backfilled from
 * GET /v1/decisions?limit=50, then tailed over ws://127.0.0.1:8787/v1/stream — which
 * the service worker holds on our behalf, because ws:// from an https page is mixed
 * content and would be blocked outright.
 *
 * The threshold slider re-thresholds CACHED per-item p_block scores. It is exact and
 * instant, and the label says so. It must never look like 1000 fresh inferences.
 */
(() => {
  if (window.__AIRLOCK_CONSOLE__) return;
  if (window.top !== window) return;          // top frame only; all_frames is for the interceptor
  window.__AIRLOCK_CONSOLE__ = true;

  window.__AIRLOCK_MODE__ = { mode: 'balanced', tau: 0.55 };
  const MODES = { audit: 0.30, balanced: 0.55, strict: 0.20 };

  const CSS = `
  .panel {
    position: fixed; left: 16px; bottom: 16px; width: 460px;
    max-width: calc(100vw - 32px);
    background: rgba(16,17,21,.93); backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,.10); border-radius: 13px;
    box-shadow: 0 20px 60px rgba(0,0,0,.55);
    pointer-events: auto; color: #e8eaed; overflow: hidden;
    font-size: 12px;
    transition: transform .18s cubic-bezier(.2,.8,.2,1);
  }
  .panel.collapsed { transform: translateY(calc(100% - 38px)); }

  .bar {
    display: flex; align-items: center; gap: 8px; padding: 9px 12px; cursor: pointer;
    border-bottom: 1px solid rgba(255,255,255,.07); user-select: none;
  }
  .bar .name { font-weight: 620; letter-spacing: -.01em; font-size: 12.5px; }
  .bar .caret { margin-left: auto; opacity: .5; font-size: 11px; }
  .health { width: 8px; height: 8px; border-radius: 50%; background: #6b7280; flex: none; }
  .health.up { background: #4ade80; } .health.amber { background: #fbbf24; } .health.down { background: #f87171; }
  .bar .count { opacity: .5; font-variant-numeric: tabular-nums; }

  .body { max-height: 46vh; overflow: auto; }
  .body::-webkit-scrollbar { width: 7px; }
  .body::-webkit-scrollbar-thumb { background: rgba(255,255,255,.12); border-radius: 7px; }

  .feed { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; line-height: 1.75; }
  .feed .ln {
    display: grid; grid-template-columns: 62px 1fr 78px 56px 46px 30px 52px;
    gap: 8px; padding: 1px 12px; white-space: nowrap;
    border-left: 2px solid transparent;
  }
  .feed .ln > span { overflow: hidden; text-overflow: ellipsis; }
  .feed .ln:hover { background: rgba(255,255,255,.04); }
  .feed .ln.block { border-left-color: #f87171; }
  .feed .ln.allow { border-left-color: rgba(74,222,128,.35); }
  .feed .t { color: #6b7280; }
  .feed .h { color: #c3cad2; overflow: hidden; text-overflow: ellipsis; }
  .feed .v { font-weight: 650; }
  .feed .v.BLOCK { color: #f87171; } .feed .v.ALLOW { color: #4ade80; }
  .feed .p, .feed .ms { color: #8a939d; font-variant-numeric: tabular-nums; text-align: right; }
  .feed .tier { color: #8ab4f8; }
  .empty { padding: 16px 12px; color: #6b7280; font-size: 11.5px; }

  .sect { padding: 11px 12px; border-top: 1px solid rgba(255,255,255,.07); }
  .sect h4 { margin: 0 0 8px; font-size: 10px; letter-spacing: .08em; text-transform: uppercase; color: #7d868f; font-weight: 600; }

  .ctl { display: flex; align-items: center; gap: 9px; }
  .ctl label { color: #9aa3ad; font-size: 11.5px; }
  select, input[type=range] { font: inherit; }
  select {
    background: rgba(255,255,255,.06); color: #e8eaed; border: 1px solid rgba(255,255,255,.12);
    border-radius: 7px; padding: 4px 7px; font-size: 11.5px;
  }
  input[type=range] { flex: 1; accent-color: #6ea8fe; }
  .tau { font-variant-numeric: tabular-nums; font-weight: 650; min-width: 34px; text-align: right; }

  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 9px; }
  .stat { background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.07);
          border-radius: 8px; padding: 7px 9px; }
  .stat dt { font-size: 9.5px; letter-spacing: .06em; text-transform: uppercase; color: #7d868f; }
  .stat dd { margin: 3px 0 0; font-size: 15px; font-weight: 650; font-variant-numeric: tabular-nums; }
  .stat dd.fpr { color: #4ade80; } .stat dd.rec { color: #8ab4f8; }
  .cached { margin-top: 7px; font-size: 10.5px; color: #7d868f; font-style: italic; }

  .gauges { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
  .g { background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.07);
       border-radius: 8px; padding: 8px 9px; }
  .g .gl { display: flex; justify-content: space-between; font-size: 10px; color: #7d868f;
           letter-spacing: .05em; text-transform: uppercase; }
  .g .gv { font-variant-numeric: tabular-nums; color: #e8eaed; font-weight: 600; letter-spacing: 0; text-transform: none; }
  .track { margin-top: 6px; height: 5px; border-radius: 3px; background: rgba(255,255,255,.08); overflow: hidden; }
  .fill { height: 100%; border-radius: 3px; transition: width .4s ease; }
  .fill.text { background: linear-gradient(90deg,#6ea8fe,#8ab4f8); }
  .fill.vision { background: linear-gradient(90deg,#c084fc,#e879f9); }
  .shared { margin-top: 8px; font-size: 10.5px; color: #7d868f; line-height: 1.5; }

  .toggles { display: flex; align-items: center; gap: 8px; }
  .sw { position: relative; width: 34px; height: 19px; border-radius: 19px; flex: none;
        background: rgba(255,255,255,.12); cursor: pointer; transition: background .15s ease; }
  .sw::after { content: ''; position: absolute; top: 2px; left: 2px; width: 15px; height: 15px;
               border-radius: 50%; background: #e8eaed; transition: transform .15s ease; }
  .sw.on { background: rgba(248,113,113,.7); }
  .sw.on::after { transform: translateX(15px); }
  .toggles .hint { color: #7d868f; font-size: 10.5px; line-height: 1.45; }
  `;

  const root = window.__AIRLOCK_UI__ && window.__AIRLOCK_UI__.root;
  if (!root) return;

  const style = document.createElement('style');
  style.textContent = CSS;
  root.appendChild(style);

  const panel = document.createElement('div');
  panel.className = 'panel collapsed';
  panel.innerHTML = `
    <div class="bar">
      <span class="health" title="inspector health"></span>
      <span class="name">Airlock</span>
      <span class="count">0 decisions</span>
      <span class="caret">▲</span>
    </div>
    <div class="body">
      <div class="feed"><div class="empty">Waiting for decisions… paste something.</div></div>

      <div class="sect">
        <h4>Operating point</h4>
        <div class="ctl">
          <label>Mode</label>
          <select class="mode">
            <option value="audit">Audit — log only</option>
            <option value="balanced" selected>Balanced</option>
            <option value="strict">Strict</option>
          </select>
          <input type="range" class="tau-range" min="0.20" max="0.75" step="0.01" value="0.55">
          <span class="tau">0.55</span>
        </div>
        <dl class="stats">
          <div class="stat"><dt>FPR @ τ</dt><dd class="fpr">—</dd></div>
          <div class="stat"><dt>Recall @ τ</dt><dd class="rec">—</dd></div>
          <div class="stat"><dt>Benign n</dt><dd class="n">—</dd></div>
        </dl>
        <div class="cached">scores cached; threshold sweep is exact — no inference is re-run</div>
      </div>

      <div class="sect">
        <h4>Unified memory · both models, one pool</h4>
        <div class="gauges">
          <div class="g"><div class="gl"><span>KV text 30B</span><span class="gv kv-text">—</span></div>
            <div class="track"><div class="fill text" style="width:0"></div></div></div>
          <div class="g"><div class="gl"><span>KV vision 30B</span><span class="gv kv-vision">—</span></div>
            <div class="track"><div class="fill vision" style="width:0"></div></div></div>
        </div>
        <div class="shared">Two vLLM processes, one 128 GB pool. Escalation to an LLM: <b class="esc">—</b> of pastes.</div>
      </div>

      <div class="sect">
        <h4>Lockdown</h4>
        <div class="toggles">
          <div class="sw lockdown" role="switch" aria-checked="false"></div>
          <div class="hint">declarativeNetRequest blocks <code>chatgpt.com/backend-api/conversation</code> in the network stack — survives a dead service worker. A switch, not an inspector.</div>
        </div>
      </div>
    </div>
  `;

  // Wait for the layer to exist (overlay.js appended it synchronously, but be safe).
  const layer = root.querySelector('.layer');
  layer.appendChild(panel);

  const $ = (sel) => panel.querySelector(sel);
  const $feed = $('.feed');
  const $count = $('.count');
  const $health = $('.health');

  $('.bar').addEventListener('click', () => {
    panel.classList.toggle('collapsed');
    $('.caret').textContent = panel.classList.contains('collapsed') ? '▲' : '▼';
  });

  // ------------------------------------------------------------------------- feed
  let n = 0;
  const hhmmss = (ts) => new Date(ts || Date.now()).toTimeString().slice(0, 8);

  // Two sources, two shapes. The WebSocket sends ConsoleHub frames, already normalised
  // ({type:'decision', host, action:'block'}). GET /v1/decisions backfills raw
  // `decisions` documents straight out of Mongo ({verdict:'BLOCK', origin:'https://…'},
  // no `type` at all). Rejecting anything without type:'decision' would drop the entire
  // backfill silently — an empty console that looks like a dead feed rather than a
  // shape mismatch. Normalise here instead; it is the consumer's job.
  function normalise(d) {
    if (!d || typeof d !== 'object') return null;
    if (d.type && d.type !== 'decision') return null;
    const origin = d.origin || '';
    const host = d.host || (origin ? origin.split('//').pop().split('/')[0] : 'local');
    let ts = d.ts;
    if (typeof ts === 'string') ts = Date.parse(ts) || Date.now();
    return {
      ts: ts || Date.now(),
      decision_id: d.decision_id || d._id || null,
      host,
      modality: d.modality || 'text',
      chars: d.chars != null ? d.chars : 0,
      action: String(d.action || d.verdict || 'allow').toLowerCase(),
      label: d.label || 'BENIGN',
      p_block: Number(d.p_block) || 0,
      tier: d.tier || 'T1',
      latency_ms: d.latency_ms != null ? d.latency_ms : null,
    };
  }

  function addRow(raw) {
    const d = normalise(raw);
    if (!d) return;
    if ($feed.querySelector('.empty')) $feed.innerHTML = '';
    const blocked = d.action === 'block';
    const el = document.createElement('div');
    el.className = 'ln ' + (blocked ? 'block' : 'allow');
    const size = d.modality === 'image' ? 'image' : (d.chars + 'ch');
    el.innerHTML = `<span class="t">${hhmmss(d.ts)}</span>` +
      `<span class="h" title="${d.host || ''}">${d.host || '—'}</span>` +
      `<span class="m">${d.modality || 'text'} ${size}</span>` +
      `<span class="v ${blocked ? 'BLOCK' : 'ALLOW'}">${blocked ? 'BLOCK' : 'ALLOW'}</span>` +
      `<span class="p">p=${(Number(d.p_block) || 0).toFixed(2)}</span>` +
      `<span class="tier">${d.tier || '—'}</span>` +
      `<span class="ms">${d.latency_ms != null ? d.latency_ms + 'ms' : '—'}</span>`;
    $feed.prepend(el);
    while ($feed.childElementCount > 300) $feed.lastElementChild.remove();
    n += 1;
    $count.textContent = n + ' decision' + (n === 1 ? '' : 's');
  }

  // -------------------------------------------------------------- threshold sweep
  // scores_benign.json is A's per-item p_block dump from bench/run_fpr.py. A drops a
  // synthetic 1000-row file with the right shape at 14:35 so this is finished before
  // the real scores exist; copy the real one over the bundled fixture when it lands.
  let SCORES = null;   // { benign: [p…], sensitive: [p…], errors, placeholder }

  // results/scores_benign.json has had three shapes today and will probably have a
  // fourth. Accept all of them here rather than making whoever copies the file learn
  // which one the slider wants:
  //   {benign:[floats], sensitive:[floats]}   ← the agreed shape (INTEGRATION.md §3)
  //   {items:[{p_block, label|verdict, tier}]} ← report.py's rich per-item shape
  //   [ {p_block, ...}, ... ]                  ← bare list, what run_fpr.py wrote first
  // Rows whose tier is "ERR" are harness failures, not classifier scores. Counting a
  // fail-closed BLOCK as a false positive would be a lie in our own favour's opposite
  // direction, and either way it is not a measurement — so they are excluded and
  // reported separately.
  function normaliseScores(raw) {
    if (!raw) return null;
    if (Array.isArray(raw)) raw = { items: raw };
    let benign = raw.benign, sensitive = raw.sensitive, errors = 0;
    if (!Array.isArray(benign) && Array.isArray(raw.items)) {
      benign = []; sensitive = [];
      for (const it of raw.items) {
        if (!it || typeof it.p_block !== 'number') continue;
        if (it.tier === 'ERR' || it.verdict_label === 'airlock_unavailable') { errors += 1; continue; }
        (String(it.label).toUpperCase() === 'BENIGN' ? benign : sensitive).push(it.p_block);
      }
    }
    if (!Array.isArray(benign)) return null;
    return {
      benign,
      sensitive: Array.isArray(sensitive) ? sensitive : [],
      errors,
      placeholder: !!raw._placeholder,
      corpusIsReal: raw.corpus_is_real !== false && !raw._placeholder,
    };
  }

  async function loadScores() {
    try {
      const url = chrome.runtime.getURL('scores_benign.json');
      const res = await fetch(url);
      SCORES = normaliseScores(await res.json());
      if (SCORES && !SCORES.corpusIsReal) {
        $('.cached').textContent =
          'PLACEHOLDER SCORES — shape only. Replace with results/scores_benign.json before quoting a number.';
        $('.cached').style.color = '#fcd34d';
      } else if (SCORES && SCORES.errors) {
        $('.cached').textContent =
          `scores cached; threshold sweep is exact — ${SCORES.errors} harness errors excluded from the denominator`;
      }
      sweep(Number($('.tau-range').value));
    } catch (e) {
      console.debug('[airlock] no cached scores bundled', e);
    }
  }

  function sweep(tau) {
    $('.tau').textContent = tau.toFixed(2);
    window.__AIRLOCK_MODE__.tau = tau;
    if (!SCORES) return;
    const benign = SCORES.benign || [];
    const sensitive = SCORES.sensitive || [];
    const fp = benign.filter((p) => p >= tau).length;
    const tp = sensitive.filter((p) => p >= tau).length;
    const fpr = benign.length ? fp / benign.length : 0;
    const rec = sensitive.length ? tp / sensitive.length : null;
    $('.fpr').textContent = benign.length ? (fpr * 100).toFixed(2) + '%' : '—';
    $('.rec').textContent = rec == null ? '—' : (rec * 100).toFixed(1) + '%';
    $('.n').textContent = benign.length || '—';
    $('.fpr').title = fp + ' / ' + benign.length + ' benign items at or above τ';
  }

  $('.tau-range').addEventListener('input', (e) => sweep(Number(e.target.value)));

  $('.mode').addEventListener('change', (e) => {
    const mode = e.target.value;
    window.__AIRLOCK_MODE__.mode = mode;
    const tau = MODES[mode];
    $('.tau-range').value = String(tau);
    sweep(tau);
  });

  // ------------------------------------------------------------------ KV gauges
  function gauge(sel, fillSel, frac) {
    if (typeof frac !== 'number') return;
    $(sel).textContent = (frac * 100).toFixed(1) + '%';
    $(fillSel).style.width = Math.min(100, frac * 100) + '%';
  }

  function onMetric(kv) {
    gauge('.kv-text', '.fill.text', kv.kv_cache_text);
    gauge('.kv-vision', '.fill.vision', kv.kv_cache_vision);
    if (typeof kv.escalation_rate === 'number') {
      $('.esc').textContent = (kv.escalation_rate * 100).toFixed(0) + '%';
    }
  }

  // ------------------------------------------------------------------- lockdown
  const $lock = $('.lockdown');
  $lock.addEventListener('click', async () => {
    const on = !$lock.classList.contains('on');
    const res = await window.__AIRLOCK_NET__.lockdown(on);
    const state = res && typeof res.on === 'boolean' ? res.on : on;
    $lock.classList.toggle('on', state);
    $lock.setAttribute('aria-checked', String(state));
  });

  // ------------------------------------------------------------------ wire it up
  function boot() {
    const net = window.__AIRLOCK_NET__;
    if (!net) return void setTimeout(boot, 50);   // airlock.js loads after us

    net.health().then((h) => {
      if (!h) return void $health.classList.add('down');
      const allUp = h.ok && h.clf && h.vlm && h.mongo;
      $health.classList.add(h.ok ? (allUp ? 'up' : 'amber') : 'down');
      const bits = [`clf ${h.clf ? '✓' : '✗'}`, `vlm ${h.vlm ? '✓' : '✗'}`,
                    `mongo ${h.mongo ? '✓' : '✗'}`, `up ${h.uptime_s || 0}s`];
      // The span-verification override count is the one deliberate fail-open in the
      // system. Showing it costs a tooltip and buys the right to call it a mechanism.
      // NFR-T6 escalation rate lives on /healthz, not in a metric frame — nothing
      // broadcasts one. Without this the console's escalation figure stays "—".
      if (typeof h.escalation_rate === 'number') {
        $('.esc').textContent = (h.escalation_rate * 100).toFixed(0) + '%';
        if (h.tiers) $('.shared').title = Object.entries(h.tiers).map(([k, v]) => `${k}:${v}`).join('  ');
      }
      if (h.overrides != null) bits.push(`span overrides ${h.overrides}`);
      if (h.img_gate && h.img_gate.seen) {
        bits.push(`img fast-pass ${Math.round(h.img_gate.fast_passed / h.img_gate.seen * 100)}%`);
      }
      if (h.stub) bits.push('STUB INSPECTOR');
      $health.title = bits.join(' · ');
    });

    net.decisions(50).then((res) => {
      const rows = (res && res.decisions) || [];
      // backfill oldest-first so prepend() leaves newest on top
      rows.slice().reverse().forEach(addRow);
      // /v1/decisions reports whether Mongo is actually CONNECTED. /healthz reports
      // whether the module IMPORTED. They disagree when the container is down, and the
      // connected one is the truth worth showing.
      if (res && res.mongo === false) {
        $health.classList.remove('up');
        $health.classList.add('amber');
        $health.title = ($health.title ? $health.title + ' · ' : '') +
          'MongoDB NOT connected — no history, no instant-block cache';
      }
    });

    net.onFrame((frame) => {
      if (!frame) return;
      if (frame.type === 'decision') addRow(frame);
      else if (frame.type === 'metric') onMetric(frame.kv || {});
      else if (frame.type === 'ws_state') $health.classList.toggle('down', frame.state !== 'open');
    });

    net.lockdownState().then((s) => {
      $lock.classList.toggle('on', !!(s && s.on));
      $lock.setAttribute('aria-checked', String(!!(s && s.on)));
    });

    loadScores();
    // Re-poll every 5 s: escalation rate, override count and the image fast-pass rate
    // all move as pastes come in, and a figure frozen at boot is worse than none.
    setInterval(() => net.health().then((h) => {
      if (!h) return;
      if (typeof h.escalation_rate === 'number') {
        $('.esc').textContent = (h.escalation_rate * 100).toFixed(0) + '%';
      }
    }), 5000);
  }
  boot();
})();
