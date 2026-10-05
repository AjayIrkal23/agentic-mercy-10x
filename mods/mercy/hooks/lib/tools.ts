// Tools that run a shell command (`input.command`): the guard, the ledger, the verify
// gate and the deck treat them alike. Pure: no `$`.

export const SHELL_TOOLS: ReadonlySet<string> = new Set(['Bash', 'PowerShell', 'mcp__lean-ctx__ctx_shell', 'mcp__lean-ctx__shell'])

export const isShellTool = (tool: string): boolean => SHELL_TOOLS.has(tool)

/** Whose exit-status rules decide what a command proves: Bash's, or the PowerShell tool's (the last native command's `$LASTEXITCODE`). */
export type Shell = 'bash' | 'powershell'

export const shellOf = (tool: string): Shell => (tool === 'PowerShell' ? 'powershell' : 'bash')
