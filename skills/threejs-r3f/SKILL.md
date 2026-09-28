---
name: threejs-r3f
description: Three.js in React via React Three Fiber (@react-three/fiber v9 + drei) — Canvas setup, loading GLB models with useGLTF + Suspense, DPR cap, on-demand frameloop, disposal, draco/meshopt compression, reduced-motion and static-poster fallbacks. Consumes GLB assets from Higgsfield generate_3d; procedural code models come from img2threejs. Pull exact API from Context7 /pmndrs/react-three-fiber and /pmndrs/drei.
when_to_use: Use when adding or editing a 3D scene, hero, or product viewer in React — files importing three, @react-three/fiber, or @react-three/drei, .glb assets, or folders named three/3d/scene/models/webgl/r3f.
user-invocable: true
paths:
  - "**/{three,3d,scene,scenes,models,webgl,r3f}/**/*.{ts,tsx,js,jsx}"
  - "**/*.glb"
metadata:
  category: frontend
  surfaces: [frontend]
  triggers:
    keywords: [three, three.js, threejs, r3f, react-three-fiber, "@react-three/fiber", drei, useGLTF, Canvas, glb, gltf, shader, webgl, 3d model, 3d hero, useFrame, OrbitControls, Environment]
    paths: [/three/, /3d/, /scene/, /scenes/, /models/, /webgl/, /r3f/, .glb]
    intents: [IMPLEMENT, DESIGN]
---

# Three.js in React — React Three Fiber + drei

## Where the 3D comes from (boundary)

| Need | Source |
|---|---|
| A mesh asset (GLB) for a hero, product, or scene | Higgsfield `mcp__higgsfield__generate_3d` (image → GLB); the reference image itself from `generate_image` |
| A procedural, code-built, animatable model reconstructed from a reference image | `img2threejs` skill (emits a `THREE.Group` factory, no downloaded meshes) |
| Rendering either one in React | **this skill** |

Never ship a placeholder cube, a stock Sketchfab URL, or a "TODO model" — the asset rule (`rules/frontend.md`) applies to 3D too.

## Install / versions

```bash
npm i three @react-three/fiber @react-three/drei && npm i -D @types/three
```
`@react-three/fiber@9` ↔ `react@19`; `@react-three/fiber@8` ↔ `react@18`. Vite needs no extra config. Import three addons from `three/addons/...` (not `three/examples/jsm`).

## Canvas setup

```tsx
import { Canvas } from '@react-three/fiber'
import { Suspense, lazy } from 'react'

<Canvas
  dpr={[1, 1.5]}                       // cap pixel ratio; [1, 2] is the default, 1.5 is plenty for UI
  frameloop="demand"                   // render only when something changes (static/product scenes)
  camera={{ position: [0, 0.8, 3], fov: 40 }}
  gl={{ antialias: true, powerPreference: 'high-performance', alpha: true }}
  shadows={false}                      // enable only when the design needs them; contact shadows are cheaper
  fallback={<img src="/poster.webp" alt="Product render" />}   // no-WebGL path
  aria-label="Interactive 3D product view" role="img"
  onCreated={({ gl }) => { gl.setClearColor(0x000000, 0) }}
>
  <Suspense fallback={null}>
    <Scene />
  </Suspense>
</Canvas>
```

- Wrap the whole `<Canvas>` in `React.lazy` + an IntersectionObserver so three (~150 KB gz) loads only when the section is near the viewport.
- `frameloop="demand"`: anything that mutates outside React (controls, `useFrame` animation) must call `invalidate()` from `useThree()`. drei controls do this for you. For a continuously animating hero use `frameloop="always"` but pause it off-screen.

## Loading a GLB (drei `useGLTF`)

```tsx
import { useGLTF, Clone, Environment, OrbitControls, Center, Bounds, Preload, useProgress, Html } from '@react-three/drei'

function Model(props) {
  const { nodes, materials, scene } = useGLTF('/models/hero.glb')   // draco + meshopt decoders on by default
  return <primitive object={scene} {...props} />
  // or, for reuse/instances: <Clone object={scene} /> — shares geometry + materials
  // or, from gltfjsx output: <group dispose={null}><mesh geometry={nodes.body.geometry} material={materials.paint} /></group>
}
useGLTF.preload('/models/hero.glb')      // start the fetch before the component mounts

function Loader() {
  const { progress } = useProgress()
  return <Html center>{Math.round(progress)}%</Html>
}

function Scene() {
  return (
    <>
      <Environment preset="studio" />                                  {/* image-based lighting; no light rig needed */}
      <Bounds fit clip observe margin={1.2}><Center><Model /></Center></Bounds>
      <OrbitControls makeDefault enablePan={false} minPolarAngle={0.8} maxPolarAngle={1.8} />
      <Preload all />
    </>
  )
}
```

- `useLoader`/`useGLTF` cache by URL — the same asset mounted twice is one download and one set of GPU buffers.
- `useGLTF(url, dracoPath?, meshopt?, extendLoader?)`: pass a local `/draco/` path (copy from `three/examples/jsm/libs/draco/gltf/`) to avoid the gstatic CDN; use `extendLoader` to attach a `KTX2Loader` for compressed textures.
- Generate typed JSX from a GLB with `npx gltfjsx model.glb --types --transform` — `--transform` also compresses.

## Performance budget

- **Asset:** run `npx @gltf-transform/cli optimize in.glb out.glb --compress draco --texture-compress webp` (or `gltfpack -cc -tc`). Target ≤ 2 MB for a hero, ≤ 100k triangles, textures ≤ 2048² (1024² on mobile). Higgsfield GLBs come unoptimized — always run this step.
- **Frames:** never `setState` inside `useFrame`; mutate refs with `delta` (`ref.current.rotation.y += delta * 0.4`). Reuse geometries/materials; use `<Instances>`/`<instancedMesh>` above ~50 copies.
- **Regression:** `<Canvas performance={{ min: 0.5 }}>` + `<AdaptiveDpr pixelated />` + `<AdaptiveEvents />` drop resolution while the camera moves; `<PerformanceMonitor onDecline={() => setLowQuality(true)}>` swaps effects off on weak GPUs.
- **Raycasting:** wrap a complex model in `<Bvh firstHitOnly>` before adding hover/click handlers.
- **Lights/shadows:** one `Environment` beats three lights; `ContactShadows` beats real shadow maps for product shots. Post-processing (`@react-three/postprocessing`) only when the design demands it and the monitor is green.

## Disposal and lifecycle

- R3F calls `.dispose()` on geometries/materials/textures when their element unmounts. Objects you cache globally or reuse across mounts must sit under `<group dispose={null}>`.
- Swapping models: unmount the old `<Model>` (key by URL) rather than mutating `scene.children`; call `useGLTF.clear(url)` if the asset will never return.
- Unmounting the `<Canvas>` releases the WebGL context; do not keep more than one live `<Canvas>` per page on mobile — use drei `<View>` to render several viewports from one canvas.

## Motion, reduced motion, and fallbacks

- `prefers-reduced-motion`: read it (`useReducedMotion()` from `motion/react` or `matchMedia`) and switch to `frameloop="demand"` with a fixed pose, no auto-rotate, no camera drift. Shipped motion still passes the `motion-dev` craft bar (easing, ≤ 300 ms UI, interruptible).
- Low-power / data-saver (`navigator.connection?.saveData`, `hardwareConcurrency <= 4`, `matchMedia('(hover: none)')` on small screens): render a static poster `<img>` (a Higgsfield `generate_image` render of the same model) instead of the canvas, with an optional "View in 3D" button.
- Keep all text, buttons, and links in DOM (`<Html>` or outside the canvas) — never inside the WebGL layer; give the canvas `role="img"` + `aria-label`.
- Scroll-driven 3D belongs to `nateherk-design:scroll-craft` for the timeline; this skill supplies the `<Canvas>` and model.

## Checklist before ship

- [ ] GLB optimized (draco/meshopt + webp/KTX2), size and triangle budget met
- [ ] `dpr` capped, `frameloop` chosen deliberately, `invalidate()` wired for demand mode
- [ ] `Suspense` fallback + `useProgress` loader; `useGLTF.preload` for the hero asset
- [ ] No `setState` in `useFrame`; no per-frame allocations
- [ ] `dispose={null}` only on shared/cached objects; model swaps unmount cleanly
- [ ] Reduced-motion pose, no-WebGL `fallback`, low-power poster path all tested
- [ ] Canvas lazy-loaded; text and controls live in DOM with ARIA

## Docs

Context7 `/pmndrs/react-three-fiber` (Canvas, hooks, scaling-performance, pitfalls), `/pmndrs/drei` (loaders, staging, performances), `/mrdoob/three.js` (GLTFLoader, DRACOLoader, KTX2Loader, disposal). Do not rely on memorized APIs — drei renames helpers between minors.

## When NOT to use it

- Generating the 3D asset itself → Higgsfield `generate_3d`; procedural reconstruction from an image → `img2threejs`.
- 2D motion in React → `motion-dev`; SVG → `animejs-motion`; scroll timelines → `nateherk-design:scroll-craft`.
- Vanilla three.js outside React: the three.js docs apply directly; the perf/disposal/fallback rules above still hold.
