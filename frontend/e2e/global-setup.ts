import path from 'path'
import { fileURLToPath } from 'url'
import { execFileSync } from 'child_process'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

export default async () => {
  const backendDir = path.resolve(__dirname, '../../backend')
  const pythonBin = process.env.CAP_PYTHON || 'python'
  if (!process.env.E2E_DATABASE_URL) throw new Error('Set E2E_DATABASE_URL to the disposable test database.')
  execFileSync(pythonBin, ['-m', 'app.seed_e2e'], {
    cwd: backendDir,
    stdio: 'inherit',
    env: { ...process.env, APP_ENV: 'test', CAP_ALLOW_TEST_SEED: '1', DATABASE_URL: process.env.E2E_DATABASE_URL },
  })
}
