/* extension/overlay.js — everything a judge sees.
 *
 * One Shadow DOM host, attached to document.documentElement (NOT document.body —
 * body is null at document_start and this script must be able to draw before the
 * page has finished parsing). `all: initial` inside the shadow root, and the host
 * itself is pinned at the top of the stacking context, because we are drawing over
 * hostile CSS on somebody else's page.
 *
 * Exposes window.__AIRLOCK_UI__ to the other ISOLATED-world scripts:
 *   scanning(meta)   — show the chip. Must be callable synchronously from the
 *                      paste handler, right after preventDefault().
 *   verdict(v, ctx)  — render allow (chip flashes green and fades) or block (card).
 *   dismiss()        — tear the card down.
 */
(() => {
  if (window.__AIRLOCK_UI__) return;

  const Z = '2147483647';

  const CSS = `
  :host { all: initial; }
  * { box-sizing: border-box; font-family: ui-sans-serif, -apple-system, "Segoe UI", Roboto, sans-serif; }

  .layer {
    position: fixed; inset: 0; z-index: ${Z};
    pointer-events: none;
    color: #e8eaed;
  }

  /* ---------------------------------------------------------------- scanning chip */
  .chip {
    position: fixed; top: 18px; left: 50%; transform: translateX(-50%) translateY(-8px);
    display: flex; align-items: center; gap: 9px;
    padding: 8px 14px; border-radius: 999px;
    background: rgba(18,20,24,.86); backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,.10);
    box-shadow: 0 8px 28px rgba(0,0,0,.45);
    font-size: 13px; letter-spacing: .01em;
    opacity: 0; transition: opacity .12s ease, transform .12s ease;
    pointer-events: none;
  }
  .chip.on { opacity: 1; transform: translateX(-50%) translateY(0); }
  .chip.ok   { border-color: rgba(74,222,128,.35); }
  .chip.bad  { border-color: rgba(248,113,113,.45); }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #6ea8fe; flex: none; }
  .chip.scan .dot { animation: pulse 1s ease-in-out infinite; }
  .chip.ok .dot  { background: #4ade80; animation: none; }
  .chip.bad .dot { background: #f87171; animation: none; }
  @keyframes pulse { 0%,100% { opacity: .35; transform: scale(.8);} 50% { opacity: 1; transform: scale(1.15);} }
  .chip .ms { opacity: .55; font-variant-numeric: tabular-nums; }

  /* ------------------------------------------------------------------- block card */
  .scrim {
    position: fixed; inset: 0; background: rgba(6,7,9,.55);
    backdrop-filter: blur(3px);
    opacity: 0; transition: opacity .18s ease; pointer-events: none;
  }
  .scrim.on { opacity: 1; pointer-events: auto; }

  .card {
    position: fixed; left: 50%; top: 50%;
    width: min(680px, calc(100vw - 40px));
    max-height: calc(100vh - 64px); overflow: auto;
    transform: translate(-50%, calc(-50% + 14px));
    background: linear-gradient(180deg, rgba(24,26,32,.96), rgba(16,17,21,.97));
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,.10);
    border-radius: 16px;
    box-shadow: 0 30px 90px rgba(0,0,0,.6), 0 0 0 1px rgba(248,113,113,.16) inset;
    padding: 20px 22px 18px;
    opacity: 0; pointer-events: none;
    transition: opacity .18s ease, transform .18s cubic-bezier(.2,.8,.2,1);
  }
  .card.on { opacity: 1; transform: translate(-50%, -50%); pointer-events: auto; }
  .card::-webkit-scrollbar { width: 8px; }
  .card::-webkit-scrollbar-thumb { background: rgba(255,255,255,.12); border-radius: 8px; }

  .hd { display: flex; align-items: center; gap: 11px; }
  .shield { width: 26px; height: 26px; flex: none; }
  .title { font-size: 17px; font-weight: 620; letter-spacing: -.01em; }
  .tag {
    margin-left: auto; font-size: 11px; font-weight: 600; letter-spacing: .06em;
    padding: 4px 9px; border-radius: 6px; text-transform: uppercase;
    background: rgba(248,113,113,.14); color: #fca5a5; border: 1px solid rgba(248,113,113,.28);
  }
  .tag.sev-MEDIUM { background: rgba(251,191,36,.13); color: #fcd34d; border-color: rgba(251,191,36,.3); }
  .tag.sev-LOW    { background: rgba(148,163,184,.14); color: #cbd5e1; border-color: rgba(148,163,184,.3); }

  .reason { margin: 13px 0 0; font-size: 14.5px; line-height: 1.5; color: #dfe3e8; }
  .label-line { margin-top: 6px; font-size: 12.5px; color: #9aa3ad; }
  .label-line b { color: #e8eaed; font-weight: 600; }

  .clause {
    margin-top: 13px; padding: 11px 13px; border-radius: 10px;
    background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.07);
    font-size: 12.5px; line-height: 1.5; color: #c3cad2;
  }
  .clause .cid { color: #8ab4f8; font-weight: 650; letter-spacing: .02em; }

  /* ------------------------------------------------------- the evidence highlight */
  .evi {
    margin-top: 13px; padding: 11px 13px; border-radius: 10px; max-height: 168px; overflow: auto;
    background: rgba(0,0,0,.32); border: 1px solid rgba(255,255,255,.07);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px; line-height: 1.65; white-space: pre-wrap; word-break: break-word;
    color: #9aa3ad;
  }
  .evi mark {
    background: rgba(248,113,113,.13); color: #ffd9d9;
    border-bottom: 2px solid #f87171; border-radius: 2px; padding: 0 1px;
  }
  .evi.unverified { border-color: rgba(251,191,36,.3); }
  .evi-note { margin-top: 6px; font-size: 11px; color: #8a939d; }
  .evi-note.warn { color: #fcd34d; }

  /* ----------------------------------------------------------------- the receipt */
  dl.receipt {
    margin: 15px 0 0; display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px;
    background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.07);
    border-radius: 10px; overflow: hidden;
  }
  dl.receipt > div { background: rgba(20,22,27,.9); padding: 10px 11px; }
  dl.receipt dt { font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; color: #7d868f; }
  dl.receipt dd { margin: 4px 0 0; font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; color: #e8eaed; }
  dl.receipt dd.zero { color: #4ade80; }

  /* ------------------------------------------------------------ scoreDetails tree */
  details.sd { margin-top: 13px; }
  details.sd > summary {
    cursor: pointer; font-size: 12px; color: #8ab4f8; list-style: none;
    padding: 7px 0; user-select: none;
  }
  details.sd > summary::-webkit-details-marker { display: none; }
  details.sd > summary::before { content: '▸ '; opacity: .7; }
  details.sd[open] > summary::before { content: '▾ '; }
  .sd-body {
    padding: 11px 13px; border-radius: 10px;
    background: rgba(0,0,0,.32); border: 1px solid rgba(255,255,255,.07);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11.5px; color: #c3cad2;
  }
  .sd-desc { color: #8a939d; margin-bottom: 9px; line-height: 1.55; font-style: italic; }
  table.sd-t { width: 100%; border-collapse: collapse; }
  table.sd-t th { text-align: left; font-weight: 600; color: #7d868f; padding: 3px 8px 6px 0; font-size: 10.5px; letter-spacing: .05em; text-transform: uppercase; }
  table.sd-t td { padding: 3px 8px 3px 0; font-variant-numeric: tabular-nums; }
  table.sd-t td.p { color: #8ab4f8; }
  .bar { height: 4px; border-radius: 2px; background: #6ea8fe; min-width: 2px; }

  pre.denied {
    margin-top: 13px; padding: 11px 13px; border-radius: 10px; overflow-x: auto;
    background: rgba(0,0,0,.42); border: 1px solid rgba(248,113,113,.22);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11.5px;
    line-height: 1.6; color: #fca5a5; white-space: pre;
  }

  /* ------------------------------------------------------------------- the answer */
  .answer {
    margin-top: 13px; padding: 12px 14px; border-radius: 10px; display: none;
    background: rgba(110,168,254,.06); border: 1px solid rgba(110,168,254,.22);
    font-size: 13.5px; line-height: 1.6; color: #dfe3e8;
    max-height: 240px; overflow: auto; white-space: pre-wrap;
  }
  .answer.on { display: block; }
  .answer .src { display: block; margin-bottom: 8px; font-size: 10.5px; letter-spacing: .06em;
                 text-transform: uppercase; color: #8ab4f8; }
  .caret { display: inline-block; width: 7px; height: 14px; background: #8ab4f8;
           vertical-align: -2px; animation: blink 1s steps(2) infinite; }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }

  /* --------------------------------------------------------------------- buttons */
  .row { display: flex; gap: 9px; margin-top: 16px; flex-wrap: wrap; }
  button {
    font: inherit; font-size: 13px; font-weight: 560; cursor: pointer;
    padding: 9px 14px; border-radius: 9px; border: 1px solid rgba(255,255,255,.12);
    background: rgba(255,255,255,.05); color: #e8eaed;
    transition: background .12s ease, border-color .12s ease, transform .06s ease;
  }
  button:hover { background: rgba(255,255,255,.10); border-color: rgba(255,255,255,.2); }
  button:active { transform: translateY(1px); }
  button.primary {
    background: rgba(110,168,254,.16); border-color: rgba(110,168,254,.4); color: #cfe0ff;
  }
  button.primary:hover { background: rgba(110,168,254,.26); }
  button.ghost { margin-left: auto; opacity: .65; }
  button[disabled] { opacity: .45; cursor: default; }
  .ok-note { margin-top: 10px; font-size: 12px; color: #4ade80; display: none; }
  .ok-note.on { display: block; }
  `;

  // The host has to survive at document_start, before <body> exists.
  const host = document.createElement('div');
  host.id = 'airlock-root';
  host.setAttribute('data-airlock', '1');
  host.style.cssText = 'all:initial;position:fixed;top:0;left:0;width:0;height:0;z-index:' + Z + ';';
  const root = host.attachShadow({ mode: 'open' });
  const style = document.createElement('style');
  style.textContent = CSS;
  root.appendChild(style);

  const layer = document.createElement('div');
  layer.className = 'layer';
  layer.innerHTML = `
    <div class="chip scan" part="chip"><span class="dot"></span><span class="txt">Airlock — inspecting locally…</span><span class="ms"></span></div>
    <div class="scrim"></div>
    <div class="card" role="alertdialog" aria-modal="true"></div>
  `;
  root.appendChild(layer);

  function mount() {
    const parent = document.documentElement || document.body;
    if (!parent) return void requestAnimationFrame(mount);
    if (host.parentNode !== parent) parent.appendChild(host);
  }
  mount();
  // Some SPAs replace documentElement's children wholesale on hydration.
  new MutationObserver(() => { if (!host.isConnected) mount(); })
    .observe(document, { childList: true, subtree: false });

  const $chip  = root.querySelector('.chip');
  const $scrim = root.querySelector('.scrim');
  const $card  = root.querySelector('.card');

  let chipTimer = null;
  let t0 = 0;

  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // ------------------------------------------------------------------- chip states
  function scanning(meta) {
    t0 = performance.now();
    clearTimeout(chipTimer);
    $chip.className = 'chip scan on';
    $chip.querySelector('.txt').textContent = meta && meta.modality === 'image'
      ? 'Airlock — inspecting image locally…'
      : 'Airlock — inspecting locally…';
    $chip.querySelector('.ms').textContent = '';
  }

  function chipResult(v) {
    const ms = v && typeof v.latency_ms === 'number' && v.latency_ms > 0
      ? v.latency_ms : Math.round(performance.now() - t0);
    const blocked = v && v.action === 'block';
    $chip.className = 'chip ' + (blocked ? 'bad' : 'ok') + ' on';
    $chip.querySelector('.txt').textContent = blocked
      ? 'Blocked — ' + (v.label || 'POLICY')
      : 'Allowed — nothing sensitive found';
    $chip.querySelector('.ms').textContent = ms + ' ms · ' + (v && v.tier || '—');
    clearTimeout(chipTimer);
    chipTimer = setTimeout(() => { $chip.className = 'chip'; }, blocked ? 2600 : 1800);
  }

  function hideChip() { clearTimeout(chipTimer); $chip.className = 'chip'; }

  // ------------------------------------------------------- evidence-span highlight
  // The verdict carries evidence_spans the server has already verified to be literal
  // substrings of the payload. We locate them and underline exactly those characters.
  // If a span is not found, we say so rather than quietly rendering a plain payload —
  // the whole point of span verification is that it is checkable.
  function highlight(payload, spans) {
    const text = String(payload || '');
    const found = [];
    (spans || []).forEach((s) => {
      if (!s) return;
      const i = text.indexOf(s);
      if (i !== -1) found.push([i, i + s.length]);
    });
    found.sort((a, b) => a[0] - b[0]);
    // merge overlaps
    const merged = [];
    for (const r of found) {
      const last = merged[merged.length - 1];
      if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
      else merged.push(r.slice());
    }
    let out = '', cursor = 0;
    for (const [a, b] of merged) {
      out += esc(text.slice(cursor, a)) + '<mark>' + esc(text.slice(a, b)) + '</mark>';
      cursor = b;
    }
    out += esc(text.slice(cursor));
    return { html: out, hits: merged.length, wanted: (spans || []).filter(Boolean).length };
  }

  // --------------------------------------------------------- scoreDetails renderer
  function scoreDetailsHTML(sd) {
    if (!sd) return '';
    const rows = Array.isArray(sd.details) ? sd.details : [];
    const max = rows.reduce((m, r) => Math.max(m, Number(r.value) || 0), 0) || 1;
    const body = rows.map((r) => {
      const val = Number(r.value) || 0;
      return `<tr>
        <td class="p">${esc(r.inputPipelineName || r.description || '—')}</td>
        <td>${esc(r.rank != null ? r.rank : '—')}</td>
        <td>${esc(r.weight != null ? r.weight : '—')}</td>
        <td>${val ? val.toFixed(6) : '—'}</td>
        <td style="width:34%"><div class="bar" style="width:${Math.max(2, (val / max) * 100)}%"></div></td>
      </tr>`;
    }).join('');
    return `
    <details class="sd">
      <summary>Why this ranked where it did — MongoDB $rankFusion scoreDetails (fused score ${esc((Number(sd.value) || 0).toFixed(6))})</summary>
      <div class="sd-body">
        <div class="sd-desc">${esc(sd.description || '')}</div>
        ${rows.length ? `<table class="sd-t">
          <tr><th>pipeline</th><th>rank</th><th>weight</th><th>contribution</th><th></th></tr>
          ${body}
        </table>` : '<div class="sd-desc">No per-pipeline detail returned.</div>'}
      </div>
    </details>`;
  }

  const SHIELD = `<svg class="shield" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M12 2.5 4.5 5.8v5.4c0 4.6 3.2 8.9 7.5 10.3 4.3-1.4 7.5-5.7 7.5-10.3V5.8L12 2.5Z"
          fill="rgba(248,113,113,.14)" stroke="#f87171" stroke-width="1.4" stroke-linejoin="round"/>
    <path d="M9 12.2l2 2 4.2-4.4" stroke="#f87171" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" opacity=".0"/>
    <path d="M9.2 9.2l5.6 5.6M14.8 9.2l-5.6 5.6" stroke="#f87171" stroke-width="1.6" stroke-linecap="round"/>
  </svg>`;

  // ------------------------------------------------------------------- the card
  let ctxPayload = '';
  let currentVerdict = null;

  function renderBlock(v, ctx) {
    currentVerdict = v;
    ctxPayload = (ctx && ctx.payloadText) || '';

    const unavailable = v.label === 'airlock_unavailable';
    const hl = highlight(ctxPayload, v.evidence_spans);
    const sev = v.severity || 'HIGH';
    const p = typeof v.p_block === 'number' ? v.p_block : null;
    const denied = {
      error: 'policy_denied',
      rule: v.policy_clause_id || 'NONE',
      origin: (ctx && ctx.origin) || location.origin,
      by: 'airlock',
      request_id: v.request_id || null,
    };

    $card.innerHTML = `
      <div class="hd">
        ${SHIELD}
        <div>
          <div class="title">${unavailable ? 'Blocked — inspector unavailable' : 'Blocked before it left this machine'}</div>
        </div>
        <span class="tag sev-${esc(sev)}">${esc(sev)} · ${esc(v.label || 'POLICY')}</span>
      </div>

      <p class="reason">${esc(v.reason || 'Policy violation.')}</p>
      <div class="label-line">Destination <b>${esc((ctx && ctx.host) || location.host)}</b> · modality <b>${esc(v.modality || 'text')}</b> · tier <b>${esc(v.tier || '—')}</b></div>

      ${v.policy_clause_id && v.policy_clause_id !== 'NONE' ? `
        <div class="clause"><span class="cid">${esc(v.policy_clause_id)}</span> — ${esc(v.policy_clause_text || '')}</div>` : ''}

      ${ctxPayload && !unavailable ? `
        <div class="evi ${hl.hits ? '' : 'unverified'}">${hl.html || '<i>(empty payload)</i>'}</div>
        <div class="evi-note ${hl.hits ? '' : 'warn'}">
          ${hl.hits
            ? `${hl.hits} evidence span${hl.hits === 1 ? '' : 's'} located verbatim in the payload${v.evidence_verified ? ' · server-verified' : ''}`
            : (hl.wanted
                ? 'Evidence spans were not found verbatim in the payload — the verdict is shown unhighlighted rather than implied'
                : 'No evidence spans returned')}
        </div>` : ''}

      <dl class="receipt">
        <div><dt>Classifier</dt><dd>${esc(v.model || '—')}</dd></div>
        <div><dt>Confidence</dt><dd>${p == null ? '—' : p.toFixed(2)}${v.threshold != null ? ` <span style="opacity:.5;font-weight:400">/ τ ${Number(v.threshold).toFixed(2)}</span>` : ''}</dd></div>
        <div><dt>Decided in</dt><dd>${esc(v.latency_ms != null ? v.latency_ms + ' ms' : '—')}</dd></div>
        <div><dt>Bytes egressed</dt><dd class="zero">${esc(v.bytes_egressed != null ? v.bytes_egressed : 0)}</dd></div>
      </dl>

      ${scoreDetailsHTML(v.score_details)}

      <pre class="denied">${esc(JSON.stringify(denied, null, 2))}</pre>

      <div class="answer"><span class="src">Answered locally · airlock-text on this box</span><span class="body"></span><span class="caret"></span></div>
      <div class="ok-note"></div>

      <div class="row">
        <button class="primary act-answer">Answer this on the local model instead</button>
        <button class="act-benign">Mark benign</button>
        <button class="ghost act-close">Dismiss</button>
      </div>
    `;

    $card.querySelector('.act-close').addEventListener('click', dismiss);
    $card.querySelector('.act-answer').addEventListener('click', onAnswer);
    $card.querySelector('.act-benign').addEventListener('click', onBenign);

    $scrim.classList.add('on');
    $card.classList.add('on');
    // Esc closes. A DLP block that traps you in a modal is a bug, not a security control.
    document.addEventListener('keydown', onKey, true);
  }

  function onKey(e) {
    if (e.key === 'Escape') { e.stopPropagation(); dismiss(); }
  }

  function dismiss() {
    $card.classList.remove('on');
    $scrim.classList.remove('on');
    document.removeEventListener('keydown', onKey, true);
  }

  // ------------------------------------------------------------- sanctioned answer
  function onAnswer(e) {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = 'Answering on the local model…';
    const panel = $card.querySelector('.answer');
    const body = panel.querySelector('.body');
    const caret = panel.querySelector('.caret');
    body.textContent = '';
    panel.classList.add('on');

    window.__AIRLOCK_NET__.answer(ctxPayload, currentVerdict && currentVerdict.decision_id, {
      onDelta: (t) => { body.textContent += t; panel.scrollTop = panel.scrollHeight; },
      onDone: () => { caret.style.display = 'none'; btn.textContent = 'Answered locally'; },
      onError: (err) => {
        caret.style.display = 'none';
        body.textContent += '\n[local model unavailable: ' + err + ']';
        btn.disabled = false;
        btn.textContent = 'Retry on the local model';
      },
    });
  }

  // --------------------------------------------------------- procedural memory beat
  function onBenign(e) {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = 'Writing back…';
    window.__AIRLOCK_NET__.feedback({
      decision_id: currentVerdict && currentVerdict.decision_id,
      verdict: 'benign',
      analyst: 'demo',
    }).then((res) => {
      const note = $card.querySelector('.ok-note');
      note.classList.add('on');
      note.textContent = res && res.ok
        ? 'Written back to policy_corpus as an analyst override' +
          (res.corpus_id ? ' (' + res.corpus_id + ')' : '') +
          ' — this exact shape will pass next time; a near neighbour still blocks. No retraining.'
        : 'Write-back failed — the inspector did not accept the override.';
      btn.textContent = res && res.ok ? 'Marked benign' : 'Retry';
      btn.disabled = !(res && res.ok);
    });
  }

  // -------------------------------------------------------------------- public API
  window.__AIRLOCK_UI__ = {
    scanning,
    hideChip,
    dismiss,
    root,
    verdict(v, ctx) {
      chipResult(v);
      if (v && v.action === 'block') renderBlock(v, ctx || {});
      else dismiss();
    },
  };
})();
