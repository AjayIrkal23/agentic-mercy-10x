import { describe, expect, test } from 'claude-code/testing'

import { portsMarkdown } from '../hooks/lib/deckviews'
import { KNOWN, netstatRows, npmFailed, parseNetstat, parseOutdated, parseTasklist, portCmds } from '../hooks/lib/probes'

// Trimmed from real `netstat -ano -p TCP|TCPv6` and `tasklist /FO CSV /NH` output (anonymised
// addresses, CRLF kept): ESTABLISHED, TIME_WAIT and SYN_SENT rows, a long IPv6 row, image names with spaces.
const CRLF = (lines: string[]): string => `${lines.join('\r\n')}\r\n`
const V4 = CRLF([
  '', 'Active Connections', '', '  Proto  Local Address          Foreign Address        State           PID',
  '  TCP    0.0.0.0:22             0.0.0.0:0              LISTENING       5928',
  '  TCP    0.0.0.0:445            0.0.0.0:0              LISTENING       4',
  '  TCP    127.0.0.1:3025         0.0.0.0:0              LISTENING       17920',
  '  TCP    127.0.0.1:4400         0.0.0.0:0              LISTENING       15984',
  '  TCP    127.0.0.1:4400         127.0.0.1:64006        ESTABLISHED     15984',
  '  TCP    127.0.0.1:5432         0.0.0.0:0              LISTENING       7132',
  '  TCP    127.0.0.1:6379         0.0.0.0:0              LISTENING       13396',
  '  TCP    127.0.0.1:58572        0.0.0.0:0              LISTENING       21536',
  '  TCP    127.0.0.1:59278        127.0.0.1:59279        TIME_WAIT       0',
  '  TCP    127.0.0.1:59583        0.0.0.0:0              LISTENING       21840',
  '  TCP    192.168.1.50:59415    192.168.1.186:7680    SYN_SENT        13404',
])
const V6 = CRLF([
  '', 'Active Connections', '', '  Proto  Local Address          Foreign Address        State           PID',
  '  TCP    [::]:22                [::]:0                 LISTENING       5928',
  '  TCP    [::1]:4400             [::]:0                 LISTENING       15984',
  '  TCP    [::1]:5432             [::]:0                 LISTENING       7132',
  '  TCP    [2001:db8:0:1::10]:53190  [2001:db8:ffff::2603]:443  ESTABLISHED     10144',
])
const TASKS = CRLF([
  '"System Idle Process","0","Services","0","8 K"', '"System","4","Services","0","6,068 K"',
  '"postgres.exe","7132","Services","0","26,796 K"', '"com.docker.backend.exe","13396","Console","1","1,72,500 K"',
  '"ollama app.exe","21840","Console","1","35,624 K"', '"node.exe","15984","Console","1","1,18,200 K"',
  '"node.exe","17920","Console","1","70,900 K"', '"claude.exe","21536","Console","1","6,05,536 K"',
])

describe('netstat -ano: what is listening, locale-proof', () => {
  test('the wildcard foreign address marks a listener; the state word is never read', () => {
    expect(netstatRows(V4).map(r => r.port)).toEqual([22, 445, 3025, 4400, 5432, 6379, 58572, 59583])
    expect(netstatRows(V6).map(r => [r.port, r.address])).toEqual([[22, '::'], [4400, '::1'], [5432, '::1']])
    for (const word of ['ABHÖREN', 'ÉCOUTE', 'ASCOLTO']) expect(netstatRows(V4.replace(/LISTENING/g, word))).toHaveLength(8)
  })
  test('ESTABLISHED, TIME_WAIT, SYN_SENT and header lines are not listeners', () => {
    expect(netstatRows('  TCP    127.0.0.1:4400         127.0.0.1:64006        ESTABLISHED     15984\r\n')).toEqual([])
    expect(netstatRows('  TCP    127.0.0.1:59278        127.0.0.1:59279        TIME_WAIT       0\r\n')).toEqual([])
    expect(netstatRows('Active Connections\r\n\r\n  Proto  Local Address          Foreign Address        State           PID\r\n')).toEqual([])
    expect(netstatRows('')).toEqual([])
  })
  test('an IPv6 loopback listener keeps address ::1 (no brackets); LF input parses too', () => {
    expect(netstatRows('  TCP    [::1]:5173             [::]:0                 LISTENING       99\n')).toEqual([{ port: 5173, address: '::1', pid: 99 }])
  })
})

describe('tasklist and the join', () => {
  test('image names: quoted CSV, spaces kept, .exe stripped in any case', () => {
    const names = parseTasklist(TASKS)
    expect(names.get(21840)).toBe('ollama app')
    expect(names.get(7132)).toBe('postgres')
    expect(names.get(4)).toBe('System')
    expect(parseTasklist('"Node.EXE","1","Console","1","1 K"\r\n').get(1)).toBe('Node')
    expect(parseTasklist('not csv\r\n').size).toBe(0)
  })
  test('one row per port, the one naming its process preferred; labels from KNOWN', () => {
    expect(parseNetstat(V4, V6, TASKS)).toEqual([
      { port: 22, address: '0.0.0.0' },
      { port: 445, address: '0.0.0.0', process: 'System', pid: 4 },
      { port: 3025, address: '127.0.0.1', process: 'node', pid: 17920 },
      { port: 4400, address: '127.0.0.1', process: 'node', pid: 15984 },
      { port: 5432, address: '127.0.0.1', process: 'postgres', pid: 7132, label: 'postgres' },
      { port: 6379, address: '127.0.0.1', process: 'com.docker.backend', pid: 13396, label: 'redis' },
      { port: 58572, address: '127.0.0.1', process: 'claude', pid: 21536 },
      { port: 59583, address: '127.0.0.1', process: 'ollama app', pid: 21840 },
    ])
    expect(KNOWN[5173]).toBe('vite')
  })
  test('a named process on the IPv6 row beats an unnamed IPv4 row of the same port', () => {
    const v4 = '  TCP    0.0.0.0:7000           0.0.0.0:0              LISTENING       1\r\n'
    const v6 = '  TCP    [::]:7000              [::]:0                 LISTENING       2\r\n'
    expect(parseNetstat(v4, v6, '"node.exe","2","Console","1","1 K"\r\n')).toEqual([{ port: 7000, address: '::', process: 'node', pid: 2 }])
  })
  test('it also takes names already known (the scan keeps a pid cache)', () => {
    expect(parseNetstat(V4, V6, new Map([[17920, 'node']])).find(r => r.port === 3025)).toEqual({ port: 3025, address: '127.0.0.1', process: 'node', pid: 17920 })
  })
})

describe('what to run', () => {
  test('ss on Linux; netstat for v4 and v6 plus tasklist on Windows', () => {
    expect(portCmds(false)).toEqual([['ss', '-ltnpH']])
    expect(portCmds(true)).toEqual([['netstat', '-ano', '-p', 'TCP'], ['netstat', '-ano', '-p', 'TCPv6'], ['tasklist', '/FO', 'CSV', '/NH']])
  })
  test('with a SystemRoot the Windows tools are spawned by absolute System32 path (SEC1-04)', () => {
    expect(portCmds(true, 'X:\\Win')).toEqual([
      ['X:\\Win\\System32\\netstat.exe', '-ano', '-p', 'TCP'], ['X:\\Win\\System32\\netstat.exe', '-ano', '-p', 'TCPv6'],
      ['X:\\Win\\System32\\tasklist.exe', '/FO', 'CSV', '/NH'],
    ])
    expect(portCmds(true, '')).toEqual(portCmds(true))
    expect(portCmds(false, 'X:\\Win')).toEqual([['ss', '-ltnpH']])
  })
})

describe('npm outdated that is really a failure (SANTA1-07)', () => {
  const row = { current: '7.0.0', wanted: '7.2.1', latest: '10.0.0' }
  test('an outdated dependency named "error" is a package row, not a failure', () => {
    const json = JSON.stringify({ error: row, react: { current: '18.2.0', wanted: '18.3.1', latest: '19.1.0' } })
    expect(npmFailed(json)).toBe(false)
    expect(parseOutdated(json).map(r => r.name)).toEqual(['error', 'react'])
    expect(parseOutdated(JSON.stringify({ error: row }))).toHaveLength(1)
  })
  test('npm\'s own error object is still a failure', () => {
    expect(npmFailed('{"error":{"code":"ECONNREFUSED","summary":"x"}}')).toBe(true)
    expect(npmFailed('{"error":{"summary":"x"}}')).toBe(true)
    expect(npmFailed('{"error":{"code":"E404"}}')).toBe(true)
    expect(parseOutdated('{"error":{"code":"ECONNREFUSED","summary":"x"}}')).toEqual([])
  })
  test('code or summary next to a version field is a package row; a bare error object is no failure', () => {
    expect(npmFailed(JSON.stringify({ error: { ...row, code: 'x' } }))).toBe(false)
    expect(npmFailed('{"error":{}}')).toBe(false)
    expect(npmFailed('{"error":"x"}')).toBe(false)
    expect(npmFailed('not json')).toBe(false)
  })
})

describe('ports card', () => {
  test('::1, 127.0.0.1 and wildcard dev ports link to localhost', () => {
    expect(portsMarkdown([{ port: 5173, address: '::1', label: 'vite' }])).toContain('[5173](http://localhost:5173)')
    expect(portsMarkdown([{ port: 5173, address: '127.0.0.1', label: 'vite' }])).toContain('[5173](http://localhost:5173)')
    expect(portsMarkdown([{ port: 5173, address: '192.168.1.5', label: 'vite' }])).not.toContain('http://localhost')
  })
  test('a failed scan says so; it is never "nothing is listening"', () => {
    const md = portsMarkdown([], 'netstat exited 1')
    expect(md).toContain('Port scan failed: netstat exited 1')
    expect(md).not.toContain('Nothing is listening')
    expect(portsMarkdown([{ port: 5173, address: '::1', label: 'vite' }], 'tasklist timed out')).toMatch(/Port scan failed: tasklist timed out[\s\S]*5173/)
    expect(portsMarkdown([])).toBe('Nothing is listening on TCP.')
  })
})
