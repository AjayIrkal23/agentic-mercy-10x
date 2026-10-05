// Pure: what a language toolchain or framework CLI subcommand does (go, cargo, make,
// vite, next, docker compose, ...). Split out of commands.ts to keep both under 250 lines.

import type { CommandKind } from '../../types'

const FRAMEWORK_CLI = new Set(['vite', 'astro', 'nuxt', 'nuxi', 'remix'])

export function toolchain(t0: string, t1: string): CommandKind | undefined {
  if (t0 === 'go') {
    const go: Record<string, CommandKind> = { test: 'test', vet: 'typecheck', build: 'build', install: 'build', fmt: 'format', mod: 'install', get: 'install' }
    return go[t1] ?? 'other'
  }
  if (t0 === 'cargo') {
    const cargo: Record<string, CommandKind> = { test: 'test', nextest: 'test', check: 'typecheck', clippy: 'lint', fmt: 'format', build: 'build', watch: 'watch', add: 'install', fetch: 'install' }
    return cargo[t1] ?? 'other'
  }
  if (t0 === 'deno') {
    const deno: Record<string, CommandKind> = { test: 'test', check: 'typecheck', lint: 'lint', fmt: 'format' }
    return deno[t1] ?? 'other'
  }
  if (t0 === 'make' || t0 === 'just') {
    if (/^(test|tests|check|tdd|ci|verify)$/.test(t1)) return 'test'
    if (/^(lint|vet)$/.test(t1)) return 'lint'
    if (/^(fmt|format)$/.test(t1)) return 'format'
    if (/^(dev|run|serve|start|up)$/.test(t1)) return 'server'
    return t1 === '' || /^(build|all|dist|compile)$/.test(t1) ? 'build' : 'other'
  }
  if (t0 === 'mvn' || t0 === 'gradle' || t0 === 'gradlew' || t0 === 'dotnet') {
    if (t1 === 'test') return 'test'
    if (/^(package|install|compile|build|assemble)$/.test(t1)) return 'build'
    if (t1 === 'run' || t1 === 'bootRun') return 'server'
    return 'other'
  }
  return undefined
}

export function frameworkCli(t0: string, t1: string, a: readonly string[]): CommandKind | undefined {
  if (FRAMEWORK_CLI.has(t0)) return t1 === 'build' || t1 === 'generate' ? 'build' : t1 === 'check' ? 'typecheck' : 'server'
  if (t0 === 'next') return t1 === 'build' ? 'build' : t1 === 'lint' ? 'lint' : t1 === 'dev' || t1 === 'start' ? 'server' : 'other'
  if (t0 === 'webpack') return t1 === 'serve' ? 'server' : 'build'
  if (t0 === 'ng') return ({ serve: 'server', build: 'build', test: 'test', lint: 'lint' } as Record<string, CommandKind>)[t1] ?? 'other'
  if (t0 === 'storybook') return t1 === 'build' ? 'build' : 'server'
  if (t0 === 'expo' || t0 === 'react-native') return t1 === 'start' ? 'server' : 'other'
  if ((t0 === 'flask' && t1 === 'run') || (t0 === 'rails' && (t1 === 's' || t1 === 'server'))) return 'server'
  if (t0 === 'php' && (t1 === '-S' || (t1 === 'artisan' && a[2] === 'serve'))) return 'server'
  if (/^python(\d(\.\d+)?)?$/.test(t0) && t1 === 'manage.py' && a[2] === 'runserver') return 'server'
  if ((t0 === 'hugo' && t1 === 'server') || ((t0 === 'mkdocs' || t0 === 'jekyll') && t1 === 'serve')) return 'server'
  if (t0 === 'pm2' && t1 === 'start') return 'server'
  if ((t0 === 'docker' && t1 === 'compose' && a[2] === 'up') || (t0 === 'docker-compose' && t1 === 'up')) return 'server'
  if (t0 === 'docker' && (t1 === 'build' || (t1 === 'buildx' && a[2] === 'build'))) return 'build'
  return undefined
}
