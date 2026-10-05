// Every tool call, main loop and subagents alike: guard checks before it runs, the
// session ledger after it, loop and thrash nudges, and delivery of queued advisories.

import type { EngineInterface, On } from 'claude-code'

import { analyze, commandKey, errorSignature } from '../lib/commands'
import { bashDeny, loopNudge, secretDeny, thrashNudge } from '../lib/guard'
import { recordAgentEnd, recordAgentStart, recordCommand, recordEdit, recordSkill, recordTool } from '../lib/ledger'
import { dirname, targetPath, WRITE_TOOLS } from '../lib/paths'
import { noteError, rt, takePending, ui } from '../lib/runtime'
import { findSecret, isSecretHome, writtenText } from '../lib/secrets'
import { snapshot } from '../lib/snap'
import { statusText } from '../lib/views'

const LEDGER = { plugin: 'mercy', key: 'ledger' } as const
const SHELL_TOOLS = new Set(['Bash', 'mcp__lean-ctx__ctx_shell', 'mcp__lean-ctx__shell'])
const PATCH_TOOLS = new Set(['mcp__lean-ctx__ctx_patch'])
const SKILL_MD = /[\\/]skills[\\/]([^\\/]+)[\\/]SKILL\.md$/

function argsOf(e: Record<string, unknown>): Record<string, unknown> {
  const { tool: _tool, tool_use_id: _id, agentId: _agent, ...input } = e
  return input
}

/** Whether git would track `path`: inside a work tree and not ignored (exit 1). No repo (128) or no answer: false. */
async function committable($: EngineInterface, path: string): Promise<boolean> {
  // run from the nearest existing folder, so a file in a folder not created yet still counts
  let dir = /^([\\/]|[A-Za-z]:)/.test(path) ? dirname(path) : ''
  while (dir && !(await $.fs.exists(dir))) dir = dirname(dir)
  try {
    // safe.directory: a repo owned by another OS user (the Windows replica's SSH account) also exits 128
    const argv = ['git', '-c', 'safe.directory=*', 'check-ignore', '-q', path]
    const r = await $.process.run(argv, dir ? { cwd: dir, timeoutMs: 3000 } : { timeoutMs: 3000 })
    return r.exitCode === 1
  } catch {
    return false
  }
}

async function guardPre($: EngineInterface, tool: string, input: Record<string, unknown>, agentId: string | undefined): Promise<string | undefined> {
  if (SHELL_TOOLS.has(tool)) {
    const command = typeof input['command'] === 'string' ? input['command'] : ''
    return bashDeny(command, analyze(command, input['run_in_background'] === true), agentId)
  }
  if (WRITE_TOOLS.has(tool) || PATCH_TOOLS.has(tool)) {
    const path = targetPath(input) ?? ''
    if (!path || isSecretHome(path)) return undefined
    const hit = findSecret(writtenText(input))
    if (!hit || !(await committable($, path))) return undefined
    return secretDeny(path, hit)
  }
  return undefined
}

async function flush($: EngineInterface, now: number): Promise<void> {
  if (now - rt.lastFlush < 700) return
  rt.lastFlush = now
  await $.state.set(LEDGER, rt.ledger)
  if (ui().status) $.ui.status(statusText(snapshot(now)))
}

type AgentResult = { agentId?: string; totalTokens?: number; totalToolUseCount?: number; totalDurationMs?: number; resolvedModel?: string }

export function registerToolflow(on: On): void {
  on('tool.call', async ($, e, next) => {
    const started = await $.clock.now()
    const input = argsOf(e as unknown as Record<string, unknown>)
    const agent = e.agentId ?? ''
    if (rt.options.guard === 'on') {
      try {
        const deny = await guardPre($, e.tool, input, e.agentId)
        if (deny) {
          recordTool(rt.ledger, e.tool, true)
          return { deny }
        }
      } catch (err) {
        noteError('guard', err)
      }
    }
    if (e.tool === 'Agent') {
      recordAgentStart(rt.ledger, {
        toolUseId: e.tool_use_id,
        type: typeof input['subagent_type'] === 'string' ? input['subagent_type'] : 'general-purpose',
        description: typeof input['description'] === 'string' ? input['description'] : '',
        model: typeof input['model'] === 'string' ? input['model'] : undefined,
        background: input['run_in_background'] !== false,
        startedAt: started,
      })
    }
    if (e.agentId !== undefined) rt.subagentCalls.add(e.tool_use_id)
    const r = await next(e).finally(() => rt.subagentCalls.delete(e.tool_use_id))
    const context: string[] = []
    try {
      const now = await $.clock.now()
      const failed = r.deny !== undefined || r.isError === true
      recordTool(rt.ledger, e.tool, failed)
      if (r.deny === undefined) {
        const staged = (r.result as { staged?: boolean } | undefined)?.staged === true
        const path = targetPath(input)
        if ((WRITE_TOOLS.has(e.tool) || PATCH_TOOLS.has(e.tool)) && !failed && !staged && path) {
          recordEdit(rt.ledger, path, now, agent)
          const nudge = thrashNudge(path, rt.ledger.turnEdits[path] ?? 0)
          if (nudge) context.push(nudge)
        }
        if (SHELL_TOOLS.has(e.tool) && typeof input['command'] === 'string') {
          const info = analyze(input['command'], input['run_in_background'] === true)
          const fail = recordCommand(rt.ledger, {
            key: commandKey(input['command']), command: input['command'].slice(0, 200), kinds: info.kinds, verify: info.verify,
            ok: !failed, at: now, ms: now - started, turn: rt.ledger.turn, agent, error: failed ? errorSignature(r.text ?? '') : undefined,
          })
          const nudge = fail ? loopNudge(fail) : undefined
          if (nudge) context.push(nudge)
        }
        if (e.tool === 'Skill' && typeof input['skill'] === 'string') recordSkill(rt.ledger, input['skill'])
        const skill = e.tool === 'Read' && path ? SKILL_MD.exec(path)?.[1] : undefined
        if (skill) recordSkill(rt.ledger, skill)
        if (e.tool === 'Agent') {
          const res = (r.result ?? {}) as AgentResult
          const run = rt.ledger.agents.find(a => a.toolUseId === e.tool_use_id)
          if (run && res.agentId) run.id = res.agentId
          if (run && res.resolvedModel) run.model = res.resolvedModel
          if (res.totalDurationMs !== undefined || failed) {
            recordAgentEnd(rt.ledger, e.tool_use_id, { endedAt: now, ok: !failed, tokens: res.totalTokens, tools: res.totalToolUseCount })
          }
        }
        // queued advisories belong to the main loop: a subagent's tool result must not take them (NEW-09)
        if (e.agentId === undefined) context.push(...takePending())
      }
      await flush($, now)
    } catch (err) {
      noteError('toolflow', err)
    }
    if (!context.length || r.deny !== undefined) return r
    return { ...r, context: [...(r.context ?? []), ...context] }
  })
}
