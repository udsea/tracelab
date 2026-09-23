import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { createInterface } from 'node:readline'
import { resolve } from 'node:path'
import { existsSync } from 'node:fs'
import type { Plugin, ViteDevServer, PreviewServer } from 'vite'

/** Browser development uses the same stdio protocol as Rust. No Python HTTP server. */
export function backendBridge(): Plugin {
  let child: ChildProcessWithoutNullStreams | undefined
  let nextId = 0
  const pending = new Map<
    number,
    {
      resolve: (value: unknown) => void
      reject: (error: Error) => void
      timer: ReturnType<typeof setTimeout>
    }
  >()
  function start() {
    if (child) return child
    const python = resolve('backend/.venv/bin/python')
    if (!existsSync(python))
      throw new Error('Run uv sync --project backend before starting TraceLab.')
    child = spawn(
      python,
      [
        '-m',
        'tracelab',
        '--stdio',
        '--data-dir',
        process.env.TRACELAB_DATA_DIR || resolve('.tracelab'),
      ],
      { env: { ...process.env, PYTHONUNBUFFERED: '1' } },
    )
    child.stderr.on('data', (data) => process.stderr.write(data))
    createInterface({ input: child.stdout }).on('line', (line) => {
      try {
        const response = JSON.parse(line)
        const request = pending.get(response.id)
        if (request) {
          clearTimeout(request.timer)
          request.resolve(response)
          pending.delete(response.id)
        }
      } catch {
        process.stderr.write('Invalid backend protocol message\n')
      }
    })
    child.on('exit', () => {
      for (const request of pending.values()) {
        clearTimeout(request.timer)
        request.reject(
          new Error('Python backend exited. Restart the development server.'),
        )
      }
      pending.clear()
      child = undefined
    })
    return child
  }
  function install(server: ViteDevServer | PreviewServer) {
    // A Tauri window uses Rust IPC; avoid opening the same database from a second process.
    if (process.env.TAURI_ENV_PLATFORM) return
    server.middlewares.use('/api/rpc', async (req, res) => {
      if (req.method !== 'POST') {
        res.statusCode = 405
        res.end()
        return
      }
      const origin = req.headers.origin
      if (
        origin &&
        !['http://127.0.0.1:1420', 'http://localhost:1420'].includes(origin)
      ) {
        res.statusCode = 403
        res.end()
        return
      }
      if (!req.headers['content-type']?.startsWith('application/json')) {
        res.statusCode = 415
        res.end()
        return
      }
      try {
        let body = ''
        for await (const chunk of req) {
          body += chunk
          if (body.length > 4_000_000) throw new Error('Request too large')
        }
        const request = JSON.parse(body)
        const id = ++nextId
        const backend = start()
        const result = await new Promise((resolve, reject) => {
          const timer = setTimeout(() => {
            pending.delete(id)
            reject(new Error('Backend request timed out'))
          }, 120_000)
          pending.set(id, { resolve, reject, timer })
          backend.stdin.write(
            JSON.stringify({
              id,
              method: request.method,
              params: request.params,
            }) + '\n',
          )
        })
        res.setHeader('Content-Type', 'application/json')
        res.end(JSON.stringify(result))
      } catch (error) {
        res.statusCode = 500
        res.end(JSON.stringify({ error: { message: String(error) } }))
      }
    })
    server.httpServer?.on('close', () => {
      child?.stdin.end()
      setTimeout(() => child?.kill(), 2000).unref()
    })
  }
  return {
    name: 'tracelab-backend',
    configureServer: install,
    configurePreviewServer: install,
  }
}
