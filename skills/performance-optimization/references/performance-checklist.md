# Performance optimisation checklist

1. Measure first (profiler / Core Web Vitals / query timing) — never guess.
2. Find the dominant cost (Amdahl): optimise the bottleneck, not the noise.
3. Backend: query plans, indexes, N+1, caching, connection pooling.
4. Frontend: bundle size, render count, hydration, image/asset weight, LCP/CLS/INP.
5. Re-measure; keep only wins that move the metric; document the tradeoff.
