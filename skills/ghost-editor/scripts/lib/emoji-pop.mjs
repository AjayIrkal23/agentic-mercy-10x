// "emoji pop" block for HyperFrames (Node side, emits HTML + GSAP lines).
// Microsoft Fluent Emoji (MIT): animated ones play as VP9-alpha <video> (seek-safe: the renderer
// extracts frames), static 3D symbols as <img> with a wobble so they don't sit dead.
//
//   installEmoji(projDir, ["fire", "skull"], manifest)          -> copies into $P/assets/emoji/
//   html += emojiPopHtml({ id: "e0", slug: "fire", item: manifest.fire, x: 780, y: 450, size: 240, at: 3.2, dur: 1.6 })
//   js   += emojiPopJs({ id: "e0", at: 3.2, dur: 1.6, side: "right" })
//
// Layering: #id (untimed, positioned, owns the exit) > #id-p (pop: scale/rotation with overshoot)
// > #id-f (float / wobble) > media. Each property tweened once per element, all fromTo with explicit
// values and the hidden start state authored inline, so any seek order gives the same frame.
// Size: the source is 256 px; keep size <= ~280 px on a 1080-wide frame (sharpness).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const EMOJI_DIR = process.env.GHOST_EMOJI_DIR || path.resolve(HERE, "../../library/emoji"); // fetched by scripts/emoji_fetch.py

export const EMOJI_POP_CSS = `
  .ep { position: absolute; pointer-events: none; filter: drop-shadow(0 16px 22px rgba(0,0,0,.38)); }
  .ep-p, .ep-f { position: absolute; inset: 0; }
  .ep-p { transform-origin: 50% 70%; }
  .ep-f video, .ep-f img { position: absolute; inset: 0; width: 100%; height: 100%; display: block; object-fit: contain; }`;

export function loadManifest(dir = EMOJI_DIR) {
  return JSON.parse(fs.readFileSync(path.join(dir, "manifest.json"), "utf8")).items;
}

export function installEmoji(projDir, slugs, man = loadManifest(), assetsDir = "assets") {
  const dst = path.join(projDir, assetsDir, "emoji");
  fs.mkdirSync(dst, { recursive: true });
  for (const s of new Set(slugs)) {
    const it = man[s];
    if (!it) throw new Error(`emoji "${s}" not in manifest (run scripts/emoji_fetch.py)`);
    const f = it.kind === "animated" ? `${s}.webm` : `${s}.png`;
    fs.copyFileSync(path.join(EMOJI_DIR, f), path.join(dst, f));
  }
}

export function emojiPopHtml({ id, slug, item, x, y, size = 240, at, dur, label = false, assetsDir = "assets" }) {
  if (!item) throw new Error(`emojiPopHtml: no manifest item for ${slug}`);
  const media = item.kind === "animated"
    ? `<video id="${id}-v" src="${assetsDir}/emoji/${slug}.webm" data-start="${r3(at)}" data-duration="${r3(Math.min(dur, item.webmSeconds || dur))}" data-track-index="${3 + (hashId(id) % 3)}" muted playsinline></video>`
    : `<img id="${id}-v" src="${assetsDir}/emoji/${slug}.png" alt="${item.glyph || slug}" />`;
  if (item.kind === "animated" && item.webmSeconds && dur > item.webmSeconds) console.warn(`emoji ${slug}: dur ${dur}s > webm ${item.webmSeconds}s; it will stop on its last frame (refetch with --loops N)`);
  return `<div id="${id}" class="ep" style="left:${Math.round(x)}px;top:${Math.round(y)}px;width:${size}px;height:${size}px"><div id="${id}-p" class="ep-p" style="opacity:0"><div id="${id}-f" class="ep-f">${media}</div>${label ? `<div class="ep-label">${typeof label === "string" ? label : slug}</div>` : ""}</div></div>`;
}

const r3 = (v) => Math.round(v * 1000) / 1000;
const hashId = (s) => [...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);

// side: which side of the head it sits on; it leans in from that side.
export function emojiPopJs({ id, at, dur, side = "right", out = true, kind }) {
  const lean = side === "left" ? 1 : -1;
  const L = [];
  // hidden start state: authored inline in the HTML (emojiPopHtml) and applied immediately here,
  // never as a tl.set at 0 (that does not render while the playhead sits exactly on 0)
  L.push(`gsap.set("#${id}-p", { scale: 0, rotation: ${22 * lean}, opacity: 0 });`);
  // pop: grow with a strong overshoot, settle the tilt with a short elastic
  L.push(`tl.fromTo("#${id}-p", { scale: 0, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.42, ease: "back.out(3)", immediateRender: false }, ${r3(at)});`);
  L.push(`tl.fromTo("#${id}-p", { rotation: ${22 * lean} }, { rotation: 0, duration: 0.7, ease: "elastic.out(1.1, 0.4)", immediateRender: false }, ${r3(at)});`);
  // float: a slow lift + tiny sway for the rest of the life (static symbols get a bit more)
  const life = Math.max(0.2, dur - 0.4);
  const sway = kind === "static" ? 6 : 3;
  L.push(`tl.fromTo("#${id}-f", { y: 0, rotation: 0 }, { y: -14, rotation: ${sway * -lean}, duration: ${r3(life)}, ease: "sine.inOut", immediateRender: false }, ${r3(at + 0.35)});`);
  // exit: shrink + fade, finished before the clip window closes
  if (out) L.push(`tl.fromTo("#${id}", { opacity: 1, scale: 1 }, { opacity: 0, scale: 0.55, duration: 0.2, ease: "power2.in", immediateRender: false }, ${r3(at + dur - 0.24)});`);
  return L.map((l) => "  " + l).join("\n");
}
