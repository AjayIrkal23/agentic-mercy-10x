---
name: expo-react-native
description: 'Expo and React Native app patterns: Expo Router file routes and layouts, StyleSheet and RN primitives instead of web DOM, CSS and Tailwind, platform permissions, native-safe libraries and verification without starting Metro or a device.'
when_to_use: Use when building or fixing screens, navigation, native modules or permissions in an Expo / React Native app (app/ routes, app.json or app.config.*, expo-* packages), or when web frontend rules would not fit a mobile file.
metadata:
  schema: 1
  category: frontend
  surfaces:
  - frontend
  platforms:
  - linux
  - darwin
  - windows
  triggers:
    keywords:
    - expo
    - expo router
    - react native
    - react-native
    - mobile app
    - expo app
    - native screen
    - android
    - ios
    - stylesheet
    - expo-camera
    - expo go
    - eas build
    - flatlist
    intents: []
---
# Expo / React Native

Read the app's own docs first (site-sync-vista: `sitesync-mobile-native/CLAUDE.md`,
`frontend_docs/16-mobile-native-frontend.md`; routing root `sitesync-mobile-native/app/`).
The project contract wins over these defaults.

## Web rules that do NOT apply here

`rules/frontend.md` and the web skills load on every `.tsx`, including mobile files. In
an RN file ignore their DOM-only parts:
- no `div`/`span`/`button`/`className`, no CSS files, no Tailwind classes unless the app
  uses NativeWind (check `package.json`); use `View`, `Text`, `Pressable`, `Image`,
  `ScrollView`, `FlatList` and `StyleSheet.create`;
- no `window`, `document`, `localStorage`, `IntersectionObserver`, `motion/react`, or
  browser-only packages; storage is `expo-secure-store` (secrets) or AsyncStorage (other);
- Higgsfield web assets and the web design-taste rules are not the visual authority;
  follow the app's existing theme module.

## Routing (Expo Router)

- Files under `app/` are routes; `_layout.tsx` defines the navigator (`Stack`, `Tabs`)
  for its folder; `(group)` folders group without adding a URL segment; `[id].tsx` is a
  dynamic segment read with `useLocalSearchParams()`.
- Navigate with `<Link href>` or `router.push()`; typed routes when the app enables them.
- Keep screens thin: data fetching in hooks / API modules (`apis/`), state in the store
  (`store/`), presentational pieces in `components/`.

## Lists, layout, performance

- Long lists use `FlatList`/`SectionList` with a stable `keyExtractor`; never
  `ScrollView` + `map` over unbounded data. Pagination and filters stay server-driven.
- Wrap screens in the app's safe-area container; respect keyboard avoidance on forms.
- Avoid inline object/array props in list rows; memoise row components when profiling
  shows re-renders.

## Native capabilities

- Request permissions at the point of use (`useCameraPermissions`, `Location.request...`)
  and handle `denied` and `undetermined`; Android 13+/14 split media permissions, so
  check the app config's declared permissions when a feature works on iOS only.
- Use `expo-*` packages that support the app's SDK version; install with
  `npx expo install <pkg>` so versions match the SDK, never a bare `npm i`.
- Config-plugin changes (`app.json` / `app.config.*`) need a new native build; say so
  instead of expecting a reload to pick them up.

## Verify without starting anything

Never start Metro, an emulator or Expo Go yourself; the user runs the app. Use commands
that exit, from the app root:

```bash
npx tsc --noEmit            # types
npm run lint                # or the app's script (site-sync-vista: lint, quality:check)
npm test -- --watch=false   # only if the app has a test script; check package.json first
```

Name what still needs a device check (permissions, camera, platform-specific layout) in
the report.

## Not this skill

Web React (`frontend-standards-always-follow`), backend contracts
(`api-contract-standards`), store slice conventions in the repo's own docs.
