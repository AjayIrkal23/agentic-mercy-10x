// ai-tag.mjs: AI word tagging for caption templates (the pycaps idea, own code).
// Gemini reads the transcript and gives each word an importance score (0-3) plus semantic tags;
// caption-templates.mjs turns them into CSS classes (kw for the top word of each caption group,
// t-<tag> for every tag) so a template can style or animate them.
//
//   node ai-tag.mjs <words.json> [--out tags.json] [--model gemini-2.5-flash]
//   import { aiTag } from "./ai-tag.mjs";  const ai = await aiTag(words, { cache: "build/ai-tags.json" });
//
// words.json: whisper json (segments[].words[]) or a flat [{word,start,end}] array.
// Needs GEMINI_API_KEY. The key is checked with one tiny call before the real request.
import fs from "node:fs";
import crypto from "node:crypto";

const API = "https://generativelanguage.googleapis.com/v1beta/models";
export const AI_TAGS = ["emotion", "number", "name", "negation", "action", "contrast"];

async function call(model, key, body) {
  const r = await fetch(`${API}/${model}:generateContent`, { method: "POST", headers: { "x-goog-api-key": key, "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json();
  if (j.error) throw new Error(`Gemini ${model}: ${j.error.status || ""} ${j.error.message}`);
  return j.candidates?.[0]?.content?.parts?.map((p) => p.text || "").join("") ?? "";
}

export async function validateKey(key = process.env.GEMINI_API_KEY, model = "gemini-2.5-flash") {
  if (!key) throw new Error("GEMINI_API_KEY is not set");
  const t = await call(model, key, { contents: [{ parts: [{ text: "Reply with: ok" }] }], generationConfig: { maxOutputTokens: 5, thinkingConfig: { thinkingBudget: 0 } } });
  if (!/ok/i.test(t)) throw new Error(`Gemini key check returned '${t}'`);
  return true;
}

const PROMPT = (lines) => `You tag the words of a spoken short-video transcript so captions can emphasise them.
Words are numbered "index:word". For EVERY word give an importance score:
3 = the one word of its phrase a viewer must catch (the punch word; at most one per 3-6 words),
2 = a strong content word, 1 = a minor content word, 0 = function word, filler or discourse marker
(e.g. "мне кажется", "наоборот", "просто", "like", "actually").
Optional tags (only when clearly true): ${AI_TAGS.join(", ")}.
Return a JSON array with one object per word in order: {"i": index, "s": score, "t": [tags]}.

${lines}`;

export async function aiTag(words, { model = "gemini-2.5-flash", key = process.env.GEMINI_API_KEY, cache } = {}) {
  const flat = words.map((w) => String(w.word ?? w.text ?? "").trim());
  const hash = crypto.createHash("sha1").update(model + "\n" + flat.join(" ")).digest("hex").slice(0, 16);
  if (cache && fs.existsSync(cache)) {
    const c = JSON.parse(fs.readFileSync(cache, "utf8"));
    if (c.hash === hash) return c.words;
  }
  await validateKey(key, model);
  const text = await call(model, key, {
    contents: [{ parts: [{ text: PROMPT(flat.map((w, i) => `${i}:${w}`).join("\n")) }] }],
    generationConfig: {
      temperature: 0.1,
      responseMimeType: "application/json",
      responseSchema: { type: "ARRAY", items: { type: "OBJECT", properties: { i: { type: "INTEGER" }, s: { type: "INTEGER" }, t: { type: "ARRAY", items: { type: "STRING" } } }, required: ["i", "s"] } },
    },
  });
  const arr = JSON.parse(text);
  const out = flat.map((w) => ({ w, score: 0, tags: [] }));
  for (const x of arr) if (out[x.i]) { out[x.i].score = Math.max(0, Math.min(3, x.s | 0)); out[x.i].tags = (x.t || []).filter((t) => AI_TAGS.includes(t)); }
  if (out.length && !arr.length) throw new Error("Gemini returned no tags");
  if (cache) fs.writeFileSync(cache, JSON.stringify({ hash, model, words: out }, null, 1));
  return out;
}

export function loadWords(file) {
  const j = JSON.parse(fs.readFileSync(file, "utf8"));
  return Array.isArray(j) ? j : j.segments.flatMap((s) => (s.words || []).map((w) => ({ word: w.word.trim(), start: w.start, end: w.end })));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const [file] = process.argv.slice(2).filter((a) => !a.startsWith("--"));
  const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
  if (!file) { console.error("usage: node ai-tag.mjs <words.json> [--out tags.json] [--model gemini-2.5-flash]"); process.exit(1); }
  const out = arg("--out", "ai-tags.json");
  const res = await aiTag(loadWords(file), { model: arg("--model", "gemini-2.5-flash"), cache: out });
  console.log(res.map((x) => (x.score >= 2 ? `[${x.w}${x.score === 3 ? "!" : ""}]` : x.w)).join(" "));
  console.log("->", out);
}
