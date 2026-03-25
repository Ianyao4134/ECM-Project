import 'dotenv/config'
import express from 'express'
import cors from 'cors'
import apiRouter from './api.js'

const app = express()
app.use(cors())
app.use(express.json({ limit: '2mb' }))
app.use('/api', apiRouter)

const PORT = Number(process.env.PORT || 8787)

app.listen(PORT, () => {
  // eslint-disable-next-line no-console
  console.log(`API server listening on http://localhost:${PORT}`)
})
