// Pure path classification: code vs test vs doc vs generated, and display helpers.

const CODE_EXT = new Set([
  'ts', 'tsx', 'js', 'jsx', 'mjs', 'cjs', 'mts', 'cts', 'py', 'go', 'rs', 'java', 'kt', 'kts', 'rb', 'php',
  'cs', 'swift', 'vue', 'svelte', 'astro', 'sql', 'c', 'cc', 'cpp', 'h', 'hpp', 'scala', 'dart', 'lua',
  'sh', 'bash', 'zsh', 'ps1', 'ex', 'exs', 'erl', 'clj', 'graphql', 'gql', 'prisma', 'proto',
])
const DOC_EXT = new Set(['md', 'mdx', 'markdown', 'rst', 'adoc', 'txt'])
const GENERATED = /(^|[\\/])(node_modules|dist|build|out|coverage|\.next|\.nuxt|\.svelte-kit|vendor|__pycache__|\.venv|venv|target|\.turbo|\.cache)([\\/]|$)/

export function extension(path: string): string {
  const name = path.split(/[\\/]/).pop() ?? ''
  const dot = name.lastIndexOf('.')
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : ''
}

export function isGenerated(path: string): boolean {
  return GENERATED.test(path)
}

export function isCode(path: string): boolean {
  return CODE_EXT.has(extension(path)) && !isGenerated(path)
}

export function isDoc(path: string): boolean {
  return DOC_EXT.has(extension(path))
}

export function isTest(path: string): boolean {
  return /(\.|_)(test|spec)\.[a-z]+$|_test\.go$|(^|[\\/])test_[^\\/]+\.py$|(^|[\\/])(tests?|__tests__|spec)[\\/]/i.test(path)
}

/** `/a/b/c/d.ts` → `c/d.ts`: enough to recognise a file in a narrow pane. */
export function shortPath(path: string, keep = 2): string {
  const parts = path.split(/[\\/]/).filter(Boolean)
  return parts.length <= keep ? parts.join('/') : `…/${parts.slice(-keep).join('/')}`
}

/** Path relative to root when inside it, else the path as given. */
export function relativeTo(root: string, path: string): string {
  const r = root.replace(/[\\/]+$/, '')
  return path.startsWith(`${r}/`) || path.startsWith(`${r}\\`) ? path.slice(r.length + 1) : path
}

/** The file a write tool targets, whatever its input spelling. */
export function targetPath(input: Record<string, unknown>): string | undefined {
  const v = input['file_path'] ?? input['notebook_path'] ?? input['path']
  return typeof v === 'string' && v ? v : undefined
}

export const WRITE_TOOLS: ReadonlySet<string> = new Set(['Write', 'Edit', 'MultiEdit', 'NotebookEdit'])

/** Joins with the separator the directory already uses (Windows paths keep backslashes). */
export function join(dir: string, name: string): string {
  const sep = dir.includes('\\') && !dir.includes('/') ? '\\' : '/'
  return `${dir.replace(/[\\/]+$/, '')}${sep}${name}`
}

/** The directory part of a path, or '' at a root. */
export function dirname(path: string): string {
  const cut = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'))
  return cut > 0 ? path.slice(0, cut) : ''
}
