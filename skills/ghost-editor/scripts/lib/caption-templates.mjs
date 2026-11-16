// caption-templates.mjs: six word-timed caption looks for ghost-editor (HyperFrames + GSAP).
//
//   import { captionTemplate } from "./caption-templates.mjs";
//   const cap = captionTemplate(words, "hype", { accent: "#A3FF12", y: 1270 });
//   // cap.html  -> <div id="tcaps">…</div>   (one clip per caption group)
//   // cap.css   -> styles for that template
//   // cap.tl    -> GSAP lines: ft(sel, from, to, at) — the same seek-safe helper build.mjs defines
//
// words: [{word, start, end}] in composition seconds (build.mjs: edit time).
//
// Templates: hype, explosive, line-focus, neo-minimal, karaoke-fill, highlighter.
//
// How it works (ideas from pycaps, MIT; own code):
//   1. paginate: words -> caption groups (max words, max chars, sentence ends, clause commas,
//      pauses, never end a group on a short word like "и", "в", "a", "to").
//   2. tag: every word gets CSS classes — structure tags (w-first, w-last, l-first, l-last) and
//      semantic tags: kw (the one keyword of the group, by a length/importance score or by an
//      AI tagger, see ai-tag.mjs), num, plus t-<tag> for any AI tag.
//   3. layout: lines are measured in Node from real font advance widths (metrics.json, built
//      from the bundled woff2 files), balanced, and the font size shrinks until the group fits
//      maxLines inside `width`. No browser measuring, so the layout is the same on every seek.
//   4. animate: every animated element is a small state machine (track()): each tween is a
//      fromTo that writes the element's FULL tracked state, tweens on one element never
//      overlap, and the first tween sets the baseline at 0. That keeps every frame seek-safe.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
let _metrics = null;
const METRICS = () => (_metrics ??= JSON.parse(fs.readFileSync(path.join(HERE, "metrics.json"), "utf8")));

export const r3 = (x) => Math.round(x * 1000) / 1000;
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const J = (o) => JSON.stringify(o);

// ---------- measuring ----------
// width in px of `text` set in font/weight/size with letter-spacing `tracking` (em)
export function measure(text, font, weight, size, tracking = 0) {
  const m = METRICS();
  const fam = m[font] || m.Inter;
  const w = Object.keys(fam).map(Number).reduce((a, b) => (Math.abs(b - weight) < Math.abs(a - weight) ? b : a));
  const t = fam[String(w)];
  let u = 0, n = 0;
  for (const ch of text) { u += t[ch] ?? t.n ?? 600; n++; }
  return (u / 1000) * size + tracking * size * n;
}

// ---------- colour helpers ----------
const hexRgb = (hex) => { const c = hex.replace("#", ""); const f = c.length === 3 ? c.split("").map((x) => x + x).join("") : c; return [0, 2, 4].map((i) => parseInt(f.slice(i, i + 2), 16)); };
export const rgba = (hex, a) => `rgba(${hexRgb(hex).join(", ")}, ${a})`;
// readable text colour on a filled accent (WCAG luminance crossover)
export function onColor(hex) {
  const L = hexRgb(hex).map((v) => v / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * L[0] + 0.7152 * L[1] + 0.0722 * L[2] > 0.179 ? "#111111" : "#ffffff";
}

// ---------- tagging ----------
const STOP = new Set(`и в во не что он на я с со как а то все всё она так его но да ты к у же вы за бы по только ее её мне было вот от меня еще ещё нет о об из ему теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот эта это эти этих этого этой этом эту того тот та те потому какой какая какие какое совсем ним здесь один почти мой моя мои тем чтобы нее неё сейчас были куда зачем всех никогда можно при наконец два другой хоть после над больше через нас про всего них много разве три впрочем хорошо свою свой перед иногда лучше чуть том нельзя такой такая такие такое им более всегда конечно всю между кажется наоборот просто вообще типа короче значит например очень реально прямо вот-вот как-то что-то где-то кто-то
a an the and or but if of to in on at by for with from as is are was were be been being it its it's this that these those i i'm you he she we they me my your our their them him her us do does did don't not no so just really very like actually basically literally then than there here what which who whom how when where why can could would should will shall may might must have has had get got am im yeah okay ok`.split(/\s+/));

const coreOf = (t) => t.toLowerCase().replace(/[^\p{L}\p{N}%$€₽'-]/gu, "");

// importance of a word as a keyword candidate; -1 = never. A cheap, language-aware heuristic:
// longer content words win, the last word of a sentence (the new information) gets a bonus, numbers
// and mid-sentence names get a bonus, and Russian verb forms (-ет, -ит, -ать, -ться ...) a penalty,
// because the punch of a Russian sentence is usually a noun, adjective or adverb.
const RU_VERB = /(ться|тся|ешь|ишь|ете|ите|ет|ит|ют|ут|ат|ят|ать|ять|еть|ить|оть|уть|ыть|ал|ял|ил|ел|ла|ли|ло)$/;
export function keywordScore(w, i, all) {
  const core = coreOf(w.text);
  const letters = core.replace(/-/g, "");
  if (!core || STOP.has(core) || letters.length <= 2) return -1;
  let s = Math.min(letters.length, 12);
  if (/\d/.test(core)) s += 4;
  if (/[.!?…]$/.test(w.text)) s += 4; else if (/[,;:]$/.test(w.text)) s += 0.5;
  if (/^\p{Lu}/u.test(w.text) && i > 0 && !/[.!?…]$/.test(all[i - 1].text)) s += 2; // a name mid-sentence
  if (/[а-яё]/.test(letters) && letters.length > 4 && RU_VERB.test(letters)) s -= /т?ся$/.test(letters) ? 4 : 3;
  return s;
}

// ---------- pagination ----------
// words -> groups. o: maxWords, maxChars, gap (s), softBreakMin (chars before a comma may end a group), minWords
export function paginate(words, o) {
  const groups = [];
  let cur = [];
  const chars = (ws) => ws.map((w) => w.disp).join(" ").length;
  const shortTail = (w) => w.core.length <= 2 && !/[.!?…,;:]$/.test(w.text);
  const close = (byLimit) => {
    if (!cur.length) return;
    // never end a group on "и", "в", "a", "to": carry it into the next group
    if (byLimit && cur.length > 1 && shortTail(cur.at(-1))) { const t = cur.pop(); groups.push(cur); cur = [t]; return; }
    groups.push(cur); cur = [];
  };
  for (const w of words) {
    if (cur.length && w.start - cur.at(-1).end > o.gap) close(false);
    if (cur.length && (cur.length >= o.maxWords || chars([...cur, w]) > o.maxChars)) close(true);
    cur.push(w);
    if (/[.!?…]$/.test(w.text)) close(false);
    else if (/[,;:]$/.test(w.text) && chars(cur) >= o.softBreakMin) close(false);
  }
  close(false);
  // a lone word that does not end a sentence joins the next group when it fits
  if ((o.minWords ?? 1) > 1) {
    for (let i = 0; i + 1 < groups.length; i++) {
      const g = groups[i], n = groups[i + 1];
      if (g.length >= o.minWords || /[.!?…]$/.test(g.at(-1).text) || n[0].start - g.at(-1).end > o.gap) continue;
      if (g.length + n.length <= o.maxWords + 1 && chars([...g, ...n]) <= o.maxChars * 1.2) { groups.splice(i, 2, [...g, ...n]); i--; }
    }
  }
  return groups;
}

// ---------- layout ----------
function wordWidth(w, size, o) { return measure(w.disp, o.font, w.kw && o.kwWeight ? o.kwWeight : o.weight, size, o.tracking) + 2 * (o.padEm || 0) * size; }
function lineWidth(ws, size, o) { return ws.reduce((a, w, i) => a + wordWidth(w, size, o) + (i ? o.gapEm * size : 0), 0); }
function wrap(ws, size, o) {
  const lines = [];
  let cur = [];
  for (const w of ws) {
    if (cur.length && lineWidth([...cur, w], size, o) > o.width) { lines.push(cur); cur = []; }
    cur.push(w);
  }
  if (cur.length) lines.push(cur);
  // two lines: pick the most balanced split that fits (typographic "balance")
  if (lines.length === 2) {
    let best = null;
    for (let j = 1; j < ws.length; j++) {
      const a = ws.slice(0, j), b = ws.slice(j);
      const wa = lineWidth(a, size, o), wb = lineWidth(b, size, o);
      if (wa > o.width || wb > o.width) continue;
      // prefer not to end line 1 on a short word, and a top line not much shorter than the bottom
      const cost = Math.max(wa, wb) + (a.at(-1).core.length <= 2 ? 200 : 0) + (wa < wb * 0.6 ? 80 : 0);
      if (!best || cost < best.cost) best = { cost, lines: [a, b] };
    }
    if (best) return { lines: best.lines, overflow: false };
  }
  return { lines, overflow: lines.some((l) => lineWidth(l, size, o) > o.width + 0.5) };
}
export function layoutGroup(ws, o) {
  let size = o.size;
  for (;;) {
    const { lines, overflow } = wrap(ws, size, o);
    if ((lines.length <= o.maxLines && !overflow) || size <= o.minSize) return { size, lines };
    size = Math.max(o.minSize, Math.floor(size * 0.95));
  }
}

// ---------- seek-safe emitter ----------
// track(sel, init): a per-element state machine. to(at, props, dur, ease) emits a fromTo whose
// from is the element's current FULL state and whose to is that state plus props; a tween never
// starts before the element's previous tween ends.
function emitter(tl) {
  return {
    track(sel, init) {
      const st = { s: { ...init }, t: 0 };
      const api = {
        to(at, props, dur = 0.2, ease = "power2.out") {
          at = Math.max(at, st.t, 0);
          const from = { ...st.s };
          const to = { ...st.s, ...props };
          tl.push(`ft("${sel}", ${J(from)}, ${J({ ...to, duration: r3(Math.max(0.01, dur)), ease })}, ${r3(at)});`);
          st.s = to;
          st.t = at + dur;
          return api;
        },
        // a stepped wobble (shake): each step a short fromTo, ending where it started
        shake(at, steps, stepDur = 0.03) {
          for (const p of steps) { api.to(at, p, stepDur, "none"); at += stepDur; }
          return api;
        },
        get end() { return st.t; },
      };
      return api;
    },
  };
}

// deterministic PRNG (mulberry32) for hand-drawn shapes
function rng(seed) { let a = seed >>> 0; return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

// a highlighter-marker stroke in a 100x40 box: wobbly long edges, slanted chisel ends, two dry streaks
function markerSvg(seed, color, id) {
  const R = rng(seed * 7919 + 13);
  const top = [], bot = [];
  for (let x = 4; x <= 96; x += 8) { top.push([x, 7 + R() * 5]); bot.push([x, 33 + R() * 5]); }
  const p = [`M 1 ${(10 + R() * 4).toFixed(1)}`, ...top.map(([x, y]) => `L ${x} ${y.toFixed(1)}`), `L 99 ${(5 + R() * 4).toFixed(1)}`, `L ${(97 + R() * 2).toFixed(1)} ${(34 + R() * 4).toFixed(1)}`,
    ...bot.reverse().map(([x, y]) => `L ${x} ${y.toFixed(1)}`), `L 3 ${(37 + R() * 2).toFixed(1)}`, "Z"].join(" ");
  const s1 = 14 + R() * 4, s2 = 25 + R() * 4;
  return `<svg id="${id}" class="hl-mk" viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true"><path d="${p}" fill="${color}"/><path d="M 6 ${s1.toFixed(1)} Q 50 ${(s1 - 2 + R() * 4).toFixed(1)} 94 ${(s1 + 1).toFixed(1)}" stroke="rgba(255,255,255,0.28)" stroke-width="1.6" fill="none"/><path d="M 10 ${s2.toFixed(1)} Q 50 ${(s2 + 2 - R() * 4).toFixed(1)} 90 ${(s2 - 1).toFixed(1)}" stroke="rgba(0,0,0,0.07)" stroke-width="2.4" fill="none"/></svg>`;
}

// ---------- templates ----------
// d: defaults. Every option can be overridden per call. size/minSize in px at 1080x1920.
const BASE = { kwMin: 5.5, width: 820, y: 1270, lead: 0.05, hold: 0.6, gap: 0.6, gapEm: 0.26, padEm: 0, tracking: 0, lineHeight: 1.15, maxLines: 2, minWords: 1, softBreakMin: 8, upper: false, lower: false, strip: /[.,;:]+$/ };

export const TEMPLATES = {
  hype: {
    title: "Hype",
    what: "Big uppercase words punch in one at a time, and the spoken word sits in a coloured box that turns pink on keywords.",
    d: { kwMin: 8, font: "Montserrat", weight: 900, size: 96, minSize: 62, upper: true, maxWords: 3, maxChars: 16, softBreakMin: 1, tracking: -0.01, lineHeight: 1.1, padEm: 0.09, gapEm: 0.16, accent: "#A3FF12", accent2: "#FF2E88" },
    css: (o, c) => `
  .${c} { color: #fff; font-family: "${o.font}", Montserrat, sans-serif; font-weight: ${o.weight}; letter-spacing: ${o.tracking}em; line-height: ${o.lineHeight}; }
  .${c} .tc-w { padding: 0 ${o.padEm}em; transform-origin: 50% 70%; }
  .${c} .tc-t { position: relative; z-index: 1; -webkit-text-stroke: 0.03em rgba(0,0,0,.55); paint-order: stroke fill; }
  .${c} .tc-box { position: absolute; left: -0.02em; right: -0.02em; top: 0.07em; bottom: 0.01em; border-radius: 0.14em; background: ${o.accent}; box-shadow: 0 0.06em 0.22em rgba(0,0,0,.4); z-index: 0; }
  .${c} .kw .tc-box { background: ${o.accent2}; }`,
    word: (w, o, id) => `<i id="${id}b" class="tc-box"></i><span id="${id}t" class="tc-t">${esc(w.disp)}</span>`,
    anim(g, o, E) {
      const sh = (a) => `0px ${r3(0.05 * g.size)}px 0px rgba(0, 0, 0, ${r3(0.55 * a)}), 0px ${r3(0.09 * g.size)}px ${r3(0.32 * g.size)}px rgba(0, 0, 0, ${r3(0.45 * a)})`;
      g.words.forEach((w, i) => {
        const id = w.id, a = i === 0 ? Math.min(g.start, w.start - 0.02) : w.start - 0.02;
        const next = i + 1 < g.words.length ? g.words[i + 1].start - 0.02 : null;
        const rot = i % 2 ? 2 : -3;
        const on = w.kw ? o.onAccent2 : o.onAccent;
        E.track(`#${id}`, { autoAlpha: 0, scale: w.kw ? 1.8 : 1.5, y: r3(0.1 * g.size) }).to(a, { autoAlpha: 1, scale: 1, y: 0 }, 0.16, "back.out(2.6)");
        const box = E.track(`#${id}b`, { autoAlpha: 0, scale: 0.4, rotation: rot }).to(a, { autoAlpha: 1, scale: 1 }, 0.14, "back.out(2.2)");
        const txt = E.track(`#${id}t`, { color: "#ffffff", textShadow: sh(1) }).to(a, { color: on, textShadow: sh(0) }, 0.06, "none");
        if (next !== null) { box.to(next, { autoAlpha: 0, scale: 0.85 }, 0.08, "power2.in"); txt.to(next, { color: "#ffffff", textShadow: sh(1) }, 0.08, "none"); }
      });
    },
  },

  explosive: {
    title: "Explosive",
    what: "The phrase waits dimmed while the spoken word grows, glows and shakes, and a keyword fires a flash that shakes the whole line.",
    d: { kwMin: 8.5, font: "Unbounded", weight: 800, size: 78, minSize: 50, upper: true, maxWords: 4, maxChars: 20, softBreakMin: 6, tracking: -0.02, lineHeight: 1.12, gapEm: 0.2, accent: "#FF5A1F", dim: 0.3, spoken: 0.55, rest: 0.82 },
    css: (o, c) => `
  .${c} { color: #fff; font-family: "${o.font}", Unbounded, sans-serif; font-weight: ${o.weight}; letter-spacing: ${o.tracking}em; line-height: ${o.lineHeight}; }
  .${c} .tc-w { transform-origin: 50% 62%; }
  .${c} .tc-s { display: inline-block; }
  .${c} .ex-flash { position: absolute; left: -18%; right: -18%; top: -70%; bottom: -70%; z-index: 0; opacity: 0; mix-blend-mode: screen;
      background: radial-gradient(closest-side, rgba(255,246,230,.95), ${rgba(o.accent, 0.6)} 42%, ${rgba(o.accent, 0)} 100%); }`,
    word: (w, o, id) => `<span id="${id}s" class="tc-s">${esc(w.disp)}</span>`,
    extra: (g, o) => (g.words.some((w) => w.kw) ? `<i id="${g.id}x" class="ex-flash"></i>` : ""),
    anim(g, o, E) {
      const glow = (a) => `0px 0px ${r3(0.35 * g.size)}px ${rgba(o.accent, r3(0.95 * a))}, 0px 4px 14px rgba(0, 0, 0, ${r3(0.55 * (1 - a) + 0.2)})`;
      E.track(`#${g.id}i`, { autoAlpha: 0.35, scale: 0.92, y: 24 }).to(g.start, { autoAlpha: 1, scale: 1, y: 0 }, 0.14, "power3.out");
      const inner = E.track(`#${g.id}s`, { x: 0, rotation: 0 });
      g.words.forEach((w, i) => {
        const id = w.id, a = w.start - 0.03;
        const next = i + 1 < g.words.length ? g.words[i + 1].start - 0.03 : null;
        const room = (next ?? g.end - 0.05) - a;
        // the line is laid out at full size and words rest at o.rest, so the spoken word grows into
        // its own slot instead of over its neighbours
        const word = E.track(`#${id}`, { opacity: o.dim, scale: o.rest, color: "#ffffff", textShadow: glow(0) });
        word.to(a, { opacity: 1, scale: w.kw ? 1.14 : 1.06, color: o.accent, textShadow: glow(1) }, Math.min(0.09, room * 0.4), "power2.out");
        if (room > 0.3) word.to(a + 0.1, { scale: 1 }, Math.min(0.2, room - 0.12), "power2.out");
        if (next !== null) word.to(next, { opacity: o.spoken, scale: o.rest, color: "#ffffff", textShadow: glow(0) }, 0.14, "power2.out");
        const amp = w.kw ? 1.8 : 1;
        E.track(`#${id}s`, { x: 0, rotation: 0 }).shake(a + 0.02, [
          { x: -5 * amp, rotation: -2 * amp }, { x: 4 * amp, rotation: 1.5 * amp }, { x: -3 * amp, rotation: -1 * amp }, { x: 2 * amp, rotation: 0.6 * amp }, { x: 0, rotation: 0 },
        ], 0.03);
        if (w.kw) {
          E.track(`#${g.id}x`, { opacity: 0, scale: 0.7 }).to(a, { opacity: 1, scale: 1 }, 0.05, "power2.out").to(a + 0.05, { opacity: 0, scale: 1.4 }, 0.32, "power2.out");
          inner.shake(a + 0.01, [{ x: -14, rotation: -0.8 }, { x: 12, rotation: 0.7 }, { x: -8, rotation: -0.4 }, { x: 5, rotation: 0.2 }, { x: -2, rotation: 0 }, { x: 0, rotation: 0 }], 0.035);
        }
      });
    },
  },

  "line-focus": {
    title: "Line focus",
    what: "Two lines roll like a lyrics view, with the current line in full white, the next line at 35 % and a slide up on every new line.",
    d: { font: "Inter", weight: 700, size: 62, minSize: 44, maxWords: 6, maxChars: 26, softBreakMin: 16, tracking: -0.015, lineHeight: 1.32, gapEm: 0.24, maxLines: 1, inactive: 0.35, blockGap: 1.2, strip: /[.;:]+$/ },
    css: (o, c) => `
  .${c} { color: #fff; font-family: "${o.font}", Inter, sans-serif; font-weight: ${o.weight}; letter-spacing: ${o.tracking}em; line-height: ${o.lineHeight}; }
  .${c} .lf-roll { position: absolute; left: 0; right: 0; top: 0; }
  .${c} .lf-line { position: absolute; left: 0; right: 0; display: flex; justify-content: center; white-space: nowrap; transform-origin: 50% 50%;
      text-shadow: 0 3px 18px rgba(0,0,0,.55), 0 1px 3px rgba(0,0,0,.5); }`,
  },

  "neo-minimal": {
    title: "Neo minimal",
    what: "Small lowercase letter-spaced words fade up out of a blur, and the keyword gets a hairline underline.",
    d: { font: "Inter", weight: 500, kwWeight: 700, size: 44, minSize: 34, lower: true, maxWords: 4, maxChars: 24, maxLines: 1, softBreakMin: 12, tracking: 0.075, lineHeight: 1.4, gapEm: 0.42, accent: "#D7FF5A", strip: /[.,;:!?…]+$/ },
    css: (o, c) => `
  .${c} { color: rgba(255,255,255,.93); font-family: "${o.font}", Inter, sans-serif; font-weight: ${o.weight}; letter-spacing: ${o.tracking}em; line-height: ${o.lineHeight};
      text-shadow: 0 2px 14px rgba(0,0,0,.55), 0 1px 2px rgba(0,0,0,.45); }
  .${c} .kw { font-weight: ${o.kwWeight}; color: #fff; }
  .${c} .nm-ul { position: absolute; left: 0; right: ${o.tracking}em; bottom: -0.06em; height: 3px; border-radius: 2px; background: ${o.accent}; transform-origin: 0 50%; box-shadow: 0 0 10px ${rgba(o.accent, 0.5)}; }`,
    word: (w, o, id) => `${esc(w.disp)}${w.kw ? `<i id="${id}u" class="nm-ul"></i>` : ""}`,
    anim(g, o, E) {
      g.words.forEach((w, i) => {
        // the first word of a phrase starts already faintly visible, so a phrase change never shows an empty band
        const from = i === 0 ? { autoAlpha: 0.3, y: 10, filter: "blur(8px)" } : { autoAlpha: 0, y: 18, filter: "blur(14px)" };
        E.track(`#${w.id}`, from).to(i === 0 ? Math.min(g.start, w.start - 0.05) : w.start - 0.05, { autoAlpha: 1, y: 0, filter: "blur(0px)" }, 0.34, "power3.out");
        if (w.kw) E.track(`#${w.id}u`, { scaleX: 0 }).to(w.start + 0.18, { scaleX: 1 }, 0.4, "power3.inOut");
      });
      if (!g.joined) E.track(`#${g.id}i`, { autoAlpha: 1, filter: "blur(0px)", y: 0 }).to(g.end - 0.26, { autoAlpha: 0, filter: "blur(10px)", y: -8 }, 0.24, "power2.in");
    },
  },

  "karaoke-fill": {
    title: "Karaoke fill",
    what: "The whole phrase stays on screen while a colour fill sweeps through each word exactly as it is spoken.",
    d: { font: "Montserrat", weight: 800, size: 72, minSize: 48, maxWords: 5, maxChars: 26, softBreakMin: 8, minWords: 2, tracking: -0.01, lineHeight: 1.18, gapEm: 0.24, accent: "#38E1FF" },
    css: (o, c) => `
  .${c} { color: #fff; font-family: "${o.font}", Montserrat, sans-serif; font-weight: ${o.weight}; letter-spacing: ${o.tracking}em; line-height: ${o.lineHeight}; }
  .${c} .kf-base, .${c} .kf-fill { -webkit-text-stroke: 0.1em rgba(8,8,10,.92); paint-order: stroke fill; }
  .${c} .kf-base { text-shadow: 0 0.06em 0.3em rgba(0,0,0,.45); }
  .${c} .kf-fill { position: absolute; left: 0; top: 0; color: ${o.accent}; clip-path: inset(-30% 100% -30% -10%); }`,
    word: (w, o, id) => `<span class="kf-base">${esc(w.disp)}</span><span id="${id}f" class="kf-fill" aria-hidden="true">${esc(w.disp)}</span>`,
    anim(g, o, E) {
      E.track(`#${g.id}i`, { autoAlpha: 0, y: 18 }).to(g.start, { autoAlpha: 1, y: 0 }, 0.16, "power3.out");
      g.words.forEach((w, i) => {
        const next = i + 1 < g.words.length ? g.words[i + 1].start : g.end;
        const dur = Math.max(0.12, Math.min(w.end, next) - w.start);
        E.track(`#${w.id}f`, { clipPath: "inset(-30% 100% -30% -10%)" }).to(w.start, { clipPath: "inset(-30% -10% -30% -10%)" }, dur, "none");
        E.track(`#${w.id}`, { y: 0, scale: 1 }).to(w.start - 0.02, { y: -6, scale: 1.05 }, 0.1, "power2.out").to(w.start + 0.1, { y: 0, scale: 1 }, 0.22, "power2.out");
      });
    },
  },

  highlighter: {
    title: "Highlighter",
    what: "Words appear as they are spoken, and one keyword per phrase gets a hand-drawn marker swipe that turns its letters dark exactly under the stroke.",
    d: { font: "Inter", weight: 800, size: 66, minSize: 46, maxWords: 5, maxChars: 28, softBreakMin: 16, minWords: 2, tracking: -0.02, lineHeight: 1.22, gapEm: 0.26, accent: "#FFE45C", ink: "#141414", markEm: 0.16 },
    css: (o, c) => `
  .${c} { color: #fff; font-family: "${o.font}", Inter, sans-serif; font-weight: ${o.weight}; letter-spacing: ${o.tracking}em; line-height: ${o.lineHeight}; }
  .${c} .tc-w { text-shadow: 0 3px 16px rgba(0,0,0,.55), 0 1px 3px rgba(0,0,0,.4); }
  .${c} .hl-base { position: relative; z-index: 1; }
  .${c} .hl-mk { position: absolute; left: -${o.markEm}em; top: 0.1em; width: calc(100% + ${2 * o.markEm}em); height: 1em; z-index: 0; overflow: visible; transform: rotate(-1.6deg); }
  .${c} .hl-ink { position: absolute; left: -${o.markEm}em; top: 0; width: calc(100% + ${2 * o.markEm}em); padding-left: ${o.markEm}em; box-sizing: border-box; z-index: 2; color: ${o.ink}; text-shadow: none; white-space: nowrap; }`,
    word: (w, o, id, gi) => (w.kw
      ? `${markerSvg(gi * 31 + w.i, o.accent, `${id}m`)}<span class="hl-base">${esc(w.disp)}</span><span id="${id}k" class="hl-ink" aria-hidden="true">${esc(w.disp)}</span>`
      : esc(w.disp)),
    anim(g, o, E) {
      g.words.forEach((w, i) => {
        E.track(`#${w.id}`, { autoAlpha: 0, y: 12 }).to(i === 0 ? Math.min(g.start, w.start - 0.04) : w.start - 0.04, { autoAlpha: 1, y: 0 }, 0.2, "power2.out");
        if (w.kw) {
          const at = w.start - 0.03, dur = Math.min(0.3, Math.max(0.18, (w.end - w.start) * 0.7));
          E.track(`#${w.id}m`, { clipPath: "inset(-20% 100% -20% 0%)" }).to(at, { clipPath: "inset(-20% 0% -20% 0%)" }, dur, "power2.inOut");
          E.track(`#${w.id}k`, { clipPath: "inset(-20% 100% -20% 0%)" }).to(at, { clipPath: "inset(-20% 0% -20% 0%)" }, dur, "power2.inOut");
        }
      });
      if (!g.joined) E.track(`#${g.id}i`, { autoAlpha: 1 }).to(g.end - 0.12, { autoAlpha: 0 }, 0.1, "power2.in");
    },
  },
};
export const TEMPLATE_NAMES = Object.keys(TEMPLATES);

// ---------- main ----------
// words: [{word|text, start, end}]. opts: any template default plus
//   accent, accent2, onAccent, font, size, y (block top), x (centre), width, group (= maxWords),
//   keywords: [..] (force keyword words) | false (none), ai: [{score, tags}] per word (ai-tag.mjs),
//   end (last allowed second), idPrefix, track (data-track-index), placeCaption(t0, t1, h) -> {y, mode, scale},
//   tl: an array to push GSAP lines into (default: a new one).
export function captionTemplate(words, name, opts = {}) {
  const T = TEMPLATES[name];
  if (!T) throw new Error(`unknown caption template '${name}'; have ${TEMPLATE_NAMES.join(", ")}`);
  const o = { ...BASE, ...T.d, ...Object.fromEntries(Object.entries(opts).filter(([, v]) => v !== undefined)) };
  if (opts.group) o.maxWords = opts.group;
  if (o.accent) o.onAccent = opts.onAccent ?? onColor(o.accent);
  if (o.accent2) o.onAccent2 = opts.onAccent2 ?? onColor(o.accent2);
  const P = o.idPrefix ?? "tc";
  const cls = `tc-${name}`;
  const tl = opts.tl ?? [];
  const E = emitter(tl);
  const X0 = (o.x ?? 540) - o.width / 2;
  const warnings = [];

  // 1. normalise + display text
  const strip = o.strip instanceof RegExp ? o.strip : o.strip ? new RegExp(o.strip) : null;
  const ws = words.map((w, i) => {
    const text = String(w.word ?? w.text ?? "").trim();
    let disp = strip ? text.replace(strip, "") || text : text;
    disp = o.upper ? disp.toUpperCase() : o.lower ? disp.toLowerCase() : disp;
    return { i, text, disp, core: coreOf(text), start: +w.start, end: +w.end };
  }).filter((w) => w.text);
  const END = o.end ?? (ws.length ? ws.at(-1).end + o.hold : 0);

  // 2. tags: numbers, AI tags
  for (const w of ws) {
    w.tags = new Set();
    if (/\d/.test(w.text)) w.tags.add("num");
    const ai = o.ai?.[w.i];
    if (ai) for (const t of ai.tags || []) w.tags.add(`t-${String(t).toLowerCase().replace(/[^a-z0-9-]/g, "")}`);
  }
  const forced = Array.isArray(o.keywords) ? new Set(o.keywords.map(coreOf)) : null;
  const score = (w, k) => {
    if (o.keywords === false) return -1;
    if (forced) return forced.has(w.core) ? 100 : -1;
    const h = keywordScore(w, k, ws);
    // AI scores (0-3) on the heuristic's scale: 3 -> 12, 2 -> 7, 1 -> 3
    if (o.ai) { const a = o.ai[w.i]?.score ?? 0; return a > 0 ? [0, 3, 7, 12][a] + Math.max(h, 0) * 0.05 : -1; }
    return h;
  };
  const markKeyword = (g) => {
    let best = null, bs = 0;
    g.forEach((w) => { const s = score(w, ws.indexOf(w)); if (s >= (forced ? 1 : o.kwMin) && s >= bs) { bs = s; best = w; } });
    if (best) { best.kw = true; best.tags.add("kw"); }
  };

  if (name === "line-focus") return lineFocus(ws, o, { T, P, cls, tl, E, X0, END, markKeyword, warnings });

  // 3. groups -> lines
  const groups = paginate(ws, o).map((g, gi) => {
    g.forEach((w) => { w.kw = false; });
    markKeyword(g);
    const { size, lines } = layoutGroup(g, o);
    if (lines.some((l) => lineWidth(l, size, o) > o.width + 1)) warnings.push(`group ${gi} "${g.map((w) => w.disp).join(" ")}" is wider than ${o.width}px at the minimum size`);
    return { gi, id: `${P}g${gi}`, words: g, size, lines };
  });
  groups.forEach((g, gi) => {
    g.start = r3(Math.max(0, g.words[0].start - o.lead));
    const nextS = gi + 1 < groups.length ? Math.max(0, groups[gi + 1].words[0].start - o.lead) : END;
    g.end = r3(Math.min(nextS, END, Math.max(g.words.at(-1).end + o.hold, g.words.at(-1).end + 0.12)));
    if (g.end <= g.start + 0.1) g.end = r3(g.start + 0.1);
    g.words.forEach((w, wi) => { w.id = `${g.id}w${wi}`; });
  });
  // joined: the next group starts the moment this one ends, so an exit fade would only cause a blank dip
  groups.forEach((g, gi) => { g.joined = gi + 1 < groups.length && groups[gi + 1].start - g.end < 0.05; });

  // 4. html + animation
  const html = groups.map((g) => {
    const h = g.lines.length * g.size * o.lineHeight;
    const pl = o.placeCaption ? o.placeCaption(g.start, g.end, h) : { y: o.y, mode: "fixed" };
    let wi = 0;
    const lines = g.lines.map((ln, li) => `<div class="tc-line">${ln.map((w, k) => {
      const c = ["tc-w", ...w.tags, wi === 0 ? "w-first" : "", wi === g.words.length - 1 ? "w-last" : "", k === 0 ? "l-first" : "", k === ln.length - 1 ? "l-last" : ""].filter(Boolean).join(" ");
      wi++;
      return `<span id="${w.id}" class="${c}">${T.word(w, o, w.id, g.gi)}</span>`;
    }).join("")}</div>`).join("");
    T.anim(g, o, E);
    const sc = pl.scale && pl.scale < 1 ? `;transform:scale(${pl.scale});transform-origin:50% 0` : "";
    return `<div id="${g.id}" class="tc-block ${cls} clip${pl.mode === "lower-face" ? " tc-backed" : ""}" style="top:${Math.round(pl.y)}px;font-size:${g.size}px${sc}" data-start="${g.start}" data-duration="${r3(g.end - g.start)}" data-track-index="${o.track ?? 5}"><div id="${g.id}i" class="tc-in">${T.extra ? T.extra(g, o) : ""}<div id="${g.id}s" class="tc-sh">${lines}</div></div></div>`;
  });

  return finish({ html, groups, o, cls, T, tl, X0, warnings });
}

// line focus: lines (not groups) roll through a two-line window
function lineFocus(ws, o, k) {
  const { T, P, cls, tl, E, X0, END, markKeyword, warnings } = k;
  const lines = paginate(ws, o).map((ln) => {
    // a line must stay ONE line: shrink just that line if it is too wide
    const w = lineWidth(ln, o.size, o);
    return { words: ln, size: w > o.width ? Math.max(o.minSize, Math.floor((o.size * o.width) / w)) : o.size };
  });
  lines.forEach((l) => { l.words.forEach((w) => { w.kw = false; }); markKeyword(l.words); });
  // blocks: runs of lines without a long pause
  const blocks = [];
  for (const l of lines) {
    const prev = blocks.at(-1)?.lines.at(-1);
    if (!prev || l.words[0].start - prev.words.at(-1).end > o.blockGap) blocks.push({ lines: [] });
    blocks.at(-1).lines.push(l);
  }
  const pitch = r3(o.size * o.lineHeight);
  const groups = [];
  const html = blocks.map((b, bi) => {
    const id = `${P}g${bi}`;
    const start = r3(Math.max(0, b.lines[0].words[0].start - 0.15));
    const nextS = bi + 1 < blocks.length ? Math.max(0, blocks[bi + 1].lines[0].words[0].start - 0.15) : END;
    const end = r3(Math.min(nextS, END, b.lines.at(-1).words.at(-1).end + o.hold));
    const g = { id, start, end, words: b.lines.flatMap((l) => l.words), size: o.size, lines: b.lines.map((l) => l.words) };
    groups.push(g);
    const pl = o.placeCaption ? o.placeCaption(start, end, 2 * pitch) : { y: o.y, mode: "fixed" };
    // block in / out
    E.track(`#${id}i`, { autoAlpha: 0, y: 16 }).to(start, { autoAlpha: 1, y: 0 }, 0.2, "power3.out").to(end - 0.22, { autoAlpha: 0, y: -10 }, 0.2, "power2.in");
    const roll = E.track(`#${id}r`, { y: 0 });
    const L = b.lines.map((l, li) => E.track(`#${id}l${li}`, li === 0 ? { opacity: 1, scale: 1 } : li === 1 ? { opacity: o.inactive, scale: 0.94 } : { opacity: 0, scale: 0.94 }));
    b.lines.forEach((l, li) => {
      if (li === 0) return;
      const at = l.words[0].start - 0.16;
      roll.to(at, { y: -li * pitch }, 0.34, "power3.inOut");
      L[li - 1].to(at, { opacity: 0, scale: 0.94 }, 0.3, "power2.out");
      L[li].to(at, { opacity: 1, scale: 1 }, 0.3, "power2.out");
      if (L[li + 1]) L[li + 1].to(at + 0.06, { opacity: o.inactive, scale: 0.94 }, 0.3, "power2.out");
    });
    const inner = b.lines.map((l, li) => `<div id="${id}l${li}" class="lf-line" style="top:${r3(li * pitch)}px${l.size !== o.size ? `;font-size:${l.size}px;line-height:${pitch}px` : ""}">${l.words.map((w, wi) => {
      w.id = `${id}l${li}w${wi}`;
      const c = ["tc-w", ...w.tags, wi === 0 ? "l-first" : "", wi === l.words.length - 1 ? "l-last" : ""].filter(Boolean).join(" ");
      return `<span id="${w.id}" class="${c}" style="margin:0 ${r3(o.gapEm / 2)}em">${esc(w.disp)}</span>`;
    }).join("")}</div>`).join("");
    return `<div id="${id}" class="tc-block ${cls} clip${pl.mode === "lower-face" ? " tc-backed" : ""}" style="top:${Math.round(pl.y)}px;height:${r3(2 * pitch)}px;font-size:${o.size}px" data-start="${start}" data-duration="${r3(end - start)}" data-track-index="${o.track ?? 5}"><div id="${id}i" class="tc-in"><div id="${id}r" class="lf-roll">${inner}</div></div></div>`;
  });
  return finish({ html, groups, o, cls, T, tl, X0, warnings });
}

function finish({ html, groups, o, cls, T, tl, X0, warnings }) {
  const css = `
  #tcaps { position: absolute; left: 0; top: 0; width: 100%; height: 0; z-index: 8; pointer-events: none; }
  .tc-block { position: absolute; left: ${r3(X0)}px; width: ${o.width}px; }
  .tc-in { position: relative; }
  .tc-sh { position: relative; z-index: 1; display: flex; flex-direction: column; align-items: center; }
  .tc-line { display: flex; justify-content: center; align-items: baseline; white-space: nowrap; column-gap: ${o.gapEm}em; }
  .tc-w { display: inline-block; position: relative; white-space: nowrap; }
  .tc-backed .tc-in { background: rgba(8,8,10,.55); border-radius: 22px; padding: 6px 22px; }
  ${T.css(o, cls)}`;
  return { html: `<div id="tcaps">\n      ${html.join("\n      ")}\n  </div>`, css, tl, groups, count: groups.length, warnings, options: o };
}

// ---------- build.mjs adapter ----------
// Mirrors buildEditorialCaptions(words, cap, ctx, hidden): pushes into ctx.tl, uses the face-aware
// placer, hides captions under full-screen scenes. cap.style is the template name.
export function buildTemplateCaptions(words, cap, ctx, hidden = []) {
  const { r3: R = r3, brand = {} } = ctx;
  const res = captionTemplate(words, cap.style, {
    ...cap, style: undefined, tl: ctx.tl, end: ctx.SPEECH,
    // captions.accent: a hex, or "brand" for brand.accent; default = the template's own colour
    accent: cap.accent === "brand" ? brand.accent : cap.accent ?? (typeof cap.highlight === "string" ? cap.highlight : undefined),
    font: cap.font, size: cap.size, y: cap.y, width: cap.width ?? (ctx.sidePad ? 1080 - 2 * ctx.sidePad : undefined),
    placeCaption: cap.y != null ? undefined : ctx.placeCaption,
  });
  ctx.tl.push(`tl.set("#tcaps", { autoAlpha: 1 }, 0);`);
  const merged = [];
  for (const [a, b] of [...hidden].sort((x, y) => x[0] - y[0])) {
    if (merged.length && a <= merged.at(-1)[1] + 0.05) merged.at(-1)[1] = Math.max(merged.at(-1)[1], b);
    else merged.push([a, b]);
  }
  for (const [a, b] of merged) { ctx.tl.push(`tl.to("#tcaps", { autoAlpha: 0, duration: 0.08 }, ${R(a)});`); ctx.tl.push(`tl.to("#tcaps", { autoAlpha: 1, duration: 0.12 }, ${R(b - 0.05)});`); }
  return res;
}

// ---------- standalone page helpers ----------
const RANGES = { latin: "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD", cyrillic: "U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116" };
const FILE_STEM = { Inter: "inter", Montserrat: "montserrat", Unbounded: "unbounded", Oswald: "oswald", "JetBrains Mono": "jetbrains-mono", Geist: "geist" };
// @font-face rules for the families a caption uses, from <fontsUrl>/<stem>-{latin,cyrillic}.woff2
export function fontFaceCss(families, fontsUrl = "assets/fonts") {
  return [...new Set(families)].flatMap((f) => ["latin", "cyrillic"].map((r) => `@font-face { font-family: "${f}"; src: url(${fontsUrl}/${FILE_STEM[f]}-${r}.woff2) format("woff2"); font-weight: 100 900; unicode-range: ${RANGES[r]}; }`)).join("\n  ");
}
export const fontFiles = (families) => [...new Set(families)].flatMap((f) => [`${FILE_STEM[f]}-latin.woff2`, `${FILE_STEM[f]}-cyrillic.woff2`]).filter((f) => !f.startsWith("geist-cyr"));

// the seek-safe helper every GSAP line above assumes. Same contract as build.mjs's ft(), but the initial
// state is applied with gsap.set at load (a tl.set at 0 does not render while the playhead sits at 0,
// so frame 0 would show un-hidden words; hyperframes lint flags it).
export const FT_HELPER = `const based = new Set();
  const ft = (sel, from, to, at) => { if (!based.has(sel)) { based.add(sel); gsap.set(sel, from); } tl.fromTo(sel, from, { ...to, immediateRender: false }, Math.max(0, at)); };`;
