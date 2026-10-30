import { describe, expect, test } from 'claude-code/testing'

import { decideResumeLock, flagBody, lockBody } from '../hooks/lib/resumelock'

const NOW = 1_761_740_000_000

describe('decideResumeLock', () => {
  test('free, stale or own lock → take; a fresh foreign lock → yield', () => {
    expect(decideResumeLock(undefined, NOW)).toEqual({ take: true, reason: 'free' })
    expect(decideResumeLock(JSON.stringify({ owner: 'python', ts: NOW / 1000 - 700 }), NOW)).toEqual({ take: true, reason: 'stale' })
    expect(decideResumeLock(JSON.stringify({ owner: 'python', ts: NOW / 1000 - 10 }), NOW)).toEqual({ take: false, reason: 'held:python' })
    expect(decideResumeLock('{bad', NOW)).toEqual({ take: true, reason: 'unreadable' })
    expect(decideResumeLock(JSON.stringify({ owner: 'mod', ts: NOW / 1000 - 10 }), NOW)).toEqual({ take: true, reason: 'own' })
  })
  test('bodies use seconds, like the Python side', () => {
    expect(JSON.parse(lockBody(NOW))).toEqual({ owner: 'mod', ts: NOW / 1000 })
    expect(JSON.parse(flagBody('s1', NOW))).toEqual({ sid: 's1', pid: null, ts: NOW / 1000 })
    expect(JSON.parse(flagBody('s1', NOW, true)).ts).toBe(0)
  })
})
