<!-- ecc:rules/react-native, skills/react-native-patterns @25278e7d -->
# React Native rules (ECC graft)

- **Expo Router layouts:** each route group has its `_layout.tsx`; auth gating lives in the
  layout, not in every screen.
- **Tokens in SecureStore:** auth tokens and secrets go to `expo-secure-store`, never
  AsyncStorage.
- **EAS readiness checklist:** app id / bundle id set, version and build number bumped,
  icons and splash present, permissions strings written, env per profile in `eas.json`.
- **Accessibility props:** `accessibilityRole`, `accessibilityLabel`, `accessibilityState`
  on every touchable; hit slop for small targets.
- **Lists:** `FlatList` / `FlashList` with `keyExtractor`, memoised `renderItem`,
  `getItemLayout` when rows are fixed height; never `map` a long array in a ScrollView.
- **No web DOM APIs:** no `window`, `document`, `localStorage` or CSS files in native code.
