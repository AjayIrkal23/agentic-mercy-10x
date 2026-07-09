#!/usr/bin/env node
/**
 * Plan Mode Gate — Auto Documentation Lookup
 *
 * Parses package.json dependencies and queries Context7
 * for documentation on each library.
 *
 * Usage: node auto-docs.js [task description]
 * Output: JSON with library IDs and doc snippets
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

function findPackageJsons(cwd) {
  const files = [];
  const rootPkg = path.join(cwd, 'package.json');
  if (fs.existsSync(rootPkg)) files.push(rootPkg);

  const commonDirs = ['client', 'server', 'packages', 'apps'];
  for (const dir of commonDirs) {
    const pkg = path.join(cwd, dir, 'package.json');
    if (fs.existsSync(pkg)) files.push(pkg);
  }

  return files;
}

function extractDeps(pkgPath) {
  try {
    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8'));
    return Object.keys({ ...pkg.dependencies, ...pkg.devDependencies });
  } catch {
    return [];
  }
}

function resolveLibrary(libName, query) {
  try {
    const output = execSync(`jcodemunch-mcp resolve-library-id "${libName}" "${query}" 2>&1`, {
      encoding: 'utf-8',
      timeout: 15000,
      stdio: ['pipe', 'pipe', 'ignore']
    });
    return JSON.parse(output);
  } catch (err) {
    return { error: err.message, libraryName: libName };
  }
}

function queryDocs(libraryId, query) {
  try {
    const output = execSync(`jcodemunch-mcp query-docs "${libraryId}" "${query}" 2>&1`, {
      encoding: 'utf-8',
      timeout: 15000,
      stdio: ['pipe', 'pipe', 'ignore']
    });
    return JSON.parse(output);
  } catch (err) {
    return { error: err.message, libraryId };
  }
}

function main() {
  const cwd = process.cwd();
  const task = process.argv[2] || '';

  const pkgPaths = findPackageJsons(cwd);
  const allDeps = new Set();
  for (const pkgPath of pkgPaths) {
    extractDeps(pkgPath).forEach(d => allDeps.add(d));
  }

  // Filter to likely relevant libraries (skip build tools, linters, types)
  const skipPatterns = [
    /^@types\//, /^eslint/, /^prettier/, /^@eslint/,
    /^vite$/, /^vitest$/, /^jest$/, /^@vitejs/,
    /^tailwindcss$/, /^postcss$/, /^autoprefixer$/,
    /^typescript$/, /^ts-node$/, /^@tsconfig/
  ];

  const relevantDeps = Array.from(allDeps).filter(dep => {
    return !skipPatterns.some(p => p.test(dep));
  });

  const results = [];
  for (const dep of relevantDeps.slice(0, 10)) {
    const resolved = resolveLibrary(dep, task || `usage patterns for ${dep}`);
    if (resolved.libraryId) {
      const docs = queryDocs(resolved.libraryId, task || `common API patterns`);
      results.push({
        name: dep,
        libraryId: resolved.libraryId,
        description: resolved.description,
        docs: docs.results ? docs.results.slice(0, 3) : []
      });
    } else {
      results.push({
        name: dep,
        libraryId: null,
        error: resolved.error || 'Not found in Context7'
      });
    }
  }

  const output = {
    task,
    package_files: pkgPaths,
    total_dependencies: allDeps.size,
    relevant_dependencies: relevantDeps.length,
    libraries: results
  };

  console.log(JSON.stringify(output, null, 2));
}

main();
