<!-- ecc:skills/react-testing @25278e7d -->
# Coverage tiers by file type (ECC graft)

| File type | Line coverage target |
|---|---|
| hooks | 90 % |
| components | 80 % |
| pages / routes | 60 % |
| config, generated, barrel files | 0 % (excluded) |

- Query by role first (`getByRole('button', { name: /save/i })`), then label, then text;
  `data-testid` is the last resort.
- One behavior per test; the test name states the behavior ("shows an error when the save
  request fails"), not the implementation.
- Coverage is a floor, not a goal: a test that cannot fail does not count.
