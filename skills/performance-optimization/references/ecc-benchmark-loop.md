<!-- ecc:skills/benchmark-optimization-loop, agents/performance-optimizer.md @25278e7d -->
# Bounded benchmark loop (ECC graft)

1. **Measure** the baseline with a repeatable benchmark (same input, warm-up, several runs,
   report median and spread).
2. **Change one thing.**
3. **Re-measure** with the same benchmark.
4. **Keep or revert:** keep only a gain larger than the run-to-run spread; revert otherwise.
5. Repeat at most N times (default 5), then stop and report the table of attempts.

Never stack unmeasured changes; never report a gain from a single run.
