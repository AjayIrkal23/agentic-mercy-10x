#!/usr/bin/env node
// gsd-hook-version: 1.42.3
// Context Monitor - PostToolUse hook
// Reads context metrics from the statusline bridge file and injects warnings.

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { sessionId, ctxBridgePath, emitPostContext } = require('./lib/gsd-hook-io');

const WARNING_THRESHOLD = 35;
const CRITICAL_THRESHOLD = 25;
const STALE_SECONDS = 60;
const DEBOUNCE_CALLS = 5;

let input = '';
const stdinTimeout = setTimeout(() => process.exit(0), 10000);
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  clearTimeout(stdinTimeout);
  try {
    const data = JSON.parse(input);
    const sid = sessionId(data);

    if (!sid) {
      process.exit(0);
    }

    if (/[/\\]|\.\./.test(sid)) {
      process.exit(0);
    }

    const cwd = data.cwd || process.cwd();
    const planningDir = path.join(cwd, '.planning');
    if (!fs.existsSync(planningDir)) {
      process.exit(0);
    }
    try {
      const configPath = path.join(planningDir, 'config.json');
      const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      if (config.hooks?.context_warnings === false) {
        process.exit(0);
      }
    } catch (e) {
      // Ignore config read/parse errors
    }

    const metricsPath = ctxBridgePath(sid);

    if (!fs.existsSync(metricsPath)) {
      process.exit(0);
    }

    const metrics = JSON.parse(fs.readFileSync(metricsPath, 'utf8'));
    const now = Math.floor(Date.now() / 1000);

    if (metrics.timestamp && (now - metrics.timestamp) > STALE_SECONDS) {
      process.exit(0);
    }

    const remaining = metrics.remaining_percentage;
    const usedPct = metrics.used_pct;

    if (remaining > WARNING_THRESHOLD) {
      process.exit(0);
    }

    const warnPath = ctxBridgePath(`${sid}-warned`);
    let warnData = { callsSinceWarn: 0, lastLevel: null };
    let firstWarn = true;

    if (fs.existsSync(warnPath)) {
      try {
        warnData = JSON.parse(fs.readFileSync(warnPath, 'utf8'));
        firstWarn = false;
      } catch (e) {
        // Corrupted file, reset
      }
    }

    warnData.callsSinceWarn = (warnData.callsSinceWarn || 0) + 1;

    const isCritical = remaining <= CRITICAL_THRESHOLD;
    const currentLevel = isCritical ? 'critical' : 'warning';

    const severityEscalated = currentLevel === 'critical' && warnData.lastLevel === 'warning';
    if (!firstWarn && warnData.callsSinceWarn < DEBOUNCE_CALLS && !severityEscalated) {
      fs.writeFileSync(warnPath, JSON.stringify(warnData));
      process.exit(0);
    }

    warnData.callsSinceWarn = 0;
    warnData.lastLevel = currentLevel;
    fs.writeFileSync(warnPath, JSON.stringify(warnData));

    const isGsdActive = fs.existsSync(path.join(cwd, '.planning', 'STATE.md'));

    if (isCritical && isGsdActive && !warnData.criticalRecorded) {
      try {
        function findGsdTools(base) {
          for (const dir of ['.claude']) {
            const p = path.join(base, dir, 'get-shit-done', 'bin', 'gsd-tools.cjs');
            if (fs.existsSync(p)) return p;
          }
          return null;
        }
        const gsdTools = findGsdTools(cwd) || findGsdTools(require('os').homedir());
        if (!gsdTools) throw new Error('gsd-tools not found');
        const safeUsedPct = Number(usedPct) || 0;
        const stoppedAt = `context exhaustion at ${safeUsedPct}% (${new Date().toISOString().split('T')[0]})`;
        spawn(
          process.execPath,
          [gsdTools, 'state', 'record-session', '--stopped-at', stoppedAt],
          { cwd, detached: true, stdio: 'ignore' }
        ).unref();
        warnData.criticalRecorded = true;
        fs.writeFileSync(warnPath, JSON.stringify(warnData));
      } catch { /* non-critical */ }
    }

    let message;
    if (isCritical) {
      message = isGsdActive
        ? `CONTEXT CRITICAL: Usage at ${usedPct}%. Remaining: ${remaining}%. ` +
          'Context is nearly exhausted. Do NOT start new complex work or write handoff files — ' +
          'GSD state is already tracked in STATE.md. Inform the user so they can run ' +
          '/gsd:pause-work at the next natural stopping point.'
        : `CONTEXT CRITICAL: Usage at ${usedPct}%. Remaining: ${remaining}%. ` +
          'Context is nearly exhausted. Inform the user that context is low and ask how they ' +
          'want to proceed. Do NOT autonomously save state or write handoff files unless the user asks.';
    } else {
      message = isGsdActive
        ? `CONTEXT WARNING: Usage at ${usedPct}%. Remaining: ${remaining}%. ` +
          'Context is getting limited. Avoid starting new complex work. If not between ' +
          'defined plan steps, inform the user so they can prepare to pause.'
        : `CONTEXT WARNING: Usage at ${usedPct}%. Remaining: ${remaining}%. ` +
          'Be aware that context is getting limited. Avoid unnecessary exploration or ' +
          'starting new complex work.';
    }

    emitPostContext(message);
  } catch (e) {
    process.exit(0);
  }
});
