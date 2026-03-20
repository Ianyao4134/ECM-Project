import 'dotenv/config'
import express from 'express'
import cors from 'cors'

const app = express()
app.use(cors())
app.use(express.json({ limit: '2mb' }))

const PORT = Number(process.env.PORT || 8787)
const DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY
const GLOBAL_RELIABILITY_INSTRUCTION =
  '在回答之前，请确保使用了最新的、政府认同的、官方网站等真实可靠的信息来源，请过滤掉所有不相关或低质量的内容，同时自我审查，避免任何错误、偏见或未经官方查实的信息， 请确保你得出的结论有用、有效且明确，不说一句废话。'

app.get('/api/health', (_req, res) => {
  res.json({ ok: true })
})

app.post('/api/chat', async (req, res) => {
  try {
    if (!DEEPSEEK_API_KEY) {
      return res.status(500).json({
        error: 'Missing DEEPSEEK_API_KEY. Create a .env file and set it.',
      })
    }

    const {
      model = 'deepseek-chat',
      messages,
      temperature,
      max_tokens,
      top_p,
      stream = false,
    } = req.body ?? {}

    if (!Array.isArray(messages) || messages.length === 0) {
      return res.status(400).json({ error: 'messages must be a non-empty array' })
    }
    if (stream) {
      return res.status(400).json({ error: 'stream is not supported in this MVP' })
    }

    const mergedMessages = [
      { role: 'system', content: GLOBAL_RELIABILITY_INSTRUCTION },
      ...messages,
    ]

    const upstream = await fetch('https://api.deepseek.com/chat/completions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${DEEPSEEK_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model,
        messages: mergedMessages,
        temperature,
        max_tokens,
        top_p,
        stream: false,
      }),
    })

    const data = await upstream.json().catch(() => null)
    if (!upstream.ok) {
      return res.status(upstream.status).json({
        error: 'DeepSeek upstream error',
        status: upstream.status,
        details: data,
      })
    }

    const choice = data?.choices?.[0]
    const content = choice?.message?.content ?? ''

    // Note: Some DeepSeek models may return reasoning fields. We intentionally do not
    // forward any hidden reasoning to the UI; only the assistant's final content.
    return res.json({
      id: data?.id,
      model: data?.model,
      created: data?.created,
      content,
      usage: data?.usage,
    })
  } catch (err) {
    return res.status(500).json({
      error: 'Server error',
      message: err instanceof Error ? err.message : String(err),
    })
  }
})

app.listen(PORT, () => {
  // eslint-disable-next-line no-console
  console.log(`API server listening on http://localhost:${PORT}`)
})

