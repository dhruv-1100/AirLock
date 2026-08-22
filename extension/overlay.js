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

  /* ------------------------------------------------- the cascade (tier_timings) */
  .cascade { margin-top: 13px; }
  .cascade .cl { font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase;
                 color: #7d868f; margin-bottom: 7px; }
  .stages { display: flex; align-items: stretch; gap: 0; }
  .stage {
    flex: 1; padding: 8px 6px; text-align: center;
    background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.07);
    border-right: 0; position: relative;
  }
  .stage:first-child { border-radius: 9px 0 0 9px; }
  .stage:last-child { border-radius: 0 9px 9px 0; border-right: 1px solid rgba(255,255,255,.07); }
  .stage .sn { font-size: 11px; font-weight: 650; color: #5d666f; letter-spacing: .03em; }
  .stage .sv { font-size: 10.5px; color: #4d565f; margin-top: 3px; font-variant-numeric: tabular-nums; }
  .stage.ran { background: rgba(110,168,254,.10); border-color: rgba(110,168,254,.28); }
  .stage.ran .sn { color: #cfe0ff; }
  .stage.ran .sv { color: #8ab4f8; }
  .stage.resolved { background: rgba(74,222,128,.11); border-color: rgba(74,222,128,.32); }
  .stage.resolved .sn { color: #bbf7d0; }
  .stage.resolved .sv { color: #4ade80; }
  .stage.model { background: rgba(192,132,252,.11); border-color: rgba(192,132,252,.32); }
  .stage.model .sn { color: #e9d5ff; }
  .stage.model .sv { color: #c084fc; }
  .stage.skipped .sn::after { content: ''; }
  .cascade .verdict-line { margin-top: 8px; font-size: 11.5px; color: #8a939d; line-height: 1.5; }
  .cascade .verdict-line b { color: #4ade80; font-weight: 600; }
  .cascade .verdict-line b.model { color: #c084fc; }

  /* --------------------------------------------------- image evidence (beat 3) */
  .imgwrap { margin-top: 13px; }
  .imgshot { position: relative; display: inline-block; max-width: 100%;
             border-radius: 10px; overflow: hidden; border: 1px solid rgba(255,255,255,.09); }
  .imgshot img { display: block; max-width: 100%; height: auto; }
  .bbox { position: absolute; border: 2px solid #f87171; border-radius: 3px;
          box-shadow: 0 0 0 9999px rgba(6,7,9,.30); }
  .bbox .bl { position: absolute; left: -2px; top: -20px; white-space: nowrap;
              background: #f87171; color: #16181d; font-size: 10px; font-weight: 700;
              padding: 1px 5px; border-radius: 3px; }
  .ocr {
    margin-top: 9px; padding: 10px 12px; border-radius: 10px; max-height: 132px; overflow: auto;
    background: rgba(0,0,0,.32); border: 1px solid rgba(255,255,255,.07);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11.5px; line-height: 1.7; color: #9aa3ad; white-space: pre-wrap;
  }
  .ocr mark { background: rgba(248,113,113,.13); color: #ffd9d9;
              border-bottom: 2px solid #f87171; border-radius: 2px; padding: 0 1px; }
  .chips { margin-top: 9px; display: flex; flex-wrap: wrap; gap: 6px; }
  .chip-m {
    font-size: 11px; padding: 4px 9px; border-radius: 6px;
    background: rgba(248,113,113,.12); color: #fca5a5;
    border: 1px solid rgba(248,113,113,.28);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  .imgnote { margin-top: 7px; font-size: 11px; color: #8a939d; line-height: 1.5; }
  
  .ok-note { margin-top: 10px; font-size: 12px; color: #4ade80; display: none; line-height: 1.5; }
  .ok-note.on { display: block; }
  .ok-note.warn { color: #fcd34d; }
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


  // ------------------------------------------------------- cascade / tier_timings
  // Additive: renders only when the verdict carries `tier_timings`. Everything below
  // degrades to nothing if A has not shipped the field yet.
  //
  // The point of this strip is the stage that did NOT run. ~86% of pastes are resolved
  // by T0/T1 with no model call at all, and that is the architecture claim — currently
  // it is a sentence in the writeup and invisible on screen. A dimmed T2 next to a lit
  // T1 says it without anyone having to narrate it.
  const CASCADE = [
    { key: 'cache', name: 'CACHE', hint: 'sha256 hit' },
    { key: 'T0',    name: 'T0',    hint: 'trivial gate' },
    { key: 'T1',    name: 'T1',    hint: 'detectors' },
    { key: 'T2',    name: 'T2',    hint: 'text model' },
    { key: 'T3',    name: 'T3',    hint: 'vision model' },
  ];

  function fmtMs(v) {
    if (typeof v !== 'number') return '—';
    if (v >= 100) return Math.round(v) + ' ms';
    if (v >= 10) return v.toFixed(1) + ' ms';
    return v.toFixed(2) + ' ms';
  }

  function cascadeHTML(v) {
    const raw = v && v.tier_timings;
    if (!raw || typeof raw !== 'object') return '';

    // Case-fold the keys. B's proposed example was {"cache":…} and A shipped {"CACHE":…};
    // matching case-sensitively meant the cache cell read "not run" on a decision that
    // had in fact hit it. Not worth a round trip over — normalise and move on.
    const t = {};
    for (const k of Object.keys(raw)) t[String(k).toLowerCase()] = raw[k];

    const deciding = String(v.tier || '').toUpperCase();  // the stage that decided
    const usedModel = deciding === 'T2' || deciding === 'T3';

    const cells = CASCADE.map((st) => {
      const k = st.key.toLowerCase();
      // Present means the stage ran — including a legitimate 0.0 for a sub-microsecond
      // T0. Absent means it did not run. Never inferred from the value.
      const ran = Object.prototype.hasOwnProperty.call(t, k) && t[k] != null;
      let cls = 'stage';
      if (!ran) cls += ' skipped';
      else if (st.name === deciding) cls += (deciding === 'T2' || deciding === 'T3') ? ' model' : ' resolved';
      else cls += ' ran';
      return `<div class="${cls}" title="${esc(st.hint)}">
                <div class="sn">${esc(st.name)}</div>
                <div class="sv">${ran ? esc(fmtMs(Number(t[k]))) : 'not run'}</div>
              </div>`;
    }).join('');

    const line = usedModel
      ? `Escalated to <b class="model">${esc(deciding === 'T3' ? 'the vision model' : 'the text model')}</b> — the deterministic tiers could not resolve this one.`
      : `<b>No model was called.</b> Resolved deterministically at ${esc(deciding || 'T1')} on CPU — no GPU, no tokens, nothing queued behind another request.`;

    return `<div class="cascade">
      <div class="cl">Cascade — where this decision was made</div>
      <div class="stages">${cells}</div>
      <div class="verdict-line">${line}</div>
    </div>`;
  }

  // ------------------------------------------------------ image evidence (beat 3)
  // Three fidelity levels, picked by what the verdict actually carries. The rule is
  // that we never draw a box we were not given coordinates for: inventing a position
  // for a marker would be fabricating evidence, which is precisely the failure this
  // product exists to prevent.
  //
  //   evidence_boxes present  -> boxes drawn on the image at the model's coordinates
  //   extracted_text present  -> the transcript, with the marker strings underlined
  //   neither                 -> the image plus the marker strings as chips
  function imageEvidenceHTML(v, ctx) {
    const img = ctx && ctx.images && ctx.images[0];
    if (!img || !img.b64) return '';

    const spans = (v.evidence_spans || []).filter(Boolean);
    const boxes = Array.isArray(v.evidence_boxes) ? v.evidence_boxes : null;
    const ocr = Array.isArray(v.extracted_text) ? v.extracted_text.join('\n') : null;

    // Coordinates are normalised 0..1 so they survive the client-side downscale to
    // 1024px — the model saw the downscaled image, not the original.
    const boxHTML = (boxes || []).map((b) => {
      const x = Number(b.x), y = Number(b.y), w = Number(b.w), h = Number(b.h);
      if (![x, y, w, h].every(Number.isFinite)) return '';
      return `<div class="bbox" style="left:${(x * 100).toFixed(2)}%;top:${(y * 100).toFixed(2)}%;`
           + `width:${(w * 100).toFixed(2)}%;height:${(h * 100).toFixed(2)}%">`
           + `<span class="bl">${esc(b.text || '')}</span></div>`;
    }).join('');

    let body;
    let note;
    if (boxHTML) {
      body = '';
      note = `${boxes.length} marker${boxes.length === 1 ? '' : 's'} located on the image by the vision model.`;
    } else if (ocr) {
      const hl = highlight(ocr, spans);
      body = `<div class="ocr">${hl.html}</div>`;
      note = hl.hits
        ? `Transcribed off the image by the vision model; ${hl.hits} marker${hl.hits === 1 ? '' : 's'} underlined in its own transcript. Positions are not shown because the model did not return coordinates.`
        : 'Transcribed off the image by the vision model.';
    } else {
      body = spans.length
        ? `<div class="chips">${spans.map((sp) => `<span class="chip-m">${esc(sp)}</span>`).join('')}</div>`
        : '';
      note = spans.length
        ? 'Read off the image by the vision model. Positions are not shown because the model did not return coordinates.'
        : '';
    }

    return `<div class="imgwrap">
      <div class="imgshot"><img src="data:${esc(img.mime || 'image/jpeg')};base64,${img.b64}" alt="">${boxHTML}</div>
      ${body}
      ${note ? `<div class="imgnote">${esc(note)}</div>` : ''}
    </div>`;
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

      ${v.modality === 'image' && !unavailable ? imageEvidenceHTML(v, ctx) : ''}

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
        <div><dt>Decided in</dt><dd>${v.latency_ms == null ? '—'
          : (v.latency_ms === 0 ? '&lt;1 ms' : esc(v.latency_ms) + ' ms')}</dd></div>
        <div><dt>Bytes egressed</dt><dd class="zero">${esc(v.bytes_egressed != null ? v.bytes_egressed : 0)}</dd></div>
      </dl>

      ${cascadeHTML(v)}

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
      // `ok:true, embedded:false` is the MONGO_ENABLED=false no-op path. Saying
      // "written back to policy_corpus" there would be a claim the system did not
      // earn, on the one beat whose whole point is that the write-back is real.
      if (res && res.ok && res.embedded) {
        note.classList.remove('warn');
        note.textContent = 'Written back to policy_corpus as an analyst override' +
          (res.corpus_id ? ' (' + res.corpus_id + ')' : '') +
          ' — this exact shape will pass next time; a near neighbour still blocks. No retraining.';
        btn.textContent = 'Marked benign';
        btn.disabled = true;
      } else if (res && res.ok) {
        note.classList.add('warn');
        note.textContent = 'Override recorded, but NOT embedded — persistence is disabled ' +
          'on this process (MONGO_ENABLED=false). Nothing was written to policy_corpus.';
        btn.textContent = 'Marked benign (not persisted)';
        btn.disabled = true;
      } else {
        note.classList.add('warn');
        note.textContent = 'Write-back failed — the inspector did not accept the override.';
        btn.textContent = 'Retry';
        btn.disabled = false;
      }
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
