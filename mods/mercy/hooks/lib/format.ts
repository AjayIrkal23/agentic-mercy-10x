// Pure display helpers shared by the status line, band, pane and tool answers.

export function duration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '?'
  if (ms < 1000) return `${Math.round(ms)}ms`
  const s = ms / 1000
  if (s < 60) return `${s < 10 ? s.toFixed(1) : Math.round(s)}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m${String(Math.round(s % 60)).padStart(2, '0')}s`
  return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}m`
}

export function ago(now: number, then: number | undefined): string {
  if (!then) return 'never'
  return `${duration(Math.max(0, now - then))} ago`
}

export function compact(n: number): string {
  if (!Number.isFinite(n)) return '?'
  if (Math.abs(n) < 1000) return String(Math.round(n))
  if (Math.abs(n) < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`
  return `${(n / 1_000_000).toFixed(1)}M`
}

export function usd(n: number | undefined): string {
  return n === undefined ? '' : `$${n < 10 ? n.toFixed(2) : n.toFixed(1)}`
}

/** A fixed-width meter like `▰▰▰▱▱` for a 0..100 value. */
export function meter(percent: number, width = 10): string {
  const p = Math.max(0, Math.min(100, percent))
  const full = Math.round((p / 100) * width)
  return '▰'.repeat(full) + '▱'.repeat(width - full)
}

export function clip(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, Math.max(0, max - 1))}…`
}
