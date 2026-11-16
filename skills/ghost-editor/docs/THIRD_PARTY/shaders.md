# Third-party code and assets: shader looks and animated emoji

| What | Repo | Licence | What we took / how |
|---|---|---|---|
| Paper Shaders core | https://github.com/paper-design/shaders (npm `@paper-design/shaders` 0.0.81) | Apache-2.0 | The `ShaderMount` class and all fragment shaders, bundled unmodified into `templates/vendor/hf-paper.js` by esbuild (`tools/paper/build-vendor.mjs`, rebuilds byte-identical). Paper's LICENSE and NOTICE ship next to it: `templates/vendor/LICENSE-paper-shaders.txt`, `NOTICE-paper-shaders.txt`. |
| Paper Shaders React | same repo (npm `@paper-design/shaders-react` 0.0.81) | Apache-2.0 | Bundled into `hf-paper.js` with React replaced by `tools/paper/src/react-shim.js`: each component function is called once to get Paper's own params-to-uniforms mapping and presets; React is never rendered. `setMinImageSize` and `processUniforms` are ported (lightly adapted) into `tools/paper/src/hf-paper.js`. Preset values: `templates/vendor/paper-shaders.json`. |
| Fluent Emoji Animated | https://github.com/microsoft/fluentui-emoji-animated | MIT (c) Microsoft | 48 APNGs (256 px) downloaded by `scripts/emoji_fetch.py` (sha256 checked against the Git LFS pointer) and re-encoded to VP9-alpha WebM in `library/emoji/` (not in git). |
| Fluent Emoji (static 3D) | https://github.com/microsoft/fluentui-emoji | MIT (c) Microsoft | 16 static 3D PNGs for symbols with no animated version (git blob sha1 checked). |
| esbuild | npm `esbuild` | MIT | Dev dependency of `tools/paper` only (bundling). |

Our own code: `scripts/lib/shader-layer.mjs` (looks, layers, the word scene), `scripts/lib/emoji-pop.mjs`, the HyperFrames seek
driver in `tools/paper/src/hf-paper.js` (redraws from the `hf-seek` time, never requestAnimationFrame), `scripts/framecheck.py`.

The emoji fetcher writes Microsoft's MIT licence files next to the media (`library/emoji/LICENSE-*.txt`); keep them with the
files if you redistribute them.
