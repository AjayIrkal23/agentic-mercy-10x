import { describe, expect, test } from 'claude-code/testing'

import { analyze, classifyArgv, commandKey, errorSignature, scriptKind } from '../hooks/lib/commands'
import { realCommand, splitSegments, words } from '../hooks/lib/shell'

const kind = (cmd: string) => analyze(cmd).kinds

describe('shell parsing', () => {
  test('splits on control operators outside quotes', () => {
    expect(splitSegments('cd web && npm test; echo "a && b" | tail -5').map(s => s.text)).toEqual([
      'cd web', 'npm test', 'echo "a && b"', 'tail -5',
    ])
  })
  test('marks a trailing & as background but not redirections', () => {
    expect(splitSegments('npm run dev &')).toEqual([{ text: 'npm run dev', background: true, sep: '&' }])
    expect(splitSegments('make 2>&1 >out.log')).toEqual([{ text: 'make 2>&1 >out.log', background: false, sep: '' }])
  })
  test('words honour quotes', () => {
    expect(words(`git commit -m "fix: a b" --no-verify`)).toEqual(['git', 'commit', '-m', 'fix: a b', '--no-verify'])
  })
  test('realCommand strips env, wrappers and runners', () => {
    expect(realCommand(words('CI=1 timeout 30 npx -y vitest run'))).toEqual(['vitest', 'run'])
    expect(realCommand(words('sudo -u bob env A=1 nohup python3 -u -m pytest -q'))).toEqual(['pytest', '-q'])
    expect(realCommand(words('uv run --frozen ruff check .'))).toEqual(['ruff', 'check', '.'])
    expect(realCommand(words('./node_modules/.bin/eslint src'))).toEqual(['eslint', 'src'])
  })
})

describe('classification', () => {
  test('package-manager scripts', () => {
    expect(kind('npm test')).toEqual(['test'])
    expect(kind('pnpm run test:unit')).toEqual(['test'])
    expect(kind('yarn lint')).toEqual(['lint'])
    expect(kind('pnpm typecheck')).toEqual(['typecheck'])
    expect(kind('npm run build')).toEqual(['build'])
    expect(kind('npm ci')).toEqual(['install'])
    expect(kind('yarn')).toEqual(['install'])
    expect(kind('bun test')).toEqual(['test'])
  })
  test('servers and watchers', () => {
    for (const cmd of ['npm run dev', 'pnpm dev', 'npm start', 'yarn preview', 'vite', 'vite --port 5173', 'next dev',
      'uvicorn app:app --reload', 'python manage.py runserver', 'python3 -m http.server 8000', 'flask run',
      'docker compose up -d', 'nodemon server.js', 'rails s', 'php artisan serve', 'npx serve dist']) {
      expect(analyze(cmd).isServer, cmd).toBe(true)
    }
    for (const cmd of ['tsc -w', 'jest --watch', 'vitest watch', 'npm run test -- --watch', 'cargo watch -x test', 'tsx watch src/index.ts',
      'jest --watchAll=true', 'npm test -- --watch', 'npm run test -- --watchAll=true', 'node --watch-path=src server.js', 'node --test --watch']) {
      expect(analyze(cmd).isWatch, cmd).toBe(true)
    }
    for (const cmd of ['npx ng test --watch=false', 'vitest --watch=false', 'jest --watchAll=0', 'npm test -- --watch=false',
      'jest --watchAll false', 'npx ng test --watch false']) {
      expect(analyze(cmd).isWatch, cmd).toBe(false)
    }
  })
  test('builds are not servers', () => {
    expect(kind('vite build')).toEqual(['build'])
    expect(kind('next build')).toEqual(['build'])
    expect(kind('tsc -p .')).toEqual(['build'])
    expect(kind('tsc --noEmit')).toEqual(['typecheck'])
    expect(kind('go build ./...')).toEqual(['build'])
    expect(kind('docker build -t x .')).toEqual(['build'])
  })
  test('direct tools', () => {
    expect(kind('pytest -q tests/')).toEqual(['test'])
    expect(kind('go test ./... -race')).toEqual(['test'])
    expect(kind('go vet ./...')).toEqual(['typecheck'])
    expect(kind('cargo clippy')).toEqual(['lint'])
    expect(kind('ruff format .')).toEqual(['format'])
    expect(kind('ruff check .')).toEqual(['lint'])
    expect(kind('npx playwright test')).toEqual(['test'])
    expect(kind('make')).toEqual(['build'])
    expect(kind('make test')).toEqual(['test'])
  })
  test('git', () => {
    expect(analyze('git add -A && git commit -m "x"').isCommit).toBe(true)
    expect(analyze('git -C repo push origin main').isPush).toBe(true)
    expect(kind('git status')).toEqual(['git'])
  })
  test('text that merely mentions a server is not one', () => {
    expect(analyze('grep "npm run dev" README.md').isServer).toBe(false)
    expect(analyze('echo vite').isServer).toBe(false)
    expect(analyze('cat package.json | grep dev').isServer).toBe(false)
  })
  test('background flag flows into segments', () => {
    expect(analyze('npm run dev &').segments[0]?.background).toBe(true)
    expect(analyze('vite', true).segments[0]?.background).toBe(true)
  })
  test('verify kinds', () => {
    expect(analyze('pnpm lint && pnpm test && pnpm build').verify).toEqual(['lint', 'test', 'build'])
  })
  test('a backgrounded run is no verification evidence', () => {
    expect(analyze('npm test', true).verify).toEqual([])
    expect(analyze('npm test &').verify).toEqual([])
    expect(analyze('pnpm lint && pnpm test &').verify).toEqual([])
  })
  test('scriptKind conventions', () => {
    expect(scriptKind('test:e2e')).toBe('test')
    expect(scriptKind('dev:api')).toBe('server')
    expect(scriptKind('build:watch')).toBe('watch')
    expect(scriptKind('check')).toBe('typecheck')
    expect(scriptKind('postinstall')).toBe('other')
  })
  test('classifyArgv on empty input', () => {
    expect(classifyArgv([])).toBe('other')
  })
})

describe('audit 2026-10-05', () => {
  test('package-manager directory options do not hide the script (H-01)', () => {
    expect(analyze('npm --prefix server run dev-http').isServer).toBe(true)
    expect(analyze('pnpm -C web dev').isServer).toBe(true)
    expect(analyze('yarn --cwd web start').isServer).toBe(true)
    expect(analyze('npm -w server run dev').isServer).toBe(true)
    expect(analyze('pnpm --filter web dev').isServer).toBe(true)
    expect(analyze('npm --prefix server run test:watch').isWatch).toBe(true)
    expect(kind('npm --prefix server run build')).toEqual(['build'])
    expect(kind('npm --prefix=server test')).toEqual(['test'])
  })
  test('bare vitest watches unless told not to (H-03)', () => {
    for (const cmd of ['vitest', 'npx vitest src/x.test.ts', 'vitest --coverage']) {
      expect(analyze(cmd).isWatch, cmd).toBe(true)
    }
    for (const cmd of ['vitest run', 'npx vitest run src/x.test.ts', 'vitest --run', 'CI=1 vitest', 'vitest --watch=false']) {
      expect(analyze(cmd).isWatch, cmd).toBe(false)
      expect(analyze(cmd).verify, cmd).toEqual(['test'])
    }
  })
  test('a masked exit status is no evidence (H-02)', () => {
    expect(analyze('npm test 2>&1 | tail -20').verify).toEqual([])
    expect(analyze('npm run build; echo done').verify).toEqual([])
    expect(analyze('npm test || true').verify).toEqual([])
    expect(analyze('set -o pipefail; npm test 2>&1 | tail -20').verify).toEqual(['test'])
    expect(analyze('cd server && npm test').verify).toEqual(['test'])
    expect(analyze('npm run lint && npm test').verify).toEqual(['lint', 'test'])
  })
})

describe('keys and signatures', () => {
  test('commandKey folds plumbing', () => {
    expect(commandKey('npm   test 2>&1 | tail -40')).toBe('npm test')
  })
  test('errorSignature picks the error line and folds timings', () => {
    const out = 'running 12 tests\nok a\nFAILED tests/x.py::test_y - AssertionError (0.31s)\n2 failed'
    expect(errorSignature(out)).toBe('FAILED tests/x.py::test_y - AssertionError (#)')
  })
})
