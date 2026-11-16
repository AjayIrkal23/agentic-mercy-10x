// Shader layers for ghost-editor / HyperFrames compositions (Node side, emits HTML strings).
//
//   import { LOOKS, shaderLayerHtml, installShaderRuntime } from "./lib/shader-layer.mjs";
//   installShaderRuntime(projDir)              // copies templates/vendor/hf-paper.js -> $P/assets/hf-paper.js
//   html += shaderLayerHtml({ id: "sc1-bg", look: "warm-grain" })                 // full-bleed background
//   html += shaderLayerHtml({ id: "fx", look: "film-grain", overlay: true })      // over the speaker
//   <script src="assets/hf-paper.js"></script>  AFTER the layers (it auto-inits and registers
//   window.__hf.buildReady["hf-paper"]), BEFORE the timeline script if you call HFPaper.tween().
//
// The runtime redraws every layer from the HyperFrames `hf-seek` time (never rAF), so frames
// are a pure function of time. Paper Shaders: github.com/paper-design/shaders (Apache-2.0).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const VENDOR = process.env.HF_PAPER_VENDOR || path.resolve(HERE, "../../templates/vendor"); // hf-paper.js (Paper Shaders bundle)

// Curated looks. `shader` + Paper `preset` + our param overrides. Backgrounds sit behind word
// cards (keep the middle calm, contrast for white or ink text), overlays sit on the speaker.
export const LOOKS = {
  // ---- backgrounds ----
  "warm-grain": {
    shader: "grain-gradient", preset: "Wave", speed: 0.6, ink: "#fff",
    params: { colorBack: "#140904", colors: ["#ff6a1a", "#ffb347", "#ffe2b8"], softness: 0.75, intensity: 0.2, noise: 0.45, scale: 1.25, rotation: -12, offsetY: 0.28 },
    what: "warm grainy wave (grain-gradient / Wave)",
  },
  "mesh-calm": {
    shader: "mesh-gradient", preset: "Default", speed: 0.35, ink: "#0d1424",
    params: { colors: ["#dfe8ff", "#a9c2ff", "#ffd4c2", "#f6f1ff"], distortion: 0.85, swirl: 0.35, grainMixer: 0.08, grainOverlay: 0.12 },
    what: "soft pastel mesh gradient with a little grain (mesh-gradient)",
  },
  "ink-warp": {
    shader: "warp", preset: "Passion", speed: 1.2, ink: "#fff", scrim: 0.35,
    params: { colors: ["#05060b", "#1a3a9e", "#8fb0ff"], proportion: 0.5, softness: 1, distortion: 0.09, swirl: 0.9, swirlIterations: 6, shapeScale: 0.25, scale: 2.5 },
    what: "slow blue marbling, like ink in water (warp / Passion)",
  },
  "god-rays": {
    shader: "god-rays", preset: "Warp", speed: 0.5, ink: "#fff", scrim: 0.3,
    params: { colorBack: "#0b0603", colorBloom: "#ff7a1a", colors: ["#ffb36b80", "#ff5e1a66", "#fff1d6", "#ffcf8a"], offsetX: 0, offsetY: -0.62, density: 0.35, spotty: 0.25, midIntensity: 0.55, midSize: 0.25, intensity: 0.75, bloom: 0.55 },
    what: "warm light rays from above the card (god-rays)",
  },
  "dither-retro": {
    shader: "dithering", preset: "Warp", speed: 0.45, ink: "#fff", scrim: 0.45,
    params: { colorBack: "#101014", colorFront: "#ff4f2b", shape: "warp", type: "4x4", size: 4, scale: 0.9 },
    what: "two-colour ordered dither over a warp field (dithering)",
  },
  "fluted-self": {
    shader: "fluted-glass", preset: "Default", speed: 0, ink: "#fff",
    params: { image: "assets/still.jpg", fit: "cover", shape: "lines", distortionShape: "prism", size: 0.62, distortion: 0.55, shift: 0, blur: 0.35, edges: 0.3, shadows: 0.25, highlights: 0.12, angle: 0, grainOverlay: 0.06, colorBack: "#00000000" },
    tween: { from: { shift: -0.15 }, to: { shift: 0.15 } }, // static filter: slide the flutes over the clip
    what: "ribbed glass over a still of the speaker (fluted-glass)",
  },
  // ---- overlays on the speaker (blend + opacity on the layer) ----
  "film-grain": {
    shader: "mesh-gradient", preset: "Default", speed: 0.3, overlay: true, blend: "soft-light", opacity: 0.8,
    jitter: { fps: 12, amount: 0.01 },
    params: { colors: ["#ff8a3d", "#808080", "#5a7dff", "#808080"], distortion: 0.8, swirl: 0.3, grainMixer: 0.3, grainOverlay: 0.9 },
    what: "film grain gradient: boiling grain (re-seeded 12x/s) and a slow warm/cool colour drift, soft-light (mesh-gradient grainOverlay; grain-gradient only grains its colour edges)",
  },
  "halftone": {
    shader: "halftone-dots", preset: "Default", speed: 0, overlay: true, blend: "screen", opacity: 0.4,
    params: { image: "gen:radial", fit: "cover", colorBack: "#000000", colorFront: "#ffe9c9", size: 0.55, radius: 1.25, contrast: 0.6, grid: "hex", type: "classic", grainMixer: 0, grainOverlay: 0, originalColors: false, inverted: false },
    what: "print halftone screen in the shadows, dots grow toward the edges, the face stays clean (halftone-dots on a generated radial ramp, screen)",
  },
};

export const RUNTIME_FILE = "hf-paper.js";

export function installShaderRuntime(projDir, assetsDir = "assets") {
  const dst = path.join(projDir, assetsDir);
  fs.mkdirSync(dst, { recursive: true });
  fs.copyFileSync(path.join(VENDOR, RUNTIME_FILE), path.join(dst, RUNTIME_FILE));
  return `<script src="${assetsDir}/${RUNTIME_FILE}"></script>`;
}

const attr = (s) => String(s).replace(/&/g, "&amp;").replace(/'/g, "&#39;").replace(/</g, "&lt;");

// Returns the layer <div>. Size/position: full-bleed absolute by default (style overrides).
export function shaderLayerHtml(o) {
  const look = o.look ? LOOKS[o.look] : {};
  if (o.look && !look) throw new Error(`unknown shader look "${o.look}" (have ${Object.keys(LOOKS).join(", ")})`);
  const shader = o.shader || look.shader;
  const preset = o.preset ?? look.preset;
  const params = { ...(look.params || {}), ...(o.params || {}) };
  const speed = o.speed ?? look.speed;
  const overlay = o.overlay ?? look.overlay;
  const blend = o.blend ?? look.blend;
  const opacity = o.opacity ?? look.opacity;
  const jitter = o.jitter ?? look.jitter;
  const style = [
    "position:absolute", "inset:0", "pointer-events:none",
    overlay && blend ? `mix-blend-mode:${blend}` : "",
    opacity !== undefined ? `opacity:${opacity}` : "",
    o.z !== undefined ? `z-index:${o.z}` : "",
    o.style || "",
  ].filter(Boolean).join(";");
  return `<div id="${o.id}" class="hf-shader${o.className ? " " + o.className : ""}" data-shader="${shader}"${preset ? ` data-preset="${attr(preset)}"` : ""} data-params='${attr(JSON.stringify(params))}'${speed !== undefined ? ` data-speed="${speed}"` : ""}${o.t0 !== undefined ? ` data-t0="${o.t0}"` : ""}${jitter ? ` data-jitter='${attr(JSON.stringify(jitter))}'` : ""}${o.minPixelRatio ? ` data-min-pixel-ratio="${o.minPixelRatio}"` : ""} style="${style}"></div>`;
}

// GSAP line(s) for a look's built-in param tween (e.g. fluted-self), to push into the timeline.
export function shaderTweenJs(id, look, t0, t1) {
  const L = LOOKS[look];
  if (!L || !L.tween) return "";
  return `HFPaper.tween(tl, "#${id}", ${JSON.stringify(L.tween.from)}, ${JSON.stringify(L.tween.to)}, ${t0}, ${Math.max(0.01, t1 - t0)}, "none");`;
}

// ---------------------------------------------------------------------------------------------
// build.mjs / motion.mjs hooks (see INTEGRATION.md)

// A scene's `bg` may be an object: {"look": "ink-warp"} or {"shader": "warp", "preset": "Passion",
// "params": {...}, "speed": 1}. Returns { html, ink, scrim } or null when bg is a plain colour.
export function sceneShaderBg(bg, sid) {
  if (!bg || typeof bg !== "object" || !(bg.look || bg.shader)) return null;
  const L = bg.look ? LOOKS[bg.look] : null;
  if (bg.look && !L) throw new Error(`unknown shader look "${bg.look}" (have ${Object.keys(LOOKS).join(", ")})`);
  return { html: shaderLayerHtml({ id: `${sid}-bg`, ...bg }), ink: bg.ink ?? L?.ink ?? "#fff", scrim: bg.scrim ?? L?.scrim ?? 0, tweenFor: (t0, t1) => (bg.look ? shaderTweenJs(`${sid}-bg`, bg.look, t0, t1) : "") };
}

// Scene kind "word": one or two words centred on the scene background, resolving from blur on
// `at` (Clean OS grammar). b = {kind:"word", text, at?, size?, ink?}. Pushes GSAP via ctx.tl
// using build.mjs's ft() helper; returns the body HTML.
export function wordSceneBody(b, sid, t0, ctx, shaderBg) {
  const at = b.at !== undefined && ctx.E ? ctx.E(b.at, "word at") : t0;
  const ink = b.ink ?? shaderBg?.ink ?? "#fff";
  const size = b.size ?? (String(b.text).length > 11 ? 112 : 136);
  const scrim = shaderBg?.scrim ? `<div style="position:absolute;inset:0;background:radial-gradient(ellipse 62% 16% at 50% ${b.y ? (b.y / 19.2).toFixed(1) : 50}%, rgba(0,0,0,${shaderBg.scrim}) 0%, rgba(0,0,0,0) 100%)"></div>` : "";
  ctx.tl.push(`ft("#${sid}-w", { opacity: 0, y: 26, scale: 0.97, filter: "blur(22px)" }, { opacity: 1, y: 0, scale: 1, filter: "blur(0px)", duration: 0.5, ease: "power3.out" }, ${Math.max(0, Math.round((at + 0.05) * 1000) / 1000)});`);
  const esc = ctx.esc || ((s) => String(s));
  return `${scrim}<div style="position:absolute;left:60px;right:60px;top:${b.y ?? 0}px;height:${b.y ? "auto" : "1920px"};display:flex;align-items:center;justify-content:center"><div id="${sid}-w" style="font-weight:600;letter-spacing:-0.035em;line-height:1.02;text-align:center;white-space:nowrap;font-size:${size}px;color:${ink};${ink === "#fff" ? "text-shadow:0 6px 40px rgba(0,0,0,.35);" : ""}">${esc(b.text)}</div></div>`;
}

// fluted-self (and any image-filter look) needs a still of the footage: grab the frame at the
// scene start from the take's source, at its media time, into $P/assets/<name>.jpg.
export function extractStill(projDir, srcVideo, mediaTime, name) {
  const dst = path.join(projDir, "assets", `${name}.jpg`);
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  execFileSync("ffmpeg", ["-v", "error", "-y", "-ss", String(Math.max(0, mediaTime)), "-i", srcVideo, "-frames:v", "1", "-q:v", "2", "-update", "1", dst]);
  return `assets/${name}.jpg`;
}
