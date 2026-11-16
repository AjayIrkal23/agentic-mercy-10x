# Seoul list as a system

Same method as recipes/clean-os/SYSTEM.md section 5: invariants and the house look make it Seoul list, slots follow the content,
catalog.json records what each reel used. A new reel that copies the previous reel's stickers is the known failure mode.

## Thesis
**A city (or a trip) read out as a list, the type doing the talking.** The voice names one observation every 4-6 s; the
picture answers with fast B-roll, and the KEY WORD of each line lands on screen as it is spoken, in one of two voices:
an elegant italic serif for mood and places, a heavy tight grotesk for facts. Every ~8-10 s the edit drops a piece of the
viewer's own phone (a comment, a window, a selection, a message) so the list feels like it is happening on their screen.

## Invariants (never change: this is the style)
0. **Footage: a format, not a source.** Use the footage the user hands over first, then the user's own library
   (`own_footage.py`, face-checked), then stock or AI full screen. Whatever the source, it is one graded world (the house
   look), with no posed stock models, at the reference pace, 1080p or better (README "Footage"). Lines with no fitting
   footage may become type. One shot per idea, never one clip per noun.
1. VO-led, no talking head (a selfie opener is allowed). Hook = a number + the place + a promise ("will change how you see").
2. Hard cuts, median shot 1.2-1.6 s; at most one transition (a zoom-blur whip into the outro).
3. Type: Playfair Display Italic (mood, places) vs Inter Tight 800 (facts, CAPS for the contrast word). One big word
   ~600-700 px wide + a small subline tucked under its right end. White with a soft shadow on footage (plus a tight dark
   halo so it holds >= 3:1 over bright shots and light clothing), black on white.
   Words land ON the spoken word (blur-in 0.22 s), 0.7-1 s each. No em dashes, no captions of the whole sentence.
4. White pages punctuate: a white word flash on a connector word, and white collage pages in the hook.
5. Phone-UI stickers are real primitives, rendered cleanly: IG comment, macOS window, text selection, iMessage.
6. The ending is an iMessage bubble with a one-word verdict (spoken), an emoji tapback on it, the last shot flying off.
7. Sound stays sparse: hook whoosh, photo-card whoosh, the send on the bubble; a bed only if the user wants one.

## House look (fixed)
One house look per style, small variation per reel: `house.json` in this folder holds it, and the build reads it instead
of inventing a new look each reel. The house look is only the type, the captions, the accents, the insert framing
and the speaker's face as shot. The COMPONENTS that fill the slots are NEW every reel, so reels don't look alike:
phone-UI scenes, paper props, polaroid / card / collage treatments, transitions, hook devices and outro
devices. `scripts/components.py plan --style seoul-list` lists what the last 7 reels used (avoid) and what is free;
`broll_qa.py --style seoul-list` warns on a repeat (check `components`). Grade: none on the speaker's face: the plate keeps
its as-shot colour and every insert is conformed to it
(`insert_prep.py --ref <plate>`); the house look is the type, graphics and devices above. B-roll obeys the people rules
(`people-rules.json`) and shows its line (references/broll.md section 0). A new look element (a new transition, a new
device) only enters the house when the user asks for it, and then it replaces the old one in house.json.
House: the two type voices (Playfair italic / Inter Tight 800; the grotesk over light clothing); white flash pages as
the format of the connector words; the word-family captions; the accents (glitch red, iMessage blue); the photo-card
insert frame. The speaker's face as shot; the footage conformed to it (or, with no face, to the main footage the user handed over).
NOT house (new every reel, see catalog.json): the hook device (the reference's shrinking card + glitch word), the phone
stickers, the collage layouts, the transitions and the outro device (the iMessage bubble).

## Slots (content: what the lines need; the components are new every reel) and their generators

**S1 The hook collage.** Generator: split the hook sentence into (line, big word, place). The big word is the promise
verb/noun ("rethink", "surprise", "fall for"): glitch it in a colour from the reel's footage (red by default). The
photo card is the most iconic frame of the reel. Stickers: 1-3 Fluent emoji that act out the promise (hands, eyes, a
face). The hook DEVICE itself is new every reel (components.py plan): the shrinking card + glitch word is used up.

**S2 Word-family map.** For each line pick the ONE word the viewer should remember. Place/mood -> serif; fact/number/
contrast -> grotesk (CAPS when it is the negation or the surprise: "NO cars"). The subline is the word that
qualifies it, as spoken ("without traffic", "of the city").

**S3 Flash words.** The connectors that carry the rhythm ("even", "and then", "and right away"): 2-5 per reel, on white.

**S4 Phone stickers.** Map each observation to the phone surface where that content lives:

| content | primitive (grow this list) |
|---|---|
| a personal aside, an opinion | IG comment card (avatar = the speaker), a reply, a DM, a story question sticker |
| a list of brands / products / places | macOS window swapping cut-outs, an App Store row, a Maps pin list, a browser tab strip |
| activities, verbs | blue text selection, a Notes checklist ticking, Reminders |
| a number, a price, a time | a calculator, a Wallet pass, a Clock, a notification |
| the verdict | iMessage bubble + tapback (invariant), a voice message, a reaction |

One sticker every 8-10 s, from the house set; a new primitive only when a line needs one.

**S5 Collage layouts.** Triptych (3 bands), 2-up split, a grid of 4, a shrinking card: one or two per reel, under a list
or a sticker.

**S6 The outro cards.** 1-4 frames from the reel that float off with the last shot.

## Planning procedure
1. Whisper the VO; table: line -> key word -> family -> subline -> sticker/collage or B-roll only.
2. `components.py plan --style seoul-list`; fill S1, S4, S5, S6 and the transitions with components the last 7 reels did
   not use (register new ones with `components.py add`, with a sig); the house look stays.
3. Shots: 1 per 1.2-1.6 s, cut on words; the opener can be the author; footage under a sticker should stay calm.
4. Build, `snap.py beats`, look at every strip, `components.py check --style seoul-list --project $P`, then render;
   after the user's yes `components.py record --style seoul-list --project $P --reel <id>`.

## Changelog
- Reference: a 46 s list reel about life in Seoul (Sep 2025): founded the style (Gemini log + frame check).
- Smoke test (Oct 2026, unrelated B-roll under the reference VO): every block built and rendered.
