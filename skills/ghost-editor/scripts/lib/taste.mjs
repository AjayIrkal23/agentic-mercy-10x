// The user's editing taste, as defaults and checks build.mjs can apply.
//
// taste.json is a ledger of corrections and approvals collected across reels
// ("no zoom on every cut", "max 3 punch-ins", "lime failed on white"). It is a
// PRIOR, not evidence: whatever reel.json says explicitly always wins. The
// build uses it twice:
//   1. applyTaste(spec, rawSpec, taste): fills defaults (`set`) for paths that
//      reel.json leaves unset. Order: style preset < taste < reel.json.
//   2. checkTaste(spec, ctx, taste): measures the plan against every `check`
//      rule and returns warnings that quote the user's own words.
//
// CLI (used by taste.py and approval_sheet.py):
//   node taste.mjs check <project> [--taste file] [--skill dir] [--json]
//   node taste.mjs apply <project> [--taste file] [--skill dir]      (dry run: defaults that would be filled)
//   node taste.mjs brief [--taste file] [--style name]               (the active rules as plain lines)

import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

// ---------- loading ----------
// lookup: explicit > $GHOST_TASTE > <project>/taste.json > <skill>/taste.json > next to this file
export function findTaste({ proj, skill, explicit } = {}) {
  const cands = [explicit, process.env.GHOST_TASTE, proj && path.join(proj, "taste.json"), skill && path.join(skill, "taste.json"), path.join(HERE, "taste.json")];
  for (const c of cands) if (c && fs.existsSync(c)) return path.resolve(c);
  return null;
}
export function loadTaste(p) {
  if (!p || !fs.existsSync(p)) return null;
  const t = JSON.parse(fs.readFileSync(p, "utf8"));
  t._path = p;
  t.rules = (t.rules || []).filter((r) => r.active !== false);
  return t;
}

// how a rule is quoted: only the user's own feedback is "you said"; a rule the skill learned says so
export const tasteQuote = (r) => (r.from === "user" ? `you said: ${r.say}` : `skill rule: ${r.say}`);

// ---------- small helpers ----------
const getPath = (o, p) => p.split(".").reduce((c, k) => (c && typeof c === "object" && k in c ? c[k] : undefined), o);
const setPath = (o, p, v) => {
  const ks = p.split(".");
  let c = o;
  for (const k of ks.slice(0, -1)) { if (!c[k] || typeof c[k] !== "object") c[k] = {}; c = c[k]; }
  c[ks.at(-1)] = v;
};
const lum = (hex) => {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || "").trim());
  if (!m) return null;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const WHITE = new Set(["#fff", "#ffffff", "white", "#fafafa", "#f5f5f5", "#f7f7f7"]);

// a rule applies to this spec?
function when(rule, spec, raw) {
  const w = rule.when;
  if (!w) return true;
  if (w.unset && raw && w.unset.some((p) => getPath(raw, p) !== undefined)) return false;
  if (w.style && !w.style.includes(spec.style)) return false;
  if (w.styleNot && w.styleNot.includes(spec.style)) return false;
  if (w.noStyle && spec.style) return false;
  if (w.accentLight !== undefined) {
    const l = lum(spec.brand?.accent);
    if (l === null || (l > 0.45) !== w.accentLight) return false;
  }
  return true;
}

// ---------- 1. defaults ----------
export function applyTaste(spec, rawSpec, taste) {
  const applied = [];
  if (!taste) return { spec, applied };
  const out = structuredClone(spec);
  for (const r of taste.rules) {
    if (!r.set || !when(r, out, rawSpec)) continue;
    for (const [p, v] of Object.entries(r.set)) {
      if (getPath(rawSpec, p) !== undefined) continue; // reel.json said it explicitly: taste never overrides
      if (JSON.stringify(getPath(out, p)) === JSON.stringify(v)) continue;
      if (v === false && !getPath(out, p)) continue; // unset already behaves as false
      setPath(out, p, v);
      applied.push({ id: r.id, path: p, value: v, say: r.say, from: r.from || "skill", quote: tasteQuote(r) });
    }
  }
  return { spec: out, applied };
}
export function bannedSfx(taste) {
  return new Set((taste?.rules || []).flatMap((r) => r.ban?.sfx || []));
}

// ---------- 2. measurements ----------
// ctx: { takes: [{a, b, start, dur}], wordsOrig: [{word, start, end}], sfxEvents: [{t, id, role, why}], proj }
const METRICS = {
  // snap zooms that punch in (scale > 1)
  punch_ins(spec) {
    const xs = (spec.zoom?.snaps || []).filter(([, z]) => z > 1.001);
    return { value: xs.length, where: xs.map(([t, z]) => `${t}s x${z}`) };
  },
  // share of cuts that also get a zoom (a snap or a push starting within 0.15 s)
  cut_zoom_share(spec, ctx, rule) {
    const cuts = ctx.takes.slice(1).map((k) => k);
    if (cuts.length < (rule.check.minCuts ?? 4)) return { value: 0, where: [], note: `${cuts.length} cuts` };
    const zt = [...(spec.zoom?.snaps || []).map(([t]) => t), ...(spec.zoom?.pushes || []).map((p) => p.at)];
    const hit = cuts.filter((k) => zt.some((t) => typeof t === "number" && Math.abs(t - k.a) < 0.15));
    return { value: +(hit.length / cuts.length).toFixed(2), where: hit.map((k) => `cut at orig ${k.a}`), note: `${hit.length} of ${cuts.length} cuts zoom` };
  },
  // expand / wipe / glitch scene transitions (blur and cut count as quiet)
  flashy_transitions(spec) {
    const def = spec.scenes?.default_in;
    const xs = (spec.beats || []).filter((b) => b.type === "scene" && ["expand", "wipe", "glitch"].includes(b.in ?? def ?? "blur"));
    return { value: xs.length, where: xs.map((b) => `${b.kind} ${b.in ?? def} at ${b.at}`) };
  },
  // sounds on bare cuts (snap whooshes)
  sfx_on_cuts(spec, ctx) {
    const ev = (ctx.sfxEvents || []).filter((e) => e.why === "snap");
    if (ctx.sfxEvents) return { value: ev.length, where: ev.map((e) => `${e.t}s ${e.id}`) };
    const on = spec.zoom?.snapSfx || spec.sfxProfile === "rich";
    return { value: on ? (spec.zoom?.snaps || []).length : 0, where: on ? ["zoom.snapSfx / sfxProfile rich"] : [] };
  },
  // cuts that remove a short pause INSIDE a sentence
  short_pause_cuts(spec, ctx, rule) {
    const gapMax = rule.check.gap ?? 0.7;
    const bad = [];
    ctx.takes.slice(1).forEach((k, i) => {
      const prev = ctx.takes[i];
      const gap = k.a - prev.b;
      if (!(gap > 0 && gap < gapMax)) return;
      const last = (ctx.wordsOrig || []).filter((w) => w.start >= prev.a - 0.05 && w.end <= prev.b + 0.15).at(-1);
      if (last && /[.?!…]["»”]?$/.test(last.word.trim())) return; // a sentence ended: a breath cut is fine
      bad.push(`${prev.b}->${k.a} (${gap.toFixed(2)} s gap${last ? ` after "${last.word.trim()}"` : ""})`);
    });
    return { value: bad.length, where: bad };
  },
  // a light accent (lime, yellow) used on white scenes
  light_accent_on_white(spec) {
    const l = lum(spec.brand?.accent);
    if (l === null || l <= 0.45) return { value: 0, where: [], note: `accent ${spec.brand?.accent} is dark enough` };
    const xs = (spec.beats || []).filter((b) => b.type === "scene" && WHITE.has(String(b.bg || "").toLowerCase()));
    return { value: xs.length, where: xs.map((b) => `${b.kind} at ${b.at} (bg ${b.bg})`), note: `accent ${spec.brand.accent} luminance ${l.toFixed(2)}` };
  },
  // B-roll / still sources below the frame's short side
  lowres_broll(spec, ctx, rule) {
    const min = rule.check.minSide ?? 1080;
    const bad = [];
    for (const b of spec.beats || []) {
      const src = b.type === "broll" ? b.src : b.type === "scene" && b.kind === "image" ? b.src : null;
      if (!src) continue;
      const p = path.resolve(ctx.proj || ".", src);
      if (!fs.existsSync(p)) continue;
      try {
        const [w, h] = execFileSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", p]).toString().trim().split(",").map(Number);
        if (Math.min(w, h) < min) bad.push(`${src} ${w}x${h}`);
      } catch { /* not a media file */ }
    }
    return { value: bad.length, where: bad };
  },
  // the same music bed as the last logged reel
  same_music_as_last_reel(spec, ctx, rule, taste) {
    const id = spec.music?.id;
    const home = (p) => path.resolve(String(p || "/nonexistent").replace(/^~/, os.homedir()));
    const last = (taste.reels || []).filter((r) => !(ctx.proj && home(r.project) === path.resolve(ctx.proj)) && !(r.title && r.title === spec.title)).at(-1);
    const same = id && id !== "auto" && last && last.music === id;
    return { value: same ? 1 : 0, where: same ? [`${id} (also on ${last.name})`] : [] };
  },
};

// ---------- 2. checks ----------
export function checkTaste(spec, ctx, taste) {
  const out = [];
  if (!taste) return out;
  for (const r of taste.rules) {
    if (!when(r, spec, ctx.raw)) continue;
    if (r.check && !r.enforcedBy) {
      const f = METRICS[r.check.metric];
      if (!f) { out.push({ id: r.id, severity: "info", msg: `unknown metric '${r.check.metric}'`, say: r.say, from: r.from || "skill", quote: tasteQuote(r) }); continue; }
      const m = f(spec, ctx, r, taste);
      const over = r.check.max !== undefined && m.value > r.check.max;
      const under = r.check.min !== undefined && m.value < r.check.min;
      if (over || under) out.push({ id: r.id, severity: r.severity || "warn", value: m.value, limit: over ? `<= ${r.check.max}` : `>= ${r.check.min}`, where: m.where, msg: `${r.check.metric} = ${m.value} (want ${over ? "<= " + r.check.max : ">= " + r.check.min})${m.where?.length ? ": " + m.where.slice(0, 6).join("; ") + (m.where.length > 6 ? ` (+${m.where.length - 6} more)` : "") : ""}`, say: r.say, from: r.from || "skill", quote: tasteQuote(r) });
    }
    if (r.ban) {
      const used = [];
      const txt = JSON.stringify(spec.beats || []);
      for (const id of r.ban.sfx || []) {
        if ((ctx.sfxEvents || []).some((e) => e.id === id) || txt.includes(`"${id}"`) || (spec.sfx || []).some((s) => s.id === id)) used.push(`sfx ${id}`);
      }
      for (const id of r.ban.memes || []) if ((spec.beats || []).some((b) => b.type === "meme" && b.id === id)) used.push(`meme ${id}`);
      for (const s of r.ban.text || []) if (txt.includes(s)) used.push(`text "${s}"`);
      for (const k of r.ban.transitions || []) if ((spec.beats || []).some((b) => b.type === "scene" && b.in === k)) used.push(`transition ${k}`);
      for (const k of r.ban.styles || []) if (spec.style === k) used.push(`style ${k}`);
      if (used.length) out.push({ id: r.id, severity: r.severity || "warn", msg: `uses banned ${used.join(", ")}`, say: r.say, from: r.from || "skill", quote: tasteQuote(r), where: used });
    }
  }
  return out;
}

// the active rules as plain lines for the planning step
export function tasteBrief(taste, style) {
  if (!taste) return [];
  return taste.rules.filter((r) => when(r, { style })).map((r) => `- ${r.from === "user" ? "(you said) " : "(skill rule) "}${r.say}${r.kind === "process" ? " [process]" : ""}`);
}

// ---------- CLI ----------
const deepMerge = (a, b) => {
  if (b === undefined) return a;
  if (a && b && typeof a === "object" && typeof b === "object" && !Array.isArray(a) && !Array.isArray(b)) {
    const o = { ...a };
    for (const k of Object.keys(b)) o[k] = deepMerge(a[k], b[k]);
    return o;
  }
  return b;
};
function projectCtx(proj, skill) {
  const raw = JSON.parse(fs.readFileSync(path.join(proj, "reel.json"), "utf8"));
  let preset = {};
  const sp = raw.style && path.join(skill, "styles", `${raw.style}.json`);
  if (sp && fs.existsSync(sp)) { preset = JSON.parse(fs.readFileSync(sp, "utf8")); delete preset._about; }
  const spec = deepMerge(preset, raw);
  const FPS = spec.fps ?? 30;
  let acc = 0;
  const takes = spec.takes.map((t) => {
    const f = Math.round((t.b - t.a) * FPS);
    const k = { a: t.a, b: t.b, start: acc / FPS, dur: f / FPS };
    acc += f + Math.round((t.hold ?? 0) * FPS);
    return k;
  });
  const wp = path.resolve(proj, spec.words || "build/words.whisper.json");
  const wordsOrig = fs.existsSync(wp) ? JSON.parse(fs.readFileSync(wp, "utf8")).segments.flatMap((s) => (s.words || []).map((w) => ({ word: w.word.trim(), start: w.start, end: w.end }))) : [];
  const ep = path.join(proj, "build", "sfx_events.json");
  const sfxEvents = fs.existsSync(ep) ? JSON.parse(fs.readFileSync(ep, "utf8")).events : null;
  return { raw, spec, ctx: { takes, wordsOrig, sfxEvents, proj, raw } };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const opt = (k) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : undefined; };
  const cmd = args[0];
  const proj = args[1] && !args[1].startsWith("--") ? path.resolve(args[1]) : null;
  const skill = path.resolve((opt("--skill") || process.env.GHOST_EDITOR_SKILL || path.resolve(HERE, "..", "..")).replace(/^~/, os.homedir()));
  const tp = findTaste({ proj, skill, explicit: opt("--taste") });
  const taste = loadTaste(tp);
  if (!taste) { console.error("no taste.json found"); process.exit(2); }
  if (cmd === "brief") {
    console.log(tasteBrief(taste, opt("--style")).join("\n"));
  } else if (cmd === "check" || cmd === "apply") {
    if (!proj) { console.error(`usage: node taste.mjs ${cmd} <project>`); process.exit(2); }
    const { raw, spec, ctx } = projectCtx(proj, skill);
    const { spec: tasted, applied } = applyTaste(spec, raw, taste);
    const res = cmd === "check" ? checkTaste(tasted, ctx, taste) : applied;
    if (args.includes("--json")) console.log(JSON.stringify({ taste: tp, applied, warnings: cmd === "check" ? res : undefined }, null, 1));
    else if (cmd === "apply") {
      console.log(`taste: ${tp}`);
      console.log(applied.length ? applied.map((a) => `  default ${a.path} = ${JSON.stringify(a.value)}  [${a.id}]`).join("\n") : "  no defaults to fill (reel.json already sets them)");
    } else {
      console.log(`taste: ${tp} (${taste.rules.length} active rules)`);
      if (applied.length) console.log(applied.map((a) => `  default ${a.path} = ${JSON.stringify(a.value)}  [${a.id}]`).join("\n"));
      console.log(res.length ? res.map((w) => `  ${w.severity.toUpperCase()} [${w.id}] ${w.msg}\n      ${w.quote}`).join("\n") : "  no taste warnings");
    }
  } else {
    console.error("usage: node taste.mjs check|apply <project> | brief [--style s]  [--taste file] [--skill dir] [--json]");
    process.exit(2);
  }
}
