# Stan style as a system

Same method as recipes/clean-os/SYSTEM.md section 5: invariants and the house look make it stan style, slots follow the content,
catalog.json records what each reel used. Copying the previous reel's diagram, icons or panels is the known failure mode.

## Thesis
**A tutorial you could follow with the sound off.** The speaker talks to camera in one seated shot; whenever they name
something on a screen, that screen takes the top of the frame behind their head; the steps are labelled like a
manual («[Step 1]»), and the small chest captions carry every word without ever covering the speaker. The first second already
says "this is a tutorial" (icon row + title strip), and the end asks for a comment keyword.

## Invariants (never change: this is the style)
0. **Prerequisite: real screen recordings** of the tool or workflow. No recordings, no stan style (stock people in the
   band read as filler). Propose Clean OS or RESULT instead. One text layer at a time: a «[Step n]» label and a chest caption that
   repeats it never sit together.
1. One seated talking head, medium shot; one hard punch-in close-up for the benefit line and the CTA.
2. Split screen: real screen recordings in the top band, edge to edge, popping in and out, BEHIND the speaker (their head is
   cut out and overlaps the screen); the eyes just below the band. About half the runtime. Back-to-back panels swap with
   no speaker move.
3. `chest` captions: small white lowercase phrases at ~68 % that cut on their first word; single bigger words only in the
   hook, the diagram and one stretch at the forehead near the end.
4. The hook card in the first seconds: icons + a 1-2 line black-on-white strip title naming the tutorial.
5. Step labels «[Step n] / title / icons» paired with their panels; a comment-keyword CTA at the end.
6. One white diagram at most, early (the "how it works" map), entered by a zoom-blur.
7. Sound: restrained (a whoosh into the diagram, scribbles on its lines, clicks on cursor clicks, pops on labels).

## House look (fixed)
One house look per style, small variation per reel: `house.json` in this folder holds it, and the build reads it instead
of inventing a new look each reel. The house look is only the type, the captions, the accents, the insert framing
and the speaker's face as shot. The COMPONENTS that fill the slots are NEW every reel, so reels don't look alike:
phone-UI scenes, paper props, polaroid / card / collage treatments, transitions, hook devices and outro
devices. `scripts/components.py plan --style stan-style` lists what the last 7 reels used (avoid) and what is free;
`broll_qa.py --style stan-style` warns on a repeat (check `components`). Grade: none on the speaker's face: the plate keeps
its as-shot colour and every insert is conformed to it
(`insert_prep.py --ref <plate>`); the house look is the type, graphics and devices above. B-roll obeys the people rules
(`people-rules.json`) and shows its line (references/broll.md section 0). A new look element (a new transition, a new
device) only enters the house when the user asks for it, and then it replaces the old one in house.json.
House: the chest captions, the strip-title typography, the white diagram style, the [Step n] labels and the CTA format
as in the invariants. The speaker's face as shot. New every reel (catalog.json): the hook device around the strip, the diagram's
entrance, the panel treatments, the transitions and the outro device.

## Slots (content: what the tutorial needs) and their generators

**S1 Hook title.** Generator: "<what kind of tutorial> / <for what outcome>" in the speaker's words ("AI automation
tutorial / for creative content ideas"). Icons: the input sources on one row, the tool (logo + wordmark) on the other.

**S2 The diagram.** Generator: draw the data flow the speaker describes in one breath: sources -> the tool -> the output
word (one bold word, «Idea»); 3-6 nodes, 2-4 lines, bottom to top. Never the same layout twice in a row: try left-to-right,
a fan-in, a loop back, a two-stage chain.

**S3 Panels.** One per sentence that names something on screen; record it fresh for this reel (the app page, the
settings toggle, the result). A modal over dimmed UI, a scroll, a typed prompt: vary the motion inside the recording.

**S4 Steps.** As many as the speaker counts; titles are imperative and short («Create a private channel»); icons
are the app(s) of that step.

**S5 The CTA.** Keyword = the one the speaker says («ritual»); the logo of what they will receive.

**S6 Asides.** 0-2 spoken jokes as «*text*» above the head; only on full speaker shots.

## Planning procedure
1. Transcribe; table: sentence -> panel recording? -> step? -> caption mode (phrase / single / top) -> aside?
2. `components.py plan --style stan-style`; fill S1-S6 from the tutorial with components the last 7 stan reels did not
   use (register new ones with `components.py add`, with a sig); the house look stays.
3. Build, approval sheet (look at the speaker's move under every panel run, the labels against the chin, the hook card
   against the eyes), `components.py check --style stan-style --project $P`, render, render_report.py + qa.py; after
   the user's yes `components.py record --style stan-style --project $P --reel <id>`.

## Changelog
- Reference: @nicktarmo's tool tutorial (Oct 2026): breakdown + full-res frame check (caption
  height and style, black-on-white title, no speaker move, no strobe, upright aside).
- Smoke test (Oct 2026, a talking head + screen recordings): every block built, rendered and checked.
