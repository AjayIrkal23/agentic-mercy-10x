# DESIGN ROUTING + TRIGGER INTELLIGENCE AUDIT (dimension 2 of 4)

Method: read the live path end-to-end (`router.py` → `classify.py` → `select.py`,
consuming `trigger-floor.json` + `skills-index.json`) at file:line level, then
proved every claim by importing and calling the *real* production functions
(`prompt_router.classify.classify`, `prompt_router.select.rank_skills`,
`prompt_router.router._gather_items/_render`, `ui_ux_stack_orchestrator._classify_ui`)
against 38 real prompts (33 design-shaped + 5 negative controls) and several
adversarial substring probes. No mocking — every number below is measured
output from those calls, reproduced inline. `validate_skills.py` was run live.
Read-only throughout; nothing in `~/.claude` was modified.

**Headline: the routing pipeline is not broken, but its DESIGN surface is
noisy and occasionally incomplete for a specific, mechanical reason — a
category-level flat score that ties ~15-20 unrelated skills together whenever
any one of 194 generic words fires once, resolved only by alphabetical skill
name. That single mechanism explains almost every symptom asked about:
`banner-design` showing up everywhere, missing craft-stack pushes on
"dashboard" prompts, and a real hard-gate risk from a MUST-READ push of an
irrelevant skill.**

---

## 1. Trigger collisions

Two independent collision mechanisms exist. They are easy to conflate but have
different fixes.

### 1a. Skill-level keyword collisions (skills-index.json, `_index_skills`)

`select.py:120-121` scores `+1.0` per keyword that is a literal substring hit
of the skill's own `keywords` list (extracted by `build-skills-index.py:169`
as `set(_tokenize(str(desc))[:25])` — first 25 tokenized description words,
confirmed by reading that line). Measured collision counts for the words named
in the brief, against the real 249-skill index:

| keyword | skills sharing it | skills |
|---|---|---|
| `design` | **21** | api-and-interface-design, apple-design, architect-system-design, autoplan, codebase-design, design-consultation, design-extract, design-html, design-review-playwright, design-shotgun, emil-design-eng, **golang-patterns**, gsd-ai-integration-phase, gsd-sketch, gsd-ui-phase, huashu-design, impeccable, ios-design-review, **mcp-usage-standards**, ui-ux-pro-max, web-design-guidelines |
| `layout` | 8 | apple-design, design-extract, emil-design-eng, frontend-structure-standards, frontend-ui-engineering, huashu-design, impeccable, ui-ux-pro-max |
| `animation` | 6 | apple-design, emil-design-eng, find-animation-opportunities, impeccable, review-animations, ui-ux-pro-max |
| `component` | 5 | design-extract, emil-design-eng, frontend-standards-always-follow, frontend-structure-standards, react-hooks-patterns |
| `css` | 4 | design-html, frontend-standards-always-follow, tailwind-design-system, ui-ux-pro-max |
| `theme` | 3 | tailwind-design-system, ui-styling, ui-ux-pro-max |
| `brand` | 2 | design-extract, taste-skill |
| `ui`, `ux`, `color`, `grid`, `taste`, `craft`, `form`, `style`, `responsive` | 1 each | — |
| `hero` | 0 | (not a literal keyword of any indexed skill) |

`design` is the one severe skill-level collision — and it drags in **two
skills that have nothing to do with UI**: `golang-patterns` (keyword present
only because its description says "interface design") and
`mcp-usage-standards` ("materially affects design, debugging..."). Proven live:

```
PROMPT: Refactor this Go service to have a cleaner interface design and better error wrapping
intents: {'DEBUG': 1, 'DESIGN': 1, 'REFACTOR': 2}
top8: [('golang-patterns', 6.8), ('debug-investigation', 6.6), ('doubt-driven-development', 5.6),
       ('dead-code-and-change-audit', 5.3), ('ui-ux-pro-max', 5.1), ('huashu-design', 4.6),
       ('impeccable', 4.6), ('banner-design', 4.1)]
```

A pure Go backend refactor prompt pulls `ui-ux-pro-max`, `huashu-design`,
`impeccable`, and `banner-design` into its top 8. (`golang-patterns` correctly
leads because its Go-specific keywords also fired — the pollution is
additive, not a hijack, but it is real noise in the emitted skill list.)

### 1b. Category-level flat collision (`_category_skills`, select.py:139-152) — the dominant mechanism

This is **not** a keyword collision at all — it's a category tax. Any one of
the DESIGN category's 194 `act_keyword`s (autonomous-skill-router.config.json)
firing even once gives `boost = 1.4 + 0.2*min(hit_score,3)` (select.py:150) to
**all 30** `DESIGN.local_skills`, identically, regardless of which keyword
matched or whether that skill's own keywords are relevant. Combined with
`_index_skills`' own coarse `intents`/`surfaces` bonus (`+1.5` if the skill's
`intents` metadata contains `DESIGN`, `+1.0` if `surfaces` contains
`frontend` — select.py:114-118), most of the 30 skills land in the same score
band whether or not they have any real keyword overlap with the prompt.
Measured decomposition for `"improve the design of this settings page, it
feels cluttered"` (DESIGN hit_score = 1):

```
banner-design   index=2.50  cross_cutting=0.00  category=1.60  TOTAL=4.10
brand           index=2.50  cross_cutting=0.00  category=1.60  TOTAL=4.10
design          index=2.50  cross_cutting=0.00  category=1.60  TOTAL=4.10
design-system   index=2.50  cross_cutting=0.00  category=1.60  TOTAL=4.10
prototype       index=2.50  cross_cutting=0.00  category=1.60  TOTAL=4.10
impeccable      index=3.00  cross_cutting=0.00  category=1.60  TOTAL=4.60
```

`banner-design`'s entire 2.50 "index" score is the flat intent+surface bonus
— **zero** of its own 15 keywords (`ad banner`, `banner design`, `hero
banner`, ...) matched this prompt. It ties exactly with `brand`,
`design`, `design-system`, `prototype` at 4.10, and the tie-break —
`sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))`, select.py:181 —
is **alphabetical by skill name**. That's why `banner-design` (b...) beats
`design-extract`/`emil-design-eng`/`find-animation-opportunities` in ties, and
why anything starting `f-`, `h-`, `p-`(after "prototype" itself),
`r-`,`s-`,`t-`,`u-`,`v-` systematically loses ties to `a-`/`b-`/`d-` names.

## 2. Ranking-quality harness (real `classify()` + `rank_skills()`, 38 prompts)

Full harness output (30+ design prompts across every category asked for, plus
5 negative controls) — each row is the actual `top6` returned by
`select.rank_skills(profile, top_n=6)`:

| # | category | prompt | intents | top6 (name, score) | verdict |
|---|---|---|---|---|---|
|1|new-build|Build a new landing page... hero + pricing table|DESIGN:3|ui-ux-pro-max 8.5, taste-skill 7.5, dead-code-and-change-audit 5.1, banner-design 4.5, brand 4.5, design 4.5|CORRECT lead, NOISE tail|
|2|new-build|Create a dashboard admin panel from scratch w/ sidebar + data tables|**none** (REVIEW:1,LARGE:1,MEDIUM:1)|ui-ux-pro-max 5.0, review-animations 4.6, dead-code 3.5, architect-system-design 3.4, triage 3.1, frontend-standards 3.0|**MISS** — no impeccable/taste-skill despite being the textbook "new dashboard" case|
|3|new-build|Add a new pricing page with three tiers|DESIGN:1|banner-design, brand, design, design-system, prototype, slides (all 4.1)|**NOISE** — the flat-tie band fully occupies top6, ui-ux-pro-max/impeccable don't even appear|
|4|polish|Polish this settings page, cluttered/cramped|REVIEW:1,DESIGN:1|find-animation-opportunities 4.6, **banner-design 4.1 (MUST-READ, rank #2)**, brand, design, design-system, prototype|**WRONG-LEAD/NOISE** — see §2a below, this one has real consequences|
|5|polish|UI looks generic/templated, make it premium|DESIGN:2|taste-skill 7.3, ui-ux-pro-max 5.3, find-animation-opportunities 4.8, banner-design 4.3, brand, design|CORRECT lead, NOISE tail|
|6|polish|Card spacing too tight, shadows flat|DESIGN:2|ui-ux-pro-max 7.3, banner-design, brand, design, design-system, prototype (all 4.3)|CORRECT lead, NOISE tail|
|7|motion|Smooth spring animation on modal open|DESIGN:2|ui-ux-pro-max, apple-design, emil-design-eng, find-animation-opportunities, impeccable, review-animations (all real motion skills)|**CORRECT** — clean|
|8|motion|Transitions choppy, improve easing curves|DESIGN:4|review-animations 7.0, emil-design-eng, find-animation-opportunities, impeccable, apple-design, improve-animations|**CORRECT** — clean|
|9|motion|"what's it called when a popover pops in with overshoot"|none|animation-vocabulary 4.0, dead-code 3.5, find-animation-opportunities 3.0, apple-design, emil-design-eng, impeccable|CORRECT lead (animation-vocabulary is exactly right)|
|10|tokens|Set up design tokens: spacing/color/typography|DESIGN:6|ui-ux-pro-max 9.5, design-system 7.5, design-extract 6.0, apple-design, tailwind-design-system, banner-design|CORRECT, minor noise (banner-design at #6)|
|11|tokens|Tailwind theme vars inconsistent|REVIEW:1,DESIGN:2|ui-styling, ui-ux-pro-max, design-extract, emil-design-eng, frontend-standards, react-hooks-patterns|**CORRECT** — clean|
|12|tokens|Extract reusable design tokens|DESIGN:3|design-extract 8.0 (correct #1), design-system, ui-ux-pro-max, emil-design-eng, impeccable, apple-design|**CORRECT** — clean|
|13|a11y|Check form for a11y/screen readers|REVIEW:2|review-animations, update-docs, dead-code, triage, ui-ux-pro-max, code-review-and-quality|**MISS** — no owasp/a11y-specific skill, ui-ux-pro-max buried at #5|
|14|a11y|Audit color contrast + focus states|REVIEW:1,DESIGN:2,AUDIT:1|ui-ux-pro-max, dead-code, improve-animations, banner-design, brand, design|WRONG-LEAD-tail: NOISE from #4|
|15|responsive|Table responsive on mobile breakpoints|DESIGN:1|ui-ux-pro-max, banner-design, brand, design, design-system, prototype|NOISE — 5/6 slots are the flat-tie band|
|16|responsive|Layout breaks tablet, fix responsive grid|DESIGN:2|ui-ux-pro-max 8.3, banner-design, brand, design, design-system, prototype|CORRECT lead, NOISE tail|
|17|brand|Design new logo + brand identity|DESIGN:3|brand, design, taste-skill, ui-ux-pro-max, design-extract, banner-design (all correctly brand-relevant)|**CORRECT** — this is the one case the flat-tie band is actually right|
|18|brand|Marketing copy consistent with brand voice|DESIGN:1|brand 6.1, taste-skill 5.1, banner-design, design, design-system, prototype|CORRECT lead, NOISE tail|
|19|slides|HTML slide deck for investor pitch|REVIEW:1,DESIGN:1,MEDIUM:1|slides 7.1 (correct #1), ui-ux-pro-max, banner-design, brand, design, design-system|**CORRECT**|
|20|slides|Presentation with a data chart slide|DESIGN:2|slides 6.3, ui-ux-pro-max, dead-code, frontend-standards, doubt-driven-development, source-driven-development|**CORRECT**|
|21|banners|Facebook ad banner + Instagram post|DESIGN:1|banner-design 7.1 (correct #1), brand, design, design-system, prototype, slides|**CORRECT**|
|22|banners|YouTube thumbnail + OG image|DESIGN:1,MEDIUM:1|banner-design 6.1 (correct #1), ui-ux-pro-max, brand, design, design-system, prototype|**CORRECT**|
|23|dashboard|Analytics dashboard w/ charts + KPI tiles|DESIGN:1,MEDIUM:1,IMPLEMENT:1|ui-ux-pro-max, dead-code, frontend-standards, doubt-driven, source-driven, banner-design|WRONG-LEAD-tail — no impeccable/taste-skill in top6|
|24|landing|Marketing landing page w/ hero + testimonials|DESIGN:2|taste-skill, ui-ux-pro-max, dead-code, frontend-standards, doubt-driven, source-driven|**CORRECT** lead, clean tail|
|25|component|Dropdown combobox w/ keyboard nav|**none**|dead-code 3.5, emil-design-eng 3.0, project-reference-linkage, apple-design, design-extract, find-animation-opportunities|**MISS** — no DESIGN intent, no impeccable/ui-ux-pro-max at all|
|26|theme|Dark mode theming|REVIEW:1,DESIGN:1,MEDIUM:1,IMPLEMENT:1|ui-styling, dead-code, ui-ux-pro-max, doubt-driven, project-reference-linkage, source-driven|WRONG-LEAD-tail — reasonable lead, weak DESIGN coverage|
|27|empty-state|Empty-state illustration for inbox|REVIEW:1,DESIGN:2|ui-ux-pro-max, banner-design, brand, design, design-system, prototype|NOISE — 5/6 flat-tie band, no higgsfield-generate (mandated for illustration assets)|
|28|form|Redesign ugly signup form|DEBUG:1,DESIGN:4|ui-ux-pro-max, debug-investigation, taste-skill, impeccable, doubt-driven-development, banner-design|CORRECT lead, tail noise|
|29|figma|Implement Figma design into React|DESIGN:2,MEDIUM:2,IMPLEMENT:1|ui-ux-pro-max, dead-code, architect-system-design, doubt-driven, mcp-usage-standards, source-driven|**MISS** — no design-extract (the Figma-specific skill), buried out of top6|
|30|icon|Custom SVG icons for toolbar|REVIEW:1,MEDIUM:1|review-animations, dead-code, triage, ui-ux-pro-max, eval-harness, update-docs|**MISS** — no DESIGN intent ("icon" is not a DESIGN act_keyword — see §4)|
|31|hero|Hero section layout weird on large screens|DEBUG:1,REVIEW:1,DESIGN:3|debug-investigation, taste-skill, ui-ux-pro-max, emil-design-eng, doubt-driven, banner-design|CORRECT-ish, DEBUG legitimately co-leads (it *is* a bug report)|
|32|color|Better color palette for dark theme|DESIGN:2|ui-ux-pro-max, ui-styling, tailwind-design-system, banner-design, brand, design|CORRECT lead, tail noise|
|33|grid|Fix bento grid layout|DESIGN:2|ui-ux-pro-max, banner-design, brand, design, design-system, prototype|NOISE — 5/6 flat-tie band|

**Negative controls (5/5 correct at the top-6 level — no design skill ever
led or placed):**

```
[backend] retry worker, exponential backoff  -> debug-investigation, doubt-driven-development, dead-code, frontend-standards*, frontend-structure*, architect-system-design
[db]      Postgres migration, index          -> dead-code, api-contract-standards, ui-ux-pro-max(2.0, rank 3, harmless), architect-system-design, codebase-intel-first, codebase-start-point-guide
[devops]  GitHub Actions CI pipeline         -> golang-testing, test-driven-development, ship, ci-cd-and-automation, dox-doc-tree, git-workflow-and-versioning
[go]      goroutine leak in pool manager     -> debug-investigation, doubt-driven-development, dead-code, architect-system-design, codebase-intel-first, codebase-start-point-guide
[security]auth middleware SQLi + rate limit  -> owasp-security, code-review-and-quality, santa-review, dead-code, triage, backend-standards-always-follow
```
*(`frontend-standards-always-follow`/`frontend-structure-standards` appear on
the backend-worker prompt from the generic `frontend`/`backend` cross-cutting
group, not from DESIGN — harmless, off-topic-but-not-design noise, not counted
against this audit.)*

**Aggregate:** `banner-design` appeared in the top 6 for **20 of 33 (60.6%)**
design prompts — including plain form/grid/responsive/empty-state prompts with
zero banner/ad/social content. **6 of 33 (18%)** prompts are clean **MISS**es
(#2, #13, #25, #30 unambiguously; #29 partially) where a real DESIGN task gets
no craft-stack push at all. Negative-control false-positive rate at the top-6
level: **0/5**.

### 2a. The banner-design tie is not just noise — it can hard-gate the turn

For prompt #4 (`"Polish this settings page, it feels cluttered and cramped"`),
`banner-design` ranks **#2**, which crosses `deep_n=8`'s `i<2` MUST-READ
threshold (router.py:~206-215). The rendered item, captured verbatim:

```
- **banner-design** (MUST-READ) — ALWAYS invoke when designing banners or ad
  creative — social media, paid ads, website heroes, and print. ...
  ACTION: invoke Skill("banner-design") before the related work.
```

`router._record_pushed_skills` (router.py:~450-465) writes this MUST-READ to
`.telemetry/<sid>.pushed-skills.jsonl` with `"enforce": "hard"`, and
`invoke-suite-gate.py:83-94` treats every `enforce:"hard"` record as
hard-gating the turn. **A prompt with zero banner/ad content can be told, with
hard-gate weight, that it must invoke `banner-design` before the router
considers the turn compliant** — purely because it tied alphabetically ahead
of `emil-design-eng`/`ui-ux-pro-max` in the flat category-boost band.

## 3. Substring false positives

Tested the exact hypotheses in the brief, plus the real mechanism (`if kw and
kw in text` / `if kw and str(kw).lower() in text`, classify.py:189/199/206
and select.py:120), against both the literal substring math and live
`classify()` calls on realistic non-UI sentences:

| kw | word | substring? | in DESIGN act_kw? | in ui_kw? |
|---|---|---|---|---|
| `ui` | build | **True** | True | True |
| `ui` | guide | **True** | True | True |
| `ui` | quick | **True** | True | True |
| `ui` | liquid | **True** | True | True |
| `ui` | equipment | **True** | True | True |
| `css` | success | **False** | — | — |
| `css` | process | **False** | — | — |
| `css` | discuss | **False** | — | — |
| `form` | performance | **True** | False | True |
| `form` | information | **True** | False | True |
| `form` | platform | **True** | False | True |
| `form` | transform | **True** | False | True |
| `grid` | gridlock | **True** | False | True |
| `grid` | hybrid | False | — | — |
| `brand` | brandish | **True** | False | True |
| `brand` | vibrant | False (but `vibrant` is itself a literal `ui_keyword`) | — | True |

**`css`-in-`success`/`process`/`discuss` is DISPROVEN** — none of those words
contain the 3-letter run `c-s-s`. Flagging this so it isn't repeated as fact.

**`form`, `grid`, `ui`, `brand` are all real, reproducible false positives**,
proven with live `classify()` calls on pure non-UI sentences:

```
"We need to build the release and ship it once tests pass"
  -> intents={'SHIP':2,'DESIGN':1,'MEDIUM':2,'IMPLEMENT':2}  is_ui=True  ui_hit=['ui']

"Read the quick start guide before running the migration"
  -> intents={'DESIGN':1,'SMALL':1}  is_ui=True  ui_hit=['ui']

"Rebalance the liquid staking pool and check the equipment inventory job"
  -> intents={'DESIGN':1}  is_ui=True  ui_hit=['ui']

"Transform the raw event stream and conform it to the target schema before
 it hits the platform queue"
  -> is_ui=True  ui_hit=['form']

"The merge caused a database gridlock during the nightly batch"
  -> intents={'SHIP':1}  is_ui=True  ui_hit=['grid']

"Our brand of database sharding is different from the vibrant open-source
 alternative"
  -> is_ui=True  ui_hit=['brand', 'vibrant']
```

Three of six sentences with zero UI content pick up a real `DESIGN` intent
point (not just the `is_ui` flag) because `ui` sits in **both** the 194-word
DESIGN act_keyword list and the 506-word ui_keyword list — the shortest,
highest-collision-risk keyword in the whole system is in both universes.

**Practical impact is smaller than it could be, and this matters:** the
*expensive* consequence — the `[UI/UX] Design work detected → DISPATCH the
frontend-uiux-designer agent NOW ... model:"opus"` block — does **not** fire
for `"We need to build the release and ship it once tests pass"`, even though
`profile.is_ui=True`. Verified directly: `"DISPATCH the frontend-uiux-designer
agent NOW" in body` → `False`. Reason in §"Looks bad but is actually fine" #2.

## 4. Dead / unreachable

**Structural gap — two disjoint keyword universes feed the same pipeline
different signals**, confirmed at file:line:
- `build-trigger-floor.py:175` sources `act_keyword` (incl. DESIGN, 194 words)
  from `autonomous-skill-router.config.json`.
- `build-trigger-floor.py:191-193` sources `ui_keyword` (506 words)
  from `ui-ux-stack-orchestrator.config.json`.
- Measured overlap: **174 shared, 20 DESIGN-only, 332 ui_keyword-only.**

Because `select.py`'s `_category_skills` (the mechanism that pushes the 30
craft-stack skills) only reads `profile.intents['DESIGN']`, and that field is
populated *only* from the 194-word DESIGN act_keyword set — **not** the
506-word ui_keyword set — every one of these 332 words silently fails to
trigger the craft stack, even though they flip `is_ui`/`surfaces`:
`dashboard`, `admin panel`, `sidebar`, `dropdown`, `combobox`, `component`,
`icon`, `card`, `button`, `table`, `hero`, `badge`, `chip`, `modal`, `navbar`,
`form`, `grid` (all confirmed absent from DESIGN act_keywords, present in
ui_keywords). This directly produced 4+ of the MISS verdicts in §2 (rows
#2, #13, #25, #30) — including the canonical "new dashboard" build the user's
own `ui-ux-playbook.mdc` Phase A intake explicitly names as a trigger.

**Skill dead on arrival — indexed under a name that doesn't exist:**
`frontend-design:frontend-design` is DESIGN's first-listed `local_skill`
(autonomous-skill-router.config.json) but **no key in `skills-index.json`
contains the substring `frontend-design`** — confirmed by iterating all 249
keys. It can only ever receive the flat category boost (never an
`_index_skills` keyword score, since `_index_skills` only iterates keys that
exist in the index), and never appeared in the top 10 across 39 varied
probes.

**Skills starved by missing metadata** (`intents=[]` and/or `surfaces=[]` in
skills-index.json, confirmed by direct lookup):

| skill | intents | surfaces | keywords indexed |
|---|---|---|---|
| `higgsfield-generate` | `[]` | `[]` | **1** |
| `design-review` | `[]` | `[]` | 11 |
| `design-consultation` | `[]` | `[]` | 9 |
| `design-shotgun` | `[]` | `[]` | 11 |
| `design-html` | `[]` | `[]` | 9 |
| `emil-design-eng` | `[]` | `['frontend']` | 52 |

Root cause at `build-skills-index.py:175-176`: `intents`/`surfaces` are
populated *only* from (a) schema-v1 SKILL.md front matter or (b) a reverse
import from `trigger-floor.json` path-route rules — none of these six skills
have either, so they permanently miss the `+1.5`/`+1.0` bonuses every other
DESIGN skill gets for free. `higgsfield-generate` is the most severe case:
**one single indexed keyword**, for the skill the user's own standing
`higgsfield-frontend-mandate.md` calls MANDATORY for every generated
raster/video/3D/audio asset in a UI build. Confirmed absent from top 10 across
all 39 probes, including the "empty-state illustration" prompt (#27) where it
is arguably the single most relevant skill.

## 5. Scoring-model critique + concrete proposal

**What's wrong, ranked by impact:**

1. **Category boost is not keyword-specific** (`_category_skills`,
   select.py:139-152) — a single generic-word hit gives the *same* score to
   30 skills. This is the dominant source of noise (§1b, §2a).
2. **No word-boundary guard on short keywords** in the two engines that feed
   the live score (`classify.py` floor matcher, `select.py:_index_skills`) —
   while a correct fix already exists, unused, one file over.
3. **Tie-break is alphabetical, not specificity-weighted**
   (`sorted(..., key=lambda kv: (-kv[1], kv[0]))`, select.py:181) — an
   accident of skill *naming*, not relevance.
4. **No negative/exclusion keywords at the category level** — the
   ui-ux-stack-orchestrator has `exclude_keywords` (25 phrases); the DESIGN
   act_keyword category and `_category_skills` have none.
5. **No per-skill score cap** — `deep_inject` triggers on raw score ≥ 3.0,
   which the flat category band alone (1.6-2.2) plus the flat intent/surface
   bonus (2.5) already clears for every DESIGN skill in the local_skills list,
   independent of actual relevance.

**Concrete, implementable proposal:**

```python
# select.py — reuse the fix that already exists in
# ui-ux-stack-orchestrator.py:152-158 (_keyword_in_text), instead of the
# current `if kw and kw in text` / `if kw and str(kw).lower() in text`.
import re
def _kw_hit(kw: str, text: str) -> bool:
    k = kw.lower().strip()
    if not k:
        return False
    if len(k) <= 3:                      # word-boundary guard for short kws
        return re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", text) is not None
    return k in text
```

```python
# select.py::_index_skills — weight by keyword length/specificity instead of
# a flat +1.0, so multi-word / longer keywords (real signal) outrank single
# generic tokens (noise) instead of tying with them.
def _kw_weight(kw: str) -> float:
    n_words = len(kw.split())
    return 0.4 if len(kw) <= 3 else (0.7 if n_words == 1 else 1.2)
```

```python
# select.py::_category_skills — cap the flat category tax well below what a
# single real keyword hit is worth, and require at least one skill-specific
# keyword hit before a DESIGN local_skill is eligible for MUST-READ/deep-inject
# (i.e. category membership alone should never reach the threshold=3 gate).
boost = min(0.6 + 0.15 * min(int(hit_score), 3), 1.2)   # was 1.4 + 0.2*min(...,3), cap ~2.0
```

```python
# select.py::rank_skills — replace the alphabetical tie-break with a
# specificity signal: number of the skill's OWN keywords that hit, so a skill
# with real coverage outranks a same-scoring skill with zero keyword coverage.
ranked = sorted(scores.items(), key=lambda kv: (-kv[1], -kw_hit_counts.get(kv[0], 0), kv[0]))
```

```json
// autonomous-skill-router.config.json — merge DESIGN.keywords with the 332
// ui_keyword-only words (dashboard, sidebar, dropdown, icon, component, ...)
// so a "new component/dashboard" prompt reaches _category_skills at all —
// OR give ui_keyword hits a small (e.g. +0.3) direct contribution to
// prof.intents['DESIGN'] in classify.py so the two lists stop silently
// diverging every time one config is edited without the other.
```

## 6. Token cost

Ran `router.py` for real (JSON payload piped to stdin, exactly the production
invocation) for 3 design prompts:

| prompt | stdout bytes | `additionalContext` chars |
|---|---|---|
| "Build a new landing page..." (DESIGN:3, crosses deep-inject threshold) | **21,172** | 20,317 |
| "Polish this settings page, cluttered" (DESIGN:1) | 3,769 | 3,578 |
| "Add a smooth spring animation..." (DESIGN:2) | 2,481 | 2,373 |

Section breakdown for prompt 1 (via `router._gather_items`/`_render`
directly, not the printed markdown, to avoid misreading the literal
`[inlined skill: ...]` header text as a section marker):

```
n_items=49  total_chars=20175
  SKILLS       n=43  chars=17316   <- dominant cost driver
  ROUTING      n=3   chars=2361
  SUBSTRATE    n=2   chars=297
  GATES        n=1   chars=201
biggest items:
  4581  deep:dead-code-and-change-audit
  4568  deep:ui-ux-pro-max
  4566  deep:taste-skill
  2222  (ui_stack_block, id=None)
```

**Redundancy, measured by literal occurrence count in the single rendered
body:**

```
'ui-ux-pro-max'               occurs 5x
'taste-skill'                 occurs 4x
'dead-code-and-change-audit'  occurs 4x
'emil-design-eng'             occurs 2x
'apple-design'                occurs 2x
'review-animations'           occurs 2x
```

Each of these skills is named in up to 3 places *within this one 20KB
emission*: the `ui_stack_block` prose (names the six-skill stack + emil/apple
by name), the ranked `SKILLS` list entry (`- **name** (LABEL) — desc + ACTION
line`), and — once the DESIGN score clears `auto_dispatch_threshold=3` — a
full ~4,500-char `deep:<name>` body inline. This is **on top of**
`core-skill-set.json`'s separate SessionStart injection, which already
includes `emil-design-eng`, `apple-design`, `review-animations`, and
`dead-code-and-change-audit` as session-scoped `pointer`/`full` entries
(confirmed by reading `core-skill-set.json` directly — these 4 names are in
its `"always"` list). So on a session that opens with any design work and
then sends one more design-shaped prompt, these 4 skill names are pushed to
context **up to 4 distinct times** across 2 injection channels before the
agent has written a line of code.

---

## Findings summary

| # | Finding | Evidence | Severity | Effort | Owner |
|---|---|---|---|---|---|
| F1 | Flat category boost ties ~15-20 DESIGN skills identically; alphabetical tie-break decides, not relevance | select.py:139-152,181; score decomposition in §1b (banner-design 2.50+1.60=4.10, zero own-keyword hits) | 4 | S | shared/infra (`hooks/prompt_router`) |
| F2 | Off-topic MUST-READ push can hard-gate a turn | §2a — router.py `_record_pushed_skills`, `invoke-suite-gate.py:83-94`, literal `banner-design` MUST-READ text captured | **5** | S | infra |
| F3 | No word-boundary guard in classify.py / select.py substring matching; fix already exists elsewhere unused | classify.py:189,199,206; select.py:120-121; working fix at ui-ux-stack-orchestrator.py:152-158; live proof in §3 | 3 | S | infra |
| F4 | DESIGN act_keyword (194) and ui_keyword (506) are disjoint by 332 words, causing craft-stack MISSes on canonical "new dashboard/component" prompts | build-trigger-floor.py:175,191-193; measured overlap; harness rows #2,#13,#25,#30 | 4 | M | infra |
| F5 | 6 DESIGN skills have `intents=[]`/`surfaces=[]` in skills-index.json (higgsfield-generate has 1 indexed keyword total) and never rank | build-skills-index.py:175-176; direct index lookups in §4; 0/39 top-10 appearances | 3 | S–M | infra |
| F6 | `frontend-design:frontend-design` has zero presence in skills-index.json — structurally capped, never ranks | key-search over 249 skills-index.json keys; 0/39 top-10 appearances | 2 | S | infra |
| F7 | `design` keyword shared by 21 skills incl. 2 unrelated backend skills (golang-patterns, mcp-usage-standards) | skills-index.json keyword lookup; live Go-prompt pollution proof in §1a | 2 | M | infra |
| F8 | `validate_skills.py` R7 ("35 pairs") monitors a near-empty, mostly-unmigrated schema-v1 surface — 0 of 35 pairs touch a real DESIGN local_skill, giving false confidence the design-routing surface is checked | scripts/validate_skills.py R7 logic read + rerun; full 35-pair dump in tool output, none intent-tagged DESIGN | 2 | M | infra |
| F9 | Same skill name repeated 2-5x within one router emission; overlaps with a separate SessionStart injection channel | §6 occurrence counts; core-skill-set.json "always" list cross-check | 2 | S–M | infra |

## Looks bad but is actually fine

1. **The `css`-in-`success`/`process`/`discuss` substring hypothesis is
   false.** None of those words contain the run `c-s-s`. Tested and disproven
   in §3 — do not carry this forward as a real bug.
2. **The worst-case outcome — an Opus-tier `frontend-uiux-designer` agent
   dispatch triggered by a devops prompt — does not happen**, even though
   `classify.py`'s `is_ui` flag *is* falsely tripped by "build"/"guide"
   substring hits. `ui-ux-stack-orchestrator.py:152-158`
   (`_keyword_in_text`) already enforces a word-boundary regex for keywords
   ≤3 chars, with a comment explicitly citing "avoid 'no ui' matching 'ui'".
   Verified: the `"DISPATCH the frontend-uiux-designer agent NOW"` text does
   **not** appear in the emitted body for `"We need to build the release and
   ship it once tests pass"`. The expensive channel is already guarded; only
   the cheap channel (classify.py's `is_ui`/DESIGN-intent flags, which feed
   `surfaces` and the category boost) is not.
3. **`impeccable-commands.json`'s 23-subcommand trigger set has zero
   exact-duplicate trigger phrases** across all 309 triggers (measured
   directly) — the earlier "24/24 routing tests passed" claim holds on the
   axis of exact-string collision. This file is not a source of the noise
   found in §1-§2.
4. **The index-driven scoring formula itself is not broken.** When a skill
   has genuinely specific keyword coverage, it correctly wins: `design-extract`
   for "extract...tokens" (score 8.0, clean #1), `banner-design` for
   "Facebook ad banner" (7.1, clean #1), `slides` for "HTML slide deck" (7.1,
   clean #1), `ui-styling` for "Tailwind theme variables" (6.3, clean #1).
   The problem is localized to generic single-word keywords and the flat
   category tax, not to `_index_skills`' per-skill weighting logic.
5. **`validate_skills.py`'s HARD rules are all clean** — 0 HARD failures
   (R1/R5/R6/R9/R10 all pass; R9 confirms all 59 floor-referenced skill names
   resolve in the index). The skill corpus is structurally sound; the issues
   in this report are a live-scoring-formula problem, not a corpus-integrity
   problem, and won't show up as a validator failure today.

## Ranked remediation order

1. **F3 — add word-boundary matching** to `classify.py`'s floor matcher and
   `select.py::_index_skills`, reusing the existing regex from
   `ui-ux-stack-orchestrator.py:152-158` verbatim. Smallest diff, no config
   changes, immediately shrinks the false-positive surface that feeds
   everything downstream (F1, F2 both get quieter inputs for free).
2. **F2 — cap the category boost below the deep-inject/MUST-READ threshold**
   so category membership alone can never hard-gate a turn; require at least
   one skill-specific keyword hit to reach MUST-READ. Depends conceptually on
   F1's fix landing at the same time (same code region, `_category_skills`).
3. **F1 — rework the tie-break** to use per-skill keyword-hit-count instead
   of alphabetical name, and weight keywords by length/specificity in
   `_index_skills`. Medium effort (touches the sort key + a new weighting
   function), highest impact on the 60.6% banner-design noise rate.
4. **F4 — reconcile the DESIGN act_keyword and ui_keyword lists** (merge or
   cross-feed) so "dashboard"/"component"/"icon" prompts reach the craft
   stack. Cross-file change (`autonomous-skill-router.config.json` +
   `build-trigger-floor.py`), needs a floor rebuild + `validate_skills.py`
   rerun after.
5. **F5/F6 — backfill missing intents/surfaces + fix the
   `frontend-design:frontend-design` key mismatch** in
   `build-skills-index.py`/skills-index.json. Mostly data fixes, unblocks
   `higgsfield-generate` in particular (mandated skill currently invisible).
6. **F7 — tighten the tokenizer** in `build-skills-index.py` to not let a
   single bare token like `design` cross-pollute unrelated backend skills
   (e.g. require 2-gram phrases for common English words, or stop-list a
   small set of over-broad unigrams).
7. **F8 — extend or add a validator rule** that checks the *actual* live
   scoring inputs (skills-index.json keywords + category local_skills
   membership), not just the mostly-unused schema-v1 opt-in surface R7
   currently covers.
8. **F9 — dedup across injection channels**: skip re-listing a skill in the
   per-prompt `SKILLS` push if it was already named in the `ui_stack_block`
   text this turn, and skip re-pushing `core-skill-set.json` "always" skills
   in the per-prompt ranked list within the same session.

## Metrics snapshot (for future-audit comparison)

- `trigger-floor.json`: 2,249 entries total. DESIGN act_keyword: 194. ui_keyword: 506. Overlap: 174. DESIGN-only: 20. ui_keyword-only: 332.
- `skills-index.json`: 249 skills indexed. DESIGN `local_skills`: 30. Of those 30: 6 with `intents=[]`/`surfaces=[]` (higgsfield-generate, design-review, design-consultation, design-shotgun, design-html, emil-design-eng partial), 1 with zero index presence (`frontend-design:frontend-design`).
- Harness: 33 design prompts + 5 negative controls, real `classify()`+`rank_skills()` calls. `banner-design` in top6: 20/33 (60.6%). Clean MISS (no craft-stack push on a real design task): 4-5/33 (~13-15%). Negative-control false-positive rate at top-6: 0/5.
- `validate_skills.py`: 0 HARD failures, 3 WARN (2 unrelated description-garble warnings, R7 = 35 keyword×intent pairs / 0 touching a true DESIGN local_skill).
- Token cost: 3 sampled prompts → 2,481 / 3,769 / 21,172 raw stdout bytes. Same-skill-name repetition within one emission: 2-5x for the top design skills, plus a separate SessionStart channel (`core-skill-set.json`) repeating 4 of the same names again.
