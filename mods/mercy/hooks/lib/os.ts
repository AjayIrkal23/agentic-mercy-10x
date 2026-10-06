// The one OS switch of the mod. A mod has no `process` global, so the host OS comes from
// the engine env: Windows sets OS=Windows_NT (WSL and Linux leave it unset). lifecycle.ts
// stores the answer in `rt.windows` at session start; pure builders take `windows: boolean`.

export function isWindowsEnv(osVar: string | undefined): boolean {
  return osVar === 'Windows_NT'
}

/**
 * A Windows system tool by absolute path (`<SystemRoot>\System32\<rel>`), so a planted `netstat.exe` earlier on PATH
 * or in the cwd never runs (SEC1-04). `root` is `$.env.get('SystemRoot')` (`rt.systemRoot`); without it, the bare name.
 */
export function system32(root: string | undefined, rel: string, bare: string): string {
  return root ? `${root.replace(/[\\/]+$/, '')}\\System32\\${rel}` : bare
}

/** The interpreter used when the rendered settings name none. */
export function defaultPython(windows: boolean): string[] {
  return windows ? ['py', '-3'] : ['python3']
}
