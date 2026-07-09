# Correct Caching Strategy for Vite Assets

Vite uses content-based hashing for built assets (e.g., `index.a1b2c3d4.js`). This allows for a very specific and efficient caching strategy.

## Why it matters
Incorrect caching leads to two major issues:
1. **Users see old code** after a deployment (if `index.html` is cached).
2. **Slow loading** (if hashed assets are not cached aggressively).

## Incorrect
Applying the same cache policy to all files.

```http
# Incorrect: Caching everything for a week
Cache-Control: public, max-age=604800
```

## Correct
Split your caching strategy into two categories:

### 1. The Entry Point (`index.html`)
This file MUST NOT be cached, or cached for a very short time. It is the "pointer" to your versioned assets.

**Header:**
```http
Cache-Control: no-cache, no-store, must-revalidate
```
*Or at most:* `Cache-Control: public, max-age=0, must-revalidate`

### 2. Hashed Assets (`/assets/*.js`, `/assets/*.css`, images)
Since the filename changes whenever the content changes, these can be cached "forever".

**Header:**
```http
Cache-Control: public, max-age=31536000, immutable
```
