/**
 * Start Flask ECM backend on 127.0.0.1:9000 for local `npm run dev` (Vite proxies /ecm here).
 * Uses project .venv if present; otherwise prints setup instructions and exits 1.
 */
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
process.chdir(root)

function venvPython() {
  const win = path.join(root, '.venv', 'Scripts', 'python.exe')
  if (fs.existsSync(win)) return win
  const unix = path.join(root, '.venv', 'bin', 'python3')
  if (fs.existsSync(unix)) return unix
  const unix2 = path.join(root, '.venv', 'bin', 'python')
  if (fs.existsSync(unix2)) return unix2
  return null
}

const py = venvPython()
if (!py) {
  console.error(
    '[ecm] No .venv found. From project root run:\n' +
      '  py -3.11 -m venv .venv\n' +
      '  .venv\\Scripts\\pip install -r requirements.txt   (Windows)\n' +
      'Or run start_ecm_backend.bat once to create the venv.',
  )
  process.exit(1)
}

const code = [
  'from waitress import serve',
  'from app.main import app',
  "serve(app, listen='127.0.0.1:9000')",
].join('; ')

const child = spawn(py, ['-c', code], {
  cwd: root,
  stdio: 'inherit',
  env: { ...process.env, PYTHONUNBUFFERED: '1' },
})

child.on('exit', (c, signal) => {
  if (signal) process.kill(process.pid, signal)
  process.exit(c ?? 1)
})
