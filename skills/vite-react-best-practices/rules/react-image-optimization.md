# Image Optimization for CLS and Performance

Images are the largest assets and the primary cause of Layout Shifts (CLS). In basic React apps, images often load lazily causing the page to "jump" when they appear.

## Why it matters
- **CLS (Cumulative Layout Shift):** Poor UX, users lose their place or click loading buttons.
- **LCP (Largest Contentful Paint):** Large images delay the visual readiness of the page.

## Incorrect
Using `img` tags without dimensions.

```tsx
// Incorrect: The browser doesn't know how much space to reserve
<img src="/hero.jpg" alt="Hero" />
```

## Correct
Always explicit width/height and `loading="lazy"` for off-screen images.

```tsx
// Correct: CSS aspect-ratio or explicit attributes reserve space
<img 
  src="/hero.jpg" 
  alt="Hero"
  width={800}
  height={400}
  className="w-full h-auto" // Responsive CSS
  loading="eager" // Above fold (hero) -> eager
/>

<img 
  src="/avatar.jpg" 
  alt="User"
  width={64}
  height={64}
  loading="lazy" // Below fold -> lazy
/>
```
