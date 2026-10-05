import type { On } from 'claude-code'
import type { Engine } from 'claude-code/testing'
import { describe, expect, mock, test } from 'claude-code/testing'

import { analyze } from '../hooks/lib/commands'
import { bashDeny } from '../hooks/lib/guard'
import { splitSegments } from '../hooks/lib/shell'
import { isShellTool, SHELL_TOOLS } from '../hooks/lib/tools'
import { isExitForwarder } from '../hooks/lib/winshell'

// Windows spellings (A1-01, A1-06..A1-08, A1-11): parsed on every OS, harmless on Linux.
const servers = [
  'npm.cmd run dev', 'pnpm.cmd dev', 'npx.cmd vite', 'D:\\x\\npm.cmd run dev', 'cmd /c npm run dev', 'cmd.exe /c "npm run dev"',
  'powershell -c "npm run dev"', 'pwsh -NoProfile -Command npm run dev', 'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "npm run dev"',
  'Start-Process npm -ArgumentList "run","dev"', "Start-Process -FilePath npm.cmd -ArgumentList 'run','dev' -NoNewWindow",
  "iex 'npm run dev'", "Invoke-Expression 'npm run dev'", 'start /b npm run dev', 'wsl npm run dev', 'D:\\Py\\python.exe -m http.server',
]

describe('Windows launchers and suffixes keep their class (A1-06)', () => {
  test('every launcher spelling of a dev server is denied', () => {
    for (const cmd of servers) {
      expect(analyze(cmd).isServer, cmd).toBe(true)
      expect(bashDeny(cmd, analyze(cmd), undefined), cmd).toContain('dev server')
    }
  })
  test('a wrapped quiet command is no server', () => {
    for (const cmd of ['cmd /c dir', 'powershell -c "Get-Date"', 'Start-Process notepad', 'npm.cmd run build']) {
      expect(analyze(cmd).isServer, cmd).toBe(false)
    }
  })
  test('git.exe commit is a commit (denied for a subagent), quoted path too', () => {
    for (const cmd of ['git.exe commit -m x', '"D:\\Program Files\\Git\\cmd\\git.exe" commit -m x']) {
      expect(analyze(cmd).isCommit, cmd).toBe(true)
      expect(bashDeny(cmd, analyze(cmd), 'agent-1'), cmd).toContain('subagents never commit')
    }
  })
  test('suffixed test, typecheck and build commands are verify evidence', () => {
    expect(analyze('npm.cmd test').verify).toEqual(['test'])
    expect(analyze('tsc.exe --noEmit').verify).toEqual(['typecheck'])
    expect(analyze('npx.cmd vitest run').verify).toEqual(['test'])
    expect(analyze('powershell -c "npm test"').verify).toEqual(['test'])
  })
})

describe('a closing backslash inside double quotes (A1-07)', () => {
  test('PowerShell "D:\\p\\" closes the quote: two segments, the server is seen', () => {
    for (const cmd of ['Set-Location "D:\\p\\"; npm run dev', 'cd "D:\\p\\" && npm run dev']) {
      expect(splitSegments(cmd), cmd).toHaveLength(2)
      expect(analyze(cmd).isServer, cmd).toBe(true)
    }
  })
  test('a bash escaped quote before a space still escapes (no swallowed tail)', () => {
    const cmd = 'echo "a \\" b"; npm run dev'
    expect(splitSegments(cmd)).toHaveLength(2)
    expect(analyze(cmd).isServer).toBe(true)
  })
})

describe('PowerShell idioms (A1-08, A1-11)', () => {
  test('$env:CI earlier in the chain makes vitest one-shot', () => {
    expect(analyze("$env:CI='1'; vitest").isWatch).toBe(false)
    expect(analyze("$env:CI='1'\nnpx vitest").kinds).toContain('test')
    expect(analyze('vitest').isWatch).toBe(true)
  })
  test('an exit-code forwarder keeps the evidence of the segment before it', () => {
    expect(analyze('npm test; if ($LASTEXITCODE -ne 0) { exit 1 }').verify).toEqual(['test'])
    expect(analyze('npm test\nif ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }').verify).toEqual(['test'])
    expect(analyze('npm test; exit $LASTEXITCODE').verify).toEqual(['test'])
    expect(analyze('npm test | Out-Null; if ($?) { exit 1 }').verify).toEqual([])
    expect(analyze('npm test; Write-Host done').verify).toEqual([])
  })
  test('a forwarder that swallows or inverts the failure gives no evidence (SANTA1-02)', () => {
    for (const cmd of [
      'npm test; if ($LASTEXITCODE -ne 0) { exit 0 }',
      'npm test; if ($LASTEXITCODE -eq 0) { exit 1 }',
      'npm test; if ($LASTEXITCODE -ne 0) { exit 0 } else { exit 1 }',
      'npm test; if ($?) { exit 1 }',
      'npm test; if (-not $?) { exit 0 }',
    ]) expect(analyze(cmd).verify, cmd).toEqual([])
  })
  test('status-preserving forwarders keep the evidence (SANTA1-02)', () => {
    for (const cmd of [
      'npm test; if ($LASTEXITCODE -ne 0) { exit 1 }',
      'npm test; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }',
      'npm test; if (-not $?) { exit 3 }',
      'npm test; if (!$?) { exit 1 }',
      'npm test; exit $LASTEXITCODE',
    ]) expect(analyze(cmd).verify, cmd).toEqual(['test'])
  })
  // SEC1-07 / A6v2-01: no absolute clock bound (it failed under load). The regex never sees a long text:
  // a candidate over the cap is refused by length, even one that would match (structural), and the work
  // grows with the input (best of 5 runs each side, so a load burst on one run cannot decide).
  const best = (f: () => void): number => {
    let m = Infinity
    for (let i = 0; i < 5; i++) {
      const t0 = performance.now()
      f()
      m = Math.min(m, performance.now() - t0)
    }
    return m
  }
  const FORWARD = (pad: number) => `if ($LASTEXITCODE -ne 0) {${' '.repeat(pad)}exit 1 }`
  test('a forwarder candidate over the length cap is refused before the regex runs (SEC1-07)', () => {
    expect(isExitForwarder(FORWARD(100))).toBe(true)
    expect(isExitForwarder(FORWARD(500))).toBe(false)
    for (const text of [`if(${'$? '.repeat(17_000)}`, `if (${'$LASTEXITCODE '.repeat(4_000)}) { exit 1 }`]) expect(isExitForwarder(text)).toBe(false)
  })
  test('classifying a long hostile command scales with its size (SEC1-07)', () => {
    const run = (unit: string, n: number) => () => void analyze(`npm test; ${unit.repeat(n)}`)
    for (const unit of ['if($? ', '$? ', '{ ', 'a{', '@\'\n', '"\\"', '(']) {
      const small = best(run(unit, 1_000))
      const big = best(run(unit, 10_000))
      expect(big, unit).toBeLessThan(40 * small + 400)
    }
  })
  test('vitest --version / --help is no watcher and no test evidence', () => {
    for (const cmd of ['vitest --version', 'vitest -v', 'vitest --help', 'vitest -h', 'npx vitest --version']) {
      expect(analyze(cmd).isWatch, cmd).toBe(false)
      expect(analyze(cmd).verify, cmd).toEqual([])
    }
  })
})

describe('the shell tool set', () => {
  test('PowerShell is a shell tool next to Bash and the lean-ctx shells', () => {
    expect([...SHELL_TOOLS].sort()).toEqual(['Bash', 'PowerShell', 'mcp__lean-ctx__ctx_shell', 'mcp__lean-ctx__shell'])
    expect(isShellTool('PowerShell')).toBe(true)
    expect(isShellTool('Edit')).toBe(false)
  })
})

function engine(on: On, ran: (tool: string) => void = () => {}) {
  const clock = mock.clock(on, { now: 1_000_000 })
  mock.store(on)
  mock.env(on, {})
  on('classic.PreToolUse', () => ({}))
  on('classic.UserPromptSubmit', () => ({}))
  on('classic.Stop', () => ({}))
  on('session.model', () => ({ value: 'claude-sonnet-5-5' }))
  on('tool.call', (_$, e) => {
    ran(e.tool)
    return (e.tool === 'Bash' || e.tool === 'PowerShell' ? { result: 'ok' } : { result: { filePath: '/r/src/a.ts' } }) as never
  })
  return clock
}

describe('the PowerShell tool through the engine (A1-01)', () => {
  test('a dev server is denied before it runs, like Bash', async ($, on) => {
    const ran: string[] = []
    engine(on, t => ran.push(t))
    for (const command of ['npm run dev', 'npx vite']) {
      const r = await $.tool.call({ tool: 'PowerShell', command })
      expect(r.deny, command).toContain('dev server')
    }
    expect(ran).toEqual([])
  })
  test('a passing PowerShell test run after the edit satisfies the verify gate', async ($, on) => {
    const clock = engine(on)
    await $.classic.UserPromptSubmit({ prompt: 'fix the bug' })
    await $.tool.call({ tool: 'Bash', command: 'npm test' }) // makes `npm test` the known verify command
    await clock.advance(5000)
    await $.tool.call({ tool: 'Edit', file_path: '/r/src/a.ts', old_string: 'a', new_string: 'b' })
    await clock.advance(5000)
    await $.tool.call({ tool: 'PowerShell', command: 'npm test' })
    expect((await $.classic.Stop({ stop_hook_active: false })).block).toBeUndefined()
  })
  // A1v2-05: the PowerShell tool reports the last native command's status, so the usual tail idiom is evidence there
  async function editThenRun(tool: 'Bash' | 'PowerShell', command: string, $: Engine, on: On) {
    const clock = engine(on)
    await $.classic.UserPromptSubmit({ prompt: 'fix the bug' })
    await $.tool.call({ tool: 'Bash', command: 'npm test' })
    await clock.advance(5000)
    await $.tool.call({ tool: 'Edit', file_path: '/r/src/a.ts', old_string: 'a', new_string: 'b' })
    await clock.advance(5000)
    await $.tool.call({ tool, command })
    return $.classic.Stop({ stop_hook_active: false })
  }
  test('`npm test 2>&1 | Select-Object -Last 20` through PowerShell satisfies the verify gate', async ($, on) => {
    expect((await editThenRun('PowerShell', 'npm test 2>&1 | Select-Object -Last 20', $, on)).block).toBeUndefined()
  })
  test('the same text through Bash does not (a pipe masks the status there)', async ($, on) => {
    expect((await editThenRun('Bash', 'npm test 2>&1 | Select-Object -Last 20', $, on)).block).toBeDefined()
  })
  test('a Start-Process run never satisfies the gate', async ($, on) => {
    expect((await editThenRun('PowerShell', 'Start-Process npm -ArgumentList test -Wait -NoNewWindow', $, on)).block).toBeDefined()
  })
})
