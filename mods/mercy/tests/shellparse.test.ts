import { describe, expect, test } from 'claude-code/testing'

import { analyze } from '../hooks/lib/commands'
import { bashDeny } from '../hooks/lib/guard'
import { splitSegments } from '../hooks/lib/shell'

const texts = (cmd: string) => splitSegments(cmd).map(s => s.text)
const verify = (cmd: string) => analyze(cmd).verify

describe('heredoc bodies are data, not commands (santa P9)', () => {
  test('the body is skipped up to its terminator', () => {
    expect(texts("cat > /tmp/x.sh <<'EOF'\ngit commit -m x\nnpm run dev\nEOF\necho done")).toEqual([
      "cat > /tmp/x.sh <<'EOF'", 'echo done',
    ])
    expect(texts('cat <<-"END" | grep x\n\tnpm run dev\n\tEND\nnpm test')).toEqual(['cat <<-"END"', 'grep x', 'npm test'])
    expect(texts('python3 - <<PY\nimport os; os.system("x")\nPY')).toEqual(['python3 - <<PY'])
  })
  test('a here-string is not a heredoc', () => {
    expect(texts('grep x <<< "$v"; npm test')).toEqual(['grep x <<< "$v"', 'npm test'])
  })
  test('a commit line inside a heredoc does not deny a subagent', () => {
    const cmd = "cat > /tmp/run.sh <<'EOF'\ngit commit -m \"x\"\nEOF"
    expect(bashDeny(cmd, analyze(cmd), 'agent-1')).toBeUndefined()
  })
})

describe('wrapped commands are unwrapped before classifying (H-10)', () => {
  test('bash -c, sh -c, eval and subshells', () => {
    for (const cmd of ['bash -c "npm run dev"', "sh -c 'npm start'", 'eval "npm run dev"', '(npm run dev &)', '( cd web && npm run dev )',
      'zsh -lc "vite"', 'cd web && (npm run dev > log 2>&1 &)']) {
      expect(analyze(cmd).isServer, cmd).toBe(true)
    }
    expect(analyze("sh -c 'vitest'").isWatch).toBe(true)
    expect(analyze('bash -lc "git commit -m x"').isCommit).toBe(true)
    expect(analyze('bash -c "echo hi"').isServer).toBe(false)
  })
  test('a wrapped verification still counts when its status is the command\'s', () => {
    expect(verify('bash -c "npm test"')).toEqual(['test'])
    expect(verify('(cd server && npm test)')).toEqual(['test'])
    expect(verify('bash -c "npm test" | tail')).toEqual([])
  })
  test('a short timeout bounds a server or watcher: allowed, a long one is not', () => {
    expect(analyze('timeout 30 npm run dev').isServer).toBe(false)
    expect(analyze('timeout 60s vitest').isWatch).toBe(false)
    expect(analyze('timeout 1m npm start').isServer).toBe(false)
    expect(analyze('timeout 600 npm run dev').isServer).toBe(true)
    expect(analyze('timeout 2h vite').isServer).toBe(true)
  })
  test('timeout 0 disables the limit: still a server or watcher (Santa A1)', () => {
    expect(analyze('timeout 0 npm run dev').isServer).toBe(true)
    expect(analyze('timeout 0s vite').isServer).toBe(true)
    expect(analyze('timeout 0 npx vitest').isWatch).toBe(true)
  })
})

describe('exit-status ownership (santa P1)', () => {
  test('`|` binds tighter than `&&`', () => {
    expect(verify('npm test && npm run lint | tail')).toEqual(['test'])
    expect(verify('npm test && npm run build || true')).toEqual([])
  })
  test('set -e makes `;` behave like `&&` for the last pipeline of each list', () => {
    expect(verify('set -e; npm test; npm run lint')).toEqual(['test', 'lint'])
    expect(verify('set -eu\nnpm test\necho done')).toEqual(['test'])
    expect(verify('set -e; npm test && npm run build; echo x')).toEqual(['build'])
    expect(verify('set -e; npm test || true')).toEqual([])
    expect(verify('npm test; set -e; echo x')).toEqual([])
  })
  test('every pipefail spelling counts, quoted text does not', () => {
    for (const cmd of ['set -o pipefail; npm test | tail -5', 'set -euo pipefail; npm test | tail', 'set -e -o pipefail; npm test | tail',
      'set -eo pipefail\nnpm test 2>&1 | tail -20']) {
      expect(verify(cmd), cmd).toEqual(['test'])
    }
    expect(verify('echo "set -o pipefail"; npm test | tail')).toEqual([])
    expect(verify('set -o pipefail; set +o pipefail; npm test | tail')).toEqual([])
  })
})

describe('one-shot vitest and pnpm -w (santa P2, P3)', () => {
  test('vitest --no-watch and options before run are one-shot', () => {
    for (const cmd of ['vitest --no-watch', 'vitest --reporter=dot run', 'npx vitest --config v.config.ts run src']) {
      expect(analyze(cmd).isWatch, cmd).toBe(false)
      expect(verify(cmd), cmd).toEqual(['test'])
    }
  })
  test('pnpm -w is boolean (--workspace-root); npm -w takes a value', () => {
    expect(analyze('pnpm -w test').kinds).toEqual(['test'])
    expect(analyze('pnpm -w dev').isServer).toBe(true)
    expect(analyze('npm -w api run dev').isServer).toBe(true)
    expect(analyze('npm --workspace api test').kinds).toEqual(['test'])
  })
})
