/**
 * Production gateway: static Vite build + /api (DeepSeek) + reverse proxy /ecm -> Python (Waitress).
 * Run after `npm run build`. Start Python backend on the same host (see scripts/start-prod.sh or Dockerfile).
 */
import 'dotenv/config'
import express from 'express'
import path from 'path'
import { fileURLToPath } from 'url'
import { createProxyMiddleware } from 'http-proxy-middleware'
import apiRouter from './api.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const app = express()
const PORT = Number(process.env.PORT || 8080)
const HOST = process.env.HOST || '0.0.0.0'
const ECM_BACKEND = process.env.ECM_BACKEND_URL || 'http://127.0.0.1:9000'

app.use(
  '/ecm',
  createProxyMiddleware({
    target: ECM_BACKEND,
    changeOrigin: true,
    // Help SSE/streaming responses pass through proxies without buffering.
    onProxyRes(proxyRes) {
      proxyRes.headers['x-accel-buffering'] = 'no'
    },
  }),
)

app.use(express.json({ limit: '2mb' }))
app.use('/api', apiRouter)

const dist = path.join(__dirname, '..', 'dist')
app.use(express.static(dist))
// Express 5 / path-to-regexp: avoid `app.get('*')` (invalid). SPA fallback for client-side routes.
app.use((req, res, next) => {
  if (req.method !== 'GET' && req.method !== 'HEAD') return next()
  if (req.path.startsWith('/ecm') || req.path.startsWith('/api')) return next()
  res.sendFile(path.join(dist, 'index.html'))
})

app.listen(PORT, HOST, () => {
  // eslint-disable-next-line no-console
  console.log(`ECM gateway listening on http://${HOST}:${PORT}`)
  // eslint-disable-next-line no-console
  console.log(`Proxy /ecm -> ${ECM_BACKEND}`)
})
