# Route-Level Code Splitting

Load code only when it's needed. In a generic CRA or Vite app, the default behavior might bundle the entire application into a single large JS file if you reference components directly in your router.

## Why it matters
A massive initial bundle delays the "Time to Interactive" (TTI). Users download code for the "Settings" page even if they only ever view the "Login" page.

## Incorrect
Importing all page components at the top level of your router.

```tsx
// App.tsx
import Dashboard from './pages/Dashboard';
import Settings from './pages/Settings';
import Profile from './pages/Profile';

function App() {
  return (
    <Routes>
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="/profile" element={<Profile />} />
    </Routes>
  );
}
```

## Correct
Use `React.lazy` and `Suspense` to split code by route.

```tsx
// App.tsx
import { lazy, Suspense } from 'react';

// Dynamic imports tell Vite to create separate chunks for these files
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Settings = lazy(() => import('./pages/Settings'));
const Profile = lazy(() => import('./pages/Profile'));

function Loading() {
  return <div className="spinner">Loading...</div>;
}

function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/profile" element={<Profile />} />
      </Routes>
    </Suspense>
  );
}
```
