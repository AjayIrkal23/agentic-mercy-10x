// Kinetic typography blocks for ghost-editor (HyperFrames + GSAP).
//
// Same contract as scripts/lib/motion.mjs: every block returns an HTML string
// and pushes GSAP lines into ctx.tl, so the whole reel stays ONE paused
// timeline. Anything that needs per-letter maths is a "painter": a proxy tween
// over the block's life whose onUpdate recomputes every element from
// tl.time(), so any frame can be sought in any order (seek-safe).
//
// Kinds (b.kind):
//   hook       first 1.5-3 s: a giant cropped key word at frame 0 pulls back
//              into a bold claim lockup while the footage punches in and rings
//   drum       words on a 3D cylinder; the drum turns to land each word on
//              its spoken onset, optional full-revolution "loop" spin
//   scramble   glyphs cycle through a pool from the text's own script
//              (Cyrillic or Latin) and lock left to right on the spoken word
//   flipstack  each word is a card that flips down onto a stack on its
//              spoken word; older cards are pushed back
//   headline   masked word rise + hand-drawn brush mark (under, marker, box,
//              strike); swap mode: "not X -> Y"
//   spring     per-letter drop with a 3-channel damped spring (position,
//              rotation, squash); section titles
//
// Times in b are ORIGINAL-recording seconds (ctx.E maps them to edit time).
// Word onsets come from ctx.words (edit time) when a token is spoken inside
// the block; otherwise from an explicit {text, at} or a fallback stagger.
//
// Sources (see THIRD_PARTY.md): techniques from heygen-com/hyperframes-launches
// (Apache-2.0), whaleyxbt/claude-motion (MIT), bangtutorial/bang-motion (MIT),
// iart-ai motion-skills packs (MIT). Code here is written fresh for this stack.

const norm = (s) => String(s).toLowerCase().replace(/ё/g, "е").replace(/[^\p{L}\p{N}%]+/gu, "");
const isCyr = (s) => /[Ѐ-ӿ]/.test(s);

// ---------------------------------------------------------------- runtime --
// Injected once per page. Pure functions only: no clocks, no Math.random.
export const KINETIC_RUNTIME = `const KT = (() => {
  const C = (v, a = 0, b = 1) => (v < a ? a : v > b ? b : v);
  // one ease family (hyperframes-launches): expo out for arrivals, its mirror for exits
  const EO = (p) => (p >= 1 ? 1 : p <= 0 ? 0 : 1 - Math.pow(2, -10 * p));
  const EI = (p) => (p <= 0 ? 0 : p >= 1 ? 1 : Math.pow(2, 10 * (p - 1)));
  // cubic-bezier solver (claude-motion curves)
  const bez = (x1, y1, x2, y2) => {
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx, cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const X = (t) => ((ax * t + bx) * t + cx) * t, Y = (t) => ((ay * t + by) * t + cy) * t, dX = (t) => (3 * ax * t + 2 * bx) * t + cx;
    return (p) => {
      if (p <= 0) return 0; if (p >= 1) return 1;
      let t = p;
      for (let i = 0; i < 8; i++) { const e = X(t) - p, d = dX(t); if (Math.abs(e) < 1e-6 || Math.abs(d) < 1e-6) break; t -= e / d; }
      if (t < 0 || t > 1) { let lo = 0, hi = 1; t = p; for (let i = 0; i < 30; i++) { if (X(t) < p) lo = t; else hi = t; t = (lo + hi) / 2; } }
      return Y(t);
    };
  };
  const OUT = bez(0.16, 1, 0.3, 1), IN = bez(0.6, 0, 0.9, 0.35), INOUT = bez(0.65, 0, 0.35, 1);
  // damped spring residual (hyperframes-launches 02-bouncy-ui): starts at A, rings to 0
  const spring = (u, A, f, z = 1 / 3) => {
    if (u <= 0) return A;
    const w = 2 * Math.PI * f;
    return A * Math.exp(-z * w * u) * Math.cos(w * Math.sqrt(1 - z * z) * u);
  };
  const hash = (i) => { const v = Math.sin(i * 127.1 + 311.7) * 43758.5453; return v - Math.floor(v); };
  const $ = (id) => document.getElementById(id);
  return { C, EO, EI, bez, OUT, IN, INOUT, spring, hash, $ };
})();`;

// -------------------------------------------------------------------- CSS --
export const KINETIC_CSS = (brand = {}) => `
  .kt { position: absolute; left: 0; right: 0; display: flex; flex-direction: column; align-items: center; text-align: center; pointer-events: none; }
  .kt-bg { position: absolute; inset: 0; }
  .kt-pocket { position: absolute; left: -15%; right: -15%; background: radial-gradient(50% 50% at 50% 50%, rgba(0,0,0,var(--kt-pk,.6)) 0%, rgba(0,0,0,calc(var(--kt-pk,.6) * .55)) 45%, rgba(0,0,0,0) 100%); }
  .kt-line { display: block; white-space: nowrap; line-height: 1.04; }
  .kt-shadow .kt-line, .kt-shadow .kt-word { text-shadow: 0 3px 14px rgba(0,0,0,.42); }
  /* claude-motion Mask: the padding/negative margin keeps descenders, diacritics and the shadow inside the mask */
  .kt-m { display: inline-block; overflow: hidden; vertical-align: bottom; padding: .12em .16em .2em; margin: -.12em -.16em -.2em; }
  .kt-mi { display: inline-block; transform-origin: 0% 100%; }
  /* brush marks: one filled stroke shape, revealed by a clip wipe, boiled by a turbulence filter */
  .kt-mk { position: relative; display: inline-block; isolation: isolate; }
  .kt-mkw { position: absolute; pointer-events: none; }
  .kt-mkw svg { display: block; width: 100%; height: 100%; overflow: visible; }
  .kt-mk.under .kt-mkw { left: -4%; right: -4%; top: 88%; height: .3em; }
  .kt-mk.marker .kt-mkw { left: -6%; right: -6%; top: 38%; height: .62em; opacity: .9; } /* emitted before the words: paints behind them */
  .kt-mk.box .kt-mkw { left: -7%; right: -7%; top: -6%; bottom: -14%; }
  .kt-mk.strike .kt-mkw { left: -6%; right: -6%; top: 40%; height: .28em; }
  .kt-stack { display: grid; justify-items: center; align-items: center; }
  .kt-stack > * { grid-area: 1 / 1; }
  /* hook */
  .kt-hook-w { position: relative; display: flex; flex-direction: column; align-items: center; }
  .kt-hook-row { display: flex; align-items: baseline; line-height: .86; }
  .kt-hook-key { line-height: .8; font-weight: 900; letter-spacing: -.04em; }
  .kt-hook-word { line-height: .95; font-weight: 900; letter-spacing: -.02em; }
  .kt-hook-sub { margin-top: .5em; font-weight: 600; letter-spacing: -.01em; }
  /* drum (rotisserie cylinder) */
  .kt-drum { position: relative; display: inline-grid; align-items: center; justify-items: center;
    -webkit-mask-image: linear-gradient(to bottom, transparent 0%, rgba(0,0,0,.28) 18%, #000 40%, #000 60%, rgba(0,0,0,.28) 82%, transparent 100%);
            mask-image: linear-gradient(to bottom, transparent 0%, rgba(0,0,0,.28) 18%, #000 40%, #000 60%, rgba(0,0,0,.28) 82%, transparent 100%); }
  .kt-drum-size { grid-area: 1 / 1; display: grid; visibility: hidden; }
  .kt-drum-size span { grid-area: 1 / 1; white-space: nowrap; line-height: 1; padding: 0 .1em; }
  .kt-drum-axis { position: absolute; inset: 0; transform-style: preserve-3d; }
  .kt-drum-cyl { position: absolute; inset: 0; transform-style: preserve-3d; }
  .kt-drum-w { position: absolute; left: 0; top: 50%; width: 100%; text-align: center; white-space: nowrap; line-height: 1; backface-visibility: hidden; -webkit-backface-visibility: hidden; }
  /* scramble: every glyph sits in a cell sized by its FINAL glyph, so the line never reflows */
  .kt-sc { position: relative; display: inline-block; }
  .kt-sc > i { font-style: normal; visibility: hidden; }
  .kt-sc > b { position: absolute; left: 50%; top: 0; transform: translateX(-50%); font-weight: inherit; white-space: pre; }
  /* flip stack */
  .kt-cards { position: relative; width: 100%; }
  .kt-cardrow { position: absolute; left: 0; right: 0; top: 0; display: flex; justify-content: center; }
  .kt-card { position: relative; display: inline-flex; align-items: center; justify-content: center; white-space: nowrap; transform-origin: 50% 0%; backface-visibility: hidden; -webkit-backface-visibility: hidden; opacity: 0; }
  .kt-card .kt-dim { position: absolute; inset: 0; border-radius: inherit; background: #000; opacity: 0; }
  /* spring letters */
  .kt-ch { display: inline-block; transform-origin: 50% 100%; opacity: 0; }
`;

// ---------------------------------------------------------------- helpers --
function fontStack(b, brand) {
  const f = b.font || brand.displayFont || "Montserrat";
  return `'${f}', Montserrat, Inter, system-ui, sans-serif`;
}
const colorOf = (c, brand, fallback) => (c === "accent" ? brand.accent : c || fallback);

// onsets (edit time) for tokens: an explicit {text, at} wins, else the next
// matching spoken word inside the window, else right after the previous token
function alignTimes(tokens, t0, t1, ctx, { step = 0.09, start = t0 } = {}) {
  const spoken = (ctx.words || []).filter((w) => w.start >= t0 - 0.35 && w.start < t1 + 0.05);
  let si = 0, last = start - step;
  return tokens.map((tok) => {
    if (tok && typeof tok === "object" && tok.at !== undefined) { last = ctx.E(tok.at, "kinetic word"); return last; }
    const n = norm(typeof tok === "object" ? tok.text : tok);
    let at = null;
    if (n) for (let k = si; k < spoken.length; k++) if (norm(spoken[k].word) === n) { at = spoken[k].start; si = k + 1; break; }
    if (at === null) at = last + step;
    last = at;
    return at;
  });
}
const tokText = (t) => (typeof t === "object" ? t.text : t);

// A line of masked words. Words rise out of their own mask on their onset
// (claude-motion: translateY 118 % + 5 deg tilt from the baseline corner).
// *word* marks emphasis: those words go inside one .kt-mk span (brush mark).
function maskLine(ctx, { id, text, times, style = "", markStyle = null, markId = id, rise = 0.6, lead = 0.06 }) {
  const { tl, r3, esc } = ctx;
  const raw = text.split(/\s+/).filter(Boolean);
  let inMark = false, html = "";
  const markWords = [];
  raw.forEach((w, i) => {
    const open = !!markStyle && w.startsWith("*"), close = !!markStyle && /\*[.,!?:;]?$/.test(w);
    const clean = w.replace(/^\*|\*(?=[.,!?:;]?$)/g, "");
    if (i) html += " ";
    if (open) { inMark = true; html += `<span class="kt-mk ${markStyle}" id="${markId}-mk">${markStyle === "marker" ? `<span class="kt-mkw" id="${markId}-mkw">${BRUSH.marker(markId)}</span>` : ""}`; }
    const wid = `${id}-w${i}`;
    html += `<span class="kt-m"><span class="kt-mi" id="${wid}">${esc(clean)}</span></span>`;
    tl.push(`gsap.set("#${wid}", { yPercent: 118, rotation: 5 }); ft("#${wid}", { yPercent: 118, rotation: 5 }, { yPercent: 0, rotation: 0, duration: ${rise}, ease: KT.OUT }, ${r3(times[i] - lead)});`);
    if (inMark) markWords.push(i);
    if (close && inMark) { html += `${markStyle === "marker" ? "" : `<span class="kt-mkw" id="${markId}-mkw">${BRUSH[markStyle](markId)}</span>`}</span>`; inMark = false; }
  });
  return { html: `<span class="kt-line" style="${style}">${html}</span>`, count: raw.length, markWords };
}
// words leave up through the same masks, faster than they came (exits ~half)
function maskOut(ctx, id, n, at, { stagger = 0.03, dur = 0.32 } = {}) {
  for (let i = 0; i < n; i++) ctx.tl.push(`ft("#${id}-w${i}", { yPercent: 0, rotation: 0 }, { yPercent: -118, rotation: 0, duration: ${dur}, ease: KT.IN }, ${ctx.r3(at + i * stagger)});`);
}

// hand-drawn brush shapes in a 200 x 20 box (stretched to the phrase); the
// boil filter is a turbulence displacement whose seed the painter steps at 12 fps
const BOIL = (id) => `<filter id="${id}-boil" x="-10%" y="-60%" width="120%" height="220%"><feTurbulence id="${id}-turb" type="fractalNoise" baseFrequency="0.045 0.3" numOctaves="2" seed="1" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="3.2" xChannelSelector="R" yChannelSelector="G"/></filter>`;
const BRUSH = {
  under: (id) => `<svg viewBox="0 0 200 20" preserveAspectRatio="none"><defs>${BOIL(id)}</defs><path filter="url(#${id}-boil)" fill="var(--kt-accent)" d="M2.5 9.6 C 40 6.4, 92 5.2, 140 5 C 166 4.9, 186 3.6, 197.6 1.8 C 200.2 1.6, 200.4 8.6, 197.6 9.6 C 178 12.8, 150 13.6, 116 14.4 C 78 15.2, 40 17, 6 18.8 C 0.8 19, 0 10.2, 2.5 9.6 Z"/></svg>`,
  strike: (id) => `<svg viewBox="0 0 200 20" preserveAspectRatio="none"><defs>${BOIL(id)}</defs><path filter="url(#${id}-boil)" fill="var(--kt-accent)" d="M2 13.6 C 50 10.8, 110 8.6, 196 4.4 C 199.6 4.4, 200 9.6, 196.6 10.2 C 120 14.2, 60 16.4, 5 18.6 C 0.8 18.6, 0 14, 2 13.6 Z"/></svg>`,
  marker: (id) => `<svg viewBox="0 0 200 20" preserveAspectRatio="none"><defs>${BOIL(id)}</defs><path filter="url(#${id}-boil)" fill="var(--kt-accent)" d="M4 3.4 C 60 1.6, 130 2.2, 196 1.2 C 199.4 1.4, 199 18, 195.6 18.4 C 130 19.2, 70 18.2, 5 19 C 1 19, 0.6 3.6, 4 3.4 Z"/></svg>`,
  box: (id) => `<svg viewBox="0 0 200 60" preserveAspectRatio="none"><defs>${BOIL(id)}</defs><path filter="url(#${id}-boil)" fill="none" stroke="var(--kt-accent)" stroke-width="3.2" stroke-linecap="round" d="M8 6 C 70 3, 140 4, 194 6 C 197 22, 197 40, 193 55 C 130 57, 60 57, 7 54 C 4 40, 4 20, 9 8"/></svg>`,
};

function pocket(ctx, id, y, h, t0, tOut, opacity = 0.6) {
  const { tl, r3 } = ctx;
  // a block that starts at frame 0 shows its pocket from frame 0 (a hook never fades up)
  tl.push(t0 <= 0.001 ? `gsap.set("#${id}-pk", { opacity: 1 });` : `gsap.set("#${id}-pk", { opacity: 0 }); ft("#${id}-pk", { opacity: 0 }, { opacity: 1, duration: 0.25, ease: "power2.out" }, ${r3(t0)});`);
  // the exit fades a wrapper: one element never carries both a hidden start and a fade-out
  tl.push(`ft("#${id}-pkx", { opacity: 1 }, { opacity: 0, duration: 0.3, ease: "power2.in" }, ${r3(tOut)});`);
  return `<div id="${id}-pkx"><div id="${id}-pk" class="kt-pocket" style="top:${Math.round(y - h / 2)}px;height:${Math.round(h)}px;--kt-pk:${opacity}"></div></div>`;
}

// ------------------------------------------------------------------ build --
export function buildKinetic(b, id, t0, t1, ctx) {
  const { tl, r3, esc, brand = {} } = ctx;
  const addSfx = ctx.addSfx || (() => {});
  if (!ctx._ktRuntime) { ctx._ktRuntime = true; tl.push(KINETIC_RUNTIME); }
  const over = !b.bg; // over footage: pocket scrim + shadow; on a ground: none
  const ink = colorOf(b.color, brand, over ? "#ffffff" : brand.ink || "#111");
  const accent = colorOf(b.accent, brand, brand.accent || "#FFD84D");
  const vars = `--kt-ink:${ink};--kt-accent:${accent};color:${ink};font-family:${fontStack(b, brand)};`;
  const bgHtml = b.bg ? `<div class="kt-bg" style="background:${b.bg === "accent" ? brand.accent : b.bg}"></div>` : "";
  const exitDur = b.exit ?? 0.35;
  const tOut = r3(t1 - exitDur);
  const D = r3(t1 - t0);
  // reading floor: text that must be read holds max(1 s, 0.3 s/word) after it settles (claude-motion, brag)
  const holdCheck = (settle, nWords, what) => {
    const need = readingHold(nWords), have = r3(tOut - settle);
    if (ctx.warn && have < need - 0.05) ctx.warn.push(`textfx ${b.kind} ${id}: ${what} holds ${have}s after it settles, reading needs ~${r3(need)}s; extend "to" or cut words`);
  };
  const painter = (body) => tl.push(`(() => { const P = { u: 0 }; const paint = () => { const t = tl.time(); ${body} };
    tl.fromTo(P, { u: 0 }, { u: 1, duration: ${D}, ease: "none", onUpdate: paint, immediateRender: false }, ${t0});
    paint(); if (document.fonts) document.fonts.ready.then(paint); })();`);

  // ------------------------------------------------------------- headline
  if (b.kind === "headline") {
    const y = b.y ?? 1240, size = b.size ?? 104, weight = b.weight ?? 800;
    const lines = (b.lines || [b.text]).map((l) => (typeof l === "string" ? { text: l } : l));
    const markStyle = b.mark?.style ?? (lines.some((l) => /\*/.test(l.text)) ? "under" : null);
    let html = "", lastMarkAt = null, lastAt = t0;
    const lineIds = [], turbs = [];
    // swap mode ("not X -> Y"): X rises, gets struck, leaves up through its mask; then Y rises in the same place
    let swapHtml = "", mainStart = t0;
    if (b.swap) {
      const sx = b.swap.text.split(/\s+/);
      const st = b.swap.at !== undefined ? E1(ctx, b.swap.at) : t0;
      const sTimes = alignTimes(sx, t0, t1, ctx, { start: st }).map((x, i) => Math.max(x, st + i * 0.07));
      const sl = maskLine(ctx, { id: `${id}-x`, text: `*${b.swap.text}*`, times: sTimes, markStyle: "strike", markId: `${id}-x`, style: `font-size:${b.swap.size ?? Math.round(size * 0.9)}px;font-weight:${weight};opacity:${b.swap.dim ?? 0.6}` });
      turbs.push(`${id}-x-turb`);
      const strikeAt = b.swap.strikeAt !== undefined ? E1(ctx, b.swap.strikeAt) : r3(Math.max(...sTimes) + 0.45);
      const outAt = b.swap.outAt !== undefined ? E1(ctx, b.swap.outAt) : r3(strikeAt + 0.5);
      tl.push(`ft("#${id}-x-mkw", { clipPath: "inset(-60% 100% -60% 0%)" }, { clipPath: "inset(-60% -2% -60% 0%)", duration: 0.32, ease: KT.OUT }, ${strikeAt});`);
      addSfx(strikeAt, "whoosh", "swap strike", { db: -4 });
      maskOut(ctx, `${id}-x`, sl.count, outAt);
      tl.push(`ft("#${id}-x-mkw", { opacity: 1 }, { opacity: 0, duration: 0.18, ease: "power2.in" }, ${outAt});`);
      swapHtml = `<div class="kt-swap">${sl.html}</div>`;
      mainStart = r3(outAt + (b.swap.gap ?? 0.3)); // X has left before Y rises: no double exposure
    }
    lines.forEach((l, li) => {
      const toks = l.text.split(/\s+/).filter(Boolean);
      const t00 = Math.max(mainStart, li ? lastAt + 0.06 : mainStart);
      const times = alignTimes(toks, mainStart, t1, ctx, { start: t00 }).map((x, i) => Math.max(x, t00 + i * 0.07));
      const lid = `${id}-l${li}`;
      const ml = maskLine(ctx, { id: lid, text: l.text, times, markStyle, markId: id, style: `font-size:${l.size ?? size}px;font-weight:${l.weight ?? weight};${l.color ? `color:${colorOf(l.color, brand, ink)};` : ""}` });
      if (ml.markWords.length) lastMarkAt = Math.max(...ml.markWords.map((k) => times[k]));
      lastAt = Math.max(...times);
      lineIds.push([lid, ml.count]);
      html += ml.html;
    });
    if (markStyle && lastMarkAt !== null) {
      turbs.push(`${id}-turb`);
      // bang-motion mark(): the brush draws 0.4-0.6 s after the marked words start rising
      const ma = b.mark?.at !== undefined ? E1(ctx, b.mark.at) : r3(lastMarkAt + 0.32);
      tl.push(`ft("#${id}-mkw", { clipPath: "inset(-60% 100% -60% 0%)" }, { clipPath: "inset(-60% -2% -60% 0%)", duration: ${b.mark?.dur ?? 0.5}, ease: KT.OUT }, ${ma});`);
      addSfx(ma, "whoosh", "headline mark", { db: -6 });
      tl.push(`ft("#${id}-mkw", { opacity: 1 }, { opacity: 0, duration: 0.2, ease: "power2.in" }, ${tOut});`);
    }
    // line boil: the turbulence seed steps at 12 fps, a pure function of t
    if (turbs.length && b.boil !== false) painter(`for (const k of ${JSON.stringify(turbs)}) { const tb = KT.$(k); if (tb) tb.setAttribute("seed", String(1 + (Math.floor(t * 12) % 53))); }`);
    holdCheck(r3(lastAt + 0.6), lineIds.reduce((n, [, c]) => n + c, 0), "headline");
    // exit: every word leaves up through its mask
    for (const [lid, c] of lineIds) maskOut(ctx, lid, c, tOut);
    const blockH = lines.reduce((s, l) => s + (l.size ?? size) * 1.1, 0);
    const body = `<div class="kt-stack">${swapHtml}<div class="kt-main">${html}</div></div>`;
    return `${bgHtml}${over && b.pocket !== false ? pocket(ctx, id, y, blockH * 2.3, t0, tOut) : ""}<div class="kt${over ? " kt-shadow" : ""}" style="${vars}top:${Math.round(y - blockH / 2)}px">${body}</div>`;
  }

  // --------------------------------------------------------------- spring
  if (b.kind === "spring") {
    const y = b.y ?? 1220, size = b.size ?? 168, weight = b.weight ?? 900;
    const text = b.upper ? b.text.toUpperCase() : b.text;
    const chars = [...text];
    const start = r3((b.start !== undefined ? E1(ctx, b.start) : alignTimes([text.split(/\s+/)[0]], t0, t1, ctx)[0]) - (b.early ?? 0.1));
    const stg = b.stagger ?? 0.045;
    const A = (b.from === "rise" ? 0.9 : -1.15) * size;
    const tilt = b.tilt ?? 16;
    const [fP, fS, fR] = b.freq ?? [1.6, 2.1, 2.8];
    const z = b.zeta ?? 1 / 3;
    const letters = chars.map((c, i) => c === " " ? `<span class="kt-ch" style="opacity:1">&nbsp;</span>` : `<span class="kt-ch" id="${id}-c${i}">${esc(c)}</span>`).join("");
    const data = JSON.stringify(chars.map((c, i) => (c === " " ? null : { i, t: r3(start + i * stg * (1 - 0.3 * i / Math.max(1, chars.length))), r: (i % 2 ? 1 : -1) * tilt * (0.6 + 0.4 * ((i * 7) % 5) / 4) })).filter(Boolean));
    painter(`const L = ${data}; for (const o of L) { const el = KT.$("${id}-c" + o.i); const u = t - o.t;
      if (u < 0) { el.style.opacity = "0"; continue; }
      const yy = KT.spring(u, ${A}, ${fP}, ${z}), rr = KT.spring(u, o.r, ${fR}, ${z}), q = KT.spring(u, -0.45, ${fS}, ${z});
      const ox = t >= ${r3(t1)} ? 1 : t > ${tOut} ? KT.EI((t - ${tOut} - o.i * 0.012) / 0.3) : 0;
      el.style.opacity = String(KT.C(u / 0.05) * (1 - KT.C(ox)));
      el.style.transform = "translateY(" + (yy - ox * ${Math.round(size * 0.9)}).toFixed(1) + "px) rotate(" + rr.toFixed(2) + "deg) scale(" + Math.exp(q / 2).toFixed(3) + "," + Math.exp(-q / 2).toFixed(3) + ")"; }`);
    addSfx(start, "whoosh", "spring title", { db: -6 });
    let sub = "", subH = 0;
    if (b.sub) {
      const st = b.sub.text.split(/\s+/);
      const times = alignTimes(st, t0, t1, ctx, { start: r3(start + chars.length * stg + 0.15) });
      const ml = maskLine(ctx, { id: `${id}-s`, text: b.sub.text, times, style: `font-size:${b.sub.size ?? 54}px;font-weight:${b.sub.weight ?? 600};margin-top:${Math.round(size * 0.12)}px;${b.sub.color ? `color:${colorOf(b.sub.color, brand, ink)};` : "opacity:.92;"}` });
      maskOut(ctx, `${id}-s`, ml.count, tOut);
      sub = ml.html; subH = (b.sub.size ?? 54) * 1.3;
    }
    holdCheck(r3(start + chars.length * stg + 0.7), 1, "title");
    const h = size + subH;
    return `${bgHtml}${over && b.pocket !== false ? pocket(ctx, id, y, h * 2.2, t0, tOut) : ""}<div class="kt${over ? " kt-shadow" : ""}" style="${vars}top:${Math.round(y - h / 2)}px"><span class="kt-line" style="font-size:${size}px;font-weight:${weight};letter-spacing:${b.tracking ?? "-0.02em"};${b.keyColor ? `color:${colorOf(b.keyColor, brand, ink)};` : ""}">${letters}</span>${sub}</div>`;
  }

  // ------------------------------------------------------------- scramble
  if (b.kind === "scramble") {
    const y = b.y ?? 1240, size = b.size ?? 124, weight = b.weight ?? 800;
    const lines = (b.lines || [b.text]).map((l) => (b.upper ? l.toUpperCase() : l));
    const toks = lines.flatMap((l) => l.split(/\s+/).filter(Boolean));
    const lead = b.lead ? b.lead.split(/\s+/) : [];
    const leadTimes = lead.length ? alignTimes(lead, t0, t1, ctx) : [];
    // unspoken words (no transcript match) still get a readable decode: ~0.35 s per word after a 0.5 s preroll
    const onsets = alignTimes(toks, t0, t1, ctx, { step: 0.35, start: (leadTimes.length ? Math.max(...leadTimes) + 0.1 : (b.start !== undefined ? E1(ctx, b.start) : t0)) + 0.5 });
    const start = b.start !== undefined ? E1(ctx, b.start) : r3(Math.max(t0, onsets[0] - (b.preroll ?? 0.45)));
    const leadEnd = leadTimes.length ? r3(Math.max(...leadTimes) + 0.08) : t0;
    // pools: narrow glyphs only (hyperframes-launches s4: width-bounded), from the target's own script and case
    const POOLS = {
      cu: "АБВГДЕЗИЙКЛНОПРСТУХЦЧЬЭЯ", cl: "абвгдезийклнопрстухцчьэя",
      lu: "ABCDEFGHJKLNOPRSTUVXYZ", ll: "abcdefghijklnopqrstuvxyz",
      d: "0123456789", s: "/*+?#<>=",
    };
    const poolFor = (ch) => {
      const sym = b.symbols === false ? "" : POOLS.s;
      if (/\d/.test(ch)) return POOLS.d + sym;
      const up = ch === ch.toUpperCase() && ch !== ch.toLowerCase();
      if (isCyr(ch)) return (up ? POOLS.cu : POOLS.cl) + sym;
      if (/[A-Za-z]/.test(ch)) return (up ? POOLS.lu : POOLS.ll) + sym;
      return null; // punctuation stays
    };
    let wi = 0;
    const W = [];
    const linesHtml = lines.map((l, li) => {
      const words = l.split(/\s+/).filter(Boolean);
      return `<span class="kt-line" style="font-size:${size}px;font-weight:${weight};letter-spacing:${b.tracking ?? "-0.01em"}">${words.map((w) => {
        const k = wi++;
        const on = onsets[k];
        // chars appear as noise left to right, then lock left to right ending just after the spoken onset
        const appear = r3(Math.max(start, leadEnd, on - (b.lockLead ?? 0.55)));
        const lock0 = r3(Math.max(appear + 0.18, on - 0.2)), lock1 = r3(on + (b.lockTail ?? 0.22));
        W.push({ k, appear, lock0, lock1, chars: [...w].map((c, ci) => ({ c, p: poolFor(c), ci })) });
        return [...w].map((c, ci) => `<span class="kt-sc"><i>${esc(c)}</i><b id="${id}-g${k}-${ci}"></b></span>`).join("");
      }).join(" ")}</span>`;
    }).join("");
    const last = Math.max(...W.map((w) => w.lock1));
    holdCheck(last, toks.length + lead.length, "decoded text");
    const shakeAt = b.shake === false ? null : (b.shakeAt !== undefined ? E1(ctx, b.shakeAt) : last);
    const rate = b.rate ?? 18;
    painter(`const W = ${JSON.stringify(W)}; const step = Math.floor((t - ${start}) * ${rate});
      for (const w of W) { const n = w.chars.length; for (const o of w.chars) { const el = KT.$("${id}-g" + w.k + "-" + o.ci);
        const shown = t >= w.appear + o.ci * 0.022; const res = (t - w.lock0) / Math.max(0.05, w.lock1 - w.lock0); const locked = !o.p || (o.ci + 1) / n <= res;
        if (!shown) { el.textContent = ""; continue; }
        if (locked) { el.textContent = o.c; el.style.color = ""; el.style.transform = "translateX(-50%)"; continue; }
        const h = KT.hash(step * 31 + w.k * 17 + o.ci * 7); el.textContent = o.p.charAt(Math.floor(h * o.p.length)); el.style.color = "var(--kt-accent)";
        el.style.transform = "translateX(-50%) translateY(" + ((KT.hash(step * 13 + o.ci * 5 + w.k) - 0.5) * ${b.jitter ?? 0.08 * size}).toFixed(1) + "px)"; } }
      const g = KT.$("${id}-sg"); let x = 0;
      ${shakeAt !== null ? `const su = t - ${shakeAt}; if (su > 0 && su < 0.7) x = ${b.shakeAmp ?? 12} * Math.sin(2 * Math.PI * 13 * su) * Math.exp(-6 * su);` : ""}
      const ox = t > ${tOut} ? KT.EI((t - ${tOut}) / ${exitDur}) : 0;
      g.style.transform = "translateX(" + x.toFixed(1) + "px) translateY(" + (-ox * 40).toFixed(1) + "px)"; g.style.opacity = String(1 - ox);`);
    addSfx(start, "typing-1", "scramble", { db: -8 });
    if (shakeAt !== null) addSfx(shakeAt, "impact", "scramble lock", { db: -6 });
    let leadHtml = "", leadH = 0;
    if (lead.length) {
      const ml = maskLine(ctx, { id: `${id}-ld`, text: b.lead, times: leadTimes, style: `font-size:${b.leadSize ?? 56}px;font-weight:600;margin-bottom:${Math.round(size * 0.12)}px;opacity:.92` });
      maskOut(ctx, `${id}-ld`, ml.count, tOut);
      leadHtml = ml.html; leadH = (b.leadSize ?? 56) * 1.3;
    }
    const h = leadH + lines.length * size * 1.06;
    return `${bgHtml}${over && b.pocket !== false ? pocket(ctx, id, y, h * 2.1, t0, tOut) : ""}<div class="kt${over ? " kt-shadow" : ""}" style="${vars}top:${Math.round(y - h / 2)}px">${leadHtml}<div id="${id}-sg">${linesHtml}</div></div>`;
  }

  // ----------------------------------------------------------------- drum
  if (b.kind === "drum") {
    const y = b.y ?? 1230, size = b.size ?? 120, weight = b.weight ?? 800;
    const items = b.items.map((it) => (typeof it === "string" ? { text: it } : it));
    const N = items.length;
    const S = b.slots ?? Math.max(6, N * 2);
    const step = 360 / S;
    const R = Math.round((b.spacing ?? 1.12) * size / (2 * Math.sin((step * Math.PI) / 360)));
    const H = Math.round(size * (b.rows ?? 2.9));
    const times = alignTimes(items, t0, t1, ctx);
    const turn = b.turn ?? 0.38;
    const cyl = `${id}-cyl`;
    const slots = Array.from({ length: S }, (_, k) => items[k % N].text);
    const words = slots.map((w, k) => `<div class="kt-drum-w" style="transform:translateY(-50%) rotateX(${r3(-k * step)}deg) translateZ(${R}px)">${esc(w)}</div>`).join("");
    // roll in: two slots of spin that land on the first word (slot machine)
    tl.push(`gsap.set("#${cyl}", { rotationX: ${r3(-2 * step)} });`);
    tl.push(`ft("#${cyl}", { rotationX: ${r3(-2 * step)} }, { rotationX: 0, duration: ${b.rollIn ?? 0.55}, ease: KT.OUT }, ${r3(Math.max(t0, times[0] - (b.rollIn ?? 0.55)))});`);
    for (let i = 1; i < N; i++) {
      tl.push(`ft("#${cyl}", { rotationX: ${r3((i - 1) * step)} }, { rotationX: ${r3(i * step)}, duration: ${turn}, ease: "power3.inOut" }, ${r3(times[i] - turn)});`);
      addSfx(r3(times[i] - turn * 0.5), "tick-1", "drum step", { db: -2 });
    }
    let loopAt = null;
    if (b.loop) {
      loopAt = b.loop.at !== undefined ? E1(ctx, b.loop.at) : alignTimes([b.loop.word], t0, t1, ctx, { start: times[N - 1] + 0.3 })[0];
      const spin = b.loop.dur ?? 0.95;
      // the rest of the circle, back to the first word: "round and round"
      tl.push(`ft("#${cyl}", { rotationX: ${r3((N - 1) * step)} }, { rotationX: ${S * step}, duration: ${spin}, ease: "power2.inOut" }, ${r3(loopAt - spin * 0.35)});`);
      addSfx(r3(loopAt - spin * 0.35), "whoosh", "drum loop spin");
    }
    holdCheck(r3((loopAt ?? times[N - 1]) + 0.6), 1 + (b.tail ? b.tail.split(/\s+/).length : 0), "last drum word");
    const drumColor = colorOf(b.drumColor ?? "accent", brand, accent);
    // the drum fades/ rises in with the first roll; leaves fast at the end
    tl.push(`gsap.set("#${id}-d", { opacity: 0, y: 30 }); ft("#${id}-d", { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.35, ease: KT.OUT }, ${r3(Math.max(t0, times[0] - (b.rollIn ?? 0.55)))});`);
    tl.push(`ft("#${id}-dx", { opacity: 1, y: 0 }, { opacity: 0, y: -40, duration: ${exitDur}, ease: KT.IN }, ${tOut});`);
    let leadHtml = "", tailHtml = "", extra = 0;
    if (b.lead) {
      const lt = b.lead.split(/\s+/);
      const ml = maskLine(ctx, { id: `${id}-ld`, text: b.lead, times: alignTimes(lt, t0, t1, ctx), style: `font-size:${b.leadSize ?? 60}px;font-weight:600;margin-bottom:${Math.round(-size * 0.05)}px` });
      maskOut(ctx, `${id}-ld`, ml.count, tOut); leadHtml = ml.html; extra += (b.leadSize ?? 60);
    }
    if (b.tail) {
      const tt = b.tail.split(/\s+/);
      const ml = maskLine(ctx, { id: `${id}-tl`, text: b.tail, times: alignTimes(tt, t0, t1, ctx, { start: loopAt ?? times[N - 1] + 0.3 }), style: `font-size:${b.tailSize ?? 60}px;font-weight:700;margin-top:${Math.round(-size * 0.08)}px` });
      maskOut(ctx, `${id}-tl`, ml.count, tOut); tailHtml = ml.html; extra += (b.tailSize ?? 60);
    }
    const sizer = `<div class="kt-drum-size">${items.map((it) => `<span>${esc(it.text)}</span>`).join("")}</div>`;
    const drum = `<div id="${id}-dx"><div id="${id}-d" class="kt-drum" style="height:${H}px;perspective:${Math.round(size * 9)}px;font-size:${size}px;font-weight:${weight};color:${drumColor};letter-spacing:-0.02em">${sizer}<div class="kt-drum-axis" style="transform:translateZ(${-R}px)"><div class="kt-drum-cyl" id="${cyl}">${words}</div></div></div></div>`;
    const h = H + extra * 0.8;
    return `${bgHtml}${over && b.pocket !== false ? pocket(ctx, id, y, h * 1.9, t0, tOut) : ""}<div class="kt${over ? " kt-shadow" : ""}" style="${vars}top:${Math.round(y - h / 2)}px">${leadHtml}${drum}${tailHtml}</div>`;
  }

  // ------------------------------------------------------------ flipstack
  if (b.kind === "flipstack") {
    const y = b.y ?? 1250, size = b.size ?? 76, weight = b.weight ?? 800;
    const items = b.items.map((it) => (typeof it === "string" ? { text: it } : it));
    const times = alignTimes(items, t0, t1, ctx).map((x) => r3(x - (b.early ?? 0.12)));
    const card = { bg: "#ffffff", ink: "#111111", radius: 30, pad: 46, minW: 600, h: Math.round(size * 2.05), ...(b.card || {}) };
    const off = b.offset ?? Math.round(card.h * 0.7), sc = b.scaleStep ?? 0.06, dimStep = b.dimStep ?? 0.22, mess = b.mess ?? 3.2;
    const flat = !!b.flat;
    const [fP, z] = [b.freq ?? 1.25, b.zeta ?? 0.42];
    const rows = items.map((it, i) => `<div class="kt-cardrow" style="z-index:${i + 1}"><div class="kt-card" id="${id}-c${i}" style="min-width:${card.minW}px;height:${card.h}px;padding:0 ${card.pad}px;border-radius:${card.radius}px;background:${i === items.length - 1 && b.lastAccent ? accent : card.bg};color:${i === items.length - 1 && b.lastAccent ? (brand.onAccent || card.ink) : card.ink};font-size:${size}px;font-weight:${weight};letter-spacing:-0.02em;box-shadow:0 18px 44px rgba(0,0,0,.38)">${esc(it.text)}<i class="kt-dim" id="${id}-d${i}"></i></div></div>`).join("");
    const shakeAt = b.shakeAt !== undefined ? E1(ctx, b.shakeAt) : null;
    painter(`const T = ${JSON.stringify(times)}; const n = T.length;
      for (let i = 0; i < n; i++) { const el = KT.$("${id}-c" + i), dm = KT.$("${id}-d" + i); const u = t - T[i];
        if (u < 0) { el.style.opacity = "0"; continue; }
        // hinge at the top edge: starts folded past horizontal (-100 deg, back face, hidden), falls, overshoots, rings
        const th = KT.spring(u, -100, ${fP}, ${z});
        // depth = how many later cards have landed (smooth), pushes this card up and back
        let d = 0; for (let j = i + 1; j < n; j++) d += KT.EO((t - T[j] - 0.06) / 0.45);
        let x = 0; ${shakeAt !== null ? `const su = t - ${shakeAt} - i * 0.04; if (su > 0 && su < 0.9) x = 16 * Math.sin(2 * Math.PI * 7 * su + i) * Math.exp(-5 * su);` : ""}
        const ox = t >= ${r3(t1)} ? 1 : t > ${tOut} ? KT.EI((t - ${tOut} - (n - 1 - i) * 0.05) / 0.3) : 0; // staggered exit, but always gone by the block end
        const ty = -d * ${off} + ox * 260, s = Math.pow(1 - ${sc}, d);
        // older cards settle slightly askew: a messy pile, deterministic per card
        const rz = Math.min(1, d) * (KT.hash(i * 7 + 3) - 0.5) * 2 * ${mess}; x += Math.min(1, d) * (KT.hash(i * 11 + 5) - 0.5) * 30;
        ${flat
          ? `const c = Math.cos(th * Math.PI / 180); el.style.opacity = c <= 0 ? "0" : String(1 - ox); el.style.transform = "translateX(" + x.toFixed(1) + "px) translateY(" + ty.toFixed(1) + "px) rotate(" + rz.toFixed(2) + "deg) scale(" + s.toFixed(4) + "," + (s * Math.max(0, c)).toFixed(4) + ")";`
          : `el.style.opacity = String(1 - ox); el.style.transform = "translateX(" + x.toFixed(1) + "px) translateY(" + ty.toFixed(1) + "px) rotate(" + rz.toFixed(2) + "deg) scale(" + s.toFixed(4) + ") perspective(${Math.round(card.h * 7)}px) rotateX(" + th.toFixed(2) + "deg)";`}
        dm.style.opacity = String(Math.min(0.62, d * ${dimStep})); }`);
    holdCheck(r3(times[times.length - 1] + 0.7), items.length, "card stack");
    times.forEach((t) => addSfx(r3(t + 0.08), "pop", "flip card", { db: -2 }));
    if (shakeAt !== null) addSfx(shakeAt, "whoosh", "stack shake", { db: -6 });
    const h = card.h + off * (items.length - 1);
    // the front card's top sits at y - card.h/2; older cards rise above it
    return `${bgHtml}${over && b.pocket !== false ? pocket(ctx, id, y - off * (items.length - 1) / 2, h * 1.9, t0, tOut, 0.5) : ""}<div class="kt" style="${vars}top:${Math.round(y - card.h / 2)}px"><div class="kt-cards">${rows}</div></div>`;
  }

  // ----------------------------------------------------------------- hook
  if (b.kind === "hook") {
    const y = b.y ?? 1250, keySize = b.keySize ?? 270, wordSize = b.wordSize ?? 118, subSize = b.subSize ?? 54;
    const key = b.key ?? "", word = b.upper === false ? b.word : (b.word || "").toUpperCase();
    const keyColor = colorOf(b.keyColor ?? "accent", brand, accent);
    const S0 = b.zoomFrom ?? 2.7;
    const pullAt = b.pullAt !== undefined ? E1(ctx, b.pullAt) : r3(t0 + 0.14);
    const pullDur = b.pullDur ?? 0.6;
    const punchAt = b.punchAt !== undefined ? E1(ctx, b.punchAt) : (b.word ? alignTimes([b.word], t0, t1, ctx, { start: pullAt + pullDur })[0] : pullAt + pullDur);
    const z0 = b.footFrom ?? 1.24, zp = b.punch ?? 1.13, zs = b.settle ?? 1.07;
    const footSel = b.footage === false ? null : (ctx.punchSel ?? "punch");
    const cy0 = b.startY ?? 880; // where the key glyph sits at frame 0 (over the face, cropped by the edges)
    let sub = "", subH = 0;
    if (b.sub) {
      const st = b.sub.split(/\s+/);
      const ml = maskLine(ctx, { id: `${id}-s`, text: b.sub, times: alignTimes(st, t0, t1, ctx, { start: punchAt + 0.2 }).map((x) => Math.max(x, pullAt + pullDur * 0.7)), style: `font-size:${subSize}px` });
      maskOut(ctx, `${id}-s`, ml.count, tOut);
      sub = `<div class="kt-hook-sub">${ml.html}</div>`; subH = subSize * 1.8;
    }
    // one painter owns the type world AND the footage wrapper: a pure function of t.
    // Geometry (where the key glyph sits in the lockup) is measured OUTSIDE the
    // timeline: once at build and again when the fonts are ready; paint() only reads it.
    const row = (b.layout ?? "stack") === "row";
    const h = row ? Math.max(keySize, wordSize) * 0.86 + subH : keySize * 0.8 + wordSize * 0.95 + subH;
    const top = Math.round(y - h / 2);
    tl.push(`const ${id}G = { dx: 0, dy: ${cy0 - Math.round(top + (row ? Math.max(keySize, wordSize) * 0.43 : keySize * 0.4))} };
    const ${id}M = () => { const w = KT.$("${id}-w"), k = KT.$("${id}-key"); if (!w || !k) return;
      const kx = k.offsetLeft + k.offsetWidth / 2, ky = k.offsetTop + k.offsetHeight / 2;
      w.style.transformOrigin = kx.toFixed(1) + "px " + ky.toFixed(1) + "px";
      ${id}G.dx = 540 - (w.offsetLeft + kx); ${id}G.dy = ${cy0} - (w.offsetTop + w.offsetParent.offsetTop + ky); };
    ${id}M(); if (document.fonts) document.fonts.ready.then(${id}M);`);
    painter(`const w = KT.$("${id}-w"), f = ${footSel ? `KT.$("${footSel}")` : "null"};
      const e = KT.EO((t - ${pullAt}) / ${pullDur});
      let s = ${S0} * Math.pow(1 / ${S0}, e); // log-space pull back: constant perceived speed
      const pu = t - ${punchAt}; if (pu >= 0) s *= 1 + KT.spring(pu, 0.07, 3.2, 0.3);
      const ox = t > ${tOut} ? KT.EI((t - ${tOut}) / ${exitDur}) : 0;
      const dx = ${id}G.dx * (1 - e), dy = ${id}G.dy * (1 - e) - ox * 60;
      w.style.transform = "translate(" + dx.toFixed(1) + "px," + dy.toFixed(1) + "px) scale(" + s.toFixed(4) + ")"; w.style.opacity = String(1 - ox);
      if (f) { let z = 1 + (${z0} - 1) * (1 - e); if (pu >= 0) z = ${zs} + KT.spring(pu, ${r3(zp - zs)}, 2.2, 0.35);
        if (t > ${tOut}) z = z + (1 - z) * KT.INOUT(KT.C((t - ${tOut}) / ${exitDur}));
        f.style.transform = "scale(" + Math.max(1, z).toFixed(4) + ")"; }`);
    holdCheck(r3(pullAt + pullDur), 2, "claim");
    addSfx(pullAt, "whoosh", "hook pull back", { db: -4 });
    addSfx(punchAt, "impact", "hook punch");
    const keyEl = `<div class="kt-hook-key" id="${id}-key" style="font-size:${keySize}px;color:${keyColor}">${esc(key)}</div>`;
    const wordEl = word ? `<div class="kt-hook-word" style="font-size:${wordSize}px">${esc(word)}</div>` : "";
    const lock = `<div class="kt-hook-w" id="${id}-w">${row ? `<div class="kt-hook-row" style="gap:${Math.round(wordSize * 0.26)}px">${keyEl}${wordEl}</div>` : keyEl + wordEl}${sub}</div>`;
    return `${bgHtml}${over && b.pocket !== false ? pocket(ctx, id, y, h * 1.8, t0, tOut, 0.55) : ""}<div class="kt${over ? " kt-shadow" : ""}" style="${vars}top:${top}px">${lock}</div>`;
  }

  throw new Error(`unknown kinetic kind '${b.kind}'`);
}

// an original-seconds time through the reel's mapping
function E1(ctx, t) { return ctx.E(t, "kinetic"); }

// for INTEGRATION: the block's approximate height in px, so build.mjs can ask the
// face-aware placer for a band (y is the block CENTRE)
export function blockHeight(b) {
  const z = b.size;
  switch (b.kind) {
    case "hook": return (b.layout === "row" ? Math.max(b.keySize ?? 270, b.wordSize ?? 118) * 0.86 : (b.keySize ?? 270) * 0.8 + (b.wordSize ?? 118) * 0.95) + (b.sub ? (b.subSize ?? 54) * 1.8 : 0);
    case "drum": return (z ?? 120) * (b.rows ?? 2.9) + (b.lead ? 60 : 0) + (b.tail ? 60 : 0);
    case "scramble": return (b.lead ? 73 : 0) + (b.lines || [b.text]).length * (z ?? 124) * 1.06;
    case "flipstack": { const h = Math.round((z ?? 76) * 2.05); return h + Math.round(h * 0.7) * ((b.items || []).length - 1); }
    case "headline": return (b.lines || [b.text]).reduce((s, l) => s + ((l && l.size) || z || 104) * 1.1, 0);
    case "spring": return (z ?? 168) + (b.sub ? (b.sub.size ?? 54) * 1.3 : 0);
    default: return 300;
  }
}

// for INTEGRATION: the `y` (block centre; for flipstack the FRONT card centre)
// that puts the block's top edge at `top` (e.g. placer.card(...).y)
export function placeY(b, top) {
  const h = blockHeight(b);
  if (b.kind === "flipstack") return Math.round(top + h - Math.round((b.size ?? 76) * 2.05) / 2);
  return Math.round(top + h / 2);
}

// for INTEGRATION: how long a block's text needs on screen after it settles
// (claude-motion: >= 1 s, +0.25 s per word past three; brag: ~0.3 s per word)
export function readingHold(words) { return Math.max(1, 0.3 * words, 1 + 0.25 * Math.max(0, words - 3)); }
