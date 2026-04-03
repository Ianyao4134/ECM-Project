import { useEffect, useMemo, useRef, useState } from 'react'
// Markdown 渲染用于 Function 4 / 5 报告
// 需要在项目中安装依赖：npm install react-markdown
import ReactMarkdown from 'react-markdown'
import './App.css'

type Role = 'user' | 'assistant'
type ChatMessage = {
  role: Role
  content: string
  ts?: number
  nodeId?: string
  parentId?: string | null
  depth?: number
  action?: 'submit' | 'followup'
}
type Module2Meta = { tags: string[]; quote: string | null; hook: string | null }

type FunctionKey = 'f1' | 'f2' | 'f4' | 'f5'
type DialogueListItem = { id: string; name: string; updatedAt?: number }

function App() {
  const f1Greeting =
    'ECM探索导师\n你好，我是你的 ECM 深度探索导师。请告诉我，你想探讨的主题是什么？（越具体越好，如果模糊也没关系，我会帮你理清）'
  const functionCards = useMemo(
    () => [
      {
        key: 'f1' as const,
        title: 'Function 1 — 问题定义',
        placeholder: '描述你想探索的主题…（Ctrl+Enter 发送）',
      },
      {
        key: 'f2' as const,
        title: 'Function 2 — 探索',
        placeholder: '输入你想进一步探索的问题…（Ctrl+Enter 发送）',
      },
      {
        key: 'f3' as const,
        title: 'Function 3 — 笔记（可编辑）',
      },
      {
        key: 'f4' as const,
        title: 'Function 4 — 洞察',
        placeholder: '输入你想提炼的洞察方向…（Ctrl+Enter 发送）',
      },
      {
        key: 'f5' as const,
        title: 'Function 5 — 灵感',
        placeholder: '输入你想要的灵感/下一步…（Ctrl+Enter 发送）',
      },
    ],
    [],
  )

  const [chats, setChats] = useState<Record<FunctionKey, ChatMessage[]>>(() => ({
    f1: [],
    f2: [],
    f4: [],
    f5: [],
  }))

  const [inputs, setInputs] = useState<Record<FunctionKey, string>>(() => ({
    f1: '',
    f2: '',
    f4: '',
    f5: '',
  }))

  const [sendingKey, setSendingKey] = useState<FunctionKey | null>(null)
  const [errors, setErrors] = useState<Record<FunctionKey, string | null>>(() => ({
    f1: null,
    f2: null,
    f4: null,
    f5: null,
  }))

  // Function 3 笔记：不再使用 localStorage，避免跨项目/跨登录残留
  const [noteText, setNoteText] = useState('')
  const [module1SessionId, setModule1SessionId] = useState<string | null>(null)
  const [module1AwaitingConfirm, setModule1AwaitingConfirm] = useState(false)
  const [module1Step, setModule1Step] = useState<number | null>(null)
  const [module1Definition, setModule1Definition] = useState<string | null>(null)
  const [module1TotalSteps, setModule1TotalSteps] = useState<number>(5)

  const [module2SessionId, setModule2SessionId] = useState<string | null>(null)
  const [module2Step, setModule2Step] = useState<number | null>(null)
  const [module2TotalSteps, setModule2TotalSteps] = useState<number>(5)
  const [module2LastExtractSig, setModule2LastExtractSig] = useState<string | null>(null)
  const [module2DisplayStep, setModule2DisplayStep] = useState<number | null>(null)
  const [module2RootNodeId, setModule2RootNodeId] = useState<string | null>(null)
  const [module2MainNodeId, setModule2MainNodeId] = useState<string | null>(null)

  const [module4SessionId, setModule4SessionId] = useState<string | null>(null)
  const [module4AwaitingConfirm, setModule4AwaitingConfirm] = useState(false)

  // 各 Function 的“确认/完成”状态（可持久化到项目）
  const [f1Confirmed, setF1Confirmed] = useState(false)
  const [f2Finished, setF2Finished] = useState(false)
  const [f4Confirmed, setF4Confirmed] = useState(false)
  const [f5Done, setF5Done] = useState(false)

  // Use refs to ensure auto-save persists the latest streamed content.
  const chatsRef = useRef(chats)
  const noteTextRef = useRef(noteText)
  const module1DefinitionRef = useRef(module1Definition)
  const flagsRef = useRef({ f1Confirmed, f2Finished, f4Confirmed, f5Done })

  const moduleProgressRef = useRef({
    module1SessionId,
    module1AwaitingConfirm,
    module1Step,
    module1TotalSteps,
    module2SessionId,
    module2Step,
    module2TotalSteps,
    module2LastExtractSig,
    module2DisplayStep,
    module2RootNodeId,
    module2MainNodeId,
    module4SessionId,
    module4AwaitingConfirm,
  })

  const f1TimingRef = useRef({
    enteredAt: 0,
    leftAt: 0,
    lastAiDoneAt: 0,
    thinkingTotalMs: 0,
    thinkingCount: 0,
    aiTotalMs: 0,
    aiCount: 0,
  })
  const f3MetricsRef = useRef({
    userEditCount: 0,
    simTotal: 0,
    simCount: 0,
    depthTotal: 0,
    depthCount: 0,
  })
  const f3PersistTimerRef = useRef<number | null>(null)

  const f2TimingRef = useRef({
    enteredAt: 0,
    leftAt: 0,
    lastAiDoneAt: 0,
    thinkingTotalMs: 0,
    thinkingCount: 0,
    aiTotalMs: 0,
    aiCount: 0,
  })

  const f4TimingRef = useRef({
    enteredAt: 0,
    leftAt: 0,
    reportGenCount: 0,
    downloadCount: 0,
  })

  // Store the latest generated Function 4 report markdown.
  // This is used for mentor analytics to avoid being polluted by later follow-up Q&A.
  const module4ReportTextRef = useRef<string>('')

  const persistF4Analytics = async (reportTextOverride?: string) => {
    if (!currentUser?.id || !currentProjectId || !currentDialogueId) return
    const now = Date.now()
    const enteredAt = f4TimingRef.current.enteredAt || now
    const leftAt = f4TimingRef.current.leftAt || now
    const dwellSeconds = Math.max(0, (leftAt - enteredAt) / 1000)
    const lastAssistant =
      (chatsRef.current.f4 ?? [])
        .slice()
        .reverse()
        .find((m) => m.role === 'assistant' && (m.content ?? '').trim())?.content ?? ''
    const reportText =
      reportTextOverride ??
      (module4ReportTextRef.current ?? '').trim() ??
      lastAssistant ??
      ''
    const metrics = {
      module_dwell_seconds: dwellSeconds,
      report_modification_count: f4TimingRef.current.reportGenCount || 0,
      download_count: f4TimingRef.current.downloadCount || 0,
    }
    // Flush React state before reading chats for report text.
    await new Promise((r) => {
      if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => r(true))
      else setTimeout(() => r(true), 0)
    })
    await fetch('/ecm/analytics/f4/upsert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: currentDialogueId,
        user_id: currentUser.id,
        project_id: currentProjectId,
        dialogue_id: currentDialogueId,
        report_text: reportText,
        metrics,
      }),
    }).catch(() => null)
  }

  const buildF2MetricsSnapshot = (history: ChatMessage[]) => {
    const userMsgs = history.filter((m) => m.role === 'user')
    const aiMsgs = history.filter((m) => m.role === 'assistant')
    const userLens = userMsgs.map((m) => (m.content || '').length)
    const aiLens = aiMsgs.map((m) => (m.content || '').length)
    const avg = (arr: number[]) => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0)
    const qWord = /(吗|么|为何|为什么|如何|怎么|怎样|是否|能否|可否|？|\?)/g
    const confirmWord = /(确认|是的|对|没错|好的|好|ok|OK|行)/g
    const optionWord = /\b([ABC])\b|(^|\s)([ABC])($|\s)|^[ABC]$|[A-C][+＋][1-9]/g

    let askCount = 0
    let confirmCount = 0
    let optionCount = 0
    let copyLikeCount = 0
    for (let i = 0; i < history.length; i++) {
      const m = history[i]
      if (m.role !== 'user') continue
      const t = m.content || ''
      if ((t.match(qWord) || []).length > 0) askCount += 1
      if ((t.match(confirmWord) || []).length > 0) confirmCount += 1
      if ((t.match(optionWord) || []).length > 0) optionCount += 1
      const prevAi = history
        .slice(0, i)
        .reverse()
        .find((x) => x.role === 'assistant' && (x.content || '').trim())
      if (prevAi) {
        const a = (prevAi.content || '').trim()
        const u = (t || '').trim()
        if (u && a && (a.includes(u) || u.includes(a)) && (u.length >= 12 || a.length >= 12)) copyLikeCount += 1
      }
    }

    const now = Date.now()
    const enteredAt = f2TimingRef.current.enteredAt || now
    const leftAt = f2TimingRef.current.leftAt || now
    const dwellSeconds = Math.max(0, (leftAt - enteredAt) / 1000)

    const thinkingAvg = f2TimingRef.current.thinkingCount > 0 ? f2TimingRef.current.thinkingTotalMs / f2TimingRef.current.thinkingCount / 1000 : 0
    const aiRespAvg = f2TimingRef.current.aiCount > 0 ? f2TimingRef.current.aiTotalMs / f2TimingRef.current.aiCount / 1000 : 0

    return {
      avg_user_msg_length: avg(userLens),
      avg_ai_msg_length: avg(aiLens),
      user_question_count: askCount,
      user_confirm_count: confirmCount,
      user_copy_example_count: copyLikeCount,
      user_option_select_count: optionCount,
      module_dwell_seconds: dwellSeconds,
      thinking_seconds_avg: thinkingAvg,
      ai_response_seconds_avg: aiRespAvg,
      turn_count: history.length,
    }
  }

  const persistF2Analytics = async (historyOverride?: ChatMessage[]) => {
    if (!currentUser?.id || !currentProjectId || !currentDialogueId) return
    // Let React finish updating `chatsRef` so we persist the latest assistant/user content.
    await new Promise((r) => {
      if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => r(true))
      else setTimeout(() => r(true), 0)
    })
    const hist = historyOverride ?? chatsRef.current.f2 ?? []
    const history = hist.map((m) => ({
      role: m.role,
      content: m.content,
      action: m.action ?? null,
      timestamp: typeof m.ts === 'number' ? m.ts : null,
      parentId: m.parentId ?? null,
      depth: typeof m.depth === 'number' ? m.depth : null,
    }))
    const metrics = buildF2MetricsSnapshot(hist)
    await fetch('/ecm/analytics/f2/upsert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: currentDialogueId,
        user_id: currentUser.id,
        project_id: currentProjectId,
        dialogue_id: currentDialogueId,
        history,
        metrics,
      }),
    }).catch(() => null)
  }

  const f5TimingRef = useRef({
    enteredAt: 0,
    leftAt: 0,
    userEditCount: 0,
    clickCount: 0,
    newCount: 0,
  })

  const persistF5Analytics = async () => {
    if (!currentUser?.id || !currentProjectId || !currentDialogueId) return
    const now = Date.now()
    const enteredAt = f5TimingRef.current.enteredAt || now
    const leftAt = f5TimingRef.current.leftAt || now
    const dwellSeconds = Math.max(0, (leftAt - enteredAt) / 1000)
    await new Promise((r) => {
      if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => r(true))
      else setTimeout(() => r(true), 0)
    })
    const lastAssistant =
      (chatsRef.current.f5 ?? [])
        .slice()
        .reverse()
        .find((m) => m.role === 'assistant' && (m.content ?? '').trim())?.content ?? ''
    const aiReviewText = lastAssistant
    const finalNoteText = lastAssistant
    const noteCharCount = (finalNoteText ?? '').length
    const metrics = {
      note_edit_count: f5TimingRef.current.userEditCount || 0,
      note_char_count: noteCharCount,
      module_dwell_seconds: dwellSeconds,
      click_count: f5TimingRef.current.clickCount || 0,
      new_count: f5TimingRef.current.newCount || 0,
    }
    await fetch('/ecm/analytics/f5/upsert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: currentDialogueId,
        user_id: currentUser.id,
        project_id: currentProjectId,
        dialogue_id: currentDialogueId,
        ai_review_text: aiReviewText,
        final_note_text: finalNoteText,
        metrics,
      }),
    }).catch(() => null)
  }

  useEffect(() => {
    chatsRef.current = chats
  }, [chats])
  useEffect(() => {
    noteTextRef.current = noteText
  }, [noteText])
  useEffect(() => {
    module1DefinitionRef.current = module1Definition
  }, [module1Definition])
  useEffect(() => {
    flagsRef.current = { f1Confirmed, f2Finished, f4Confirmed, f5Done }
  }, [f1Confirmed, f2Finished, f4Confirmed, f5Done])

  useEffect(() => {
    moduleProgressRef.current = {
      module1SessionId,
      module1AwaitingConfirm,
      module1Step,
      module1TotalSteps,
      module2SessionId,
      module2Step,
      module2TotalSteps,
      module2LastExtractSig,
      module2DisplayStep,
      module2RootNodeId,
      module2MainNodeId,
      module4SessionId,
      module4AwaitingConfirm,
    }
  }, [
    module1SessionId,
    module1AwaitingConfirm,
    module1Step,
    module1TotalSteps,
    module2SessionId,
    module2Step,
    module2TotalSteps,
    module2LastExtractSig,
    module2DisplayStep,
    module2RootNodeId,
    module2MainNodeId,
    module4SessionId,
    module4AwaitingConfirm,
  ])

  const [currentUser, setCurrentUser] = useState<{ id: string; username: string } | null>(() => {
    try {
      const raw = sessionStorage.getItem('ecm_user')
      if (!raw) return null
      const obj = JSON.parse(raw) as { id?: unknown; username?: unknown }
      const id = String(obj.id ?? '')
      const username = String(obj.username ?? '')
      return id && username ? { id, username } : null
    } catch {
      return null
    }
  })
  const [loginForm, setLoginForm] = useState({ username: '', password: '', captcha: '' })
  const [loginError, setLoginError] = useState<string | null>(null)
  const expectedCaptcha = '123456'

  const [projects, setProjects] = useState<{ id: string; name: string; updatedAt?: number }[]>([])
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null)
  const [currentProjectName, setCurrentProjectName] = useState<string>('未命名项目')
  const [projectSaving, setProjectSaving] = useState(false)
  const [projectError, setProjectError] = useState<string | null>(null)

  const [exportLoading, setExportLoading] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  const [dialogues, setDialogues] = useState<DialogueListItem[]>([])
  const [currentDialogueId, setCurrentDialogueId] = useState<string | null>(null)
  const [currentDialogueName, setCurrentDialogueName] = useState<string>('未命名对话')

  type ProfileForm = {
    age: string
    stage: string
    major: string
    interests: string
    hobbies: string
    core_motivation?: string
    end_goal?: string
    learning_habits?: string
    persona_summary?: string
    persona_transcript?: { role: 'user' | 'assistant'; content: string }[]
  }
  const [profile, setProfile] = useState<ProfileForm>({
    age: '',
    stage: '',
    major: '',
    interests: '',
    hobbies: '',
    core_motivation: '',
    end_goal: '',
    learning_habits: '',
    persona_summary: '',
    persona_transcript: [],
  })
  const [showProfileModal, setShowProfileModal] = useState(false)
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)

  const [showPersonaModal, setShowPersonaModal] = useState(false)
  const [personaChats, setPersonaChats] = useState<{ role: 'user' | 'assistant'; content: string }[]>([])
  const [personaInput, setPersonaInput] = useState('')
  const [personaSending, setPersonaSending] = useState(false)
  const [personaDone, setPersonaDone] = useState(false)
  const [personaError, setPersonaError] = useState<string | null>(null)
  const personaUserTurns = useMemo(() => personaChats.filter((m) => m.role === 'user' && m.content.trim()).length, [personaChats])

  const computeF2Depth = (parentId: string | null | undefined, nodeDepth: Record<string, number>) => {
    if (!parentId) return 0
    const d = nodeDepth[parentId]
    return Number.isFinite(d) ? d + 1 : 1
  }

  const buildF2NodeMaps = (msgs: ChatMessage[]) => {
    const nodeParent: Record<string, string | null> = {}
    const nodeDepth: Record<string, number> = {}
    for (const m of msgs) {
      if (!m.nodeId) continue
      nodeParent[m.nodeId] = (m.parentId ?? null) as any
    }
    // compute depths with simple memoized walk
    const depthOf = (id: string): number => {
      if (id in nodeDepth) return nodeDepth[id]
      const p = nodeParent[id]
      if (!p) {
        nodeDepth[id] = 0
        return 0
      }
      nodeDepth[id] = depthOf(p) + 1
      return nodeDepth[id]
    }
    for (const id of Object.keys(nodeParent)) depthOf(id)
    return { nodeParent, nodeDepth }
  }

  const f1HistoryRef = useRef<HTMLDivElement | null>(null)
  const f2HistoryRef = useRef<HTMLDivElement | null>(null)
  const f4HistoryRef = useRef<HTMLDivElement | null>(null)
  const f5HistoryRef = useRef<HTMLDivElement | null>(null)
  const scrollRafRef = useRef<number | null>(null)

  const scrollToBottom = (key: FunctionKey) => {
    const el =
      key === 'f1'
        ? f1HistoryRef.current
        : key === 'f2'
          ? f2HistoryRef.current
          : key === 'f4'
            ? f4HistoryRef.current
            : f5HistoryRef.current
    if (!el) return
    if (scrollRafRef.current != null) cancelAnimationFrame(scrollRafRef.current)
    scrollRafRef.current = requestAnimationFrame(() => {
      // only scroll inside this function panel, not the whole page
      el.scrollTop = el.scrollHeight
    })
  }

  const readSse = async (resp: Response, onDelta: (text: string) => void, onFinal: (data: unknown) => void) => {
    const contentType = resp.headers.get('content-type') || ''
    // If backend returned JSON/HTML (e.g. DEEPSEEK 401 -> error JSON), don't try to parse it as SSE stream.
    if (!contentType.includes('text/event-stream')) {
      const bodyText = await resp.text().catch(() => '')
      const preview = (bodyText || '').slice(0, 600)
      throw new Error(`Expected SSE but got "${contentType}". Body: ${preview}`)
    }

    const reader = resp.body?.getReader()
    if (!reader) throw new Error('No response body (expected SSE)')
    const decoder = new TextDecoder('utf-8')
    let buf = ''
    let currentEvent: string | null = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      // Some runtimes may provide `value` as undefined; guard it.
      if (value) buf += decoder.decode(value, { stream: true })

      while (true) {
        const idx = buf.indexOf('\n\n')
        if (idx < 0) break
        const chunk = buf.slice(0, idx)
        buf = buf.slice(idx + 2)

        const lines = chunk.split('\n').map((l) => l.trimEnd())
        let dataLines: string[] = []
        currentEvent = null
        for (const line of lines) {
          if (line.startsWith('event:')) currentEvent = line.slice('event:'.length).trim()
          if (line.startsWith('data:')) dataLines.push(line.slice('data:'.length).trimStart())
        }
        const dataStr = dataLines.join('\n')
        if (!dataStr) continue

        if (currentEvent === 'final') {
          try {
            onFinal(JSON.parse(dataStr))
          } catch {
            onFinal(dataStr)
          }
        } else {
          onDelta(dataStr)
        }
      }
    }

    // Flush remaining buffer if the server closed the connection without the trailing `\n\n`.
    // This prevents the last few characters from being dropped.
    if (buf.trim()) {
      const chunk = buf
      buf = ''
      const lines = chunk.split('\n').map((l) => l.trimEnd())
      const dataLines: string[] = []
      let lastEvent: string | null = null
      for (const line of lines) {
        if (line.startsWith('event:')) lastEvent = line.slice('event:'.length).trim()
        if (line.startsWith('data:')) dataLines.push(line.slice('data:'.length).trimStart())
      }
      const dataStr = dataLines.join('\n')
      if (dataStr) {
        if (lastEvent === 'final') {
          try {
            onFinal(JSON.parse(dataStr))
          } catch {
            onFinal(dataStr)
          }
        } else {
          onDelta(dataStr)
        }
      }
    }
  }

  const textSimilarity = (a: string, b: string) => {
    const aSet = new Set((a || '').split(''))
    const bSet = new Set((b || '').split(''))
    if (!aSet.size && !bSet.size) return 1
    const inter = [...aSet].filter((c) => bSet.has(c)).length
    const union = new Set([...aSet, ...bSet]).size || 1
    return inter / union
  }

  const persistF3Analytics = async (noteTextForCalc?: string) => {
    if (!currentUser?.id || !currentProjectId || !currentDialogueId) return
    const note = noteTextForCalc ?? noteTextRef.current ?? ''
    const parts = note.split(/\n{2,}(?=\[Step\s*\d+\s*提炼\])/g).filter((s) => s.trim())
    const cardCount = parts.length
    const editedCardCount = f3MetricsRef.current.userEditCount > 0 ? cardCount : 0
    const editRate = cardCount > 0 ? editedCardCount / cardCount : 0
    const avgSimilarity = f3MetricsRef.current.simCount ? f3MetricsRef.current.simTotal / f3MetricsRef.current.simCount : 0
    const avgDepth = f3MetricsRef.current.depthCount ? f3MetricsRef.current.depthTotal / f3MetricsRef.current.depthCount : 0
    await fetch('/ecm/analytics/f3/upsert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: currentDialogueId,
        user_id: currentUser.id,
        project_id: currentProjectId,
        dialogue_id: currentDialogueId,
        note_text: note,
        metrics: {
          user_edit_count: f3MetricsRef.current.userEditCount,
          avg_similarity: avgSimilarity,
          avg_update_depth: avgDepth,
          card_count: cardCount,
          edited_card_count: editedCardCount,
          edit_rate: editRate,
          star_rate: 0,
          send_rate: 0,
        },
      }),
    }).catch(() => null)
  }

  const persistNoteText = (next: string, opts?: { fromSystem?: boolean }) => {
    const prev = noteTextRef.current ?? ''
    const fromSystem = Boolean(opts?.fromSystem)
    if (!fromSystem && prev !== next) {
      const sim = textSimilarity(prev, next)
      const depth = Math.max(0, 1 - sim)
      f3MetricsRef.current.userEditCount += 1
      f3MetricsRef.current.simTotal += sim
      f3MetricsRef.current.simCount += 1
      f3MetricsRef.current.depthTotal += depth
      f3MetricsRef.current.depthCount += 1
    }
    setNoteText(next)
    if (f3PersistTimerRef.current != null) window.clearTimeout(f3PersistTimerRef.current)
    f3PersistTimerRef.current = window.setTimeout(() => {
      void persistF3Analytics(next)
    }, 1200)
  }

  const appendModule2MetaToNotes = (meta: Module2Meta, step: number | null) => {
    const tags = meta.tags?.length ? meta.tags.join(' ') : ''
    const quote = meta.quote ? `“${meta.quote}”` : ''
    const hookRaw = meta.hook ?? ''
    const hook = hookRaw.replace(/^HOOK:\s*/i, '').trim()
    const header = `\n\n[Step ${step ?? '-'} 提炼]\n`
    const block =
      header +
      `🏷️ 关键词：${tags || '（无）'}\n` +
      `💡 核心金句：${quote || '（无）'}\n` +
      `⚡ 记忆钩子：${hook || '（无）'}\n\n`

    const next = (noteTextRef.current || '') + block
    persistNoteText(next, { fromSystem: true })
  }

  const updateInput = (key: FunctionKey, value: string) => {
    setInputs((prev) => ({ ...prev, [key]: value }))
  }

  const ensureF1Entered = () => {
    if (!f1TimingRef.current.enteredAt) f1TimingRef.current.enteredAt = Date.now()
  }

  const buildF1MetricsSnapshot = (history: ChatMessage[]) => {
    const userMsgs = history.filter((m) => m.role === 'user')
    const aiMsgs = history.filter((m) => m.role === 'assistant')
    const userLens = userMsgs.map((m) => (m.content || '').length)
    const aiLens = aiMsgs.map((m) => (m.content || '').length)
    const avg = (arr: number[]) => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0)
    const qWord = /(吗|么|为何|为什么|如何|怎么|怎样|是否|能否|可否|？|\?)/g
    const confirmWord = /(确认|是的|对|没错|好的|好|ok|OK|行)/g
    const optionWord = /\b([ABC])\b|(^|\s)([ABC])($|\s)|^[ABC]$|[A-C][+＋][1-9]/g

    let askCount = 0
    let confirmCount = 0
    let optionCount = 0
    let copyLikeCount = 0
    for (let i = 0; i < history.length; i++) {
      const m = history[i]
      if (m.role !== 'user') continue
      const t = m.content || ''
      if ((t.match(qWord) || []).length > 0) askCount += 1
      if ((t.match(confirmWord) || []).length > 0) confirmCount += 1
      if ((t.match(optionWord) || []).length > 0) optionCount += 1
      const prevAi = history.slice(0, i).reverse().find((x) => x.role === 'assistant' && (x.content || '').trim())
      if (prevAi) {
        const a = (prevAi.content || '').trim()
        const u = t.trim()
        if (u && a && (a.includes(u) || u.includes(a) || (u.length >= 12 && a.length >= 12 && u.slice(0, 12) === a.slice(0, 12)))) {
          copyLikeCount += 1
        }
      }
    }

    const now = Date.now()
    const dwellSeconds = Math.max(0, ((f1TimingRef.current.leftAt || now) - (f1TimingRef.current.enteredAt || now)) / 1000)
    const thinkingAvg =
      f1TimingRef.current.thinkingCount > 0 ? f1TimingRef.current.thinkingTotalMs / f1TimingRef.current.thinkingCount / 1000 : 0
    const aiRespAvg = f1TimingRef.current.aiCount > 0 ? f1TimingRef.current.aiTotalMs / f1TimingRef.current.aiCount / 1000 : 0

    return {
      avg_user_msg_length: avg(userLens),
      avg_ai_msg_length: avg(aiLens),
      user_question_count: askCount,
      user_confirm_count: confirmCount,
      user_copy_example_count: copyLikeCount,
      user_option_select_count: optionCount,
      module_dwell_seconds: dwellSeconds,
      user_thinking_seconds_avg: thinkingAvg,
      ai_response_seconds_avg: aiRespAvg,
      turn_count: history.length,
    }
  }

  const persistF1Analytics = async (historyOverride?: ChatMessage[]) => {
    if (!currentUser?.id || !currentProjectId || !currentDialogueId) return
    const history = (historyOverride ?? chatsRef.current.f1 ?? []).map((m) => ({
      role: m.role,
      content: m.content,
      action: m.action ?? null,
      timestamp: typeof m.ts === 'number' ? m.ts : null,
    }))
    const metrics = buildF1MetricsSnapshot(historyOverride ?? (chatsRef.current.f1 ?? []))
    await fetch('/ecm/analytics/f1/upsert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: currentDialogueId,
        user_id: currentUser.id,
        project_id: currentProjectId,
        dialogue_id: currentDialogueId,
        history,
        metrics,
      }),
    }).catch(() => null)
  }

  const clearChat = (key: FunctionKey) => {
    setChats((prev) => ({ ...prev, [key]: [] }))
    setErrors((prev) => ({ ...prev, [key]: null }))
    setInputs((prev) => ({ ...prev, [key]: '' }))
    if (key === 'f1') {
      setModule1SessionId(null)
      setModule1AwaitingConfirm(false)
      setModule1Step(null)
      setModule1Definition(null)
      setModule1TotalSteps(5)
      setF1Confirmed(false)
      f1TimingRef.current = {
        enteredAt: 0,
        leftAt: 0,
        lastAiDoneAt: 0,
        thinkingTotalMs: 0,
        thinkingCount: 0,
        aiTotalMs: 0,
        aiCount: 0,
      }
    }
    if (key === 'f2') {
      setModule2SessionId(null)
      setModule2Step(null)
      setModule2TotalSteps(5)
      setModule2LastExtractSig(null)
      setModule2DisplayStep(null)
      setModule2RootNodeId(null)
      setModule2MainNodeId(null)
      setF2Finished(false)
      f2TimingRef.current = {
        enteredAt: 0,
        leftAt: 0,
        lastAiDoneAt: 0,
        thinkingTotalMs: 0,
        thinkingCount: 0,
        aiTotalMs: 0,
        aiCount: 0,
      }
    }
    if (key === 'f4') {
      setModule4SessionId(null)
      setModule4AwaitingConfirm(false)
      f4TimingRef.current = {
        enteredAt: 0,
        leftAt: 0,
        reportGenCount: 0,
        downloadCount: 0,
      }
    }
    if (key === 'f5') {
      // Let users continue multi-turn even if an old project state had f5Done=true.
      setF5Done(false)
      f5TimingRef.current = {
        enteredAt: 0,
        leftAt: 0,
        userEditCount: 0,
        clickCount: 0,
        newCount: 0,
      }
    }
  }

  const parseF2ABCOptions = (assistantText: string) => {
    const t = assistantText || ''
    // Expect strict format from module2_steps.txt:
    // A. xxx / B. xxx / C. xxx  (each on its own line)
    const mA = t.match(/^\s*(?:>\s*)?A[\.．：:]\s*([^\n\r]+)\s*$/m)
    const mB = t.match(/^\s*(?:>\s*)?B[\.．：:]\s*([^\n\r]+)\s*$/m)
    const mC = t.match(/^\s*(?:>\s*)?C[\.．：:]\s*([^\n\r]+)\s*$/m)
    if (!mA || !mB || !mC) return null
    const optA = String(mA[1] ?? '').trim()
    const optB = String(mB[1] ?? '').trim()
    const optC = String(mC[1] ?? '').trim()
    if (!optA || !optB || !optC) return null
    return { A: optA, B: optB, C: optC }
  }

  const extractAnchorKeywords = (definition: string) => {
    const def = definition || ''
    // Extract 2-8 Chinese chars chunks as candidate keywords.
    const candidates = def.match(/[\u4e00-\u9fa5]{2,8}/g) ?? []
    const stop = new Set([
      '我们',
      '讨论',
      '主题',
      '目标',
      '价值',
      '范围',
      '前提',
      '资源',
      '限制',
      '场景',
      '人群',
      '阶段',
      '主要',
      '为了',
      '基于',
      '通过',
      '其中',
      '以及',
      '确保',
      '探讨',
      '围绕',
      '会',
      '要',
      '一个',
      '的',
      '和',
      '与',
    ])
    const freq = new Map<string, number>()
    for (const w of candidates) {
      const k = w.trim()
      if (!k || stop.has(k)) continue
      freq.set(k, (freq.get(k) || 0) + 1)
    }
    const sorted = Array.from(freq.entries())
      .sort((a, b) => b[1] - a[1])
      .map((x) => x[0])
    return sorted.slice(0, 6)
  }

  const shouldF2RejectOffTopic = (text: string) => {
    const t = (text || '').trim()
    if (!t) return false
    // Allow control words to pass.
    if (/^(确认|是的|对|没错|好的|好|行|可以|继续|下一步|回到定义|结束探索)$/.test(t)) return false

    const step = Number(module2Step ?? 0)
    const stepKwMap: Record<number, string[]> = {
      1: ['本质', '第一性', '底层', '原理', '是什么', '为什么', '逻辑'],
      2: ['典型', '案例', '流程', '标准', '应用', '怎么用', '实操'],
      3: ['迁移', '跨界', '举一反三', '例子', '不同领域', '转换'],
      4: ['辩证', '利弊', '权衡', '副作用', '系统', '外部性', '反例'],
      5: ['趋势', '未来', '3', '5', '推演', '不确定', '终局', '演变'],
    }
    const stepKw = stepKwMap[step] ?? []
    const commonKw = [
      '案例',
      '例子',
      '创新',
      '创业',
      '维度',
      '模型',
      '框架',
      '分析',
      '解释',
      '推演',
      '趋势',
      '未来',
      '迁移',
      '应用',
      '流程',
      '逻辑',
      '利弊',
      '权衡',
      '副作用',
      '系统',
    ]
    const anchorKw = extractAnchorKeywords(module1DefinitionRef.current ?? '')

    const hasAnchor = anchorKw.some((k) => t.includes(k))
    const hasStep = stepKw.some((k) => t.includes(k))
    const hasCommon = commonKw.some((k) => t.includes(k))
    // If user mentions nothing related to either the target or the current step, treat as off-topic.
    return !hasAnchor && !hasStep && !hasCommon
  }

  const collectProjectState = () => ({
    chats: chatsRef.current,
    noteText: noteTextRef.current,
    module1Definition: module1DefinitionRef.current,
    moduleProgress: {
      ...moduleProgressRef.current,
    },
    flags: {
      ...flagsRef.current,
    },
  })

  const applyProjectState = (state: unknown) => {
    if (!state || typeof state !== 'object') return
    const s = state as {
      chats?: unknown
      noteText?: unknown
      module1Definition?: unknown
      moduleProgress?: unknown
      flags?: { f1Confirmed?: unknown; f2Finished?: unknown; f4Confirmed?: unknown; f5Done?: unknown }
    }
    const f1ConfirmedFromState =
      s.flags && typeof s.flags === 'object' && typeof (s.flags as any).f1Confirmed === 'boolean' ? Boolean((s.flags as any).f1Confirmed) : false

    const deriveModule1DefinitionFromF1Chat = (f1Chat: ChatMessage[]): string | null => {
      const lastAssistant = [...(f1Chat ?? [])].reverse().find((m) => m?.role === 'assistant' && typeof m.content === 'string' && m.content.trim())
      const content = lastAssistant?.content ?? ''
      if (!content) return null
      const idx = content.indexOf('这个定义准确吗')
      const head = idx > 0 ? content.slice(0, idx) : content
      const trimmed = head.trim()
      // Heuristic: only accept if it contains the expected marker.
      return trimmed.includes('🚩问题定义确认') ? trimmed : null
    }

    let loadedF1: ChatMessage[] = []
    if (s.chats && typeof s.chats === 'object') {
      const c = s.chats as Record<string, unknown>
      loadedF1 = (Array.isArray(c.f1) ? (c.f1 as ChatMessage[]) : []) ?? []
      const loadedF4 = (Array.isArray(c.f4) ? (c.f4 as ChatMessage[]) : []) ?? []
      setChats({
        f1: loadedF1 ?? [],
        f2: (Array.isArray(c.f2) ? (c.f2 as ChatMessage[]) : []) ?? [],
        f4: loadedF4 ?? [],
        f5: (Array.isArray(c.f5) ? (c.f5 as ChatMessage[]) : []) ?? [],
      })
      // Reconstruct latest Function 4 report text for "end/confirm" fallback after reload.
      const f4Assistants = [...(loadedF4 ?? [])].filter(
        (m) => m?.role === 'assistant' && typeof m.content === 'string' && m.content.trim(),
      ) as { role?: string; content?: string }[]
      const reportLike =
        f4Assistants.find((m) =>
          String(m.content ?? '').includes('ECM深度洞察报告') ||
          String(m.content ?? '').includes('结构化导图') ||
          String(m.content ?? '').includes('Mermaid') ||
          String(m.content ?? '').includes('MermaidCode'),
        )?.content ?? ''
      const maxLen = f4Assistants.reduce((acc, m) => {
        const v = String(m.content ?? '')
        return v.length > acc.length ? v : acc
      }, '' as string)
      const candidate = (reportLike || maxLen || '').trim()
      if (candidate) module4ReportTextRef.current = candidate
    }
    if (typeof s.noteText === 'string') {
      persistNoteText(s.noteText, { fromSystem: true })
    }
    if (typeof s.module1Definition === 'string' && s.module1Definition) {
      setModule1Definition(s.module1Definition)
    } else {
      // Backward compat for older saved dialogues: try to recover module1Definition from F1 chat.
      const derived = f1ConfirmedFromState ? deriveModule1DefinitionFromF1Chat(loadedF1) : null
      setModule1Definition(derived)
    }
    if (s.flags && typeof s.flags === 'object') {
      const f = s.flags
      if (typeof f.f1Confirmed === 'boolean') setF1Confirmed(f.f1Confirmed)
      if (typeof f.f2Finished === 'boolean') setF2Finished(f.f2Finished)
      if (typeof f.f4Confirmed === 'boolean') setF4Confirmed(f.f4Confirmed)
      if (typeof f.f5Done === 'boolean') setF5Done(f.f5Done)
    } else {
      setF1Confirmed(false)
      setF2Finished(false)
      setF4Confirmed(false)
      setF5Done(false)
    }

    // Reset module sessions/steps to avoid stale values when loading older states.
    setModule1SessionId(null)
    setModule1AwaitingConfirm(false)
    setModule1Step(null)
    setModule1TotalSteps(5)
    setModule2SessionId(null)
    setModule2Step(null)
    setModule2TotalSteps(5)
    setModule2LastExtractSig(null)
    setModule2DisplayStep(null)
    setModule2RootNodeId(null)
    setModule2MainNodeId(null)
    setModule4SessionId(null)
    setModule4AwaitingConfirm(false)

    // Restore module progress (so subsequent Functions can resume without re-running prerequisites).
    const mp = s.moduleProgress
    if (mp && typeof mp === 'object') {
      const m = mp as {
        module1SessionId?: unknown
        module1AwaitingConfirm?: unknown
        module1Step?: unknown
        module1TotalSteps?: unknown
        module2SessionId?: unknown
        module2Step?: unknown
        module2TotalSteps?: unknown
        module2LastExtractSig?: unknown
        module2DisplayStep?: unknown
        module2RootNodeId?: unknown
        module2MainNodeId?: unknown
        module4SessionId?: unknown
        module4AwaitingConfirm?: unknown
      }

      if (typeof m.module1SessionId === 'string') setModule1SessionId(m.module1SessionId)
      if (typeof m.module1AwaitingConfirm === 'boolean') setModule1AwaitingConfirm(m.module1AwaitingConfirm)
      if (typeof m.module1Step === 'number' && Number.isFinite(m.module1Step)) setModule1Step(m.module1Step)
      if (typeof m.module1TotalSteps === 'number' && Number.isFinite(m.module1TotalSteps)) setModule1TotalSteps(m.module1TotalSteps)

      if (typeof m.module2SessionId === 'string') setModule2SessionId(m.module2SessionId)
      if (typeof m.module2Step === 'number' && Number.isFinite(m.module2Step)) setModule2Step(m.module2Step)
      if (typeof m.module2TotalSteps === 'number' && Number.isFinite(m.module2TotalSteps)) setModule2TotalSteps(m.module2TotalSteps)
      if (typeof m.module2LastExtractSig === 'string' || m.module2LastExtractSig === null) setModule2LastExtractSig(m.module2LastExtractSig as any)
      if (typeof m.module2DisplayStep === 'number' && Number.isFinite(m.module2DisplayStep)) setModule2DisplayStep(m.module2DisplayStep)
      if (typeof m.module2RootNodeId === 'string' || m.module2RootNodeId === null) setModule2RootNodeId(m.module2RootNodeId as any)
      if (typeof m.module2MainNodeId === 'string' || m.module2MainNodeId === null) setModule2MainNodeId(m.module2MainNodeId as any)

      if (typeof m.module4SessionId === 'string') setModule4SessionId(m.module4SessionId)
      if (typeof m.module4AwaitingConfirm === 'boolean') setModule4AwaitingConfirm(m.module4AwaitingConfirm)
    }
  }

  const handleLogin = async () => {
    const username = loginForm.username.trim()
    const password = loginForm.password.trim()
    const captcha = loginForm.captcha.trim()
    if (!username || !password) {
      setLoginError('请输入用户名和密码')
      return
    }
    if (captcha !== expectedCaptcha) {
      setLoginError('验证码错误')
      return
    }
    setLoginError(null)
    try {
      const resp = await fetch('/ecm/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, captcha, userType: 'student' }),
      })
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const msg =
          typeof data === 'object' && data && 'error' in data
            ? String((data as { error?: unknown }).error ?? '')
            : '登录失败'
        throw new Error(msg)
      }
      const id =
        typeof data === 'object' && data && 'id' in data ? String((data as { id?: unknown }).id ?? '') : ''
      const uname =
        typeof data === 'object' && data && 'username' in data
          ? String((data as { username?: unknown }).username ?? '')
          : username
      setCurrentUser({ id, username: uname })
      sessionStorage.setItem('ecm_user', JSON.stringify({ id, username: uname }))
      setLoginError(null)
      // 登录后加载项目列表
      const listResp = await fetch(`/ecm/projects/list?userId=${encodeURIComponent(id)}`)
      const listData: unknown = await listResp.json().catch(() => null)
      if (listResp.ok && Array.isArray(listData)) {
        const items = listData as { id: string; name?: string; updatedAt?: number }[]
        setProjects(items.map((p) => ({ id: p.id, name: p.name ?? '未命名项目', updatedAt: p.updatedAt })))
        if (items.length === 0) {
          // 首次登录且没有项目时，创建一个带引导语的空白项目
          createNewProjectLocal()
          setDialogues([])
          setCurrentDialogueId(null)
          setCurrentDialogueName('未命名对话')
        }
      } else {
        setProjects([])
      }
    } catch (e) {
      setLoginError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    // Student app is now under /student; if a user exists, preload projects list and profile
    if (!currentUser) return
    void (async () => {
      try {
        const listResp = await fetch(`/ecm/projects/list?userId=${encodeURIComponent(currentUser.id)}`)
        const listData: unknown = await listResp.json().catch(() => null)
        if (listResp.ok && Array.isArray(listData)) {
          const items = listData as { id: string; name?: string; updatedAt?: number }[]
          setProjects(items.map((p) => ({ id: p.id, name: p.name ?? '未命名项目', updatedAt: p.updatedAt })))
          if (items.length === 0) {
            // unified login -> student app: ensure a fresh project exists with the opening question
            createNewProjectLocal()
          }
        }
      } catch {
        // ignore
      }
      try {
        const profileResp = await fetch(`/ecm/profile?userId=${encodeURIComponent(currentUser.id)}`)
        const profileData: unknown = await profileResp.json().catch(() => null)
        if (profileResp.ok && profileData && typeof profileData === 'object' && 'profile' in profileData) {
          const p = (profileData as { profile?: Record<string, unknown> }).profile
          if (p && typeof p === 'object') {
            setProfile({
              age: String(p.age ?? ''),
              stage: String(p.stage ?? ''),
              major: String(p.major ?? ''),
              interests: String(p.interests ?? ''),
              hobbies: String(p.hobbies ?? ''),
              core_motivation: String(p.core_motivation ?? ''),
              end_goal: String(p.end_goal ?? ''),
              learning_habits: String(p.learning_habits ?? ''),
              persona_summary: String(p.persona_summary ?? ''),
              persona_transcript: Array.isArray(p.persona_transcript)
                ? (p.persona_transcript as unknown[])
                    .map((x) => (x && typeof x === 'object' ? (x as any) : null))
                    .filter(Boolean)
                    .map((x) => ({ role: String((x as any).role) === 'user' ? 'user' : 'assistant', content: String((x as any).content ?? '') }))
                : [],
            })
          }
        }
      } catch {
        // ignore
      }
    })()
  }, [currentUser])

  const saveProfile = async () => {
    if (!currentUser) return
    setProfileSaving(true)
    setProfileError(null)
    try {
      const resp = await fetch('/ecm/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId: currentUser.id, profile }),
      })
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const msg =
          typeof data === 'object' && data && 'error' in data ? String((data as { error?: unknown }).error ?? '') : '保存失败'
        throw new Error(msg)
      }
      setShowProfileModal(false)
    } catch (e) {
      setProfileError(e instanceof Error ? e.message : String(e))
    } finally {
      setProfileSaving(false)
    }
  }

  const personaTurn = async (userText: string) => {
    if (!currentUser) return
    setPersonaSending(true)
    setPersonaError(null)
    try {
      const nextHistory = [...personaChats, ...(userText ? [{ role: 'user' as const, content: userText }] : [])]
      if (userText) setPersonaChats(nextHistory)

      const resp = await fetch('/ecm/persona/next_stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userId: currentUser.id,
          history: nextHistory,
          user_input: userText,
        }),
      })
      if (!resp.ok) throw new Error(await resp.text().catch(() => ''))

      // placeholder assistant
      setPersonaChats((prev) => [...prev, { role: 'assistant', content: '' }])
      let finalPayload: any = null
      await readSse(
        resp,
        (delta) => {
          setPersonaChats((prev) => {
            const arr = [...prev]
            const idx = arr.length - 1
            if (idx >= 0 && arr[idx]?.role === 'assistant') arr[idx] = { ...arr[idx], content: (arr[idx].content ?? '') + delta }
            return arr
          })
        },
        (data) => {
          finalPayload = data
        },
      )

      const fp: any = finalPayload
      const assistantText = fp && typeof fp === 'object' && 'assistant' in fp ? String(fp.assistant ?? '') : ''
      const done = fp && typeof fp === 'object' && 'done' in fp ? Boolean(fp.done) : false
      const extracted = fp && typeof fp === 'object' && 'extracted' in fp ? (fp.extracted as any) : null

      if (assistantText) {
        setPersonaChats((prev) => {
          const arr = [...prev]
          const idx = arr.length - 1
          if (idx >= 0 && arr[idx]?.role === 'assistant') arr[idx] = { ...arr[idx], content: assistantText }
          return arr
        })
      }

      if (done && extracted && typeof extracted === 'object') {
        setPersonaDone(true)
        const merged: ProfileForm = {
          ...profile,
          core_motivation: String(extracted.core_motivation ?? ''),
          end_goal: String(extracted.end_goal ?? ''),
          learning_habits: String(extracted.learning_habits ?? ''),
          persona_summary: String(extracted.persona_summary ?? assistantText ?? ''),
          persona_transcript: [...nextHistory, { role: 'assistant', content: assistantText }],
        }
        setProfile(merged)
        // persist immediately
        await fetch('/ecm/profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ userId: currentUser.id, profile: merged }),
        }).catch(() => null)
      }
    } catch (e) {
      setPersonaError(e instanceof Error ? e.message : String(e))
    } finally {
      setPersonaSending(false)
    }
  }

  const saveProject = async () => {
    if (!currentUser) {
      setProjectError('请先登录')
      return
    }
    setProjectSaving(true)
    setProjectError(null)
    try {
      // Ensure the latest state snapshot is committed (especially right after streaming).
      await new Promise((r) => {
        if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => r(true))
        else setTimeout(() => r(true), 0)
      })
      await new Promise((r) => {
        if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => r(true))
        else setTimeout(() => r(true), 0)
      })
      if (!currentProjectId) {
        // 创建项目（同时创建默认“对话 1”）
        const resp = await fetch('/ecm/projects/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            userId: currentUser.id,
            projectId: null,
            name: currentProjectName || '未命名项目',
            state: collectProjectState(),
          }),
        })
        const data: unknown = await resp.json().catch(() => null)
        if (!resp.ok) {
          const msg =
            typeof data === 'object' && data && 'error' in data
              ? String((data as { error?: unknown }).error ?? '')
              : '保存失败'
          throw new Error(msg)
        }
        const id = typeof data === 'object' && data && 'id' in data ? String((data as { id?: unknown }).id ?? '') : ''
        const name =
          typeof data === 'object' && data && 'name' in data
            ? String((data as { name?: unknown }).name ?? '')
            : currentProjectName
        const updatedAt =
          typeof data === 'object' && data && 'updatedAt' in data
            ? Number((data as { updatedAt?: unknown }).updatedAt)
            : Date.now() / 1000
        const did =
          typeof data === 'object' && data && 'dialogueId' in data
            ? String((data as { dialogueId?: unknown }).dialogueId ?? '')
            : ''
        setCurrentProjectId(id || null)
        setCurrentProjectName(name || '未命名项目')
        if (did) {
          setCurrentDialogueId(did)
          setCurrentDialogueName('对话 1')
        }
        setProjects((prev) => {
          const rest = prev.filter((p) => p.id !== id)
          return [{ id, name, updatedAt }, ...rest]
        })

        if (id) {
          const respList = await fetch(
            `/ecm/dialogues/list?userId=${encodeURIComponent(currentUser.id)}&projectId=${encodeURIComponent(id)}`,
          )
          const listData: unknown = await respList.json().catch(() => null)
          if (respList.ok && Array.isArray(listData)) {
            setDialogues(
              (listData as { id?: unknown; name?: unknown; updatedAt?: unknown }[])
                .map((d) => ({ id: String(d.id ?? ''), name: String(d.name ?? '未命名对话'), updatedAt: Number(d.updatedAt ?? 0) }))
                .filter((d) => d.id),
            )
          }
        }
      } else {
        // 保存到对话（dialogueId 为空则创建新对话）
        const resp = await fetch('/ecm/dialogues/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            userId: currentUser.id,
            projectId: currentProjectId,
            dialogueId: currentDialogueId,
            name: currentDialogueName || '未命名对话',
            state: collectProjectState(),
          }),
        })
        const data: unknown = await resp.json().catch(() => null)
        if (!resp.ok) {
          const msg =
            typeof data === 'object' && data && 'error' in data
              ? String((data as { error?: unknown }).error ?? '')
              : '保存失败'
          throw new Error(msg)
        }
        const did = typeof data === 'object' && data && 'id' in data ? String((data as { id?: unknown }).id ?? '') : ''
        const dname =
          typeof data === 'object' && data && 'name' in data
            ? String((data as { name?: unknown }).name ?? '')
            : currentDialogueName
        const updatedAt =
          typeof data === 'object' && data && 'updatedAt' in data
            ? Number((data as { updatedAt?: unknown }).updatedAt)
            : Date.now() / 1000
        setCurrentDialogueId(did || null)
        setCurrentDialogueName(dname || '未命名对话')
        setDialogues((prev) => {
          const rest = prev.filter((d) => d.id !== did)
          return [{ id: did, name: dname, updatedAt }, ...rest]
        })
      }
    } catch (e) {
      setProjectError(e instanceof Error ? e.message : String(e))
    } finally {
      setProjectSaving(false)
    }
  }

  /** 导出为 Word（DeepSeek 整理后填入表格模板） */
  const exportWord = async () => {
    if (!currentUser) {
      setExportError('请先登录')
      return
    }
    if (exportLoading) return
    setExportLoading(true)
    setExportError(null)
    try {
      const resp = await fetch('/ecm/student/export_word', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userId: currentUser.id,
          projectName: currentProjectName,
          projectId: currentProjectId ?? '',
          dialogueName: currentDialogueName,
          dialogueId: currentDialogueId ?? '',
          chats: {
            f1: chatsRef.current.f1 ?? [],
            f2: chatsRef.current.f2 ?? [],
            f4: chatsRef.current.f4 ?? [],
            f5: chatsRef.current.f5 ?? [],
          },
          noteText: noteTextRef.current,
          module1Definition: module1DefinitionRef.current ?? '',
        }),
      })
      if (!resp.ok) {
        const ct = resp.headers.get('content-type') || ''
        if (ct.includes('application/json')) {
          const data: unknown = await resp.json().catch(() => null)
          if (data && typeof data === 'object' && 'error' in data) {
            const err = (data as { error?: unknown }).error
            const detail = (data as { detail?: unknown }).detail
            throw new Error(`${String(err ?? '')}${detail ? ` (${String(detail)})` : ''}`.trim() || '导出失败')
          }
        }
        const msg = await resp.text().catch(() => '')
        throw new Error(msg || '导出失败')
      }
      const ctOk = resp.headers.get('content-type') || ''
      let blob: Blob | null = null
      let filename = 'ECM_export.docx'

      if (ctOk.includes('application/json')) {
        const data: unknown = await resp.json().catch(() => null)
        if (!data || typeof data !== 'object') throw new Error('导出失败：JSON 返回格式异常')
        const b64 = (data as { base64?: unknown }).base64
        const fn = (data as { filename?: unknown }).filename
        if (typeof b64 !== 'string' || !b64) throw new Error('导出失败：base64 缺失')
        if (typeof fn === 'string' && fn.trim()) filename = fn
        const byteCharacters = atob(b64)
        const byteNumbers = new Array(byteCharacters.length)
        for (let i = 0; i < byteCharacters.length; i++) byteNumbers[i] = byteCharacters.charCodeAt(i)
        const byteArray = new Uint8Array(byteNumbers)
        blob = new Blob([byteArray], {
          type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        })
      } else {
        const dataBlob = await resp.blob()
        blob = dataBlob
        const cd = resp.headers.get('content-disposition') || ''
        const m = cd.match(/filename="?([^"]+)"?/i)
        filename = m?.[1] || 'ECM_export.docx'
      }

      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)

      // Count report downloads for Function 4 analytics (Word export).
      if (f4Confirmed) {
        const lastF4Assistant = [...(chatsRef.current.f4 ?? [])]
          .slice()
          .reverse()
          .find((m) => m.role === 'assistant' && (m.content ?? '').trim())?.content
        if (lastF4Assistant && String(lastF4Assistant).trim()) {
          f4TimingRef.current.downloadCount = (f4TimingRef.current.downloadCount || 0) + 1
          void persistF4Analytics(String(lastF4Assistant))
        }
      }
    } catch (e) {
      setExportError(e instanceof Error ? e.message : String(e))
    } finally {
      setExportLoading(false)
    }
  }

  const autoSaveProject = async () => {
    if (!currentUser) return
    try {
      await saveProject()
    } catch {
      // 忽略自动保存错误
    }
  }

  const loadDialogueById = async (pid: string, did: string) => {
    if (!currentUser) return
    setProjectError(null)
    try {
      const resp = await fetch(
        `/ecm/dialogues/load?userId=${encodeURIComponent(currentUser.id)}&projectId=${encodeURIComponent(pid)}&dialogueId=${encodeURIComponent(did)}`,
      )
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const msg =
          typeof data === 'object' && data && 'error' in data
            ? String((data as { error?: unknown }).error ?? '')
            : '加载失败'
        throw new Error(msg)
      }
      const projectName =
        typeof data === 'object' && data && 'projectName' in data
          ? String((data as { projectName?: unknown }).projectName ?? '')
          : '未命名项目'
      const dialogueName =
        typeof data === 'object' && data && 'name' in data ? String((data as { name?: unknown }).name ?? '') : '未命名对话'
      const state = typeof data === 'object' && data && 'state' in data ? (data as { state?: unknown }).state : null
      setCurrentProjectId(pid)
      setCurrentProjectName(projectName || '未命名项目')
      setCurrentDialogueId(did)
      setCurrentDialogueName(dialogueName || '未命名对话')
      applyProjectState(state as unknown)
    } catch (e) {
      setProjectError(e instanceof Error ? e.message : String(e))
    }
  }

  const loadProjectById = async (pid: string) => {
    if (!currentUser) return
    setProjectError(null)
    try {
      const resp = await fetch(
        `/ecm/projects/load?userId=${encodeURIComponent(currentUser.id)}&projectId=${encodeURIComponent(pid)}`,
      )
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const msg =
          typeof data === 'object' && data && 'error' in data
            ? String((data as { error?: unknown }).error ?? '')
            : '加载失败'
        throw new Error(msg)
      }
      const name =
        typeof data === 'object' && data && 'name' in data ? String((data as { name?: unknown }).name ?? '') : '未命名项目'
      setCurrentProjectId(pid)
      setCurrentProjectName(name || '未命名项目')

      const respList = await fetch(
        `/ecm/dialogues/list?userId=${encodeURIComponent(currentUser.id)}&projectId=${encodeURIComponent(pid)}`,
      )
      const listData: unknown = await respList.json().catch(() => null)
      if (respList.ok && Array.isArray(listData)) {
        const items = (listData as { id?: unknown; name?: unknown; updatedAt?: unknown }[])
          .map((d) => ({ id: String(d.id ?? ''), name: String(d.name ?? '未命名对话'), updatedAt: Number(d.updatedAt ?? 0) }))
          .filter((d) => d.id)
        setDialogues(items)
        if (items[0]) {
          await loadDialogueById(pid, items[0].id)
          return
        }
      } else {
        setDialogues([])
      }

      // fallback: old state
      const state = typeof data === 'object' && data && 'state' in data ? (data as { state?: unknown }).state : null
      setCurrentDialogueId(null)
      setCurrentDialogueName('未命名对话')
      applyProjectState(state as unknown)
    } catch (e) {
      setProjectError(e instanceof Error ? e.message : String(e))
    }
  }

  const createNewProjectLocal = () => {
    setCurrentProjectId(null)
    setCurrentProjectName('未命名项目')
    setDialogues([])
    setCurrentDialogueId(null)
    setCurrentDialogueName('未命名对话')
    setChats({ f1: [{ role: 'assistant', content: f1Greeting }], f2: [], f4: [], f5: [] })
    persistNoteText('', { fromSystem: true })
    setModule1SessionId(null)
    setModule1AwaitingConfirm(false)
    setModule1Step(null)
    setModule1Definition(null)
    setModule1TotalSteps(5)
    setModule2SessionId(null)
    setModule2Step(null)
    setModule2TotalSteps(5)
    setModule2LastExtractSig(null)
    setModule2DisplayStep(null)
    setModule2RootNodeId(null)
    setModule2MainNodeId(null)
    setModule4SessionId(null)
    setModule4AwaitingConfirm(false)
  }

  const createNewDialogueLocal = () => {
    setCurrentDialogueId(null)
    setCurrentDialogueName(`对话 ${Math.max(1, dialogues.length + 1)}`)
    setChats({ f1: [{ role: 'assistant', content: f1Greeting }], f2: [], f4: [], f5: [] })
    persistNoteText('', { fromSystem: true })
    setModule1SessionId(null)
    setModule1AwaitingConfirm(false)
    setModule1Step(null)
    setModule1Definition(null)
    setModule1TotalSteps(5)
    setModule2SessionId(null)
    setModule2Step(null)
    setModule2TotalSteps(5)
    setModule2LastExtractSig(null)
    setModule2DisplayStep(null)
    setModule2RootNodeId(null)
    setModule2MainNodeId(null)
    setModule4SessionId(null)
    setModule4AwaitingConfirm(false)
    setF1Confirmed(false)
    setF2Finished(false)
    setF4Confirmed(false)
    setF5Done(false)
  }

  const sendChat = async (key: FunctionKey, opts?: { action?: 'followup' | 'submit' }, directText?: string) => {
    const text = (directText ?? (inputs[key] ?? '')).trim()
    if (!text) return
    if (sendingKey) return
    const action = opts?.action ?? 'submit'
    if (key === 'f5' && f5Done) return

    // Off-topic detection for Function 2 (方案A：关键词/正则，简单稳定)
    // Only apply when user clicks "追问" (followup) and the user typed manually in textarea.
    // This avoids showing the warning during normal "回复"/submit turns.
    if (key === 'f2' && action === 'followup' && directText == null) {
      const offTopic = shouldF2RejectOffTopic(text)
      if (offTopic) {
        const ok = window.confirm('你这句话可能偏离当前 Step 主线。是否允许切换话题并继续对话？')
        if (!ok) {
          updateInput('f2', '')
          window.alert('已清空输入，请继续围绕当前 Step 回答。')
          return
        }
      }
    }

    setErrors((prev) => ({ ...prev, [key]: null }))
    setSendingKey(key)
    // If user picked A/B/C options, directText should be visible as "auto fill".
    // Otherwise clear the textarea before streaming begins.
    updateInput(key, directText != null ? directText : '')

    try {
      // Function 1 uses ECM Module1 step-by-step tutor flow.
      if (key === 'f1') {
        const userTs = Date.now()
        ensureF1Entered()
        if (f1TimingRef.current.lastAiDoneAt > 0) {
          f1TimingRef.current.thinkingTotalMs += Math.max(0, userTs - f1TimingRef.current.lastAiDoneAt)
          f1TimingRef.current.thinkingCount += 1
        }
        const userMsg: ChatMessage = { role: 'user', content: text, ts: userTs }
        setChats((prev) => ({ ...prev, f1: [...(prev.f1 ?? []), userMsg] }))

        if (!module1SessionId) {
          // 先创建会话，再立刻把本次输入作为 next 发送，确保“第一次提问就有回复”
          const startResp = await fetch('/ecm/module1/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            // Use the first user input as "question" so backend context isn't missing
            // when you reopen and restart Function 1.
            body: JSON.stringify({ question: text }),
          })
          const startData: unknown = await startResp.json().catch(() => null)
          if (!startResp.ok) {
            throw new Error(typeof startData === 'string' ? startData : JSON.stringify(startData))
          }

          const sid =
            typeof startData === 'object' && startData && 'session_id' in startData
              ? String((startData as { session_id?: unknown }).session_id ?? '')
              : ''
          const step =
            typeof startData === 'object' && startData && 'step' in startData
              ? Number((startData as { step?: unknown }).step)
              : null

          setModule1SessionId(sid || null)
          setModule1Step(step && Number.isFinite(step) ? step : 1)
          setModule1AwaitingConfirm(false)
          setModule1TotalSteps(5)
          if (!sid) return

          const aiStartTs = Date.now()
          const nextResp = await fetch('/ecm/module1/next_stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sid, user_input: text, userId: currentUser?.id }),
          })
          if (!nextResp.ok) {
            const errText = await nextResp.text().catch(() => '')
            throw new Error(errText || 'stream request failed')
          }

          setChats((prev) => ({ ...prev, f1: [...(prev.f1 ?? []), { role: 'assistant', content: '', ts: aiStartTs }] }))
          let finalPayload: any = null
          await readSse(
            nextResp,
            (delta) => {
              setChats((prev) => {
                const arr = [...(prev.f1 ?? [])]
                const idx = arr.length - 1
                if (idx >= 0 && arr[idx]?.role === 'assistant') {
                  arr[idx] = { ...arr[idx], content: (arr[idx].content ?? '') + delta }
                }
                return { ...prev, f1: arr }
              })
              scrollToBottom('f1')
            },
            (data) => {
              finalPayload = data
            },
          )

          const nextData: any = finalPayload
          const assistant = typeof nextData === 'object' && nextData && 'assistant' in nextData ? String(nextData.assistant ?? '') : ''
          const step2 = typeof nextData === 'object' && nextData && 'step' in nextData ? Number(nextData.step) : null
          const done = typeof nextData === 'object' && nextData && 'done' in nextData ? Boolean(nextData.done) : false
          const awaiting =
            typeof nextData === 'object' && nextData && 'awaiting_confirm' in nextData ? Boolean(nextData.awaiting_confirm) : false
          const totalSteps = typeof nextData === 'object' && nextData && 'total_steps' in nextData ? Number(nextData.total_steps) : null

          if (step2 && Number.isFinite(step2)) setModule1Step(step2)
          if (totalSteps && Number.isFinite(totalSteps)) setModule1TotalSteps(totalSteps)
          setModule1AwaitingConfirm(Boolean(done && awaiting))

          const confirmedDefinition =
            typeof nextData === 'object' && nextData && 'confirmed_definition' in nextData ? String(nextData.confirmed_definition ?? '') : ''
          if (confirmedDefinition && confirmedDefinition.includes('🚩') && confirmedDefinition.includes('问题定义确认')) {
            setModule1Definition(confirmedDefinition)
            setF1Confirmed(true)
          }

          if (assistant) {
            setChats((prev) => {
              const arr = [...(prev.f1 ?? [])]
              const idx = arr.length - 1
              if (idx >= 0 && arr[idx]?.role === 'assistant') arr[idx] = { ...arr[idx], content: assistant }
              return { ...prev, f1: arr }
            })
          }
          const aiEndTs = Date.now()
          f1TimingRef.current.aiTotalMs += Math.max(0, aiEndTs - aiStartTs)
          f1TimingRef.current.aiCount += 1
          f1TimingRef.current.lastAiDoneAt = aiEndTs
          await persistF1Analytics()
          return
        }

        const aiStartTs = Date.now()
        let nextResp = await fetch('/ecm/module1/next_stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: module1SessionId, user_input: text, userId: currentUser?.id }),
        })
        if (!nextResp.ok) {
          const errText = await nextResp.text().catch(() => '')
          if (nextResp.status === 404) {
            const startResp = await fetch('/ecm/module1/start', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ question: text }),
            })
            const startData: unknown = await startResp.json().catch(() => null)
            if (startResp.ok) {
              const sid =
                typeof startData === 'object' && startData && 'session_id' in startData
                  ? String((startData as { session_id?: unknown }).session_id ?? '')
                  : ''
              if (sid) {
                setModule1SessionId(sid)
                setModule1Step(1)
                setModule1AwaitingConfirm(false)
                setModule1TotalSteps(5)
                nextResp = await fetch('/ecm/module1/next_stream', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ session_id: sid, user_input: text, userId: currentUser?.id }),
                })
              }
            }
          }
          if (!nextResp.ok) {
            const retryErr = await nextResp.text().catch(() => '')
            throw new Error(retryErr || errText || 'stream request failed')
          }
        }

        // insert an assistant placeholder, then stream into it
        const assistantIdx = (chats.f1 ?? []).length + 1
        setChats((prev) => ({ ...prev, f1: [...(prev.f1 ?? []), { role: 'assistant', content: '', ts: aiStartTs }] }))

        let finalPayload: any = null
        await readSse(
          nextResp,
          (delta) => {
            setChats((prev) => {
              const arr = [...(prev.f1 ?? [])]
              const idx = Math.min(arr.length - 1, assistantIdx)
              if (idx >= 0 && arr[idx] && arr[idx].role === 'assistant') {
                arr[idx] = { ...arr[idx], content: (arr[idx].content ?? '') + delta }
              }
              return { ...prev, f1: arr }
            })
          },
          (data) => {
            finalPayload = data
          },
        )

        const nextData: any = finalPayload
        const done = typeof nextData === 'object' && nextData && 'done' in nextData ? Boolean(nextData.done) : false
        const awaiting =
          typeof nextData === 'object' && nextData && 'awaiting_confirm' in nextData ? Boolean(nextData.awaiting_confirm) : false
        const step = typeof nextData === 'object' && nextData && 'step' in nextData ? Number(nextData.step) : null
        const totalSteps =
          typeof nextData === 'object' && nextData && 'total_steps' in nextData ? Number(nextData.total_steps) : null
        const nextModule = typeof nextData === 'object' && nextData && 'next' in nextData ? String(nextData.next ?? '') : ''

        if (step && Number.isFinite(step)) setModule1Step(step)
        if (totalSteps && Number.isFinite(totalSteps)) setModule1TotalSteps(totalSteps)
        setModule1AwaitingConfirm(Boolean(done && awaiting))

        const confirmedDefinition =
          typeof nextData === 'object' && nextData && 'confirmed_definition' in nextData
            ? String(nextData.confirmed_definition ?? '')
            : ''
        if (confirmedDefinition && confirmedDefinition.includes('🚩') && confirmedDefinition.includes('问题定义确认')) {
          setModule1Definition(confirmedDefinition)
          setF1Confirmed(true)
        }

        // 自动衔接：Function 1 结束（确认）后，立刻自动执行 Function 2 的第一次输出（并触发 Function 3 提炼）
        if (done && !awaiting && nextModule === 'module2' && !module2SessionId) {
          f1TimingRef.current.leftAt = Date.now()
          const def = confirmedDefinition || module1Definition || ''
          if (def) {
            try {
              if (!f2TimingRef.current.enteredAt) {
                // Starting Function 2 (auto) -> reset Function 2 timing counters.
                f2TimingRef.current.enteredAt = Date.now()
                f2TimingRef.current.leftAt = 0
                f2TimingRef.current.lastAiDoneAt = 0
                f2TimingRef.current.thinkingTotalMs = 0
                f2TimingRef.current.thinkingCount = 0
                f2TimingRef.current.aiTotalMs = 0
                f2TimingRef.current.aiCount = 0
              }
              setChats((prev) => ({ ...prev, f2: [...(prev.f2 ?? []), { role: 'assistant', content: '' }] }))
              const f2AiStartTs = Date.now()
              const resp2 = await fetch('/ecm/module2/start_stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  definition: def,
                  module1_session_id: module1SessionId,
                  userId: currentUser?.id,
                }),
              })
              if (!resp2.ok) throw new Error(await resp2.text().catch(() => ''))

              let final2: any = null
              await readSse(
                resp2,
                (delta) => {
                  setChats((prev) => {
                    const arr = [...(prev.f2 ?? [])]
                    const idx = arr.length - 1
                    if (idx >= 0 && arr[idx]?.role === 'assistant') {
                      arr[idx] = { ...arr[idx], content: (arr[idx].content ?? '') + delta }
                    }
                    return { ...prev, f2: arr }
                  })
                  scrollToBottom('f2')
                },
                (data) => {
                  final2 = data
                },
              )
              const f2AiEndTs = Date.now()
              f2TimingRef.current.aiTotalMs += Math.max(0, f2AiEndTs - f2AiStartTs)
              f2TimingRef.current.aiCount += 1
              f2TimingRef.current.lastAiDoneAt = f2AiEndTs

              if (final2 && typeof final2 === 'object') {
                const sid2 = 'session_id' in final2 ? String(final2.session_id ?? '') : ''
                const step2 = 'step' in final2 ? Number(final2.step) : null
                const total2 = 'total_steps' in final2 ? Number(final2.total_steps) : null
                const assistant2 = 'assistant' in final2 ? String(final2.assistant ?? '') : ''
                const meta2 = 'meta' in final2 ? (final2 as { meta?: unknown }).meta : null

                setModule2SessionId(sid2 || null)
                if (step2 && Number.isFinite(step2)) setModule2Step(step2)
                if (total2 && Number.isFinite(total2)) setModule2TotalSteps(total2)

                // 用 final 的 display_text 兜底覆盖
                if (assistant2) {
                  setChats((prev) => {
                    const arr = [...(prev.f2 ?? [])]
                    const idx = arr.length - 1
                    if (idx >= 0 && arr[idx]?.role === 'assistant') arr[idx] = { ...arr[idx], content: assistant2 }
                    return { ...prev, f2: arr }
                  })
                }

                if (meta2 && typeof meta2 === 'object') {
                  const m = meta2 as { tags?: unknown; quote?: unknown; hook?: unknown }
                  const parsedMeta: Module2Meta = {
                    tags: Array.isArray(m.tags) ? (m.tags as unknown[]).map(String) : [],
                    quote: m.quote == null ? null : String(m.quote),
                    hook: m.hook == null ? null : String(m.hook),
                  }
                  const sig = JSON.stringify({ tags: parsedMeta.tags, quote: parsedMeta.quote, hook: parsedMeta.hook })
                  if (module2LastExtractSig !== sig) {
                    const displayStep = (module2DisplayStep ?? 0) + 1
                    appendModule2MetaToNotes(parsedMeta, displayStep)
                    setModule2DisplayStep(displayStep)
                    setModule2LastExtractSig(sig)
                  }
                }
              }
            } catch {
              // 自动衔接失败时静默（不阻塞 Function 1）
            }
          }
        }
        const aiEndTs = Date.now()
        f1TimingRef.current.aiTotalMs += Math.max(0, aiEndTs - aiStartTs)
        f1TimingRef.current.aiCount += 1
        f1TimingRef.current.lastAiDoneAt = aiEndTs
        await persistF1Analytics()
        return
      }

      // Function 2 uses ECM Module2 exploration loop (requires confirmed definition).
      if (key === 'f2') {
        const userTs = Date.now()
        // 新开一次 Function 2 探索：重置时间统计，避免上一次残留影响平均值
        if (!module2SessionId) {
          f2TimingRef.current.enteredAt = userTs
          f2TimingRef.current.leftAt = 0
          f2TimingRef.current.lastAiDoneAt = 0
          f2TimingRef.current.thinkingTotalMs = 0
          f2TimingRef.current.thinkingCount = 0
          f2TimingRef.current.aiTotalMs = 0
          f2TimingRef.current.aiCount = 0
        }
        if (!f2TimingRef.current.enteredAt) f2TimingRef.current.enteredAt = userTs
        if (f2TimingRef.current.lastAiDoneAt > 0) {
          f2TimingRef.current.thinkingTotalMs += Math.max(0, userTs - f2TimingRef.current.lastAiDoneAt)
          f2TimingRef.current.thinkingCount += 1
        }
        const f2Now = chats.f2 ?? []
        const { nodeDepth } = buildF2NodeMaps(f2Now)
        const lastAssistantNodeId = [...f2Now].reverse().find((m) => m.role === 'assistant' && m.nodeId)?.nodeId ?? null
        const parentId = action === 'followup' ? lastAssistantNodeId : (module2MainNodeId ?? module2RootNodeId ?? null)
        const depth = computeF2Depth(parentId, nodeDepth)
        const userMsg: ChatMessage = { role: 'user', content: text, parentId, depth, action, ts: userTs }

        // If already finished (or Function 4 already has content), do not trigger module2 regeneration; just guide user.
        const f2LikelyFinished = f2Finished
        if (f2LikelyFinished) {
          setChats((prev) => ({
            ...prev,
            f2: [...(prev.f2 ?? []), userMsg, { role: 'assistant', content: 'Function 2 已完成。你可以继续查看 Function 4（并在需要时进入 Function 5）。' }],
          }))
          return
        }

        setChats((prev) => ({ ...prev, f2: [...(prev.f2 ?? []), userMsg] }))

        const derivedDefinition =
          !module1Definition
            ? (() => {
                const lastF1Assistant = [...(chats.f1 ?? [])]
                  .reverse()
                  .find((m) => m?.role === 'assistant' && typeof m.content === 'string' && m.content.includes('🚩问题定义确认'))
                const t = lastF1Assistant?.content ?? ''
                const idx = t.indexOf('这个定义准确吗')
                const head = idx > 0 ? t.slice(0, idx) : t
                const trimmed = head.trim()
                return trimmed.includes('🚩问题定义确认') ? trimmed : null
              })()
            : null

        const effectiveModule1Definition = module1Definition ?? derivedDefinition

        if (!effectiveModule1Definition) {
          setChats((prev) => ({
            ...prev,
            f2: [
              ...(prev.f2 ?? []),
              {
                role: 'assistant',
                content: '请先在 Function 1 完成“🚩问题定义确认”，并输入「确认」后再开始 Function 2。',
              },
            ],
          }))
          return
        }

        // module2 session 在后端是内存态：如果后端进程重启/丢失，会导致 404 session not found。
        // 这里做一次“自动重建”，确保 Function 2 的回复/追问都能继续运行。
        let isStart = !module2SessionId
        let url = isStart ? '/ecm/module2/start_stream' : '/ecm/module2/next_stream'
        let payload = isStart
          ? {
              definition: effectiveModule1Definition,
              module1_session_id: module1SessionId,
              userId: currentUser?.id,
              action: 'submit',
              parent_id: module2RootNodeId,
            }
          : { session_id: module2SessionId, user_input: text, userId: currentUser?.id, action, parent_id: parentId }

        const f2AiStartTs = Date.now()
        let nextResp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
        if (!nextResp.ok) {
          const errText = await nextResp.text().catch(() => '')
          // 只做一次重试，避免无限循环；重建后走 start_stream（从 Step 1 重新生成）。
          if (nextResp.status === 404 && !isStart) {
            try {
              setModule2SessionId(null)
              setModule2RootNodeId(null)
              setModule2MainNodeId(null)
              setModule2Step(null)
              setModule2LastExtractSig(null)
              setModule2DisplayStep(null)

              isStart = true
              url = '/ecm/module2/start_stream'
              payload = {
                definition: effectiveModule1Definition,
                module1_session_id: module1SessionId,
                userId: currentUser?.id,
                action: 'submit',
                parent_id: null,
              }

              nextResp = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
              })
              // if retry ok: continue; if retry still fail: handled below
            } catch {
              // fall through to outer error handling
            }
          }

          if (!nextResp.ok) {
            const retryText = await nextResp.text().catch(() => '')
            throw new Error(retryText || errText || 'stream request failed')
          }
        }

        setChats((prev) => ({ ...prev, f2: [...(prev.f2 ?? []), { role: 'assistant', content: '', parentId, depth, action }] }))

        // 流式过滤：跳过“📌 ... 👉”之间的笔记卡片块（避免 Function 2 显示笔记卡片）
        let filterMode: 'pass' | 'skip' = 'pass'
        let carry = ''
        const filterDelta = (delta: string) => {
          let t = carry + delta
          carry = ''
          let out = ''
          while (t.length) {
            if (filterMode === 'pass') {
              const i = t.indexOf('📌')
              if (i < 0) {
                out += t
                t = ''
              } else {
                out += t.slice(0, i)
                t = t.slice(i)
                filterMode = 'skip'
              }
            } else {
              const j = t.indexOf('👉')
              if (j < 0) {
                carry = t.slice(-3)
                t = ''
              } else {
                t = t.slice(j)
                filterMode = 'pass'
              }
            }
          }
          return out
        }

        let finalPayload: any = null
        await readSse(
          nextResp,
          (delta) => {
            const shown = filterDelta(delta)
            if (!shown) return
            setChats((prev) => {
              const arr = [...(prev.f2 ?? [])]
              const idx = arr.length - 1
              if (idx >= 0 && arr[idx]?.role === 'assistant') {
                arr[idx] = { ...arr[idx], content: (arr[idx].content ?? '') + shown }
              }
              return { ...prev, f2: arr }
            })
            scrollToBottom('f2')
          },
          (data) => {
            finalPayload = data
          },
        )
        const f2AiEndTs = Date.now()
        f2TimingRef.current.aiTotalMs += Math.max(0, f2AiEndTs - f2AiStartTs)
        f2TimingRef.current.aiCount += 1
        f2TimingRef.current.lastAiDoneAt = f2AiEndTs

        const nextData: any = finalPayload
        const sid =
          typeof nextData === 'object' && nextData && 'session_id' in nextData ? String(nextData.session_id ?? '') : ''
        const assistant =
          typeof nextData === 'object' && nextData && 'assistant' in nextData ? String(nextData.assistant ?? '') : ''
        const step =
          typeof nextData === 'object' && nextData && 'step' in nextData ? Number(nextData.step) : null
        const totalSteps =
          typeof nextData === 'object' && nextData && 'total_steps' in nextData ? Number(nextData.total_steps) : null
        const meta =
          typeof nextData === 'object' && nextData && 'meta' in nextData ? (nextData as { meta?: unknown }).meta : null

        if (isStart) setModule2SessionId(sid || null)
        if (step && Number.isFinite(step)) setModule2Step(step)
        if (totalSteps && Number.isFinite(totalSteps)) setModule2TotalSteps(totalSteps)

        const nodeId =
          typeof nextData === 'object' && nextData && 'node_id' in nextData ? String(nextData.node_id ?? '') : ''
        const parentIdResp =
          typeof nextData === 'object' && nextData && 'parent_id' in nextData ? String(nextData.parent_id ?? '') : ''
        if (!module2RootNodeId && parentIdResp) setModule2RootNodeId(parentIdResp)
        if (action === 'submit' && nodeId) setModule2MainNodeId(nodeId)

        // 用 final 的 display_text 替换占位内容（避免过滤器边界导致残留）
        if (assistant) {
          setChats((prev) => {
            const arr = [...(prev.f2 ?? [])]
            const idx = arr.length - 1
            if (idx >= 0 && arr[idx]?.role === 'assistant')
              arr[idx] = { ...arr[idx], content: assistant, nodeId: nodeId || arr[idx].nodeId, parentId: parentIdResp || arr[idx].parentId }
            return { ...prev, f2: arr }
          })
        }

        if (meta && typeof meta === 'object') {
          const m = meta as { tags?: unknown; quote?: unknown; hook?: unknown }
          const parsedMeta: Module2Meta = {
            tags: Array.isArray(m.tags) ? (m.tags as unknown[]).map(String) : [],
            quote: m.quote == null ? null : String(m.quote),
            hook: m.hook == null ? null : String(m.hook),
          }
          const sig = JSON.stringify({ tags: parsedMeta.tags, quote: parsedMeta.quote, hook: parsedMeta.hook })
          if (module2LastExtractSig !== sig) {
            const displayStep = (module2DisplayStep ?? 0) + 1
            appendModule2MetaToNotes(parsedMeta, displayStep)
            setModule2DisplayStep(displayStep)
            setModule2LastExtractSig(sig)
          }
        }

        // 当模块二已到最后一步且用户输入「确认」时：标记模块二完成，并自动生成模块四的第一轮洞察报告
        const effectiveModule2Sid = module2SessionId || (typeof nextData === 'object' && nextData && 'session_id' in nextData ? String(nextData.session_id ?? '') : '')
        // Function 2 结束（输入/点击“确认”）后自动进入 Function 4。
        // module1_session_id 在后端是内存态，服务重启后可能丢失；因此同时把“已确认的问题定义”文本传给后端兜底。
        if (step && Number.isFinite(step) && step >= 5 && text.includes('确认') && effectiveModule1Definition && effectiveModule2Sid) {
          setF2Finished(true)
          f2TimingRef.current.leftAt = Date.now()
          void persistF2Analytics()
          try {
            if (!f4TimingRef.current.enteredAt) f4TimingRef.current.enteredAt = Date.now()
            f4TimingRef.current.reportGenCount += 1
            const resp = await fetch('/ecm/module4/generate_stream', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                module1_session_id: module1SessionId,
                // Back-end can fall back to this when module1 session state is missing.
                module1_definition: effectiveModule1Definition,
                module2_session_id: effectiveModule2Sid,
                module2_history: (chatsRef.current.f2 ?? []).map((m) => ({ role: m.role, content: m.content })),
                force: true,
                user_input: text,
                userId: currentUser?.id,
              }),
            })
            if (!resp.ok) throw new Error(await resp.text().catch(() => ''))
            setChats((prev) => ({ ...prev, f4: [...(prev.f4 ?? []), { role: 'assistant', content: '' }] }))
            let final4: any = null
            await readSse(
              resp,
              (delta) => {
                setChats((prev) => {
                  const arr = [...(prev.f4 ?? [])]
                  const idx = arr.length - 1
                  if (idx >= 0 && arr[idx]?.role === 'assistant') arr[idx] = { ...arr[idx], content: (arr[idx].content ?? '') + delta }
                  return { ...prev, f4: arr }
                })
                scrollToBottom('f4')
              },
              (data) => {
                final4 = data
              },
            )
            if (final4 && typeof final4 === 'object') {
              const sid4 = 'session_id' in final4 ? String(final4.session_id ?? '') : ''
              const state4 = 'state' in final4 ? String(final4.state ?? '') : ''
              setModule4SessionId(sid4 || null)
              setModule4AwaitingConfirm(state4 === 'awaiting_confirm')
              const reportMd =
                'assistant' in final4 && final4.assistant != null ? String((final4 as { assistant?: unknown }).assistant ?? '') : ''
              if (reportMd.trim()) module4ReportTextRef.current = reportMd
            }
          } catch {
            // 自动衔接失败时静默
          }
        }
        return
      }

      // Other functions keep direct chat proxy for now.
      if (key === 'f4') {
        setChats((prev) => ({ ...prev, f4: [...(prev.f4 ?? []), { role: 'user', content: text }] }))

        const force = ["总结", "生成笔记", "结束探索"].some((k) => text.includes(k))

        // If already confirmed/finished, avoid any regeneration or prerequisite checks.
        if (f4Confirmed) {
          setChats((prev) => ({
            ...prev,
            f4: [...(prev.f4 ?? []), { role: 'assistant', content: 'Function 4 已完成（已确认洞察报告）。如需继续，请进入 Function 5。' }],
          }))
          return
        }

        const f4HasContent = (chats.f4 ?? []).some((m) => m.role === 'assistant' && m.content.trim())
        if (!module4AwaitingConfirm && f4HasContent && text.includes('确认')) {
          const lastF4Assistant = [...(chats.f4 ?? [])]
            .reverse()
            .find((m) => m.role === 'assistant' && m.content.trim())

          // If Module4 session is missing, generate Function 5 directly from the existing report text.
          if (!module4SessionId && lastF4Assistant?.content?.trim()) {
            setF4Confirmed(true)
            f4TimingRef.current.leftAt = Date.now()
            void persistF4Analytics(lastF4Assistant.content)
            try {
              setChats((prev) => ({ ...prev, f5: [...(prev.f5 ?? []), { role: 'assistant', content: '' }] }))
              if (!f5TimingRef.current.enteredAt) f5TimingRef.current.enteredAt = Date.now()
              const resp5 = await fetch('/ecm/module5/generate_stream_from_report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  module4Definition: module1DefinitionRef.current ?? '',
                  module4ReportMd: lastF4Assistant.content,
                  force: true,
                  user_input: text,
                module5_history: (chatsRef.current.f5 ?? []).map((m) => ({ role: m.role, content: m.content })),
                  userId: currentUser?.id,
                }),
              })
              if (!resp5.ok) throw new Error(await resp5.text().catch(() => ''))
              await readSse(
                resp5,
                (delta) => {
                  setChats((prev) => {
                    const arr = [...(prev.f5 ?? [])]
                    const idx = arr.length - 1
                    if (idx >= 0 && arr[idx]?.role === 'assistant') arr[idx] = { ...arr[idx], content: (arr[idx].content ?? '') + delta }
                    return { ...prev, f5: arr }
                  })
                  scrollToBottom('f5')
                },
                () => {},
              )
              f5TimingRef.current.leftAt = Date.now()
              void persistF5Analytics()
            } catch {
              setChats((prev) => ({
                ...prev,
                f4: [
                  ...(prev.f4 ?? []),
                  { role: 'assistant', content: 'Function 4 已记录，但 Function 5 生成失败。你可以稍后再试或重新触发 Function 4 生成。' },
                ],
              }))
            }
            return
          }

          // Normal case: Module4 session exists or user doesn't need generation.
          setChats((prev) => ({
            ...prev,
            f4: [
              ...(prev.f4 ?? []),
              { role: 'assistant', content: 'Function 4 当前已完成（或无需再次确认）。如需继续，请查看 Function 5。' },
            ],
          }))
          return
        }

        if (!module4SessionId) {
          // Module1 session is server-memory state; reload后可能丢失。
          // 这里允许只要前端已经有“已确认的问题定义文本”，就继续生成 Function 4。
          if (!module2SessionId) {
            setChats((prev) => ({
              ...prev,
              f4: [...(prev.f4 ?? []), { role: 'assistant', content: '请先完成 Function 1（确认）与 Function 2（探索）。' }],
            }))
            return
          }
            if (!f4TimingRef.current.enteredAt) f4TimingRef.current.enteredAt = Date.now()
            f4TimingRef.current.reportGenCount += 1
          const resp = await fetch('/ecm/module4/generate_stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              module1_session_id: module1SessionId,
              module1_definition: module1DefinitionRef.current ?? module1Definition ?? '',
              module2_session_id: module2SessionId,
              module2_history: (chatsRef.current.f2 ?? []).map((m) => ({ role: m.role, content: m.content })),
              force,
              user_input: text,
              userId: currentUser?.id,
            }),
          })
          if (!resp.ok) throw new Error(await resp.text().catch(() => ''))
          setChats((prev) => ({ ...prev, f4: [...(prev.f4 ?? []), { role: 'assistant', content: '' }] }))
          let final4: any = null
          await readSse(
            resp,
            (delta) => {
              setChats((prev) => {
                const arr = [...(prev.f4 ?? [])]
                const idx = arr.length - 1
                if (idx >= 0 && arr[idx]?.role === 'assistant') arr[idx] = { ...arr[idx], content: (arr[idx].content ?? '') + delta }
                return { ...prev, f4: arr }
              })
              scrollToBottom('f4')
            },
            (data) => {
              final4 = data
            },
          )
          if (final4 && typeof final4 === 'object') {
            const sid = 'session_id' in final4 ? String(final4.session_id ?? '') : ''
            const state = 'state' in final4 ? String(final4.state ?? '') : ''
          setModule4SessionId(sid || null)
          setModule4AwaitingConfirm(state === 'awaiting_confirm')
          const reportMd =
            'assistant' in final4 && final4.assistant != null ? String((final4 as { assistant?: unknown }).assistant ?? '') : ''
          if (reportMd.trim()) module4ReportTextRef.current = reportMd
          }
          return
        }

        // 如果还在“等待确认”阶段：
        //  - 输入确认/结束指令：走 /ecm/module4/confirm
        //  - 其他追问：只调用 AI 回答问题（不重生成整份报告）
        if (module4AwaitingConfirm) {
          const confirmTokens = ['确认', 'ok', 'OK', 'Ok', '可以结束了', '结束探索', '结束']
          const isConfirm = confirmTokens.includes(text)

          if (!isConfirm) {
            // Q&A follow-up: do NOT regenerate the whole report.
            const reportMd = (module4ReportTextRef.current ?? '').trim()
            const respQ = await fetch('/api/chat', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                model: 'deepseek-chat',
                messages: [
                  {
                    role: 'system',
                    content: '你是ECM探索导师。用户处在Function 4 已完成但等待确认阶段。用户提出追问时：只回答追问、解释概念或给出针对报告的修订建议；不要重写整份“ECM深度洞察报告”。',
                  },
                  {
                    role: 'user',
                    content: `当前Function 4 报告（供参考，不要全文复述）：\n${reportMd || '(报告文本缺失，请仅基于追问回答)'}\n\n用户追问：${text}`,
                  },
                ],
              }),
            })

            if (!respQ.ok) throw new Error(await respQ.text().catch(() => ''))
            const dataQ: unknown = await respQ.json().catch(() => null)
            if (dataQ && typeof dataQ === 'object' && 'content' in (dataQ as any)) {
              const contentQ = String((dataQ as { content?: unknown }).content ?? '')
              setChats((prev) => ({ ...prev, f4: [...(prev.f4 ?? []), { role: 'assistant', content: contentQ }] }))
              scrollToBottom('f4')
            }
            return
          }

          // Confirm: if backend module4 session is missing (e.g. server restart), fall back to generating Function 5 from existing report text.
          const lastF4Assistant = (chatsRef.current.f4 ?? [])
            .slice()
            .reverse()
            .find((m) => m.role === 'assistant' && (m.content ?? '').trim())?.content
          const reportMd = (module4ReportTextRef.current ?? '').trim() || String(lastF4Assistant ?? '').trim()

          let confirmed = false
          try {
            if (module4SessionId) {
        const resp = await fetch('/ecm/module4/confirm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: module4SessionId, user_input: text }),
        })
        const data: unknown = await resp.json().catch(() => null)
        if (!resp.ok) throw new Error(typeof data === 'string' ? data : JSON.stringify(data))

        const assistant =
                typeof data === 'object' && data && 'assistant' in data ? String((data as { assistant?: unknown }).assistant ?? '') : ''
        const state =
          typeof data === 'object' && data && 'state' in data ? String((data as { state?: unknown }).state ?? '') : ''
              const nextModule4 =
                typeof data === 'object' && data && 'next' in data ? String((data as { next?: unknown }).next ?? '') : ''

        setModule4AwaitingConfirm(state === 'awaiting_confirm')
        if (assistant) setChats((prev) => ({ ...prev, f4: [...(prev.f4 ?? []), { role: 'assistant', content: assistant }] }))

              if (state === 'confirmed' && nextModule4 === 'module5') {
                confirmed = true
              }
            }
          } catch {
            // ignore and fallback below
          }

          if (confirmed && module4SessionId) {
            setF4Confirmed(true)
            f4TimingRef.current.leftAt = Date.now()
            void persistF4Analytics(reportMd)
            try {
              if (!f5TimingRef.current.enteredAt) {
                f5TimingRef.current.enteredAt = Date.now()
                f5TimingRef.current.leftAt = 0
                f5TimingRef.current.userEditCount = 0
                f5TimingRef.current.clickCount = 0
                f5TimingRef.current.newCount = 0
              }
              const resp5 = await fetch('/ecm/module5/generate_stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  module4_session_id: module4SessionId,
                  user_input: text,
                  force: true,
                  module5_history: (chatsRef.current.f5 ?? []).map((m) => ({ role: m.role, content: m.content })),
                  userId: currentUser?.id,
                }),
              })
              if (!resp5.ok) throw new Error(await resp5.text().catch(() => ''))
              setChats((prev) => ({ ...prev, f5: [...(prev.f5 ?? []), { role: 'assistant', content: '' }] }))
              await readSse(
                resp5,
                (delta) => {
                  setChats((prev) => {
                    const arr = [...(prev.f5 ?? [])]
                    const idx = arr.length - 1
                    if (idx >= 0 && arr[idx]?.role === 'assistant') arr[idx] = { ...arr[idx], content: (arr[idx].content ?? '') + delta }
                    return { ...prev, f5: arr }
                  })
                  scrollToBottom('f5')
                },
                () => {},
              )
              f5TimingRef.current.leftAt = Date.now()
              void persistF5Analytics()
            } catch {
              // ignore automatic connect errors
            }
            return
          }

          // Fallback generation (session not found).
          if (!reportMd) {
            setChats((prev) => ({
              ...prev,
              f4: [...(prev.f4 ?? []), { role: 'assistant', content: 'Function 4 报告文本缺失，无法从当前追问生成 Function 5。请先重新生成 Function 4。' }],
            }))
            return
          }

          setF4Confirmed(true)
          f4TimingRef.current.leftAt = Date.now()
          void persistF4Analytics(reportMd)
          try {
            if (!f5TimingRef.current.enteredAt) {
              f5TimingRef.current.enteredAt = Date.now()
              f5TimingRef.current.leftAt = 0
              f5TimingRef.current.userEditCount = 0
              f5TimingRef.current.clickCount = 0
              f5TimingRef.current.newCount = 0
            }
            setChats((prev) => ({
              ...prev,
              f5: [...(prev.f5 ?? []), { role: 'user', content: text }, { role: 'assistant', content: '' }],
            }))
            const resp5 = await fetch('/ecm/module5/generate_stream_from_report', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                module4Definition: module1DefinitionRef.current ?? '',
                module4ReportMd: reportMd,
                force: true,
                user_input: text,
                module5_history: (chatsRef.current.f5 ?? []).map((m) => ({ role: m.role, content: m.content })),
                userId: currentUser?.id,
              }),
            })
            if (!resp5.ok) throw new Error(await resp5.text().catch(() => ''))
            await readSse(
              resp5,
              (delta) => {
                setChats((prev) => {
                  const arr = [...(prev.f5 ?? [])]
                  const idx = arr.length - 1
                  if (idx >= 0 && arr[idx]?.role === 'assistant') arr[idx] = { ...arr[idx], content: (arr[idx].content ?? '') + delta }
                  return { ...prev, f5: arr }
                })
                scrollToBottom('f5')
              },
              () => {},
            )
            f5TimingRef.current.leftAt = Date.now()
            void persistF5Analytics()
          } catch {
            // ignore automatic connect errors
          }
          return
        }

        // 已经确认完毕，再次输入则视为微调 / 追加说明，强制重新生成新的洞察报告
        if (!module2SessionId) {
          setChats((prev) => ({
            ...prev,
            f4: [...(prev.f4 ?? []), { role: 'assistant', content: '当前 Function 1/2 的会话信息缺失，无法为 Function 4 进行微调重生成。你可以重新开始 Function 1/2 或重新加载对话后再试。' }],
          }))
          return
        }
        if (!f4TimingRef.current.enteredAt) f4TimingRef.current.enteredAt = Date.now()
        f4TimingRef.current.reportGenCount += 1
        const regenResp = await fetch('/ecm/module4/generate_stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            module1_session_id: module1SessionId,
            module1_definition: module1DefinitionRef.current ?? module1Definition ?? '',
            module2_session_id: module2SessionId,
            module2_history: (chatsRef.current.f2 ?? []).map((m) => ({ role: m.role, content: m.content })),
            force: true,
            user_input: text,
            userId: currentUser?.id,
          }),
        })
        if (!regenResp.ok) throw new Error(await regenResp.text().catch(() => ''))
        setChats((prev) => ({ ...prev, f4: [...(prev.f4 ?? []), { role: 'assistant', content: '' }] }))
        let final4: any = null
        await readSse(
          regenResp,
          (delta) => {
            setChats((prev) => {
              const arr = [...(prev.f4 ?? [])]
              const idx = arr.length - 1
              if (idx >= 0 && arr[idx]?.role === 'assistant') arr[idx] = { ...arr[idx], content: (arr[idx].content ?? '') + delta }
              return { ...prev, f4: arr }
            })
            scrollToBottom('f4')
          },
          (data) => {
            final4 = data
          },
        )
        if (final4 && typeof final4 === 'object') {
          const sid = 'session_id' in final4 ? String(final4.session_id ?? '') : ''
          const state = 'state' in final4 ? String(final4.state ?? '') : ''
          setModule4SessionId(sid || null)
          setModule4AwaitingConfirm(state === 'awaiting_confirm')
          const reportMd =
            'assistant' in final4 && final4.assistant != null ? String((final4 as { assistant?: unknown }).assistant ?? '') : ''
          if (reportMd.trim()) module4ReportTextRef.current = reportMd
        }
        return
      }

      if (key === 'f5') {
        setChats((prev) => ({ ...prev, f5: [...(prev.f5 ?? []), { role: 'user', content: text }] }))

        if (!module4SessionId) {
          const lastF4Assistant = [...(chats.f4 ?? [])]
            .reverse()
            .find((m) => m.role === 'assistant' && m.content.trim())
          if (!lastF4Assistant?.content?.trim()) {
          setChats((prev) => ({
            ...prev,
            f5: [...(prev.f5 ?? []), { role: 'assistant', content: '请先在 Function 4 生成并确认洞察报告，然后再进入 Function 5。' }],
          }))
          return
        }

          setChats((prev) => ({ ...prev, f5: [...(prev.f5 ?? []), { role: 'assistant', content: '' }] }))
          const trimmed = (text ?? '').trim()
          if (!f5TimingRef.current.enteredAt) {
            f5TimingRef.current.enteredAt = Date.now()
            f5TimingRef.current.leftAt = 0
            f5TimingRef.current.userEditCount = 0
            f5TimingRef.current.clickCount = 0
            f5TimingRef.current.newCount = 0
          }
          f5TimingRef.current.userEditCount += 1
          if (/^[ABC]$/.test(trimmed)) f5TimingRef.current.clickCount += 1
          else f5TimingRef.current.newCount += 1
          try {
            const resp = await fetch('/ecm/module5/generate_stream_from_report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                module4Definition: module1DefinitionRef.current ?? '',
                module4ReportMd: lastF4Assistant.content,
                force: true,
                user_input: text,
                module5_history: (chatsRef.current.f5 ?? []).map((m) => ({ role: m.role, content: m.content })),
                userId: currentUser?.id,
              }),
            })
            if (!resp.ok) throw new Error(await resp.text().catch(() => ''))
            await readSse(
              resp,
              (delta) => {
                setChats((prev) => {
                  const arr = [...(prev.f5 ?? [])]
                  const idx = arr.length - 1
                  if (idx >= 0 && arr[idx]?.role === 'assistant') arr[idx] = { ...arr[idx], content: (arr[idx].content ?? '') + delta }
                  return { ...prev, f5: arr }
                })
                scrollToBottom('f5')
              },
              () => {},
            )
            f5TimingRef.current.leftAt = Date.now()
            void persistF5Analytics()
          } catch (e) {
            setErrors((prev) => ({ ...prev, f5: e instanceof Error ? e.message : String(e) }))
          } finally {
            void autoSaveProject()
          }
          return
        }

        const trimmed = (text ?? '').trim()
        if (!f5TimingRef.current.enteredAt) {
          f5TimingRef.current.enteredAt = Date.now()
          f5TimingRef.current.leftAt = 0
          f5TimingRef.current.userEditCount = 0
          f5TimingRef.current.clickCount = 0
          f5TimingRef.current.newCount = 0
        }
        f5TimingRef.current.userEditCount += 1
        if (/^[ABC]$/.test(trimmed)) f5TimingRef.current.clickCount += 1
        else f5TimingRef.current.newCount += 1
        const resp = await fetch('/ecm/module5/generate_stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            module4_session_id: module4SessionId,
            user_input: text,
            force: true,
            module5_history: (chatsRef.current.f5 ?? []).map((m) => ({ role: m.role, content: m.content })),
            userId: currentUser?.id,
          }),
        })
        if (!resp.ok) throw new Error(await resp.text().catch(() => ''))
        // `f5` 已在开头追加了用户消息，这里只追加 assistant 占位，确保 streaming delta 追加到最后一条 assistant。
        setChats((prev) => ({
          ...prev,
          f5: [...(prev.f5 ?? []), { role: 'assistant', content: '' }],
        }))
        await readSse(
          resp,
          (delta) => {
            setChats((prev) => {
              const arr = [...(prev.f5 ?? [])]
              const idx = arr.length - 1
              if (idx >= 0 && arr[idx]?.role === 'assistant') arr[idx] = { ...arr[idx], content: (arr[idx].content ?? '') + delta }
              return { ...prev, f5: arr }
            })
            scrollToBottom('f5')
          },
          () => {},
        )
        // module5 session_id currently not used on client
        f5TimingRef.current.leftAt = Date.now()
        void persistF5Analytics()
        return
      }

      const nextMessages: ChatMessage[] = [...(chats[key] ?? []), { role: 'user', content: text }]
      setChats((prev) => ({ ...prev, [key]: nextMessages }))

      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'deepseek-chat',
          messages: nextMessages,
        }),
      })

      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const details =
          typeof data === 'object' && data && 'details' in data
            ? (data as { details?: unknown }).details
            : data
        throw new Error(typeof details === 'string' ? details : JSON.stringify(details))
      }

      const content =
        typeof data === 'object' && data && 'content' in data
          ? String((data as { content?: unknown }).content ?? '')
          : ''

      setChats((prev) => ({ ...prev, [key]: [...(prev[key] ?? []), { role: 'assistant', content }] }))
    } catch (e) {
      setErrors((prev) => ({ ...prev, [key]: e instanceof Error ? e.message : String(e) }))
      setChats((prev) => ({
        ...prev,
        [key]: [
          ...(prev[key] ?? []),
          {
            role: 'assistant',
            content:
              key === 'f1'
                ? '请求失败：请确认你已启动后端 `start_ecm_backend.bat`，并在 `ecm_backend/.env` 设置 `DEEPSEEK_API_KEY`。'
                : key === 'f2'
                  ? '请求失败：Function 2 会话可能已过期。请稍后重试或重新开始 Function 2。'
                : '请求失败：请确认你已在项目根目录创建 `.env` 并设置 `DEEPSEEK_API_KEY`，然后重新启动开发服务。',
          },
        ],
      }))
    } finally {
      setSendingKey(null)
      // Ensure React state updates (e.g. streaming deltas like Function 5) are flushed
      // before we persist the project, otherwise mentor page may miss latest content.
      await new Promise((r) => {
        if (typeof requestAnimationFrame === 'function') {
          requestAnimationFrame(() => r(true))
        } else {
          setTimeout(() => r(true), 0)
        }
      })
      await new Promise((r) => {
        if (typeof requestAnimationFrame === 'function') {
          requestAnimationFrame(() => r(true))
        } else {
          setTimeout(() => r(true), 0)
        }
      })
      await autoSaveProject()
    }
  }

  return (
    <div className="dashShell studentApp">
      <header className="dashHeader">
        <div className="brandTitle">ECM探索导师</div>
        <div className="brandSub">Function 1–5：对话 / 笔记编辑</div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          {currentUser ? (
            <>
              <button type="button" className="primary" onClick={() => setShowProfileModal(true)}>
                个人资料
              </button>
              <span style={{ fontSize: 12 }}>当前用户：{currentUser.username}</span>
              <input
                style={{ fontSize: 12, padding: '2px 4px', minWidth: 120 }}
                value={currentProjectName}
                onChange={(e) => setCurrentProjectName(e.target.value)}
                placeholder="项目名称"
              />
              <select
                style={{ fontSize: 12 }}
                value={currentProjectId ?? ''}
                onChange={(e) => {
                  const pid = e.target.value
                  if (!pid) {
                    createNewProjectLocal()
                  } else {
                    void loadProjectById(pid)
                  }
                }}
              >
                <option value="">新建项目（空白）</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <input
                style={{ fontSize: 12, padding: '2px 4px', minWidth: 120 }}
                value={currentDialogueName}
                onChange={(e) => setCurrentDialogueName(e.target.value)}
                placeholder="对话名称"
                disabled={!currentProjectId}
              />
              <select
                style={{ fontSize: 12, maxWidth: 180 }}
                value={currentDialogueId ?? ''}
                disabled={!currentProjectId}
                onChange={(e) => {
                  const did = e.target.value
                  if (!currentProjectId) return
                  if (!did) {
                    createNewDialogueLocal()
                  } else {
                    void loadDialogueById(currentProjectId, did)
                  }
                }}
              >
                <option value="">新建对话（空白）</option>
                {dialogues.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
              <button type="button" onClick={() => void saveProject()} disabled={projectSaving}>
                {projectSaving ? '保存中…' : '保存项目'}
              </button>
              <button
                type="button"
                onClick={() => void exportWord()}
                disabled={exportLoading || sendingKey !== null}
              >
                {exportLoading ? '导出中…' : '导出 Word'}
              </button>
            </>
          ) : (
            <>
              <input
                style={{ fontSize: 12, padding: '2px 4px' }}
                placeholder="用户名"
                value={loginForm.username}
                onChange={(e) => setLoginForm((prev) => ({ ...prev, username: e.target.value }))}
              />
              <input
                style={{ fontSize: 12, padding: '2px 4px' }}
                placeholder="密码"
                type="password"
                value={loginForm.password}
                onChange={(e) => setLoginForm((prev) => ({ ...prev, password: e.target.value }))}
              />
              <input
                style={{ fontSize: 12, padding: '2px 4px', marginLeft: 8 }}
                placeholder="验证码"
                value={loginForm.captcha}
                onChange={(e) => setLoginForm((prev) => ({ ...prev, captcha: e.target.value }))}
              />
              <button type="button" onClick={() => void handleLogin()}>
                登录 / 注册
              </button>
              <span style={{ fontSize: 11, opacity: 0.8, marginLeft: 8 }}>
                导师入口：
                <a href="/mentor-admin" style={{ color: '#9ab4ff', marginLeft: 4 }}>
                  查看学生对话
                </a>
                ｜
                <a href="/prompts-admin" style={{ color: '#9ab4ff', marginLeft: 4 }}>
                  修改提示词
                </a>
              </span>
            </>
          )}
        </div>
      </header>

      {!currentUser ? (
      <main className="dashMain">
          <section className="grid">
            <article className="card cardWide">
              <div className="cardTop">
                <div className="cardTitle">请先登录</div>
              </div>
              <div style={{ padding: 16, fontSize: 14 }}>
                <p>请先回到统一登录页选择入口并登录。</p>
                <a href="/" style={{ color: '#9ab4ff' }}>
                  返回登录页
                </a>
                {loginError ? <div className="error">登录错误：{loginError}</div> : null}
              </div>
            </article>
          </section>
        </main>
      ) : (
        <main className="dashMain">
          {exportError ? <div className="error" style={{ marginBottom: 8 }}>导出失败：{exportError}</div> : null}
          {projectError ? <div className="error" style={{ marginBottom: 8 }}>项目错误：{projectError}</div> : null}
        <section className="grid">
          <article className="card cardWide">
            <div className="cardTop">
              <div className="cardTitle">
                {functionCards[0].title}
                <span style={{ opacity: 0.7, fontSize: 12 }}>
                  {module1SessionId ? `会话：${module1SessionId.slice(0, 8)}…` : '未开始'}
                  {module1Step ? `｜Step ${module1Step}/${module1TotalSteps}` : ''}
                  {module1AwaitingConfirm ? '｜等待确认' : ''}
                </span>
              </div>
            </div>

            <div className="chatArea">
              <div className="chatHistory" ref={f1HistoryRef}>
                {(chats.f1 ?? []).length === 0 ? (
                  <div className="chatEmpty">在下方输入主题并发送，即可开始互动对话。</div>
                ) : null}
                {(chats.f1 ?? []).map((m, i) => (
                  <div key={i} className={m.role === 'user' ? 'msg user' : 'msg assistant'}>
                    <div className="msgRole">{m.role === 'user' ? '你' : 'ECM探索导师'}</div>
                    <div className="msgContent">{m.content}</div>
                  </div>
                ))}
              </div>

              <div className="composerRow">
                <textarea
                  className="textarea composer"
                  placeholder={functionCards[0].placeholder}
                  value={inputs.f1}
                  onChange={(e) => updateInput('f1', e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                      e.preventDefault()
                      void sendChat('f1')
                    }
                  }}
                  rows={2}
                  disabled={sendingKey !== null}
                />
                <div className="composerButtons">
                <button className="primary" type="button" onClick={() => void sendChat('f1')} disabled={sendingKey !== null}>
                  {sendingKey === 'f1' ? '发送中…' : '发送'}
                </button>
                <button type="button" onClick={() => clearChat('f1')} disabled={sendingKey !== null || (chats.f1 ?? []).length === 0}>
                  清空
                </button>
                  <button
                    type="button"
                    className="wide"
                    onClick={() => {
                      if (!module1SessionId || sendingKey !== null) return
                      void (async () => {
                        try {
                          const resp = await fetch('/ecm/module1/undo', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ session_id: module1SessionId }),
                          })
                          const data: unknown = await resp.json().catch(() => null)
                          if (!resp.ok) {
                            const msg =
                              typeof data === 'object' && data && 'error' in data
                                ? String((data as { error?: unknown }).error ?? '')
                                : '撤销失败'
                            throw new Error(msg)
                          }
                          const step =
                            typeof data === 'object' && data && 'step' in data ? Number((data as { step?: unknown }).step) : null
                          if (step && Number.isFinite(step)) setModule1Step(step)
                          setModule1AwaitingConfirm(false)
                          setF1Confirmed(false)
                          setModule1Definition(null)
                          // 删除最近一轮 user+assistant（如果存在）
                          setChats((prev) => ({ ...prev, f1: (prev.f1 ?? []).slice(0, Math.max(0, (prev.f1 ?? []).length - 2)) }))
                        } catch (e) {
                          setErrors((prev) => ({ ...prev, f1: e instanceof Error ? e.message : String(e) }))
                        }
                      })()
                    }}
                    disabled={sendingKey !== null || !module1SessionId || (chats.f1 ?? []).length < 2}
                  >
                    撤销上一步
                </button>
                </div>
              </div>
              {errors.f1 ? <div className="error">错误：{errors.f1}</div> : null}
            </div>
          </article>

          <div className="pairRow">
            <article className="card">
              <div className="cardTop">
                <div className="cardTitle">
                  {functionCards[1].title}
                  <span style={{ opacity: 0.7, fontSize: 12 }}>
                    {module2SessionId ? `会话：${module2SessionId.slice(0, 8)}…` : '未开始'}
                    {module2Step ? `｜Step ${module2Step}/${module2TotalSteps}` : ''}
                  </span>
                </div>
              </div>

              <div className="chatArea compact">
                <div className="chatHistory compact" ref={f2HistoryRef}>
                  {(chats.f2 ?? []).length === 0 ? <div className="chatEmpty">在这里进行互动对话（板块 2）。</div> : null}
                  {(() => {
                    const msgs = chats.f2 ?? []
                    return msgs
                      .map((m, i) => {
                        const indent = m.action === 'followup' ? 24 : 0
                        return (
                          <div key={i} className={m.role === 'user' ? 'msg user' : 'msg assistant'} style={{ marginLeft: indent }}>
                            <div className="msgRole">
                              <span>{m.role === 'user' ? '你' : 'ECM探索导师'}</span>
                              {m.action === 'followup' ? <span style={{ fontSize: 11, opacity: 0.6, marginLeft: 8 }}>（追问）</span> : null}
                            </div>
                      <div className="msgContent">{m.content}</div>
                    </div>
                        )
                      })
                  })()}
                </div>
                <div className="composerRow">
                  <textarea
                    className="textarea composer"
                    placeholder={functionCards[1].placeholder}
                    value={inputs.f2}
                    onChange={(e) => updateInput('f2', e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                        e.preventDefault()
                        void sendChat('f2', { action: 'submit' })
                      }
                    }}
                    rows={2}
                    disabled={sendingKey !== null}
                  />
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {(() => {
                      const lastF2Assistant = [...(chats.f2 ?? [])]
                        .slice()
                        .reverse()
                        .find((m) => m.role === 'assistant' && (m.content ?? '').trim())?.content
                      const opts = parseF2ABCOptions(String(lastF2Assistant ?? ''))
                      if (!opts) return null
                      const canPick =
                        sendingKey === null && !f2Finished && Boolean(module2SessionId) && Boolean(module1SessionId)
                      return (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 6 }}>
                          <button
                            type="button"
                            className="primary"
                            onClick={() => void sendChat('f2', { action: 'submit' }, opts.A)}
                            disabled={!canPick}
                            title={opts.A}
                            style={{ fontSize: 11 }}
                          >
                            A
                          </button>
                          <button
                            type="button"
                            className="primary"
                            onClick={() => void sendChat('f2', { action: 'submit' }, opts.B)}
                            disabled={!canPick}
                            title={opts.B}
                            style={{ fontSize: 11 }}
                          >
                            B
                          </button>
                          <button
                            type="button"
                            className="primary"
                            onClick={() => void sendChat('f2', { action: 'submit' }, opts.C)}
                            disabled={!canPick}
                            title={opts.C}
                            style={{ fontSize: 11 }}
                          >
                            C
                  </button>
                </div>
                      )
                    })()}
                    <div className="composerButtons">
                    <button className="primary" type="button" onClick={() => void sendChat('f2', { action: 'submit' })} disabled={sendingKey !== null}>
                      {sendingKey === 'f2' ? '发送中…' : '回复'}
                  </button>
                    <button type="button" onClick={() => void sendChat('f2', { action: 'followup' })} disabled={sendingKey !== null}>
                      追问
                    </button>
                    <button
                      type="button"
                      className="primary"
                      onClick={() => void sendChat('f2', { action: 'followup' }, '确认')}
                      disabled={
                        sendingKey !== null ||
                        f2Finished ||
                        !module2SessionId ||
                        !module1SessionId ||
                        Number(module2Step ?? 0) < 5
                      }
                      title="结束 Function 2（至少完成 5 步后可用）"
                    >
                      结束
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (!module2SessionId || sendingKey !== null) return
                        void (async () => {
                          try {
                            const resp = await fetch('/ecm/module2/undo', {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ session_id: module2SessionId }),
                            })
                            const data: unknown = await resp.json().catch(() => null)
                            if (!resp.ok) {
                              const msg =
                                typeof data === 'object' && data && 'error' in data
                                  ? String((data as { error?: unknown }).error ?? '')
                                  : JSON.stringify(data)
                              throw new Error(msg)
                            }
                            const step =
                              typeof data === 'object' && data && 'step' in data ? Number((data as { step?: unknown }).step) : null
                            const totalSteps =
                              typeof data === 'object' && data && 'total_steps' in data
                                ? Number((data as { total_steps?: unknown }).total_steps)
                                : null
                            if (step && Number.isFinite(step)) setModule2Step(step)
                            if (totalSteps && Number.isFinite(totalSteps)) setModule2TotalSteps(totalSteps)
                            setModule2LastExtractSig(null)
                            setModule2DisplayStep(null)
                            setChats((prev) => {
                              const arr = prev.f2 ?? []
                              const cut = arr.length >= 2 ? arr.length - 2 : Math.max(0, arr.length - 1)
                              return { ...prev, f2: arr.slice(0, cut) }
                            })
                          } catch (e) {
                            setErrors((prev) => ({ ...prev, f2: e instanceof Error ? e.message : String(e) }))
                          }
                        })()
                      }}
                      disabled={sendingKey !== null || !module2SessionId || (chats.f2 ?? []).length < 2}
                    >
                      撤销上一步
                    </button>
                  <button
                    type="button"
                    onClick={() => clearChat('f2')}
                    disabled={sendingKey !== null || (chats.f2 ?? []).length === 0}
                  >
                    清空对话
                  </button>
                    </div>
                  </div>
                </div>
                {errors.f2 ? <div className="error">错误：{errors.f2}</div> : null}
              </div>
            </article>

            <article className="card">
              <div className="cardTop">
                <div className="cardTitle">{functionCards[2].title}</div>
              </div>

              <div className="noteArea">
                <textarea
                  className="textarea noteEditor"
                  placeholder="Function 2 每一步的提炼（Tags/金句/钩子）会自动写到这里。你也可以自由编辑并保存（自动本地保存）。"
                  value={noteText}
                  onChange={(e) => persistNoteText(e.target.value)}
                  rows={10}
                />
                <div className="noteHint">提示：此文本框内容会保存到“项目存档”，随项目切换。</div>
              </div>
            </article>
          </div>

          <div className="pairRow">
            <article className="card">
              <div className="cardTop">
                <div className="cardTitle">{functionCards[3].title}</div>
              </div>

              <div className="chatArea compact">
                <div className="chatHistory compact" ref={f4HistoryRef}>
                  {(chats.f4 ?? []).length === 0 ? <div className="chatEmpty">在这里进行互动对话（板块 4）。</div> : null}
                  {(chats.f4 ?? []).map((m, i) => (
                    <div key={i} className={m.role === 'user' ? 'msg user' : 'msg assistant'}>
                      <div className="msgRole">{m.role === 'user' ? '你' : 'ECM探索导师'}</div>
                      <div className="msgContent">
                        {m.role === 'assistant' ? <ReactMarkdown>{m.content}</ReactMarkdown> : m.content}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="composerRow">
                  <textarea
                    className="textarea composer"
                    placeholder={functionCards[3].placeholder}
                    value={inputs.f4}
                    onChange={(e) => updateInput('f4', e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                        e.preventDefault()
                        void sendChat('f4')
                      }
                    }}
                    rows={2}
                    disabled={sendingKey !== null}
                  />
                  <div className="composerButtons vertical">
                  <button className="primary" type="button" onClick={() => void sendChat('f4')} disabled={sendingKey !== null}>
                    {sendingKey === 'f4' ? '发送中…' : '发送'}
                  </button>
                  <button
                    type="button"
                    className="primary"
                    onClick={() => {
                      if (sendingKey !== null || f4Confirmed) return
                      // module1_session_id 是后端内存态；这里允许使用前端“已确认的问题定义”文本兜底。
                      if (!module2SessionId) return
                      void (async () => {
                        setErrors((prev) => ({ ...prev, f4: null }))
                        setSendingKey('f4')
                        updateInput('f4', '')
                        const regenUserInput = (inputs.f4 ?? '').trim() || '请重新生成洞察报告，并保持原有结构。'
                        try {
                          if (!f4TimingRef.current.enteredAt) f4TimingRef.current.enteredAt = Date.now()
                          f4TimingRef.current.reportGenCount += 1

                          const regenResp = await fetch('/ecm/module4/generate_stream', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                              module1_session_id: module1SessionId,
                              module1_definition: module1DefinitionRef.current ?? module1Definition ?? '',
                              module2_session_id: module2SessionId,
                              module2_history: (chatsRef.current.f2 ?? []).map((m) => ({ role: m.role, content: m.content })),
                              force: true,
                              user_input: regenUserInput,
                              userId: currentUser?.id,
                            }),
                          })
                          if (!regenResp.ok) throw new Error(await regenResp.text().catch(() => ''))

                          setChats((prev) => ({
                            ...prev,
                            f4: [
                              ...(prev.f4 ?? []),
                              ...(regenUserInput ? [{ role: 'user', content: regenUserInput } as ChatMessage] : []),
                              { role: 'assistant', content: '' },
                            ],
                          }))

                          let final4: any = null
                          await readSse(
                            regenResp,
                            (delta) => {
                              setChats((prev) => {
                                const arr = [...(prev.f4 ?? [])]
                                const idx = arr.length - 1
                                if (idx >= 0 && arr[idx]?.role === 'assistant') arr[idx] = { ...arr[idx], content: (arr[idx].content ?? '') + delta }
                                return { ...prev, f4: arr }
                              })
                              scrollToBottom('f4')
                            },
                            (data) => {
                              final4 = data
                            },
                          )

                          if (final4 && typeof final4 === 'object') {
                            const sid = 'session_id' in final4 ? String(final4.session_id ?? '') : ''
                            const state = 'state' in final4 ? String(final4.state ?? '') : ''
                            setModule4SessionId(sid || null)
                            setModule4AwaitingConfirm(state === 'awaiting_confirm')
                            const reportMd = 'assistant' in final4 ? String((final4 as { assistant?: unknown }).assistant ?? '') : ''
                            if (reportMd.trim()) module4ReportTextRef.current = reportMd
                          }
                        } catch (e) {
                          setErrors((prev) => ({ ...prev, f4: e instanceof Error ? e.message : String(e) }))
                        } finally {
                          setSendingKey(null)
                          await autoSaveProject()
                        }
                      })()
                    }}
                    disabled={sendingKey !== null || f4Confirmed || !module2SessionId}
                    title="重新生成 Function 4 报告（保持等待确认，可继续追问/修订）"
                  >
                    重新生成
                  </button>
                  <button
                    type="button"
                    className="primary"
                    onClick={() => void sendChat('f4', undefined, '确认')}
                    disabled={sendingKey !== null || f4Confirmed || !module4SessionId || !module4AwaitingConfirm}
                    title="结束 Function 4（确认后进入 Function 5）"
                  >
                    结束
                  </button>
                  <button
                    type="button"
                    onClick={() => clearChat('f4')}
                    disabled={sendingKey !== null || (chats.f4 ?? []).length === 0}
                  >
                    清空对话
                  </button>
                  </div>
                </div>
                {errors.f4 ? <div className="error">错误：{errors.f4}</div> : null}
              </div>
            </article>

            <article className="card">
              <div className="cardTop">
                <div className="cardTitle">{functionCards[4].title}</div>
              </div>

              <div className="chatArea compact">
                <div className="chatHistory compact" ref={f5HistoryRef}>
                  {(chats.f5 ?? []).length === 0 ? <div className="chatEmpty">在这里进行互动对话（板块 5）。</div> : null}
                  {(chats.f5 ?? []).map((m, i) => (
                    <div key={i} className={m.role === 'user' ? 'msg user' : 'msg assistant'}>
                      <div className="msgRole">{m.role === 'user' ? '你' : 'ECM探索导师'}</div>
                      <div className="msgContent">
                        {m.role === 'assistant' ? <ReactMarkdown>{m.content}</ReactMarkdown> : m.content}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="composerRow">
                  <textarea
                    className="textarea composer"
                    placeholder={functionCards[4].placeholder}
                    value={inputs.f5}
                    onChange={(e) => updateInput('f5', e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                        e.preventDefault()
                        void sendChat('f5')
                      }
                    }}
                    rows={2}
                    disabled={sendingKey !== null || f5Done}
                  />
                  <div className="composerButtons vertical">
                  <button className="primary" type="button" onClick={() => void sendChat('f5')} disabled={sendingKey !== null || f5Done}>
                    {sendingKey === 'f5' ? '发送中…' : '发送'}
                  </button>
                  <button
                    type="button"
                    className="primary"
                    onClick={() => {
                      if (sendingKey !== null || f5Done) return
                      f5TimingRef.current.leftAt = Date.now()
                      setF5Done(true)
                      void persistF5Analytics()
                      void autoSaveProject()
                    }}
                    disabled={sendingKey !== null || f5Done || (chats.f5 ?? []).length === 0}
                    title="结束 Function 5（结束后不再生成新的回复）"
                  >
                    结束
                  </button>
                  <button
                    type="button"
                    onClick={() => clearChat('f5')}
                    disabled={sendingKey !== null || (chats.f5 ?? []).length === 0}
                  >
                    清空对话
        </button>
                  </div>
                </div>
                {errors.f5 ? <div className="error">错误：{errors.f5}</div> : null}
              </div>
            </article>
          </div>
        </section>
      </main>
      )}

      {showProfileModal && currentUser ? (
        <div className="profileOverlay" onClick={() => setShowProfileModal(false)}>
          <section className="profileModal card" onClick={(e) => e.stopPropagation()}>
            <div className="cardTop" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="cardTitle">个人资料与偏好设置</div>
              <button type="button" onClick={() => setShowProfileModal(false)} style={{ fontSize: 18 }}>×</button>
            </div>
            <p style={{ fontSize: 12, opacity: 0.85 }}>
              填写后，ECM探索导师会在你的背景下进行个性化引导（用于画像与回答）。
            </p>
            <div className="profileForm">
              <div className="rowEnd" style={{ justifyContent: 'flex-start', gap: 8 }}>
                <button
                  type="button"
                  className="primary"
                  onClick={() => {
                    setPersonaError(null)
                    setPersonaDone(false)
                    setPersonaInput('')
                    setPersonaChats([])
                    setShowPersonaModal(true)
                    void personaTurn('')
                  }}
                  disabled={profileSaving}
                >
                  画像破冰 Persona Builder
                </button>
                {profile.core_motivation || profile.end_goal || profile.learning_habits ? (
                  <span style={{ fontSize: 12, opacity: 0.75 }}>（已生成画像，可再次破冰刷新）</span>
                ) : (
                  <span style={{ fontSize: 12, opacity: 0.75 }}>（建议探索前先做 3–5 轮画像破冰）</span>
                )}
              </div>
              <label>
                <span>年龄</span>
                <input value={profile.age} onChange={(e) => setProfile((p) => ({ ...p, age: e.target.value }))} placeholder="如：18" />
              </label>
              <label>
                <span>阶段</span>
                <input value={profile.stage} onChange={(e) => setProfile((p) => ({ ...p, stage: e.target.value }))} placeholder="如：高中/大学/在职" />
              </label>
              <label>
                <span>专业</span>
                <input value={profile.major} onChange={(e) => setProfile((p) => ({ ...p, major: e.target.value }))} placeholder="如：计算机科学" />
              </label>
              <label>
                <span>兴趣</span>
                <input value={profile.interests} onChange={(e) => setProfile((p) => ({ ...p, interests: e.target.value }))} placeholder="如：编程、写作、心理学" />
              </label>
              <label>
                <span>爱好</span>
                <input value={profile.hobbies} onChange={(e) => setProfile((p) => ({ ...p, hobbies: e.target.value }))} placeholder="如：阅读、运动" />
              </label>
              {profile.core_motivation ? (
                <div style={{ fontSize: 12, opacity: 0.85 }}>
                  <b>画像摘要</b>
                  <div>核心动力：{profile.core_motivation}</div>
                  <div>终局规划：{profile.end_goal}</div>
                  <div>学习习惯：{profile.learning_habits}</div>
                </div>
              ) : null}
              {profileError ? <div className="error">保存失败：{profileError}</div> : null}
              <div className="rowEnd" style={{ gap: 8 }}>
                <button type="button" onClick={() => setShowProfileModal(false)}>取消</button>
                <button className="primary" type="button" onClick={() => void saveProfile()} disabled={profileSaving}>
                  {profileSaving ? '保存中…' : '保存'}
                </button>
              </div>
            </div>
          </section>
        </div>
      ) : null}

      {showPersonaModal && currentUser ? (
        <div className="profileOverlay" onClick={() => setShowPersonaModal(false)}>
          <section className="profileModal card" onClick={(e) => e.stopPropagation()}>
            <div className="cardTop" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="cardTitle">画像破冰 · Persona Builder</div>
              <button type="button" onClick={() => setShowPersonaModal(false)} style={{ fontSize: 13 }}>
                ×
              </button>
            </div>
            <div className="chatArea compact" style={{ minHeight: 0 }}>
              <div className="chatHistory compact" style={{ maxHeight: 380 }}>
                {personaChats.length === 0 ? (
                  <div className="chatEmpty">正在启动画像破冰…</div>
                ) : null}
                {personaChats.map((m, i) => (
                  <div key={i} className={m.role === 'user' ? 'msg user' : 'msg assistant'}>
                    <div className="msgRole">{m.role === 'user' ? '你' : 'ECM探索导师'}</div>
                    <div className="msgContent">{m.content}</div>
                  </div>
                ))}
              </div>
              {personaError ? <div className="error">错误：{personaError}</div> : null}
              <div style={{ fontSize: 12, opacity: 0.8 }}>
                轮数：{Math.min(5, Math.max(0, personaUserTurns))}/5（至少 3 轮后才会收口生成画像）
              </div>
              {personaDone ? (
                <div style={{ fontSize: 12, opacity: 0.85 }}>
                  已完成画像破冰，结果已写入个人资料，并会自动注入全局提示词（后续回答会更个性化）。
                </div>
              ) : null}
              <div className="composerRow">
                <textarea
                  className="textarea composer"
                  placeholder="输入你的回答…（Enter 换行，Ctrl+Enter 发送）"
                  value={personaInput}
                  onChange={(e) => setPersonaInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                      e.preventDefault()
                      const t = personaInput.trim()
                      if (!t || personaSending) return
                      setPersonaInput('')
                      void personaTurn(t)
                    }
                  }}
                  rows={2}
                  disabled={personaSending || personaDone || personaUserTurns >= 5}
                />
                <div className="composerButtons">
                  <button
                    className="primary"
                    type="button"
                    onClick={() => {
                      const t = personaInput.trim()
                      if (!t || personaSending || personaDone || personaUserTurns >= 5) return
                      setPersonaInput('')
                      void personaTurn(t)
                    }}
                    disabled={personaSending || personaDone || personaUserTurns >= 5}
                  >
                    {personaSending ? '发送中…' : '发送'}
                  </button>
                </div>
              </div>
              <div className="rowEnd" style={{ gap: 8 }}>
                <button type="button" onClick={() => setShowPersonaModal(false)}>
                  关闭
                </button>
              </div>
            </div>
          </section>
        </div>
      ) : null}
      </div>
  )
}

export default App
