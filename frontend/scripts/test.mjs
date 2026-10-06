import { spawnSync } from 'node:child_process'

// jsdom owns browser storage in tests. Node 24's experimental global storage
// otherwise shadows it when Vitest 2 installs the window globals.
const flags = Number(process.versions.node.split('.')[0]) >= 24
  ? ['--no-experimental-webstorage'] : []
const result = spawnSync(process.execPath, [
  ...flags, 'node_modules/vitest/vitest.mjs', ...process.argv.slice(2),
], { stdio: 'inherit', env: { ...process.env, NODE_OPTIONS: [process.env.NODE_OPTIONS || '', ...flags].join(' ') } })
process.exit(result.status ?? 1)
