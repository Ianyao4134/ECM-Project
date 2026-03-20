import { useEffect, useState } from 'react'
import './App.css'

type PromptKeys = 'module0_' | 'module3_Summary' | 'module4_summary' | 'module5_inspiration'

type PromptRecord = Record<PromptKeys, string>

const EMPTY_PROMPTS: PromptRecord = {
  module0_: '',
  module3_Summary: '',
  module4_summary: '',
  module5_inspiration: '',
}

const LABELS: { key: PromptKeys; title: string; desc: string }[] = [
  {
    key: 'module3_Summary',
    title: 'Function 3 — 元数据提炼（module3_Summary.txt）',
    desc: '（可选）如果你希望单独配置 Function 3 的总结/元数据提炼逻辑，可以在这里调整。',
  },
  {
    key: 'module4_summary',
    title: 'Function 4 — 洞察报告模版（module4_summary.txt）',
    desc: '控制 ECM 深度洞察报告的 Markdown 结构（道/法/术/器/势 等）以及 Mermaid 思维导图格式。',
  },
  {
    key: 'module5_inspiration',
    title: 'Function 5 — 灵感&闭环模版（module5_inspiration.txt）',
    desc: '控制 Function 5 的“思维画像 / Spark / Next Loop”等输出结构与语气。',
  },
  {
    key: 'module0_',
    title: '全局设定（module0_.txt）',
    desc: '整体身份与输出要求的总纲提示词，所有模块都会拼接这一段作为系统前缀。',
  },
]

function PromptsAdminApp() {
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
  const [loginForm, setLoginForm] = useState({ username: '', password: '' })
  const [loginError, setLoginError] = useState<string | null>(null)
  const [prompts, setPrompts] = useState<PromptRecord>(EMPTY_PROMPTS)
  const [loading, setLoading] = useState(true)
  const [savingKey, setSavingKey] = useState<PromptKeys | null>(null)
  const [savingModule1, setSavingModule1] = useState(false)
  const [savingModule2, setSavingModule2] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  const [module1Global, setModule1Global] = useState('')
  const [module1Steps, setModule1Steps] = useState<string[]>([])
  const [module2Global, setModule2Global] = useState('')
  const [module2Steps, setModule2Steps] = useState<string[]>([])

  useEffect(() => {
    if (!currentUser) return
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        // 普通 prompts（Module 0/3/4/5）
        const resp = await fetch('/ecm/prompts')
        const data: unknown = await resp.json().catch(() => null)
        if (!resp.ok) {
          const msg =
            typeof data === 'object' && data && 'error' in data
              ? String((data as { error?: unknown }).error ?? '')
              : '加载 prompts 失败'
          throw new Error(msg)
        }
        const merged: PromptRecord = { ...EMPTY_PROMPTS }
        if (data && typeof data === 'object') {
          for (const key of Object.keys(merged) as PromptKeys[]) {
            const v = (data as Record<string, unknown>)[key]
            if (typeof v === 'string') merged[key] = v
          }
        }
        setPrompts(merged)

        // Module 1：global + steps
        const m1Resp = await fetch('/ecm/prompts/module1')
        const m1Data: unknown = await m1Resp.json().catch(() => null)
        if (m1Resp.ok && m1Data && typeof m1Data === 'object') {
          const g = (m1Data as { global?: unknown }).global
          const s = (m1Data as { steps?: unknown }).steps
          if (typeof g === 'string') setModule1Global(g)
          if (Array.isArray(s)) setModule1Steps((s as unknown[]).map(String))
        }

        // Module 2：global + steps（前 5 个 step 默认不可编辑，只允许追加）
        const m2Resp = await fetch('/ecm/prompts/module2')
        const m2Data: unknown = await m2Resp.json().catch(() => null)
        if (m2Resp.ok && m2Data && typeof m2Data === 'object') {
          const g = (m2Data as { global?: unknown }).global
          const s = (m2Data as { steps?: unknown }).steps
          if (typeof g === 'string') setModule2Global(g)
          if (Array.isArray(s)) setModule2Steps((s as unknown[]).map(String))
        }

        setInfo('已从后端加载当前提示词。首次保存时会自动备份为 defaults 版本。')
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [currentUser])

  const handleLogin = async () => {
    const username = loginForm.username.trim()
    const password = loginForm.password.trim()

    if (!username || !password) {
      setLoginError('请输入用户名和密码')
      return
    }

    setLoginError(null)
    setError(null)

    try {
      const resp = await fetch('/ecm/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
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

  const updatePrompt = (key: PromptKeys, value: string) => {
    setPrompts((prev) => ({ ...prev, [key]: value }))
  }

  const saveOne = async (key: PromptKeys) => {
    setSavingKey(key)
    setError(null)
    setInfo(null)
    try {
      const resp = await fetch('/ecm/prompts/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, content: prompts[key] }),
      })
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const msg =
          typeof data === 'object' && data && 'error' in data
            ? String((data as { error?: unknown }).error ?? '')
            : '保存失败'
        throw new Error(msg)
      }
      setInfo(`已保存：${key}。如是首次保存，已在 prompts/defaults/ 下自动备份默认版本。`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingKey(null)
    }
  }

  const addModule1Step = () => {
    setModule1Steps((prev) => {
      const n = prev.length + 1
      return [...prev, `## Step ${n}：新增步骤\n请在这里填写该 Step 的导师提问规则与输出要求。`]
    })
  }

  const saveModule1 = async () => {
    setSavingModule1(true)
    setError(null)
    setInfo(null)
    try {
      const resp = await fetch('/ecm/prompts/module1/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ global: module1Global, steps: module1Steps }),
      })
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const msg =
          typeof data === 'object' && data && 'error' in data
            ? String((data as { error?: unknown }).error ?? '')
            : '保存 Module 1 失败'
        throw new Error(msg)
      }
      setInfo('已保存 Module 1（全局 + Steps）。')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingModule1(false)
    }
  }

  const addModule2Step = () => {
    setModule2Steps((prev) => {
      const n = prev.length + 1
      return [...prev, `### Step ${n}：新增步骤\n任务：\n方法：\n\n> 📘 深度解析\n> ...\n\n> 📌 笔记卡片\n> 🏷️ 关键词：#...\n> 💡 核心金句：“...”\n> ⚡ 记忆钩子： ...\n\n> 👉 导师提问\n> ...`]
    })
  }

  const saveModule2 = async () => {
    setSavingModule2(true)
    setError(null)
    setInfo(null)
    try {
      const resp = await fetch('/ecm/prompts/module2/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ global: module2Global, steps: module2Steps }),
      })
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const msg =
          typeof data === 'object' && data && 'error' in data
            ? String((data as { error?: unknown }).error ?? '')
            : '保存 Module 2 失败'
        throw new Error(msg)
      }
      setInfo('已保存 Module 2（前 5 步锁定，追加步生效）。')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingModule2(false)
    }
  }

  return (
    <div className="dashShell">
      <header className="dashHeader">
        <div className="brandTitle">ECM探索导师 · Prompt 管理台</div>
        <div className="brandSub">仅供导/配置者使用，用于调整多模块提示词。</div>
      </header>

      <main className="dashMain">
        {!currentUser ? (
          <section className="grid">
            <article className="card cardWide">
              <div className="cardTop">
                <div className="cardTitle">登录 · Prompt 管理</div>
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
                <button type="button" onClick={() => void handleLogin()}>
                  登录 / 注册
                </button>
                {loginError ? <div className="error">登录错误：{loginError}</div> : null}
              </div>
              <div style={{ padding: 16, fontSize: 13, opacity: 0.8 }}>
                说明：登录后会自动加载所有模块的提示词文本，你可以在下方进行修改并保存。
              </div>
            </article>
          </section>
        ) : (
          <>
            {loading ? <div className="error">正在加载当前提示词…</div> : null}
            {error ? <div className="error">错误：{error}</div> : null}
            {info ? <div className="noteHint">{info}</div> : null}

            <section className="grid">
              <article className="card cardWide">
                <div className="cardTop">
                  <div className="cardTitle">Function 1 — 问题定义（全局 + Steps）</div>
                  <div className="noteHint">
                    说明：默认前 5 个 Step 为基准步骤（锁定不可编辑），你只能在其后追加新的 Step。保存后将直接影响学生端 Function 1 的 Step 推进与提问内容。
                  </div>
                </div>
                <div className="noteArea">
                  <div className="docScroll">
                    <div className="noteHint">Global（全局规则，可编辑）</div>
                    <textarea
                      className="textarea noteEditor"
                      value={module1Global}
                      onChange={(e) => setModule1Global(e.target.value)}
                      rows={10}
                      spellCheck={false}
                    />

                    <details>
                      <summary style={{ fontSize: 13, opacity: 0.85 }}>查看默认前 5 个 Step（只读）</summary>
                      {module1Steps.slice(0, 5).map((s, idx) => (
                        <textarea key={idx} className="textarea noteEditor" value={s} readOnly rows={8} spellCheck={false} />
                      ))}
                    </details>

                    <div className="noteHint">新增 Steps（可编辑）</div>
                    {module1Steps.slice(5).length === 0 ? (
                      <div className="noteHint">暂无新增 Step。你可以点击下方“新增 Step”来追加第 6 步。</div>
                    ) : null}
                    {module1Steps.slice(5).map((s, j) => {
                      const idx = j + 5
                      return (
                        <textarea
                          key={idx}
                          className="textarea noteEditor"
                          value={s}
                          onChange={(e) => setModule1Steps((prev) => prev.map((x, i) => (i === idx ? e.target.value : x)))}
                          rows={8}
                          spellCheck={false}
                        />
                      )
                    })}
                  </div>
                  <div className="rowEnd" style={{ gap: 10 }}>
                    <button type="button" onClick={addModule1Step}>
                      新增 Step
                    </button>
                    <button className="primary" type="button" onClick={() => void saveModule1()} disabled={savingModule1}>
                      {savingModule1 ? '保存中…' : '保存 Module 1（全局 + Steps）'}
                    </button>
                  </div>
                </div>
              </article>

              <article className="card cardWide">
                <div className="cardTop">
                  <div className="cardTitle">Function 2 — 深度探索（全局 + Steps）</div>
                  <div className="noteHint">
                    说明：默认前 5 个 Step 为基准步骤（锁定不可编辑），你只能在其后追加新的 Step。保存后将直接影响学生端 Function 2 的 Step 推进。
                  </div>
                </div>
                <div className="noteArea">
                  <div className="docScroll">
                    <div className="noteHint">Global（全局规则，可编辑）</div>
                    <textarea
                      className="textarea noteEditor"
                      value={module2Global}
                      onChange={(e) => setModule2Global(e.target.value)}
                      rows={10}
                      spellCheck={false}
                    />
                    <details>
                      <summary style={{ fontSize: 13, opacity: 0.85 }}>查看默认前 5 个 Step（只读）</summary>
                      {module2Steps.slice(0, 5).map((s, idx) => (
                        <textarea key={idx} className="textarea noteEditor" value={s} readOnly rows={8} spellCheck={false} />
                      ))}
                    </details>
                    <div className="noteHint">新增 Steps（可编辑）</div>
                    {module2Steps.slice(5).length === 0 ? (
                      <div className="noteHint">暂无新增 Step。你可以点击下方“新增 Step”来追加第 6 步。</div>
                    ) : null}
                    {module2Steps.slice(5).map((s, j) => {
                      const idx = j + 5
                      return (
                        <textarea
                          key={idx}
                          className="textarea noteEditor"
                          value={s}
                          onChange={(e) => setModule2Steps((prev) => prev.map((x, i) => (i === idx ? e.target.value : x)))}
                          rows={8}
                          spellCheck={false}
                        />
                      )
                    })}
                  </div>
                  <div className="rowEnd" style={{ gap: 10 }}>
                    <button type="button" onClick={addModule2Step}>
                      新增 Step
                    </button>
                    <button className="primary" type="button" onClick={() => void saveModule2()} disabled={savingModule2}>
                      {savingModule2 ? '保存中…' : '保存 Module 2（追加 Step）'}
                    </button>
                  </div>
                </div>
              </article>

              {LABELS.map((item) => (
                <article key={item.key} className="card cardWide">
                  <div className="cardTop">
                    <div className="cardTitle">{item.title}</div>
                    <div className="noteHint">{item.desc}</div>
                  </div>
                  <div className="noteArea">
                    <div className="docScroll">
                      <textarea
                        className="textarea noteEditor"
                        value={prompts[item.key]}
                        onChange={(e) => updatePrompt(item.key, e.target.value)}
                        rows={14}
                        spellCheck={false}
                      />
                    </div>
                    <div className="rowEnd">
                      <button
                        className="primary"
                        type="button"
                        onClick={() => void saveOne(item.key)}
                        disabled={savingKey === item.key}
                      >
                        {savingKey === item.key ? '保存中…' : '保存该模块提示词'}
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </section>
          </>
        )}
      </main>
    </div>
  )
}

export default PromptsAdminApp

