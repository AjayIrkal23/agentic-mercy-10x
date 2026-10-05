// Pure detection of live-looking secrets in text a Write/Edit is about to put on disk.
// High-confidence shapes only: a false positive blocks real work, so generic
// "password = ..." heuristics are deliberately left out.

export type SecretHit = { kind: string; sample: string }

const PATTERNS: ReadonlyArray<readonly [string, RegExp]> = [
  ['private key', /-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY(?: BLOCK)?-----/],
  ['AWS access key', /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/],
  ['GitHub token', /\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b/],
  ['Anthropic API key', /\bsk-ant-[A-Za-z0-9_-]{24,}/],
  ['OpenAI API key', /\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}/],
  ['Slack token', /\bxox[baprs]-[A-Za-z0-9-]{10,}\b/],
  ['Google API key', /\bAIza[0-9A-Za-z_-]{35}\b/],
  ['Stripe live key', /\b(?:sk|rk)_live_[0-9A-Za-z]{24,}\b/],
]

// Documented placeholders that tutorials and tests use on purpose.
const EXAMPLES = ['AKIAIOSFODNN7EXAMPLE', 'AKIAI44QH8DHBEXAMPLE', 'sk-ant-api03-EXAMPLE', 'xoxb-EXAMPLE']

/** Files where a secret is expected to live (and that the repos here gitignore).
 *  Committed templates (`.env.example`, `.sample`, …) are not: a live key pasted
 *  into one gets published (audit H-05). */
export function isSecretHome(path: string): boolean {
  const name = path.split(/[\\/]/).pop() ?? ''
  if (/^\.env\.(example|sample|template|dist|defaults)$/i.test(name)) return false
  return /^\.env(\..+)?$/.test(name) || /\.(pem|key|p12|pfx)$/i.test(name) || /(^|[\\/])\.credentials\.json$/.test(path)
}

export function findSecret(text: string): SecretHit | undefined {
  for (const [kind, re] of PATTERNS) {
    const m = re.exec(text)
    if (!m) continue
    const hit = m[0]
    if (EXAMPLES.some(x => hit.startsWith(x)) || /EXAMPLE|PLACEHOLDER|REDACTED|xxxx/i.test(hit)) continue
    return { kind, sample: `${hit.slice(0, 8)}…` }
  }
  return undefined
}

/** The text a write tool would add: Write's content, Edit's new_string, NotebookEdit's source. */
export function writtenText(input: Record<string, unknown>): string {
  const parts: string[] = []
  for (const key of ['content', 'new_string', 'new_source']) {
    const v = input[key]
    if (typeof v === 'string') parts.push(v)
  }
  const edits = input['edits']
  if (Array.isArray(edits)) {
    for (const e of edits) {
      const v = (e as Record<string, unknown>)['new_string']
      if (typeof v === 'string') parts.push(v)
    }
  }
  return parts.join('\n')
}
