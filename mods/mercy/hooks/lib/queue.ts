// Pure job queues for background Python runs. Two lanes: `fast` (post-write advisories,
// ~100 ms each, write state the Stop gates read, so they run in order and are drained
// before the next Python chain and before Stop) and `slow` (tdd-guard, seconds each,
// coalesced per file so a burst of edits costs one validation per file).

export type Lane = 'fast' | 'slow'

export type Job = {
  lane: Lane
  event: 'pre-tool-use' | 'post-tool-use'
  ids: string[]
  payload: string
  /** Same key in the slow lane replaces the queued job (latest edit per file wins). */
  key: string
  queuedAt: number
  /** The subagent loop the call ran in; its advisory is not delivered to the main loop (NEW-08). */
  agentId?: string
}

type LaneState = { jobs: Job[]; running: boolean; waiters: Array<() => void> }

const lanes: Record<Lane, LaneState> = {
  fast: { jobs: [], running: false, waiters: [] },
  slow: { jobs: [], running: false, waiters: [] },
}

export function enqueue(job: Job): void {
  const lane = lanes[job.lane]
  if (job.lane === 'slow') {
    const at = lane.jobs.findIndex(j => j.key === job.key)
    if (at >= 0) {
      lane.jobs[at] = job
      return
    }
  }
  lane.jobs.push(job)
}

/** Takes the next job of a lane and marks it running; undefined when idle. */
export function take(lane: Lane): Job | undefined {
  const s = lanes[lane]
  if (s.running) return undefined
  const job = s.jobs.shift()
  if (job) s.running = true
  return job
}

/** Marks the lane's running job done and wakes waiters when the lane is empty. */
export function done(lane: Lane): void {
  const s = lanes[lane]
  s.running = false
  if (s.jobs.length === 0) {
    const waiters = s.waiters.splice(0)
    for (const w of waiters) w()
  }
}

export function busy(lane: Lane): boolean {
  const s = lanes[lane]
  return s.running || s.jobs.length > 0
}

export function size(): number {
  return lanes.fast.jobs.length + lanes.slow.jobs.length + Number(lanes.fast.running) + Number(lanes.slow.running)
}

/** Resolves once the lane is empty and idle (at once when it already is). */
export function idle(lane: Lane): Promise<void> {
  if (!busy(lane)) return Promise.resolve()
  return new Promise(resolve => lanes[lane].waiters.push(resolve))
}
