import { describe, expect, test } from 'claude-code/testing'

import { clip } from '../hooks/lib/format'
import { sanitizeXmlText, toastCmd } from '../hooks/lib/winalerts'

// A model answer reaches the toast: nothing in it may run, break the XML or split a surrogate pair.
const CONTROL = /[\u0000-\u0008\u000B\u000C\u000E-\u001F￾￿]/
const LONE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/
const HOSTILE = [
  "'; Remove-Item x; '", '$(whoami)', '`calc`', '"dq"', '</text><text>INJECTED</text>', '<toast launch="calc.exe"/>',
  '\x1b[31mred', 'bell\x07', 'a\r\nb', 'lone \ud83d tail',
]

describe('sanitizeXmlText', () => {
  test('drops control characters XML 1.0 forbids; keeps tab, LF, CR and valid pairs', () => {
    expect(sanitizeXmlText('a\x1b[31mb\x07\x00c')).toBe('a[31mbc')
    expect(sanitizeXmlText('a\tb\nc\r🚀')).toBe('a\tb\nc\r🚀')
    expect(sanitizeXmlText('x￾￿y')).toBe('xy')
  })
  test('replaces a lone surrogate, high or low, with U+FFFD', () => {
    expect(sanitizeXmlText('a\ud83db')).toBe('a�b')
    expect(sanitizeXmlText('a\ude80b')).toBe('a�b')
    expect(sanitizeXmlText('\ud83d')).toBe('�')
  })
})

describe('clip', () => {
  test('never ends inside a surrogate pair; short text and plain text are untouched', () => {
    expect(clip('hello', 10)).toBe('hello')
    expect(clip('hello world', 6)).toBe('hello…')
    expect(clip('ab🚀🚀', 4)).toBe('ab…')
    expect(clip('abc🚀🚀', 5)).toBe('abc…')
    expect(clip('abc🚀🚀', 6)).toBe('abc🚀…')
  })
})

describe('toastCmd on Windows', () => {
  test('with a SystemRoot powershell.exe is the absolute Windows PowerShell path; without, the bare name (SEC1-04)', () => {
    const c = toastCmd('t', 'b', 'normal', true, undefined, 'X:\\Win')
    expect(c.argv.slice(0, 4)).toEqual(['X:\\Win\\System32\\WindowsPowerShell\\v1.0\\powershell.exe', '-NoProfile', '-NonInteractive', '-Command'])
    expect(c.argv).toHaveLength(5)
    expect(toastCmd('t', 'b', 'normal', true, undefined, '').argv[0]).toBe('powershell.exe')
    expect(toastCmd('t', 'b', 'normal', false, undefined, 'X:\\Win').argv[0]).toBe('notify-send')
  })
  test('powershell.exe 5.1 with a fixed script; no payload ever reaches argv', () => {
    for (const bad of HOSTILE) {
      const c = toastCmd(bad, bad, 'critical', true)
      expect(c.argv.slice(0, 4)).toEqual(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command'])
      expect(c.argv).toHaveLength(5)
      expect(c.argv.join(' ').includes(bad)).toBe(false)
      expect(c.argv.join(' ')).not.toMatch(/Remove-Item|whoami|INJECTED|calc\.exe/)
    }
  })
  test('the script has no double quote and no drive literal; text comes from env only', () => {
    const script = toastCmd('t', 'b', 'normal', true).argv[4] ?? ''
    expect(script).not.toContain('"')
    expect(/[A-Za-z]:\\/.test(script)).toBe(false)
    expect(script).toContain('$env:MERCY_TITLE')
    expect(script).toContain('$env:MERCY_BODY')
    expect(script).toContain('$env:MERCY_URGENT')
    expect(script).toContain('$env:MERCY_LONG')
    expect(script).toContain("Tag='mercy'")
  })
  test('env carries sanitized text: control chars and lone surrogates gone, pairs and line breaks kept', () => {
    for (const bad of HOSTILE) {
      const env = toastCmd(bad, bad, 'normal', true).env ?? {}
      for (const key of ['MERCY_TITLE', 'MERCY_BODY']) {
        expect(CONTROL.test(env[key] ?? '')).toBe(false)
        expect(LONE.test(env[key] ?? '')).toBe(false)
      }
    }
    const env = toastCmd('✗ — 🚀', 'a\r\nb\tc', 'normal', true).env ?? {}
    expect(env['MERCY_TITLE']).toBe('✗ — 🚀')
    expect(env['MERCY_BODY']).toBe('a\r\nb\tc')
  })
  test('a 10 KB body is clipped at a code-point boundary', () => {
    const env = toastCmd('t', '🚀'.repeat(5000), 'normal', true).env ?? {}
    const body = env['MERCY_BODY'] ?? ''
    expect(body.length).toBeLessThanOrEqual(240)
    expect(LONE.test(body)).toBe(false)
    expect(body.endsWith('…')).toBe(true)
    const odd = toastCmd('t', `${'a'.repeat(238)}🚀🚀`, 'normal', true).env?.['MERCY_BODY'] ?? ''
    expect(LONE.test(odd)).toBe(false)
  })
  test('critical is a reminder; the error turn is a long toast instead; normal is plain', () => {
    expect(toastCmd('t', 'b', 'critical', true).env).toMatchObject({ MERCY_URGENT: '1', MERCY_LONG: '0' })
    expect(toastCmd('t', 'b', 'normal', true).env).toMatchObject({ MERCY_URGENT: '0', MERCY_LONG: '0' })
    expect(toastCmd('t', 'b', 'critical', true, 'error').env).toMatchObject({ MERCY_URGENT: '0', MERCY_LONG: '1' })
    expect(toastCmd('t', 'b', 'critical', true, 'input').env).toMatchObject({ MERCY_URGENT: '1', MERCY_LONG: '0' })
  })
})

describe('toastCmd elsewhere', () => {
  test('notify-send keeps its argv, `--` before the text, no env', () => {
    const c = toastCmd('-t evil', 'body', 'critical', false)
    expect(c.argv).toEqual(['notify-send', '-a', 'Claude Code', '-i', 'utilities-terminal', '-u', 'critical', '-t', '10000', '--', '-t evil', 'body'])
    expect(c.env).toBeUndefined()
    expect(toastCmd('t', 'x'.repeat(500), 'normal', false).argv.at(-1)?.length).toBe(240)
  })
})
