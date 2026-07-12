#!/usr/bin/env node
'use strict';
/**
 * gsd-check-update-launcher.js — 7-day-TTL activation of the GSD update check (P6-T4).
 *
 * The GSD update check (gsd-check-update.js -> gsd-check-update-worker.js) runs
 * `npm view get-shit-done-cc version` with NO internal throttle, so it must be
 * rate-limited from outside. This launcher (NOT a GSD-managed file — the upstream
 * files stay byte-intact) is wired as a SessionStart link and:
 *
 *   1. spawns the update check at most once per 7 days (cache-age TTL gate);
 *   2. surfaces a one-line advisory when the cached result reports an available
 *      update or stale hooks (the statusline already shows this; the advisory
 *      makes it visible in session context too).
 *
 * Fail-open: any error -> exit 0, no output. Windows+POSIX (detached spawn).
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn } = require('child_process');

const TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days
const CACHE_FILE = path.join(os.homedir(), '.cache', 'gsd', 'gsd-update-check.json');

function readCache() {
  try {
    return JSON.parse(fs.readFileSync(CACHE_FILE, 'utf8'));
  } catch {
    return null;
  }
}

function ageMs(cache) {
  if (!cache || typeof cache.checked !== 'number') return Infinity;
  return Date.now() - cache.checked * 1000;
}

function triggerRefresh() {
  try {
    const script = path.join(__dirname, 'gsd-check-update.js');
    if (!fs.existsSync(script)) return;
    const child = spawn(process.execPath, [script], {
      stdio: 'ignore',
      windowsHide: true,
      detached: true,
    });
    child.unref();
  } catch {
    /* fail-open */
  }
}

try {
  const cache = readCache();
  // 7-day TTL gate: only spawn the (npm-hitting) worker if the cache is stale.
  if (ageMs(cache) > TTL_MS) {
    triggerRefresh();
  }
  // Surface a concise advisory from whatever the cache currently holds.
  if (cache) {
    const parts = [];
    if (cache.update_available && cache.latest && cache.latest !== 'unknown') {
      parts.push(
        `GSD update available: ${cache.installed || '?'} -> ${cache.latest} (npm i -g get-shit-done-cc)`
      );
    }
    if (Array.isArray(cache.stale_hooks) && cache.stale_hooks.length > 0) {
      parts.push(`${cache.stale_hooks.length} stale GSD hook(s) — run /gsd-update`);
    }
    if (parts.length) process.stdout.write(parts.join(' | '));
  }
} catch {
  /* fail-open */
}
process.exit(0);
