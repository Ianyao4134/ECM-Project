import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import './App.css'

type Role = 'user' | 'assistant'
type ChatMessage = { role: Role; content: string }
type FunctionKey = 'f1' | 'f2' | 'f4' | 'f5'

type ProjectListItem = { id: string; name: string; updatedAt?: number }
type DialogueListItem = { id: string; name: string; updatedAt?: number }

type LoadedProjectState = {
  chats?: Record<FunctionKey, ChatMessage[]>
  noteText?: string
  module1Definition?: string
  flags?: {
    f1Confirmed?: boolean
    f2Finished?: boolean
    f4Confirmed?: boolean
    f5Done?: boolean
  }
}

type PerfFigure = {
  title?: string
  mime?: string
  data_base64?: string
  width_px?: number
  height_px?: number
}

type TimelinePayload = {
  event_count?: number
  events_truncated?: boolean
  dialogue_order?: string[]
  events?: Array<{
    seq?: number
    ts_ms?: number
    module?: string
    dialogue_id?: string
    project_id?: string
    conversation_id?: string
  }>
}

type PerformanceBundle = {
  user_id?: string
  chart?: {
    module_row_counts?: Record<string, number>
    metrics_avg_by_module?: Record<string, Record<string, number>>
    daily_total_events?: { date: string; events: number }[]
    module_daily_top?: Record<string, { date: string; events: number }[]>
  }
  analytics_by_module?: Record<string, unknown[]>
  recent_access_log?: Array<{
    ts?: number
    path?: string
    method?: string
    status_code?: number
    ip?: string
    query?: string
  }>
  projects_summary?: {
    project_count?: number
    dialogue_count_total?: number
    projects?: unknown[]
  }
  generated_at_ms?: number
}

type StudentProfile = {
  age?: string
  stage?: string
  major?: string
  interests?: string
  hobbies?: string
  core_motivation?: string
  end_goal?: string
  learning_habits?: string
  persona_summary?: string
  persona_transcript?: { role: 'user' | 'assistant'; content: string }[]
}

const metricKeyToCn: Record<string, string> = {
  // Common / F1
  avg_ai_msg_length: 'AI消息长度均值（字符）',
  avg_user_msg_length: '学生消息长度均值（字符）',
  ai_response_seconds_avg: 'AI回应时长均值（秒）',
  module_dwell_seconds: '模块停留时长均值（秒）',
  turn_count: '对话轮次均值',
  user_confirm_count: '确认次数均值',
  user_copy_example_count: '复制/范例使用次数均值',
  user_option_select_count: '选项选择次数均值',
  user_question_count: '提问次数均值',
  user_thinking_seconds_avg: '思考时长均值（秒）',
  thinking_seconds_avg: '思考时长均值（秒）',

  // F3
  avg_similarity: '卡片相似度均值',
  avg_update_depth: '更新深度均值',
  card_count: '卡片数量均值',
  edit_rate: '编辑率',
  edited_card_count: '已编辑卡片数量均值',
  user_edit_count: '用户编辑次数均值',
  star_rate: '标星率',
  send_rate: '发送率',

  // F4
  download_count: '下载次数',
  report_modification_count: '报告修改次数',

  // F5
  click_count: '点击次数',
  new_count: '新增次数',
  note_char_count: '笔记字符数',
  note_edit_count: '笔记编辑次数',
}

function MentorAdminApp() {
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
  const expectedCaptcha = 'asdfgh'
  const [users, setUsers] = useState<{ id: string; username: string }[]>([])
  const [selectedUserId, setSelectedUserId] = useState<string>('')
  const [projects, setProjects] = useState<ProjectListItem[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<string>('')
  const [dialogues, setDialogues] = useState<DialogueListItem[]>([])
  const [selectedDialogueId, setSelectedDialogueId] = useState<string>('')
  const [loadedProject, setLoadedProject] = useState<{
    name: string
    dialogueName?: string
    state: LoadedProjectState
  } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [profileLoading, setProfileLoading] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [studentProfile, setStudentProfile] = useState<StudentProfile | null>(null)

  const [analysisLoading, setAnalysisLoading] = useState<Record<string, boolean>>({})
  const [analysisError, setAnalysisError] = useState<Record<string, string | null>>({})
  const [analysisResult, setAnalysisResult] = useState<Record<string, string>>({})

  const [perfBundle, setPerfBundle] = useState<PerformanceBundle | null>(null)
  const [perfCharts, setPerfCharts] = useState<{ timeline: TimelinePayload; figures: PerfFigure[] } | null>(null)
  const [perfLoading, setPerfLoading] = useState(false)
  const [perfError, setPerfError] = useState<string | null>(null)
  const [perfChartsError, setPerfChartsError] = useState<string | null>(null)
  const [behaviorLoading, setBehaviorLoading] = useState(false)
  const [behaviorError, setBehaviorError] = useState<string | null>(null)
  const [behaviorMarkdown, setBehaviorMarkdown] = useState<string | null>(null)

  useEffect(() => {
    if (!currentUser) return
    const loadUsers = async () => {
      setLoading(true)
      setError(null)
      try {
        const resp = await fetch('/ecm/users')
        const data: unknown = await resp.json().catch(() => null)
        if (!resp.ok) {
          const msg =
            typeof data === 'object' && data && 'error' in data
              ? String((data as { error?: unknown }).error ?? '')
              : '加载用户列表失败'
          throw new Error(msg)
        }
        if (Array.isArray(data)) {
          const list = (data as { id?: unknown; username?: unknown }[])
            .map((u) => ({
              id: String(u.id ?? ''),
              username: String(u.username ?? ''),
            }))
            .filter((u) => u.id)
          setUsers(list)
        } else {
          setUsers([])
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoading(false)
      }
    }
    void loadUsers()
  }, [currentUser])

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
    setError(null)
    try {
      const resp = await fetch('/ecm/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, captcha, userType: 'mentor' }),
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
    } catch (e) {
      setLoginError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    if (!selectedUserId) {
      setStudentProfile(null)
      setProfileError(null)
      return
    }
    setProfileLoading(true)
    setProfileError(null)
    void (async () => {
      try {
        const resp = await fetch(`/ecm/profile?userId=${encodeURIComponent(selectedUserId)}`)
        const data: unknown = await resp.json().catch(() => null)
        if (!resp.ok) {
          const msg =
            typeof data === 'object' && data && 'error' in data ? String((data as { error?: unknown }).error ?? '') : '加载画像失败'
          throw new Error(msg)
        }
        const p = data && typeof data === 'object' && 'profile' in data ? (data as { profile?: unknown }).profile : null
        if (p && typeof p === 'object') setStudentProfile(p as StudentProfile)
        else setStudentProfile({})
      } catch (e) {
        setStudentProfile(null)
        setProfileError(e instanceof Error ? e.message : String(e))
      } finally {
        setProfileLoading(false)
      }
    })()
  }, [selectedUserId])

  useEffect(() => {
    setPerfBundle(null)
    setPerfCharts(null)
    setPerfError(null)
    setPerfChartsError(null)
    setBehaviorMarkdown(null)
    setBehaviorError(null)
  }, [selectedUserId])

  const loadPerformanceBundle = async () => {
    if (!selectedUserId) return
    setPerfLoading(true)
    setPerfError(null)
    setPerfChartsError(null)
    try {
      const uid = encodeURIComponent(selectedUserId)
      const [bundleResp, chartsResp] = await Promise.all([
        fetch(`/ecm/mentor/student_performance_bundle?userId=${uid}`),
        fetch(`/ecm/mentor/student_performance_charts?userId=${uid}`),
      ])
      const bundleData: unknown = await bundleResp.json().catch(() => null)
      if (!bundleResp.ok) {
        const msg =
          typeof bundleData === 'object' && bundleData && 'error' in bundleData
            ? String((bundleData as { error?: unknown }).error ?? '')
            : '加载表现数据失败'
        throw new Error(msg)
      }
      setPerfBundle(bundleData && typeof bundleData === 'object' ? (bundleData as PerformanceBundle) : null)

      const chartsData: unknown = await chartsResp.json().catch(() => null)
      if (!chartsResp.ok) {
        const msg =
          typeof chartsData === 'object' && chartsData && 'error' in chartsData
            ? String((chartsData as { error?: unknown }).error ?? '')
            : '生成 Matplotlib 图表失败'
        setPerfCharts(null)
        setPerfChartsError(msg)
      } else if (chartsData && typeof chartsData === 'object' && 'figures' in chartsData) {
        const c = chartsData as { timeline?: TimelinePayload; figures?: PerfFigure[] }
        setPerfCharts({
          timeline: c.timeline ?? {},
          figures: Array.isArray(c.figures) ? c.figures : [],
        })
      } else {
        setPerfCharts(null)
      }
    } catch (e) {
      setPerfBundle(null)
      setPerfCharts(null)
      setPerfError(e instanceof Error ? e.message : String(e))
    } finally {
      setPerfLoading(false)
    }
  }

  const generateBehaviorAnalysis = async () => {
    if (!selectedUserId) return
    setBehaviorLoading(true)
    setBehaviorError(null)
    try {
      const resp = await fetch('/ecm/mentor/student_behavior_analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId: selectedUserId }),
      })
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const msg =
          typeof data === 'object' && data && 'error' in data
            ? String((data as { error?: unknown }).error ?? '')
            : '生成行为学解读失败'
        throw new Error(msg)
      }
      const md =
        typeof data === 'object' && data && 'analysis' in data
          ? String((data as { analysis?: unknown }).analysis ?? '')
          : ''
      setBehaviorMarkdown(md || '未返回解读内容')
    } catch (e) {
      setBehaviorMarkdown(null)
      setBehaviorError(e instanceof Error ? e.message : String(e))
    } finally {
      setBehaviorLoading(false)
    }
  }

  const generateAnalysis = async (functionKey: 'f1' | 'f2' | 'f3' | 'f4' | 'f5') => {
    if (!selectedUserId || !loadedProject) return
    if (analysisLoading[functionKey]) return
    const state = loadedProject.state
    const chats = (state.chats ?? {}) as Record<string, any>

    // Strict rule: if the selected Function has no content, do not generate analysis.
    if (functionKey === 'f3') {
      const nt = typeof state.noteText === 'string' ? state.noteText : ''
      if (!nt.trim()) {
        setAnalysisResult((prev) => ({ ...prev, [functionKey]: '该 Function 暂无内容，已跳过分析。' }))
        setAnalysisError((prev) => ({ ...prev, [functionKey]: null }))
        return
      }
    } else {
      const history = Array.isArray(chats?.[functionKey]) ? chats[functionKey] : []
      const hasText = history.some((m: any) => typeof m?.content === 'string' && m.content.trim())
      if (!hasText) {
        setAnalysisResult((prev) => ({ ...prev, [functionKey]: '该 Function 暂无内容，已跳过分析。' }))
        setAnalysisError((prev) => ({ ...prev, [functionKey]: null }))
        return
      }
    }

    setAnalysisLoading((prev) => ({ ...prev, [functionKey]: true }))
    setAnalysisError((prev) => ({ ...prev, [functionKey]: null }))
    try {
      const resp = await fetch('/ecm/mentor/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: selectedDialogueId,
          functionKey,
          userProfile: studentProfile ?? {},
          module1Definition: functionKey === 'f1' ? state.module1Definition ?? '' : '',
          noteText: functionKey === 'f3' ? state.noteText ?? '' : '',
          chats,
        }),
      })
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const msg = typeof data === 'object' && data && 'error' in data ? String((data as { error?: unknown }).error ?? '') : '生成分析失败'
        throw new Error(msg)
      }
      const analysis = typeof data === 'object' && data && 'analysis' in data ? String((data as { analysis?: unknown }).analysis ?? '') : ''
      setAnalysisResult((prev) => ({ ...prev, [functionKey]: analysis || '未返回分析结果' }))
    } catch (e) {
      setAnalysisError((prev) => ({ ...prev, [functionKey]: e instanceof Error ? e.message : String(e) }))
    } finally {
      setAnalysisLoading((prev) => ({ ...prev, [functionKey]: false }))
    }
  }

  const loadProjectsForUser = async (userId: string) => {
    if (!userId) {
      setProjects([])
      setSelectedProjectId('')
      setDialogues([])
      setSelectedDialogueId('')
      setLoadedProject(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch(`/ecm/projects/list?userId=${encodeURIComponent(userId)}`)
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const msg =
          typeof data === 'object' && data && 'error' in data
            ? String((data as { error?: unknown }).error ?? '')
            : '加载项目列表失败'
        throw new Error(msg)
      }
      if (Array.isArray(data)) {
        const list = (data as { id?: unknown; name?: unknown; updatedAt?: unknown }[]).map((p) => ({
          id: String(p.id ?? ''),
          name: String(p.name ?? '未命名项目'),
          updatedAt: typeof p.updatedAt === 'number' ? p.updatedAt : undefined,
        }))
        setProjects(list)
      } else {
        setProjects([])
      }
      setSelectedProjectId('')
      setLoadedProject(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const loadProjectDetail = async (userId: string, projectId: string) => {
    if (!userId || !projectId) {
      setLoadedProject(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      // list dialogues under project
      const respList = await fetch(
        `/ecm/dialogues/list?userId=${encodeURIComponent(userId)}&projectId=${encodeURIComponent(projectId)}`,
      )
      const listData: unknown = await respList.json().catch(() => null)
      if (respList.ok && Array.isArray(listData)) {
        const items = (listData as { id?: unknown; name?: unknown; updatedAt?: unknown }[])
          .map((d) => ({
            id: String(d.id ?? ''),
            name: String(d.name ?? '未命名对话'),
            updatedAt: typeof d.updatedAt === 'number' ? d.updatedAt : undefined,
          }))
          .filter((d) => d.id)
        setDialogues(items)
        const first = items[0]
        if (first) {
          setSelectedDialogueId(first.id)
          const resp = await fetch(
            `/ecm/dialogues/load?userId=${encodeURIComponent(userId)}&projectId=${encodeURIComponent(projectId)}&dialogueId=${encodeURIComponent(first.id)}`,
          )
          const data: unknown = await resp.json().catch(() => null)
          if (!resp.ok) {
            const msg =
              typeof data === 'object' && data && 'error' in data
                ? String((data as { error?: unknown }).error ?? '')
                : '加载对话详情失败'
            throw new Error(msg)
          }
          const pname =
            typeof data === 'object' && data && 'projectName' in data ? String((data as { projectName?: unknown }).projectName ?? '') : '未命名项目'
          const dname = typeof data === 'object' && data && 'name' in data ? String((data as { name?: unknown }).name ?? '') : '未命名对话'
          const state =
            typeof data === 'object' && data && 'state' in data && (data as { state?: unknown }).state && typeof (data as { state?: unknown }).state === 'object'
              ? ((data as { state: unknown }).state as LoadedProjectState)
              : {}
          setLoadedProject({ name: pname || '未命名项目', dialogueName: dname || '未命名对话', state })
          return
        }
      } else {
        setDialogues([])
      }

      // fallback: old endpoint (single state)
      const resp = await fetch(`/ecm/projects/load?userId=${encodeURIComponent(userId)}&projectId=${encodeURIComponent(projectId)}`)
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) throw new Error('加载项目详情失败')
      const name =
        data && typeof data === 'object' && 'name' in data && typeof (data as { name?: unknown }).name === 'string'
          ? String((data as { name?: unknown }).name)
          : '未命名项目'
      const state =
        data && typeof data === 'object' && 'state' in data && (data as { state?: unknown }).state && typeof (data as { state?: unknown }).state === 'object'
          ? ((data as { state: unknown }).state as LoadedProjectState)
          : {}
      setLoadedProject({ name, state })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const loadDialogueDetail = async (userId: string, projectId: string, dialogueId: string) => {
    if (!userId || !projectId || !dialogueId) return
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch(
        `/ecm/dialogues/load?userId=${encodeURIComponent(userId)}&projectId=${encodeURIComponent(projectId)}&dialogueId=${encodeURIComponent(dialogueId)}`,
      )
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const msg =
          typeof data === 'object' && data && 'error' in data
            ? String((data as { error?: unknown }).error ?? '')
            : '加载对话详情失败'
        throw new Error(msg)
      }
      const pname =
        typeof data === 'object' && data && 'projectName' in data ? String((data as { projectName?: unknown }).projectName ?? '') : '未命名项目'
      const dname = typeof data === 'object' && data && 'name' in data ? String((data as { name?: unknown }).name ?? '') : '未命名对话'
      const state =
        typeof data === 'object' && data && 'state' in data && (data as { state?: unknown }).state && typeof (data as { state?: unknown }).state === 'object'
          ? ((data as { state: unknown }).state as LoadedProjectState)
          : {}
      setLoadedProject({ name: pname || '未命名项目', dialogueName: dname || '未命名对话', state })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const renderChat = (key: FunctionKey, title: string) => {
    const chats = (loadedProject?.state.chats?.[key] ?? []) as ChatMessage[]
    return (
      <article className="card mentorFuncCard">
        <div className="cardTop">
          <div className="cardTitle">{title}</div>
        </div>
        <div className="mentorFuncGrid">
          <div className="chatArea compact">
            <div className="chatHistory compact">
              {chats.length === 0 ? <div className="chatEmpty">该项目在此模块暂无对话。</div> : null}
              {chats.map((m, i) => (
                <div key={i} className={m.role === 'user' ? 'msg user' : 'msg assistant'}>
                  <div className="msgRole">{m.role === 'user' ? '学生' : 'ECM探索导师'}</div>
                  <div className="msgContent">{m.content}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="mentorAnalysisPanel">
            <button
              type="button"
              className="analysisPrimary"
              onClick={() => void generateAnalysis(key)}
              disabled={analysisLoading[key]}
            >
              {analysisLoading[key] ? '生成中…' : '生成分析'}
            </button>
            {analysisError[key] ? <div className="error">错误：{analysisError[key]}</div> : null}
            <div className="mentorAnalysisOutput">
              {analysisResult[key] ? (
                analysisResult[key]
              ) : (
                <div className="noteHint">点击按钮生成 {title} 分析。</div>
              )}
            </div>
          </div>
        </div>
      </article>
    )
  }

  return (
    <div className="dashShell">
      <header className="dashHeader">
        <div className="brandTitle">ECM探索导师 · 导师面板</div>
        <div className="brandSub">查看学生列表 / 项目 / 整个对话过程（只读）。</div>
      </header>

      <main className="dashMain">
        {!currentUser ? (
          <section className="grid">
            <article className="card cardWide">
              <div className="cardTop">
                <div className="cardTitle">登录 · 导师面板</div>
              </div>
              <div style={{ padding: 16, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
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
                  style={{ fontSize: 12, padding: '2px 4px' }}
                  placeholder="验证码"
                  value={loginForm.captcha}
                  onChange={(e) => setLoginForm((prev) => ({ ...prev, captcha: e.target.value }))}
                />
                <button type="button" onClick={() => void handleLogin()}>
                  登录 / 注册
                </button>
                {loginError ? <div className="error">登录错误：{loginError}</div> : null}
              </div>
              <div style={{ padding: 16, fontSize: 13, opacity: 0.8 }}>
                说明：登录后可以查看所有学生的项目列表，并选择任意项目查看完整对话过程（只读）。
              </div>
            </article>
          </section>
        ) : (
          <>
            {error ? <div className="error">错误：{error}</div> : null}
            {loading ? <div className="noteHint">正在加载数据，请稍候…</div> : null}

            <section className="grid">
              <article className="card cardWide">
                <div className="cardTop">
                  <div className="cardTitle">选择学生与项目</div>
                </div>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <label style={{ fontSize: 13 }}>
                学生：
                <select
                  style={{ marginLeft: 6 }}
                  value={selectedUserId}
                  onChange={(e) => {
                    const userId = e.target.value
                    setSelectedUserId(userId)
                    void loadProjectsForUser(userId)
                  }}
                >
                  <option value="">请选择学生</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.username || u.id}
                    </option>
                  ))}
                </select>
              </label>

              <label style={{ fontSize: 13 }}>
                项目：
                <select
                  style={{ marginLeft: 6, minWidth: 180 }}
                  value={selectedProjectId}
                  onChange={(e) => {
                    const pid = e.target.value
                    setSelectedProjectId(pid)
                    setSelectedDialogueId('')
                    void loadProjectDetail(selectedUserId, pid)
                  }}
                  disabled={!selectedUserId}
                >
                  <option value="">请选择项目</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>

              <label style={{ fontSize: 13 }}>
                对话：
                <select
                  style={{ marginLeft: 6, minWidth: 180 }}
                  value={selectedDialogueId}
                  onChange={(e) => {
                    const did = e.target.value
                    setSelectedDialogueId(did)
                    if (selectedUserId && selectedProjectId && did) {
                      void loadDialogueDetail(selectedUserId, selectedProjectId, did)
                    }
                  }}
                  disabled={!selectedUserId || !selectedProjectId}
                >
                  <option value="">请选择对话</option>
                  {dialogues.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </label>

              {loadedProject ? (
                <span style={{ fontSize: 12, opacity: 0.8 }}>
                  当前项目：{loadedProject.name}
                  {loadedProject.dialogueName ? ` ｜当前对话：${loadedProject.dialogueName}` : ''}
                  {loadedProject.state.flags?.f1Confirmed ? ' ｜F1 已确认' : ''}
                  {loadedProject.state.flags?.f2Finished ? ' ｜F2 已完成' : ''}
                  {loadedProject.state.flags?.f4Confirmed ? ' ｜F4 已确认' : ''}
                  {loadedProject.state.flags?.f5Done ? ' ｜F5 已生成' : ''}
                </span>
              ) : null}

              {selectedUserId ? (
                <div style={{ width: '100%', marginTop: 10 }}>
                  <div style={{ fontSize: 13, fontWeight: 750, marginBottom: 6 }}>学生基本信息（注册 + Persona 画像）</div>
                  {profileLoading ? <div className="noteHint">加载中…</div> : null}
                  {profileError ? <div className="error">画像加载失败：{profileError}</div> : null}
                  {studentProfile ? (
                    <div className="mentorStudentProfileGrid">
                      <div className="mentorStudentProfileLeft">
                        <div className="mentorStudentFieldLabel">用户名</div>
                        <div className="mentorStudentFieldValue">{users.find((u) => u.id === selectedUserId)?.username || selectedUserId}</div>

                        <div className="mentorStudentFieldSpacer" />

                        <div className="mentorStudentFieldLabel">年龄 / 阶段</div>
                        <div className="mentorStudentFieldValue">
                          {studentProfile.age ? studentProfile.age : '未填写'} / {studentProfile.stage ? studentProfile.stage : '未填写'}
                        </div>

                        <div className="mentorStudentFieldSpacer" />

                        <div className="mentorStudentFieldLabel">专业 / 兴趣 / 爱好</div>
                        <div className="mentorStudentFieldValue">
                          {studentProfile.major ? studentProfile.major : '未填写'}
                          {' / '}
                          {studentProfile.interests ? studentProfile.interests : '未填写'}
                          {' / '}
                          {studentProfile.hobbies ? studentProfile.hobbies : '未填写'}
                        </div>
                      </div>

                      <div className="mentorStudentProfileRight mentorStudentProfileScroll">
                        <div className="mentorStudentFieldLabel">画像摘要（AI生成）</div>
                        <div className="mentorStudentFieldValue mentorStudentPre">
                          {studentProfile.persona_summary ? studentProfile.persona_summary : '未完成画像破冰'}
                        </div>

                        <div className="mentorStudentFieldSpacer" />

                        <div className="mentorStudentFieldLabel">核心动力 / 终局规划 / 学习习惯</div>
                        <div className="mentorStudentFieldValue mentorStudentPre">
                          {studentProfile.core_motivation ? `核心动力：${studentProfile.core_motivation}\n` : '核心动力：未填写\n'}
                          {studentProfile.end_goal ? `终局规划：${studentProfile.end_goal}\n` : '终局规划：未填写\n'}
                          {studentProfile.learning_habits ? `学习习惯：${studentProfile.learning_habits}` : '学习习惯：未填写'}
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}
                </div>
              </article>

              <article className="card mentorCardWide">
                <div className="cardTop">
                  <div className="cardTitle">全量表现数据 · 可视化与行为学解读</div>
                </div>
                <div style={{ padding: '0 16px 16px' }}>
                  {!selectedUserId ? (
                    <div className="noteHint">请先选择一名学生。</div>
                  ) : (
                    <>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
                        <button
                          type="button"
                          className="analysisPrimary"
                          onClick={() => void loadPerformanceBundle()}
                          disabled={perfLoading}
                        >
                          {perfLoading ? '加载中…' : '加载该学生全量表现数据'}
                        </button>
                        <button type="button" onClick={() => void generateBehaviorAnalysis()} disabled={behaviorLoading}>
                          {behaviorLoading ? '正在解读中…' : '生成行为学深度解读'}
                        </button>
                        <span style={{ fontSize: 12, opacity: 0.75 }}>
                          加载后将并行生成 Matplotlib 时间序列大图（可滚动查看）；解读需配置 DEEPSEEK_API_KEY。
                        </span>
                      </div>
                      {perfError ? <div className="error">{perfError}</div> : null}
                      {perfChartsError ? <div className="error">图表：{perfChartsError}</div> : null}
                      {behaviorError ? <div className="error">{behaviorError}</div> : null}
                      {perfCharts && (perfCharts.figures?.length ?? 0) > 0 ? (
                        <div className="mentorPerfChartsBlock">
                          <div style={{ fontWeight: 650, marginBottom: 8 }}>Python Matplotlib · 时间序列多维可视化</div>
                          {perfCharts.timeline?.event_count != null ? (
                            <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 8 }}>
                              事件总数 {perfCharts.timeline.event_count}
                              {perfCharts.timeline.events_truncated ? '（时间线表仅展示前若干条）' : ''}
                              {perfCharts.timeline.dialogue_order && perfCharts.timeline.dialogue_order.length > 0 ? (
                                <span>
                                  {' '}
                                  ｜对话顺序（去重）：{perfCharts.timeline.dialogue_order.slice(0, 8).join(' → ')}
                                  {perfCharts.timeline.dialogue_order.length > 8 ? ' …' : ''}
                                </span>
                              ) : null}
                            </div>
                          ) : null}
                          {perfCharts.timeline?.events && perfCharts.timeline.events.length > 0 ? (
                            <div className="mentorPerfTimelineTableWrap">
                              <table className="mentorPerfTimelineTable">
                                <thead>
                                  <tr>
                                    <th>序号</th>
                                    <th>时间</th>
                                    <th>模块</th>
                                    <th>对话</th>
                                    <th>项目</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {perfCharts.timeline.events.map((row, idx) => (
                                    <tr key={`${row.seq}-${idx}`}>
                                      <td>{row.seq ?? '—'}</td>
                                      <td>
                                        {row.ts_ms != null ? new Date(row.ts_ms).toLocaleString() : '—'}
                                      </td>
                                      <td>{row.module ? String(row.module).toUpperCase() : '—'}</td>
                                      <td title={row.dialogue_id}>{row.dialogue_id ? String(row.dialogue_id).slice(0, 14) : '—'}</td>
                                      <td title={row.project_id}>{row.project_id ? String(row.project_id).slice(0, 10) : '—'}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          ) : null}
                          <div className="mentorPerfChartsScroll">
                            {perfCharts.figures.map((f, i) => (
                              <figure key={i} className="mentorPerfFigure">
                                {f.title ? <figcaption>{f.title}</figcaption> : null}
                                {f.data_base64 && f.mime ? (
                                  <img
                                    src={`data:${f.mime};base64,${f.data_base64}`}
                                    alt={f.title || `chart-${i}`}
                                    className="mentorPerfChartImg"
                                  />
                                ) : null}
                              </figure>
                            ))}
                          </div>
                        </div>
                      ) : null}
                      {perfBundle ? (
                        <div className="mentorPerfViz">
                          {perfBundle.projects_summary ? (
                            <div style={{ fontSize: 13, marginBottom: 12 }}>
                              <strong>项目概览：</strong>
                              项目数 {perfBundle.projects_summary.project_count ?? 0}，对话数{' '}
                              {perfBundle.projects_summary.dialogue_count_total ?? 0}
                              {perfBundle.generated_at_ms ? (
                                <span style={{ opacity: 0.75 }}>
                                  {' '}
                                  ｜数据快照 {new Date(perfBundle.generated_at_ms).toLocaleString()}
                                </span>
                              ) : null}
                            </div>
                          ) : null}

                          {perfBundle.chart?.module_row_counts ? (
                            <div style={{ marginBottom: 16 }}>
                              <div style={{ fontWeight: 650, marginBottom: 8 }}>各模块 analytics 记录条数</div>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                {(['f1', 'f2', 'f3', 'f4', 'f5'] as const).map((k) => {
                                  const counts = perfBundle.chart!.module_row_counts!
                                  const n = counts[k] ?? 0
                                  const vals = Object.values(counts).filter((v) => typeof v === 'number') as number[]
                                  const max = Math.max(1, ...vals)
                                  const pct = (n / max) * 100
                                  return (
                                    <div key={k}>
                                      <div style={{ fontSize: 12, marginBottom: 2 }}>
                                        {k.toUpperCase()} · {n} 条
                                      </div>
                                      <div style={{ background: 'rgba(0,0,0,0.07)', borderRadius: 4, height: 10 }}>
                                        <div
                                          style={{
                                            width: `${pct}%`,
                                            height: 10,
                                            background: 'linear-gradient(90deg, #3d6df0, #6a9cff)',
                                            borderRadius: 4,
                                          }}
                                        />
                                      </div>
                                    </div>
                                  )
                                })}
                              </div>
                            </div>
                          ) : null}

                          {perfBundle.chart?.daily_total_events && perfBundle.chart.daily_total_events.length > 0 ? (
                            <div style={{ marginBottom: 16 }}>
                              <div style={{ fontWeight: 650, marginBottom: 8 }}>按天活动强度（analytics 更新 + 审计请求，UTC 日期）</div>
                              <div
                                style={{
                                  display: 'grid',
                                  gridTemplateColumns: 'repeat(auto-fill, minmax(72px, 1fr))',
                                  gap: 6,
                                  maxHeight: 200,
                                  overflow: 'auto',
                                }}
                              >
                                {perfBundle.chart.daily_total_events.slice(-40).map((d) => {
                                  const peak = Math.max(
                                    1,
                                    ...perfBundle.chart!.daily_total_events!.map((x) => x.events),
                                  )
                                  const h = Math.max(6, (d.events / peak) * 40)
                                  return (
                                    <div key={d.date} style={{ textAlign: 'center' }}>
                                      <div
                                        title={`${d.date}: ${d.events}`}
                                        style={{
                                          height: h,
                                          margin: '0 auto 4px',
                                          width: '80%',
                                          background: '#3d6df0',
                                          borderRadius: 3,
                                          opacity: 0.65 + 0.35 * (d.events / peak),
                                        }}
                                      />
                                      <div style={{ fontSize: 10, opacity: 0.8, lineHeight: 1.1 }}>{d.date.slice(5)}</div>
                                      <div style={{ fontSize: 10, fontWeight: 600 }}>{d.events}</div>
                                    </div>
                                  )
                                })}
                              </div>
                            </div>
                          ) : null}

                          {perfBundle.chart?.metrics_avg_by_module &&
                          Object.keys(perfBundle.chart.metrics_avg_by_module).length > 0 ? (
                            <div style={{ marginBottom: 16 }}>
                              <div style={{ fontWeight: 650, marginBottom: 8 }}>各模块 metrics 数值字段均值（有则显示）</div>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                {(['f1', 'f2', 'f3', 'f4', 'f5'] as const).map((k) => {
                                  const block = perfBundle.chart!.metrics_avg_by_module![k]
                                  if (!block || Object.keys(block).length === 0) return null
                                  const keys = Object.keys(block).slice(0, 12)
                                  return (
                                    <div key={k}>
                                      <div style={{ fontSize: 12, fontWeight: 650, marginBottom: 4 }}>{k.toUpperCase()}</div>
                                      <div style={{ fontSize: 12, opacity: 0.9, lineHeight: 1.5 }}>
                                        {keys.map((mk) => (
                                          <span key={mk} style={{ marginRight: 12 }}>
                                            {metricKeyToCn[mk] ? metricKeyToCn[mk] : mk}: {block[mk]}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  )
                                })}
                              </div>
                            </div>
                          ) : null}

                          {perfBundle.recent_access_log && perfBundle.recent_access_log.length > 0 ? (
                            <div style={{ marginBottom: 8 }}>
                              <div style={{ fontWeight: 650, marginBottom: 6 }}>近期访问轨迹（节选）</div>
                              <div style={{ overflow: 'auto', maxHeight: 160, fontSize: 11, fontFamily: 'monospace' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                  <thead>
                                    <tr style={{ textAlign: 'left', opacity: 0.8 }}>
                                      <th style={{ padding: '2px 6px' }}>时间</th>
                                      <th style={{ padding: '2px 6px' }}>请求</th>
                                      <th style={{ padding: '2px 6px' }}>状态</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {perfBundle.recent_access_log.slice(0, 12).map((row, idx) => (
                                      <tr key={`${row.ts}-${idx}`} style={{ borderTop: '1px solid rgba(0,0,0,0.06)' }}>
                                        <td style={{ padding: '4px 6px', whiteSpace: 'nowrap' }}>
                                          {row.ts ? new Date(row.ts).toLocaleString() : '—'}
                                        </td>
                                        <td style={{ padding: '4px 6px' }}>
                                          {row.method} {row.path}
                                          {row.query ? `?${String(row.query).slice(0, 48)}` : ''}
                                        </td>
                                        <td style={{ padding: '4px 6px' }}>{row.status_code ?? '—'}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          ) : null}
                        </div>
                      ) : (
                        <div className="noteHint">点击「加载该学生全量表现数据」查看图表；可先加载再生成 DeepSeek 行为学解读。</div>
                      )}
                      {behaviorMarkdown ? (
                        <div className="mentorBehaviorMarkdown">
                          <ReactMarkdown>{behaviorMarkdown}</ReactMarkdown>
                        </div>
                      ) : null}
                    </>
                  )}
                </div>
              </article>

              {loadedProject ? (
                <>
                  <div className="mentorStack">
                    {renderChat('f1', 'Function 1 — 问题定义')}
                    {renderChat('f2', 'Function 2 — 深度探索')}
                    <article className="card">
                      <div className="cardTop">
                        <div className="cardTitle">Function 3 — 学生笔记内容（只读预览）</div>
                      </div>
                      <div className="mentorFuncGrid mentorFuncGridNote">
                        <div className="noteArea">
                          <textarea
                            className="textarea noteEditor"
                            value={loadedProject.state.noteText ?? ''}
                            readOnly
                            rows={10}
                          />
                          <div className="noteHint">此处展示学生在 Function 3 中累积的所有笔记内容（只读）。</div>
                        </div>
                        <div className="mentorAnalysisPanel">
                          <button
                            type="button"
                            className="analysisPrimary"
                            onClick={() => void generateAnalysis('f3')}
                            disabled={analysisLoading['f3']}
                          >
                            {analysisLoading['f3'] ? '生成中…' : '生成分析'}
                          </button>
                          {analysisError['f3'] ? <div className="error">错误：{analysisError['f3']}</div> : null}
                          <div className="mentorAnalysisOutput">
                            {analysisResult['f3'] ? analysisResult['f3'] : <div className="noteHint">点击按钮生成 Function 3 分析。</div>}
                          </div>
                        </div>
                      </div>
                    </article>
                    {renderChat('f4', 'Function 4 — 洞察报告')}
                    {renderChat('f5', 'Function 5 — 灵感与闭环')}
                  </div>
                </>
              ) : (
                <article className="card cardWide">
                  <div className="cardTop">
                    <div className="cardTitle">提示</div>
                  </div>
                  <div className="noteArea">
                    <div className="noteHint">
                      请先在上方选择一名学生，再选择该学生的一个项目。加载成功后，你将看到该项目在 Function 1、2、4、5
                      中的完整对话（学生 / ECM探索导师），以及 Function 3 的笔记内容。
                    </div>
                  </div>
                </article>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  )
}

export default MentorAdminApp

