'use strict';

/**
 * injection-patterns.js — single source of truth for prompt-injection /
 * summarisation-injection detection patterns (P6-T4).
 *
 * Before this lib, gsd-prompt-guard.js (PreToolUse write guard on .planning/)
 * and gsd-read-injection-scanner.js (PostToolUse read advisory) each carried
 * their OWN INJECTION_PATTERNS array — the two had DRIFTED (the scanner added
 * `act as` + four summarisation patterns the write guard never had). This lib
 * holds the UNION of both — no pattern lost — categorised so each consumer keeps
 * its exact semantics:
 *
 *   HARD_BLOCK_PATTERNS   unambiguous adversarial tokens; the write guard denies
 *                         on first occurrence (ack-override on the second).
 *   ADVISORY_PATTERNS     `act as …` — false-positive risk too high for a hard
 *                         block; advisory only (role-assignment).
 *   SUMMARISATION_PATTERNS survive-the-compaction ("retain this through
 *                         summarisation") injections.
 *   INJECTION_PATTERNS    = HARD_BLOCK ∪ ADVISORY  (the union of the two files'
 *                         historical INJECTION_PATTERNS arrays; the read scanner
 *                         treats all of these as detections).
 *   ALL_PATTERNS          = INJECTION ∪ SUMMARISATION (everything).
 *
 * Union, not intersection: neither file may silently drop a pattern the other
 * had, and both are strictly stronger (the write guard now advises on
 * summarisation-injection too).
 */

// Unambiguous adversarial tokens — HARD BLOCK on first attempt in the write guard.
const HARD_BLOCK_PATTERNS = [
  /ignore\s+(all\s+)?previous\s+instructions/i,
  /ignore\s+(all\s+)?above\s+instructions/i,
  /disregard\s+(all\s+)?previous/i,
  /forget\s+(all\s+)?(your\s+)?instructions/i,
  /override\s+(system|previous)\s+(prompt|instructions)/i,
  /you\s+are\s+now\s+(?:a|an|the)\s+/i,
  /pretend\s+(?:you(?:'re| are)\s+|to\s+be\s+)/i,
  /from\s+now\s+on,?\s+you\s+(?:are|will|should|must)/i,
  /(?:print|output|reveal|show|display|repeat)\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions)/i,
  /<\/?(?:system|assistant|human)>/i,
  /\[SYSTEM\]/i,
  /\[INST\]/i,
  /<<\s*SYS\s*>>/i,
];

// Advisory-only — "act as a reviewer" in documentation must not be hard-blocked.
const ADVISORY_PATTERNS = [
  /act\s+as\s+(?:a|an|the)\s+(?!plan|phase|wave)/i,
];

// Summarisation / compaction persistence injections.
const SUMMARISATION_PATTERNS = [
  /when\s+(?:summari[sz]ing|compressing|compacting),?\s+(?:retain|preserve|keep)\s+(?:this|these)/i,
  /this\s+(?:instruction|directive|rule)\s+is\s+(?:permanent|persistent|immutable)/i,
  /preserve\s+(?:these|this)\s+(?:rules?|instructions?|directives?)\s+(?:in|through|after|during)/i,
  /(?:retain|keep)\s+(?:this|these)\s+(?:in|through|after)\s+(?:summar|compress|compact)/i,
];

// Union of the two files' historical INJECTION_PATTERNS arrays.
const INJECTION_PATTERNS = [...HARD_BLOCK_PATTERNS, ...ADVISORY_PATTERNS];

// Everything.
const ALL_PATTERNS = [...INJECTION_PATTERNS, ...SUMMARISATION_PATTERNS];

module.exports = {
  HARD_BLOCK_PATTERNS,
  ADVISORY_PATTERNS,
  SUMMARISATION_PATTERNS,
  INJECTION_PATTERNS,
  ALL_PATTERNS,
};
