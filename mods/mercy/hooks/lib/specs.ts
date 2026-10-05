// Pure declarations of what the plugin registers: model-callable tools and slash commands.

export const TOOL_SESSION_STATE = 'session_state'
export const TOOL_REPO_FACTS = 'repo_facts'
export const TOOL_REMEMBER = 'remember'

export const TOOL_SPECS = [
  {
    name: TOOL_SESSION_STATE,
    description:
      "mercy: this session's live workflow state — files changed and which are unverified, Bash commands with pass/fail, " +
      'repeated failures, subagents, the last verification, queued hook advisories. Call it before claiming work is done, ' +
      'after a compaction, or when resuming.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: TOOL_REPO_FACTS,
    description:
      'mercy: what earlier sessions learned about this repo — verified build/test/lint commands with their pass history, ' +
      'package manager and stack, past fixes, and saved notes. Cheaper than rediscovering how to build and test.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: TOOL_REMEMBER,
    description:
      'mercy: save one durable fact about this repo (a command, a convention, a gotcha) for future sessions. One sentence, never a secret.',
    inputSchema: {
      type: 'object',
      properties: { fact: { type: 'string', description: 'One sentence. No secrets, tokens or credentials.' } },
      required: ['fact'],
      additionalProperties: false,
    },
  },
] as const

export const COMMAND_SPECS = [
  {
    name: 'pulse',
    description: 'mercy: open the live pane (usage, git, CI, tasks, files, commands, agents, hooks, repo brain)',
    argumentHint: '[overview|usage|git|ci|todo|files|commands|agents|hooks|brain]',
  },
  {
    name: 'mercy',
    description: 'mercy mods: status, brain, forget, release (hand all hook links back to Python), resume-cancel',
    argumentHint: '[status|brain|forget|release|resume-cancel]',
  },
  { name: 'ui', description: 'mercy: UI mode and toggles (full shows everything, focus failures only, quiet the status line only)', argumentHint: '[full|focus|quiet|off|sound on|off|notify on|off|pane on|off|reset]', immediate: true },
  { name: 'wrapup', description: 'mercy: session recap card (time, cost, files, checks, agents, tasks); the pane overview shows the previous session by itself', immediate: true },
  { name: 'standup', description: 'mercy: standup card (made by itself each morning; pane tab s), with a Copy button' },
  { name: 'ports', description: 'mercy: listening ports as a card (watched every minute; pane tab p)', immediate: true },
  { name: 'deps', description: 'mercy: outdated npm packages as a card (checked daily; pane tab d)' },
  { name: 'ci', description: "mercy: refresh this branch's PR checks or workflow runs and show them in the pane" },
  { name: 'sound', description: 'mercy: test the alert sounds, or turn them on or off', argumentHint: '[test|on|off]', immediate: true },
] as const

export const PANE_ID = 'mercy'

/** `$.store` key of the `/ui` and `/sound` overrides, shared by every session. */
export const PREFS_KEY = 'ui:prefs'
