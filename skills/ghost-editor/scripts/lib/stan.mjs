// Stan style for build.mjs (recipes/stan-style; from @nicktarmo's tool tutorial reel): a seated talking-head tool
// tutorial with screen recordings. Blocks (reel.json beats; every time is an ORIGINAL-recording second, like the rest):
//   panel    a screen recording fills the top band (cover-cropped, pops in 1.05 -> 1 and out 1 -> 0.95, mouse-click SFX).
//            The speaker moves down only as far as the eyes need to sit just under the band, once per run of adjacent
//            panels (so back-to-back panels swap without the speaker bouncing). The panel sits BEHIND the speaker: build.mjs
//            cuts them out (BiRefNet, the panel seconds only) and draws the cut-out over it (stanMatteWindows). The
//            reference never moved: its eyes sat at 42 % of the frame, just under the band (37-40 %), hair over the screen.
//   hook     the first seconds: rows of icons around a 1-2 line bold title in black on white strips, over the speaker
//   diagram  a white frame entered by a zoom-blur from the speaker: icons and labels joined by curved black lines that
//            draw on (stroke-dashoffset tweened on the timeline), captions turn black and go one word at a time
//   step     "[Step n]" + a title + icons over the chest, stacked above the caption (pair it with a panel)
//   cta      «Comment "WORD" for ...» + a logo, in the step's place
//   aside    "*text*" above the head (a spoken joke)
// and the `chest` caption style: small lowercase phrases (3-6 words) at ~68 % height that CUT on their first word (no
// animation), one bigger word at a time in `single` windows (the hook; every diagram), at the forehead (~29 %) in `top`
// windows and for `emphasis` words, an optional `strobe`. Measured on the reference frames (1080x1920): phrases ~38 px
// Inter medium centred at y 1305, single words ~66 px, top words ~64 px at y 557, step/cta text ~46 px, icons ~88 px.
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const W = 1080, H = 1920;
export const STAN = { capY: 1305, size: 38, wordSize: 66, topY: 557, topSize: 64, inkY: 1378, panelH: 768, eyeGap: 80, maxWords: 6, maxChars: 30 };
const TYPES = new Set(["panel", "hook", "diagram", "step", "cta", "aside"]);
export const isStanBeat = (b) => TYPES.has(b.type);

export const STAN_CSS = `
  .st-panel { overflow: hidden; background: #000; transform-origin: 50% 0; }
  .st-panel video { width: 100%; height: 100%; object-fit: cover; display: block; }
  .st-icon { display: inline-flex; align-items: center; gap: 0.32em; }
  .st-icon img { display: block; box-sizing: border-box; }
  .st-ilabel { font-family: "Inter Tight", Inter, sans-serif; font-weight: 700; letter-spacing: -0.02em; color: #fff; white-space: nowrap; text-shadow: 0 2px 10px rgba(0,0,0,.45); }
  .st-hook { left: 90px; right: 90px; display: flex; flex-direction: column; align-items: center; gap: 26px; }
  .st-row { display: flex; width: 100%; justify-content: space-between; align-items: center; }
  .st-row.c { justify-content: center; gap: 34px; }
  .st-title { display: flex; flex-direction: column; align-items: center; }
  .st-strip { display: block; width: fit-content; background: #fff; color: #000; font-family: "Inter Tight", Inter, sans-serif; font-weight: 800; letter-spacing: -0.035em; line-height: 1.02; padding: 0.06em 0.2em 0.1em; border-radius: 0.2em; white-space: nowrap; }
  .st-strip + .st-strip { margin-top: -0.06em; }
  .st-diagram { background: #fff; }
  .st-links { position: absolute; left: 0; top: 0; width: ${W}px; height: ${H}px; overflow: visible; }
  .st-node { position: absolute; transform: translate(-50%, -50%); }
  .st-node-in { display: flex; align-items: center; gap: 0.3em; white-space: nowrap; }
  .st-ntext { font-family: "Inter Tight", Inter, sans-serif; font-weight: 800; letter-spacing: -0.04em; color: #111; line-height: 1; }
  .st-diagram .st-ilabel { color: #111; text-shadow: none; font-weight: 800; }
  .st-dot { position: absolute; width: 30px; height: 30px; margin: -15px 0 0 -15px; border-radius: 50%; background: #111; box-shadow: 0 0 0 5px #fff, 0 0 0 8px #111; }
  .st-label { left: 60px; right: 60px; display: flex; flex-direction: column; align-items: center; color: #fff; font-family: Inter, sans-serif; text-shadow: 0 2px 10px rgba(0,0,0,.55), 0 1px 2px rgba(0,0,0,.45); text-align: center; }
  .st-l1, .st-l2 { font-weight: 500; letter-spacing: -0.02em; line-height: 1.12; white-space: nowrap; }
  .st-label .st-row { margin-top: 10px; }
  .st-aside { left: 40px; right: 40px; text-align: center; color: #fff; font-family: Inter, sans-serif; font-weight: 600; letter-spacing: -0.02em; white-space: nowrap; text-shadow: 0 3px 14px rgba(0,0,0,.5); }
  .st-cap { position: absolute; left: 50%; transform: translate(-50%, -50%); white-space: nowrap; text-align: center; color: #fff; font-family: Inter, system-ui, sans-serif; font-weight: 500; letter-spacing: -0.01em; line-height: 1.1; text-shadow: 0 2px 10px rgba(0,0,0,.55), 0 1px 2px rgba(0,0,0,.45); }
  .st-cap.single, .st-cap.top { font-weight: 600; letter-spacing: -0.02em; }
  .st-cap.ink { color: #111; text-shadow: none; font-weight: 700; }
`;

const probe = (p) => {
  const o = JSON.parse(execFileSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration", "-of", "json", p]).toString());
  return { w: o.streams?.[0]?.width ?? 0, h: o.streams?.[0]?.height ?? 0, dur: parseFloat(o.format?.duration ?? "0") };
};
const nrm = (s) => String(s).toLowerCase().replace(/ё/g, "е").replace(/[^\p{L}\p{N}%/]+/gu, "");
// rough rendered width of a line (Inter-ish ~0.53 em per char): to shrink a line that would leave the frame
const fitSize = (text, size, maxW, k = 0.53) => Math.min(size, Math.floor(maxW / Math.max(1, String(text).length * k)));

// ------------------------------------------------------------------ icons (user images, Fluent emoji, simple-icons)
// each use gets its own copy (assets/icons/<name>-<use id>): the same file in two <img> trips hyperframes'
// duplicate_media_discovery_risk
function perUse(ctx, file, use) {
  const ext = path.extname(file), base = path.basename(file, ext);
  fs.mkdirSync(path.join(ctx.A, "icons"), { recursive: true });
  fs.copyFileSync(file, path.join(ctx.A, "icons", `${base}-${use}${ext}`));
  return `assets/icons/${base}-${use}${ext}`;
}
function iconSrc(it, ctx, what, use) {
  if (it.emoji) {
    const src = path.join(ctx.LIB, "emoji", `${it.emoji}.png`);
    if (!fs.existsSync(src)) ctx.die(`${what}: emoji "${it.emoji}" is not in library/emoji (ls library/emoji/*.png; scripts/emoji_fetch.py)`);
    return perUse(ctx, src, use);
  }
  if (it.icon) return perUse(ctx, path.join(ctx.proj, ctx.icon(it.icon)), use); // simple-icons slug, fetched at build time (never bundled)
  if (it.src) return perUse(ctx, path.join(ctx.proj, ctx.userAsset(it.src)), use);
  return null;
}
function iconHtml(it, ctx, what, size, id) {
  const o = typeof it === "string" ? { emoji: it } : it;
  const img = iconSrc(o, ctx, what, id);
  const s = o.size ?? size;
  const tile = o.bg ? `background:${o.bg};border-radius:${Math.round(s * 0.14)}px;padding:${Math.round(s * 0.14)}px;` : "";
  const im = img ? `<img src="${img}" style="width:${s}px;height:${s}px;object-fit:contain;${tile}${o.invert ? "filter:invert(1);" : ""}"/>` : "";
  const lab = o.label ? `<span class="st-ilabel" style="font-size:${Math.round(o.labelSize ?? s * 0.42)}px${o.color ? `;color:${o.color}` : ""}">${ctx.esc(o.label)}</span>` : "";
  if (!im && !lab) ctx.die(`${what}: an icon needs emoji, icon, src or label`);
  return `<span id="${id}" class="st-icon">${im}${lab}</span>`;
}

// edit-time windows where panels stand BEHIND the speaker (behind: false = the panel covers the speaker), one per run of
// back-to-back panels: build.mjs mattes these source seconds and draws the cut-out over the panels
export function stanMatteWindows(beats, E) {
  const ws = beats.filter((b) => b.type === "panel" && b.behind !== false).map((b) => {
    const t0 = E(b.at, "panel at");
    return [t0, b.to === undefined ? t0 + 3 : E(b.to, "panel to")];
  }).sort((a, b) => a[0] - b[0]);
  const out = [];
  for (const w of ws) { const l = out.at(-1); if (l && w[0] <= l[1] + 0.1) l[1] = Math.max(l[1], w[1]); else out.push([...w]); }
  return out;
}

// ------------------------------------------------------------------ prepare: panel runs, the speaker shift, windows
// Runs first (before any beat is built) so labels and captions know where the face is during a panel.
export function stanPrepare(beats, ctx) {
  const { E, r3, placer, face, warn } = ctx;
  const cap = ctx.cap || {};
  const S = { ...STAN, capY: cap.y ?? STAN.capY, size: cap.size ?? STAN.size, wordSize: cap.wordSize ?? STAN.wordSize,
    topY: cap.topY ?? STAN.topY, topSize: cap.topSize ?? STAN.topSize, inkY: cap.inkY ?? STAN.inkY };
  const end = (b, t0, d) => (b.to === undefined ? t0 + d : E(b.to, `${b.type} to`));
  const panels = beats.filter((b) => b.type === "panel").map((b) => {
    const t0 = E(b.at, "panel at");
    return { b, t0, t1: end(b, t0, 3), h: b.h ?? S.panelH };
  }).sort((a, b) => a.t0 - b.t0);
  const runs = [];
  for (const p of panels) {
    const last = runs.at(-1);
    if (last && p.t0 <= last.t1 + 0.6) { last.t1 = Math.max(last.t1, p.t1); last.h = Math.max(last.h, p.h); last.panels.push(p); }
    else runs.push({ t0: p.t0, t1: p.t1, h: p.h, panels: [p] });
  }
  for (const r of runs) {
    // the eyes (screen px, with the camera's zoom) at their highest over the run, plus the gap under the band
    const sp = face ? placer.span(r.t0, r.t1) : null;
    const want = sp && sp.seen ? r.h + (r.panels[0].b.gap ?? S.eyeGap) - sp.eyes : 0;
    r.shift = Math.round(Math.max(0, Math.min(r.h - 60, want)));
    if (sp && sp.seen && want > r.h - 60) warn.push(`panel ${r3(r.t0)}-${r3(r.t1)} s: the eyes sit at ${Math.round(sp.eyes)} px, too high for a ${r.h} px band even with the speaker moved ${r.shift} px; use a smaller "h"`);
    if (!face) warn.push("panel: no face track, the speaker is not reframed under the band (run scripts/face_track.py)");
  }
  panels.forEach((p, i) => {
    p.prevAdj = i > 0 && p.t0 - panels[i - 1].t1 <= 0.08;
    p.nextAdj = i + 1 < panels.length && panels[i + 1].t0 - p.t1 <= 0.08;
  });
  const shiftAt = (t) => runs.find((r) => t >= r.t0 - 0.05 && t < r.t1)?.shift ?? 0;
  const inPanel = (t0, t1) => runs.some((r) => t0 < r.t1 && t1 > r.t0);
  const inkWins = beats.filter((b) => b.type === "diagram").map((b) => { const t0 = E(b.at, "diagram at"); return [t0, end(b, t0, 4)]; });
  return { S, panels, runs, shiftAt, inPanel, inkWins, capDrops: [], usedPip: runs.some((r) => r.shift > 0) || inkWins.length > 0 };
}

const beatsOrder = (ctx, b) => (ctx.beats || []).indexOf(b);

// face box on screen over [t0, t1] with the panel shift applied (null without a face track)
function faceSpan(st, ctx, t0, t1) {
  if (!ctx.face) return null;
  const sp = ctx.placer.span(t0, t1);
  if (!sp.seen) return null;
  const d = st.shiftAt((t0 + t1) / 2);
  return { ...sp, top: sp.top + d, bottom: sp.bottom + d, eyes: sp.eyes + d, mouth: sp.mouth + d };
}

// a label stack (step, cta) sits on top of the caption; it moves down (and the captions with it) when it would cover the
// chin, and says so when there is no room left
function stackTop(st, ctx, t0, t1, h, what) {
  const { S } = st;
  const capH = S.size * 0.62;
  let bottom = S.capY - capH - 22;
  const fs_ = faceSpan(st, ctx, t0, t1);
  let drop = 0;
  if (fs_ && bottom - h < fs_.bottom + 12) drop = Math.round(fs_.bottom + 12 - (bottom - h));
  const maxDrop = Math.max(0, ctx.placer.safeBottom - (S.capY + capH) - 6);
  if (drop > maxDrop) { ctx.warn.push(`${what}: the label covers the chin by ${drop - maxDrop} px (no room below for it and the caption); shorten it or drop the icons`); drop = maxDrop; }
  if (drop) st.capDrops.push([t0, t1, drop]);
  return Math.round(bottom + drop - h);
}

// ------------------------------------------------------------------ blocks
export function stanBeat(b, id, t0, t1, st, ctx) {
  const { tl, r3, esc, E, warn, die, fgrid, FPS, proj } = ctx;
  const { S } = st;
  const dur = r3(t1 - t0);
  const what = `${b.type} at ${b.at}`;
  const fadeOut = (sel, d = 0.18) => tl.push(`ft("${sel}", { autoAlpha: 1 }, { autoAlpha: 0, duration: ${d}, ease: "power2.in" }, ${r3(t1 - d)});`);
  const pop = (sel, at, k = 0) => tl.push(`ft("${sel}", { autoAlpha: 0, scale: 0.6 }, { autoAlpha: 1, scale: 1, duration: 0.28, ease: "back.out(2)" }, ${r3(at + 0.06 * k)});`);

  if (b.type === "panel") {
    const p = st.panels.find((x) => x.b === b);
    if (!b.src) die(`${what}: needs "src" (a screen recording)`);
    const src = ctx.userAsset(b.src);
    const info = probe(path.resolve(proj, b.src));
    if (info.h < 1080 && info.w < 1920) warn.push(`${what}: ${b.src} is ${info.w}x${info.h}; record at 1080p or better (no 720p)`);
    const inS = b.in ?? 0, F0 = Math.round(t0 * FPS), n = Math.round(t1 * FPS) - F0;
    if (inS + n / FPS > info.dur + 1e-3) die(`${what}: needs ${(n / FPS).toFixed(2)} s of ${b.src} from ${inS} s but it is ${info.dur.toFixed(2)} s long`);
    // followed directly by another panel: stay up 0.2 s longer under the incoming pop (it fades in over this one, never
    // over black); needs 0.2 s more of the recording
    let over = 0;
    if (p.nextAdj) {
      over = Math.round(0.2 * FPS);
      if (inS + (n + over) / FPS > info.dur + 1e-3) { over = 0; warn.push(`${what}: ${b.src} ends with the panel, so the next panel pops in over black; start it ("in") 0.2 s earlier`); }
      const k = st.panels.indexOf(p);
      if (st.panels[k + 1] && beatsOrder(ctx, st.panels[k + 1].b) < beatsOrder(ctx, b)) warn.push(`${what}: list back-to-back panels in time order (the later one must be drawn on top)`);
    }
    const h = p.h;
    const html = `<div id="${id}-in" class="ov st-panel" style="left:0;top:0;width:${W}px;height:${h}px"><video id="${id}-v" src="${src}" data-start="${fgrid(F0)}" data-duration="${fgrid(n + over)}" data-media-start="${inS}" muted playsinline style="object-position:${b.pos ?? "50% 50%"}"></video></div>`;
    tl.push(`ft("#${id}-in", { autoAlpha: 0, scale: 1.05 }, { autoAlpha: 1, scale: 1, duration: 0.2, ease: "power2.out" }, ${r3(t0)});`);
    if (!p.nextAdj) tl.push(`ft("#${id}-in", { autoAlpha: 1, scale: 1 }, { autoAlpha: 0, scale: 0.95, duration: 0.18, ease: "power2.in" }, ${r3(t1 - 0.18)});`);
    else tl.push(`ft("#${id}-in", { autoAlpha: 1, scale: 1 }, { autoAlpha: 0, scale: 1, duration: 0.001, ease: "none" }, ${r3((F0 + n + over) / FPS - 0.001)});`);
    if (b.zoom) tl.push(`ft("#${id}-v", { scale: ${b.zoom[0]} }, { scale: ${b.zoom[1]}, duration: ${dur}, ease: "none" }, ${r3(t0)});`);
    // clicks: recording seconds; default = the "clicks" list of the recording's sidecar json (scripts that record a page
    // write one), false = none
    let clicks = Array.isArray(b.clicks) ? b.clicks : [];
    if (b.clicks === undefined) {
      const side = path.resolve(proj, b.src).replace(/\.[^.]+$/, ".json");
      try { clicks = JSON.parse(fs.readFileSync(side, "utf8")).clicks || []; } catch { clicks = []; }
    }
    for (const c of clicks) {
      const te = t0 + (c - inS);
      if (te >= t0 && te < t1 - 0.05) ctx.beatSfx({ sfx: b.clickSfx }, r3(te), "click-1", "panel click");
    }
    if (b.sfx) ctx.beatSfx(b, t0, null, "panel in");
    return { html, timedInside: true, z: b.behind === false ? undefined : 2 };
  }

  if (b.type === "hook") {
    const rows = !b.icons ? [] : Array.isArray(b.icons[0]) ? b.icons : [b.icons];
    const lines = [].concat(b.title || []);
    const isz = b.iconSize ?? 150;
    const longest = lines.reduce((m, l) => Math.max(m, l.length), 0);
    const tsize = fitSize("x".repeat(longest), b.size ?? 62, 880, 0.5);
    const rowHtml = (row, r) => `<div id="${id}-r${r}" class="st-row${row.length < 2 ? " c" : ""}">${row.map((it, k) => iconHtml(it, ctx, what, isz, `${id}-r${r}i${k}`)).join("")}</div>`;
    const parts = [];
    if (rows[0]) parts.push(rowHtml(rows[0], 0));
    if (lines.length) parts.push(`<div class="st-title" style="font-size:${tsize}px">${lines.map((l, i) => `<span id="${id}-t${i}" class="st-strip">${esc(l)}</span>`).join("")}</div>`);
    if (rows[1]) parts.push(rowHtml(rows[1], 1));
    const est = (rows[0] ? isz + 26 : 0) + lines.length * tsize * 1.16 + (rows[1] ? isz + 26 : 0);
    let y = b.y ?? 250;
    const fs_ = faceSpan(st, ctx, t0, t1);
    if (fs_ && b.y === undefined && y + est > fs_.eyes - 30) {
      y = Math.max(ctx.placer.safeTop, Math.round(fs_.eyes - 30 - est));
      if (y + est > fs_.eyes - 30) warn.push(`${what}: the card reaches the eyes (bottom ~${Math.round(y + est)} px, eyes ${Math.round(fs_.eyes)} px); one title line, a smaller iconSize or one icon row`);
    }
    if (t0 > 0.05) {
      rows.forEach((row, r) => row.forEach((_, k) => pop(`#${id}-r${r}i${k}`, t0, k + r * 2)));
      lines.forEach((_, i) => tl.push(`ft("#${id}-t${i}", { autoAlpha: 0, y: 16 }, { autoAlpha: 1, y: 0, duration: 0.22, ease: "power3.out" }, ${r3(t0 + 0.08 + 0.08 * i)});`));
      ctx.beatSfx(b, t0, "pop", "hook card");
    } // at frame 0 the card is simply there (the first frame is the thumbnail people scroll past)
    fadeOut(`#${id}-in`, 0.2);
    return { html: `<div id="${id}-in" class="ov st-hook" style="top:${y}px">${parts.join("")}</div>` };
  }

  if (b.type === "diagram") {
    const nodes = b.nodes || [];
    if (!nodes.length) die(`${what}: needs "nodes"`);
    const byId = {};
    const nAt = (nd, k) => (nd.at !== undefined ? E(nd.at, `${what} node`) : t0 + 0.3 + 0.45 * k);
    const nodeHtml = nodes.map((nd, k) => {
      const nid = `${id}-n${k}`;
      const at = r3(Math.max(t0 + 0.12, nAt(nd, k)));
      const size = nd.size ?? (nd.text ? 110 : 120);
      // half extents of the node (for line anchors): a text node is ~0.55 em per char wide and one line tall
      const hw = nd.text ? (nd.text.length * size * 0.55) / 2 : size / 2 + (nd.label ? nd.label.length * size * 0.42 * 0.55 + size * 0.15 : 0) / 2;
      const hh = nd.text ? size * 0.55 : size / 2;
      byId[nd.id ?? `n${k}`] = { x: nd.x, y: nd.y, hw, hh, at };
      const inner = nd.text ? `<div class="st-ntext" style="font-size:${size}px">${esc(nd.text)}</div>` : iconHtml(nd, ctx, what, size, `${nid}-i`);
      pop(`#${nid}`, at);
      if (nd.sfx) ctx.beatSfx(nd, at, null, "diagram node");
      return `<div class="st-node" style="left:${nd.x}px;top:${nd.y}px"><div id="${nid}" class="st-node-in">${inner}</div></div>`;
    }).join("");
    const lastAt = Math.max(...Object.values(byId).map((n) => n.at));
    const paths = (b.links || []).map((ln, k) => {
      const A = byId[ln.from], B = byId[ln.to];
      if (!A || !B) die(`${what}: link ${k} names a node that does not exist (${ln.from} -> ${ln.to}); give nodes an "id"`);
      // leave A from the side facing B and arrive at B's facing side; a gentle S between them
      const vert = Math.abs(B.y - A.y) >= Math.abs(B.x - A.x) * 0.6;
      const pad = ln.pad ?? 22;
      let x0, y0, x3, y3;
      if (vert) { const s = Math.sign(B.y - A.y) || 1; x0 = A.x; y0 = A.y + s * (A.hh + pad); x3 = B.x; y3 = B.y - s * (B.hh + pad); }
      else { const s = Math.sign(B.x - A.x) || 1; x0 = A.x + s * (A.hw + pad); y0 = A.y; x3 = B.x - s * (B.hw + pad); y3 = B.y; }
      const bend = ln.bend ?? 0.5;
      const d = vert
        ? `M${x0} ${y0} C${x0} ${r3(y0 + (y3 - y0) * bend)} ${x3} ${r3(y3 - (y3 - y0) * bend)} ${x3} ${y3}`
        : `M${x0} ${y0} C${r3(x0 + (x3 - x0) * bend)} ${y0} ${r3(x3 - (x3 - x0) * bend)} ${y3} ${x3} ${y3}`;
      const at = r3(ln.at !== undefined ? E(ln.at, `${what} link`) : Math.max(t0 + 0.15, A.at + 0.1));
      const dd = r3(ln.dur ?? Math.min(0.7, Math.max(0.25, B.at - at)));
      tl.push(`ft("#${id}-l${k}", { attr: { "stroke-dashoffset": 1 } }, { attr: { "stroke-dashoffset": 0 }, duration: ${dd}, ease: "power1.inOut" }, ${at});`);
      ctx.beatSfx(ln, at, "marker-scribble", "diagram line", { db: -2 });
      let dot = "";
      if (ln.dot) { dot = `<div id="${id}-d${k}" class="st-dot" style="left:${x3}px;top:${y3}px"></div>`; pop(`#${id}-d${k}`, r3(at + dd - 0.05)); }
      return { path: `<path id="${id}-l${k}" d="${d}" fill="none" stroke="${b.ink ?? "#111"}" stroke-width="${ln.width ?? 5}" stroke-linecap="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>`, dot };
    });
    // entrance: the speaker zooms into a blur while the white frame resolves out of one (pip: the camera's outer wrapper)
    tl.push(`ft("#pip", { scale: 1, filter: "blur(0px)" }, { scale: 1.4, filter: "blur(16px)", duration: 0.24, ease: "power2.in" }, ${r3(Math.max(0, t0 - 0.12))});`);
    tl.push(`ft("#pip", { scale: 1.4, filter: "blur(16px)" }, { scale: 1, filter: "blur(0px)", duration: 0.02, ease: "none" }, ${r3(t0 + 0.24)});`);
    tl.push(`ft("#${id}-sc", { autoAlpha: 0, scale: 1.12, filter: "blur(14px)" }, { autoAlpha: 1, scale: 1, filter: "blur(0px)", duration: 0.22, ease: "power2.out" }, ${r3(t0)});`);
    // exit: the frame blurs away and the speaker settles back out of a smaller zoom-blur
    tl.push(`ft("#${id}-sc", { autoAlpha: 1, scale: 1, filter: "blur(0px)" }, { autoAlpha: 0, scale: 1.06, filter: "blur(14px)", duration: 0.2, ease: "power2.in" }, ${r3(t1 - 0.2)});`);
    tl.push(`ft("#pip", { scale: 1.2, filter: "blur(10px)" }, { scale: 1, filter: "blur(0px)", duration: 0.26, ease: "power2.out" }, ${r3(t1 - 0.12)});`);
    ctx.beatSfx({ sfx: b.sfx }, r3(t0 - 0.12), "whoosh", "diagram in");
    if (lastAt > t1 - 0.4) warn.push(`${what}: the last node lands ${r3(t1 - lastAt)} s before the frame leaves; give the diagram a later "to"`);
    const svg = `<svg class="st-links" viewBox="0 0 ${W} ${H}">${paths.map((x) => x.path).join("")}</svg>`;
    return { html: `<div id="${id}-sc" class="scene st-diagram"${b.bg ? ` style="background:${b.bg}"` : ""}>${svg}${nodeHtml}${paths.map((x) => x.dot).join("")}</div>`, track: 4 };
  }

  if (b.type === "step" || b.type === "cta") {
    const tsz = b.size ?? 46, isz = b.iconSize ?? (b.type === "cta" ? 92 : 88);
    let l1 = "", l2 = "";
    if (b.type === "step") {
      const label = b.label ?? (ctx.cyr ? "Шаг" : "Step");
      l1 = `[${label} ${b.n ?? ""}]`.replace(" ]", "]");
      l2 = b.title || "";
    } else {
      const word = b.word || die(`${what}: needs "word" (the comment keyword)`);
      const tpl = b.text ?? (ctx.cyr ? 'Напиши "{word}" в комментариях' : 'Comment "{word}" for the prompt');
      l2 = tpl.replace("{word}", word);
    }
    const icons = [].concat(b.icons || (b.logo ? [b.logo] : []));
    const h = (l1 ? tsz * 1.12 : 0) + (l2 ? tsz * 1.12 : 0) + (icons.length ? isz + 10 : 0);
    const top = stackTop(st, ctx, t0, t1, h, what);
    const s1 = fitSize(l1, tsz, 940), s2 = fitSize(l2, tsz, 940);
    const html = `<div id="${id}-in" class="ov st-label" style="top:${top}px">${l1 ? `<div class="st-l1" style="font-size:${s1}px">${esc(l1)}</div>` : ""}${l2 ? `<div class="st-l2" style="font-size:${s2}px">${esc(l2)}</div>` : ""}${icons.length ? `<div class="st-row c">${icons.map((it, k) => iconHtml(it, ctx, what, isz, `${id}-i${k}`)).join("")}</div>` : ""}</div>`;
    tl.push(`ft("#${id}-in", { autoAlpha: 0, y: 10, filter: "blur(8px)" }, { autoAlpha: 1, y: 0, filter: "blur(0px)", duration: 0.18, ease: "power2.out" }, ${r3(t0)});`);
    fadeOut(`#${id}-in`, 0.15);
    ctx.beatSfx(b, t0, "pop", `${b.type} label`);
    return { html };
  }

  if (b.type === "aside") {
    const size = fitSize(`*${b.text}*`, b.size ?? 66, 980);
    let y = b.y ?? S.topY - 40;
    const fs_ = faceSpan(st, ctx, t0, t1);
    if (fs_ && b.y === undefined && y + size * 0.62 > fs_.eyes - 70) {
      y = Math.max(ctx.placer.safeTop + size * 0.62, fs_.eyes - 70 - size * 0.62);
      if (y + size * 0.62 > fs_.eyes - 40) warn.push(`${what}: no room above the eyes for the aside; give it a "y"`);
    }
    if (st.inPanel(t0, t1) && y < (st.runs.find((r) => t0 < r.t1 && t1 > r.t0)?.h ?? 0)) warn.push(`${what}: it sits on the panel; asides belong on a full speaker shot`);
    const html = `<div id="${id}-in" class="ov st-aside" style="top:${Math.round(y - size * 0.6)}px;font-size:${size}px${b.italic ? ";font-style:italic" : ""}">*${esc(b.text)}*</div>`;
    tl.push(`ft("#${id}-in", { autoAlpha: 0, scale: 0.9 }, { autoAlpha: 1, scale: 1, duration: 0.16, ease: "power2.out" }, ${r3(t0)});`);
    fadeOut(`#${id}-in`, 0.15);
    if (b.sfx) ctx.beatSfx(b, t0, null, "aside");
    return { html };
  }
  die(`stan: unknown block ${b.type}`);
}

// the camera's outer wrapper moves down under each run of panels (one move per run: no bounce between panels)
export function stanPipTweens(st, ctx) {
  const { tl, r3 } = ctx;
  if (!st.usedPip) return;
  // one baseline for every property the stan blocks tween on #pip (ft would only set the first tween's)
  tl.unshift(`based.add("#pip"); gsap.set("#pip", { y: 0, scale: 1${st.inkWins.length ? `, filter: "blur(0px)"` : ""} });`);
  for (const r of st.runs) {
    if (!r.shift) continue;
    tl.push(`ft("#pip", { y: 0 }, { y: ${r.shift}, duration: 0.25, ease: "power3.inOut" }, ${r3(Math.max(0, r.t0 - 0.05))});`);
    tl.push(`ft("#pip", { y: ${r.shift} }, { y: 0, duration: 0.25, ease: "power3.inOut" }, ${r3(r.t1 - 0.2)});`);
  }
}

// ------------------------------------------------------------------ chest captions
export function buildChestCaptions(words, cap, st, ctx) {
  const { E, r3, esc, tl, warn, placer } = ctx;
  const { S } = st;
  const win = (list, what) => (list || []).map(([a, b]) => [E(a, what), E(b, what)]);
  const single = [...win(cap.single, "captions.single"), ...st.inkWins];
  const top = win(cap.top, "captions.top");
  const inW = (t, ws) => ws.some(([a, b]) => t >= a - 1e-3 && t < b);
  const emph = (cap.emphasis || []).map((x) => (typeof x === "string" ? { w: nrm(x) } : { w: nrm(x.word), at: x.at !== undefined ? E(x.at, "captions.emphasis") : undefined }));
  const strobe = new Set((cap.strobe || []).map(nrm));
  const maxWords = cap.maxWords ?? S.maxWords, maxChars = cap.maxChars ?? S.maxChars;
  const lower = cap.lower !== false;
  const clean = (s) => s.replace(/^[«"“„'(]+/, "").replace(/[.,!?;:…»"”')]+$/, "");
  const used = new Set();
  const groups = [];
  let cur = null;
  words.forEach((w, i) => {
    const txt = clean(w.word);
    if (!txt) return;
    const n = nrm(w.word);
    let isEmph = false;
    emph.forEach((e, k) => { if (!isEmph && !used.has(k) && e.w === n && (e.at === undefined || Math.abs(e.at - w.start) < 0.6)) { used.add(k); isEmph = true; } });
    const mode = isEmph || inW(w.start, top) ? "top" : inW(w.start, single) ? "single" : "phrase";
    if (mode !== "phrase") { if (cur) groups.push(cur); cur = null; groups.push({ mode, words: [w], text: txt }); return; }
    const prev = words[i - 1];
    const brk = cur && (/[.?!…]$/.test(prev.word) || w.start - prev.end > 0.45 || (/[,;:]$/.test(prev.word) && cur.words.length >= 3) ||
      cur.words.length >= maxWords || (cur.text + " " + txt).length > maxChars);
    if (brk) { groups.push(cur); cur = null; }
    if (!cur) cur = { mode: "phrase", words: [], text: "" };
    cur.words.push(w);
    cur.text = cur.text ? `${cur.text} ${txt}` : txt;
  });
  if (cur) groups.push(cur);
  // a lone trailing word joins the phrase before it when no sentence ends between them and it still fits
  for (let i = groups.length - 1; i > 0; i--) {
    const g = groups[i], p = groups[i - 1];
    if (g.mode === "phrase" && p.mode === "phrase" && g.words.length === 1 && !/[.?!…]$/.test(p.words.at(-1).word) &&
      g.words[0].start - p.words.at(-1).end < 0.3 && (p.text + " " + g.text).length <= maxChars + 6) {
      p.words.push(g.words[0]); p.text += " " + g.text; groups.splice(i, 1);
    }
  }
  const dropAt = (s, e) => Math.max(0, ...st.capDrops.filter(([a, b]) => s < b && e > a).map(([, , d]) => d));
  let moved = 0;
  const html = groups.map((g, gi) => {
    const s = Math.max(0, g.words[0].start - 0.02);
    const nx = groups[gi + 1];
    const e = Math.min(g.words.at(-1).end + 0.45, nx ? nx.words[0].start - 0.02 : Infinity, ctx.SPEECH);
    const ink = inW((s + e) / 2, st.inkWins); // by the midpoint: a word that starts as the frame fades in is still on it
    let mode = g.mode;
    // the forehead line would sit on a screen recording: keep the word at the chest instead
    if (mode === "top" && st.inPanel(s, e)) mode = "single";
    let size = mode === "phrase" ? S.size : mode === "top" ? S.topSize : S.wordSize;
    // lowercase, but an acronym stays as spoken on screen («ИИ», «AI», «CEO»)
    const text = lower ? g.text.split(" ").map((x) => (/^\p{Lu}{2,}$/u.test(x.replace(/[^\p{L}]/gu, "")) ? x : x.toLowerCase())).join(" ") : g.text;
    size = fitSize(text, size, W - 2 * (placer.sidePad + 20), 0.55);
    let y = ink ? S.inkY : mode === "top" ? S.topY : S.capY + dropAt(s, e);
    const fs_ = ink ? null : faceSpan(st, ctx, s, e);
    if (fs_ && mode !== "top" && fs_.bottom + 18 > y - size * 0.62) {
      const ny = Math.round(fs_.bottom + 18 + size * 0.62);
      if (ny + size * 0.62 > placer.safeBottom) warn.push(`chest caption "${text}" at ${r3(s)} s: no room under the chin (face to ${Math.round(fs_.bottom)} px)`);
      y = Math.min(ny, Math.round(placer.safeBottom - size * 0.62)); moved++;
    }
    if (fs_ && mode === "top" && y + size * 0.62 > fs_.eyes - 40) {
      y = Math.round(Math.max(placer.safeTop + size * 0.62, fs_.eyes - 40 - size * 0.62));
      if (y + size * 0.62 > fs_.eyes - 20) warn.push(`top word "${text}" at ${r3(s)} s: it reaches the eyes (eyes ${Math.round(fs_.eyes)} px)`);
    }
    const gid = `sc${gi}`;
    if (g.words.length === 1 && strobe.has(nrm(g.words[0].word))) {
      // 3 quick blinks right after it lands, as separate tiny fromTo steps (seek-safe)
      [0.1, 0.17, 0.24, 0.31, 0.38, 0.45].forEach((dt, k) => tl.push(`ft("#${gid}", { opacity: ${k % 2 ? 0.12 : 1} }, { opacity: ${k % 2 ? 1 : 0.12}, duration: 0.001 }, ${r3(s + dt)});`));
    }
    g.s = r3(s); g.e = r3(e); g.y = y; g.mode = mode; g.shown = text;
    // into build/caption_layout.json (top-left y, height) so render_report.py checks the safe area like any caption
    placer.log.push({ t0: g.s, t1: g.e, y: Math.round(y - size * 0.62), h: Math.round(size * 1.24), mode: `chest-${mode}${ink ? "-ink" : ""}`, scale: 1,
      face: fs_ ? { top: Math.round(fs_.top), bottom: Math.round(fs_.bottom), eyes: Math.round(fs_.eyes), mouth: Math.round(fs_.mouth) } : null });
    return `<div id="${gid}" class="st-cap ${mode}${ink ? " ink" : ""} clip" style="top:${y}px;font-size:${size}px" data-start="${r3(s)}" data-duration="${r3(Math.max(0.05, e - s))}" data-track-index="5">${esc(text)}</div>`;
  }).join("\n      ");
  if (moved) warn.push(`${moved} chest caption(s) moved down under the chin (the speaker sits low in the frame)`);
  return { html, count: groups.length, groups };
}
