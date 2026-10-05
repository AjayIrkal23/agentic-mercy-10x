import { describe, expect, test } from 'claude-code/testing'

import { analyze } from '../hooks/lib/commands'
import { bashDeny } from '../hooks/lib/guard'
import { splitSegments } from '../hooks/lib/shell'

// Audit #2 (A1v2-01..03, 05..08): PowerShell script blocks, here-strings, tool-aware
// evidence, Git Bash `//c` spellings, py/python names. Pure tables: run on every OS.
const ps = (cmd: string) => analyze(cmd, false, 0, 'powershell')
const bash = (cmd: string) => analyze(cmd)
const texts = (cmd: string) => splitSegments(cmd).map(s => s.text)

describe('verify evidence is tool-aware (A1v2-05)', () => {
  const tails = [
    'npm test 2>&1 | Select-Object -Last 20', 'npm test | Tee-Object x.log', 'npm test; Write-Host done',
    'npm test; Get-Content test.log -Tail 20', 'npm test | Out-Null', 'npm test 2>&1 | Select-Object -Last 5; Write-Host ok',
  ]
  test('the PowerShell tool reports the last native command: trailing cmdlets and pipe tails do not mask it', () => {
    for (const cmd of tails) expect(ps(cmd).verify, cmd).toEqual(['test'])
  })
  test('the same text under Bash keeps the bash rules (no evidence)', () => {
    for (const cmd of tails) expect(bash(cmd).verify, cmd).toEqual([])
  })
  test('a later native command owns the status; a native pipe tail still masks', () => {
    expect(ps('npm test; npm run lint').verify).toEqual(['lint'])
    expect(ps('npm test | findstr ok').verify).toEqual([])
    expect(ps('npm test && Write-Host ok').verify).toEqual(['test'])
    expect(ps('npm test || Write-Host failed').verify).toEqual(['test'])
    expect(bash('npm test || Write-Host failed').verify).toEqual([])
  })
  test('a script block body is never evidence', () => {
    for (const cmd of ['if (Test-Path node_modules) { npm test }', 'try { npm test } catch { Write-Host failed }', '& { npm test }']) {
      expect(ps(cmd).verify, cmd).toEqual([])
      expect(bash(cmd).verify, cmd).toEqual([])
    }
  })
  test('the exit-code forwarders keep working (no split inside them)', () => {
    expect(ps('npm test; if ($LASTEXITCODE -ne 0) { exit 1 }').verify).toEqual(['test'])
    expect(ps('npm test; if ($LASTEXITCODE -ne 0) { exit 0 }').verify).toEqual([])
  })
})

describe('Start-Process and start never give evidence (A1v2-01)', () => {
  test('a detached run reports nothing to the tool: no evidence, the guard still sees the kind', () => {
    for (const cmd of ['Start-Process npm -ArgumentList test -Wait -NoNewWindow', 'start npm test', 'saps npm -ArgumentList test',
      'powershell -c "Start-Process npm -ArgumentList test -Wait"', 'cmd /c start npm test']) {
      expect(bash(cmd).verify, cmd).toEqual([])
      expect(ps(cmd).verify, cmd).toEqual([])
      expect(bash(cmd).kinds, cmd).toContain('test')
    }
  })
  test('a server behind Start-Process is still a server', () => {
    for (const cmd of ['Start-Process npm -ArgumentList run,dev', 'saps npm -ArgumentList run,dev', 'start npm run dev']) {
      expect(bash(cmd).isServer, cmd).toBe(true)
    }
  })
})

describe('script blocks and control flow are scanned (A1v2-02)', () => {
  const blocks = [
    '{ npm run dev }', 'if ($true) { npm run dev }', 'Start-Job { npm run dev }', 'Start-Job -ScriptBlock { npm run dev }',
    'Start-ThreadJob { npm run dev }', 'Invoke-Command -ScriptBlock { npm run dev }', '& { npm run dev }', '. { npm run dev }',
    'foreach ($i in 1..2) { npm run dev }', 'try { npm run dev } catch { }', '1..1 | ForEach-Object { npm run dev }',
    '$job = Start-Job { npm run dev }', 'Start-Job -ScriptBlock { npm run dev } | Wait-Job | Receive-Job', 'if ($x) { 1 } else { npm run dev }',
  ]
  test('a dev server inside a block is a server, in both tools', () => {
    for (const cmd of blocks) {
      expect(bash(cmd).isServer, cmd).toBe(true)
      expect(ps(cmd).isServer, cmd).toBe(true)
      expect(bashDeny(cmd, ps(cmd), undefined), cmd).toContain('dev server')
    }
  })
  test('watchers and commits inside a block are seen', () => {
    expect(ps('Start-Job { vitest }').isWatch).toBe(true)
    expect(ps('if ($true) { git commit -m x }').isCommit).toBe(true)
    expect(bashDeny('Start-Job { git commit -m x }', ps('Start-Job { git commit -m x }'), 'agent-1')).toContain('subagents never commit')
  })
  test('hashtables, ${}, quoted braces and a quiet block stay quiet', () => {
    for (const cmd of ['@{ serve = 1 }', 'Write-Host "{ npm run dev }"', 'echo ${HOME}', '$h = @{ a = 1 }; npm run build', 'git diff HEAD@{1}',
      'if ($x) { Write-Host hi }', "Write-Host '{ npm run dev }'"]) {
      expect(ps(cmd).isServer, cmd).toBe(false)
    }
  })
  test('a split brace never hides a segment from the timeout bound or breaks the quote tracking', () => {
    expect(ps('Start-Job { timeout 30 npm run dev }').isServer).toBe(false)
    expect(texts('if ($x) { npm run dev }')).toEqual(['if ($x)', 'npm run dev'])
  })
})

describe('PowerShell here-strings are data (A1v2-06)', () => {
  test('an apostrophe inside @\'…\'@ makes no phantom segment, no false deny', () => {
    const cmd = "Set-Content README.md @'\nDon't forget\nnpm run dev\n'@"
    expect(texts(cmd)).toHaveLength(1)
    expect(ps(cmd).isServer).toBe(false)
    expect(bashDeny(cmd, ps(cmd), undefined)).toBeUndefined()
    const commit = "Set-Content notes.md @'\nDon't run git commit here\n'@"
    expect(bashDeny(commit, ps(commit), 'agent-1')).toBeUndefined()
  })
  test('a double-quoted here-string and CRLF line ends are skipped too', () => {
    expect(ps('$m = @"\r\nit\'s "quoted"\r\nnpm run dev\r\n"@').isServer).toBe(false)
    expect(texts('Set-Content a.md @\'\r\nDon\'t\r\n\'@')).toHaveLength(1)
  })
  test('what follows the terminator is still read (pipe, next line)', () => {
    expect(ps("$m = @'\nhello\n'@\nnpm run dev").isServer).toBe(true)
    expect(ps("@'\nx\n'@ | Out-File a.txt; npm run dev").isServer).toBe(true)
  })
  test('@\' not followed by a newline is no here-string', () => {
    expect(ps("echo @'x'; npm run dev").isServer).toBe(true)
  })
})

describe('Git Bash spellings of the cmd and start switches (A1v2-03)', () => {
  test('`//c`, `//k` and `//b` unwrap like `/c`, `/b`', () => {
    for (const cmd of ['cmd //c npm run dev', 'cmd.exe //c "npm run dev"', 'cmd //c start npm run dev', 'cmd //c "cd /d D:\\app && npm run dev"',
      '/c/Windows/System32/cmd.exe //c npm run dev', 'start //b npm run dev', 'cmd //k npm run dev']) {
      expect(bash(cmd).isServer, cmd).toBe(true)
    }
    expect(bash('cmd //c npm test').kinds).toContain('test')
    expect(bash('cmd //c dir').isServer).toBe(false)
  })
})

describe('Python launchers and executable case (A1v2-07, A1v2-08)', () => {
  test('py -3.12, py -V:3.12, python313 and pythonw read as Python', () => {
    for (const cmd of ['py -3.12 -m http.server', 'py -3.12 -m uvicorn app:app', 'py -V:3.12 -m http.server', 'python313 -m http.server',
      'pythonw -m http.server', 'py -3.12-32 -m http.server', 'python3.12 -m http.server', 'py -3 -m http.server']) {
      expect(bash(cmd).isServer, cmd).toBe(true)
    }
    expect(bash('py -3.12 -m pytest -q').verify).toEqual(['test'])
    expect(bash('py -V:3.12 -m pytest -q').verify).toEqual(['test'])
  })
  test('executable names are compared case-insensitively', () => {
    for (const cmd of ['NPM run dev', 'Npm.cmd run dev', 'Npx vite', 'NPX.CMD vite', 'Vitest', 'PYTHON.EXE -m http.server', 'Py -3 -m http.server',
      'Start-process npm -ArgumentList run,dev']) {
      expect(bash(cmd).isServer || bash(cmd).isWatch, cmd).toBe(true)
    }
    expect(bash('GIT.EXE push origin x').isPush).toBe(true)
    expect(bash('Git commit -m x').isCommit).toBe(true)
    expect(bash('NPM.cmd test').verify).toEqual(['test'])
  })
})
