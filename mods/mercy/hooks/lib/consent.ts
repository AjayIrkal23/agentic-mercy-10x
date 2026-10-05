// Pure: did the user's last prompt tell the agent to stop? Ported from
// hooks/hard-completion-gate.py CONSENT_RE (keep the two in step), plus "just stop" and
// "skip verification". The WHOLE message must be consent clauses: "stop the server and
// fix X" is a task, not consent.

const CLAUSE =
  "(?:(?:ok(?:ay)?|please|just)[,\\s]+)?" +
  "(?:stop(?:\\s+(?:now|here|there))?|don['’]?t do anything(?:\\s+else)?" +
  "|do nothing(?:\\s+else)?|leave it(?:\\s+there)?|no more changes" +
  "|that['’]?s (?:all|it|enough)|skip (?:the )?verif(?:y|ication))"

const CONSENT_RE = new RegExp(`^\\s*${CLAUSE}(?:\\s*[.,;!]+\\s*${CLAUSE})*\\s*[.!]*\\s*$`, 'i')

export function isConsent(prompt: string): boolean {
  return CONSENT_RE.test(prompt)
}
