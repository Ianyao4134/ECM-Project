import { useMemo, useState } from 'react'
import './App.css'

type UserType = 'student' | 'mentor' | 'prompts'

const USER_TYPE_LABELS: { id: UserType; title: string; desc: string }[] = [
  { id: 'student', title: '学生', desc: '进入学习与探索界面（Function 1–5）' },
  { id: 'mentor', title: '导师', desc: '进入导师面板（查看学生对话）' },
  { id: 'prompts', title: '流程管理', desc: '进入提示词管理（全局 + steps）' },
]

function nextPath(type: UserType) {
  if (type === 'mentor') return '/mentor-admin'
  if (type === 'prompts') return '/prompts-admin'
  return '/student'
}

function LoginApp() {
  const [userType, setUserType] = useState<UserType>('student')
  const [form, setForm] = useState({ username: '', password: '', captcha: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const CAPTCHA_BY_TYPE: Record<UserType, string> = { student: '123456', mentor: 'asdfgh', prompts: 'xcvbnm' }
  const expectedCaptcha = CAPTCHA_BY_TYPE[userType]

  const typeMeta = useMemo(() => USER_TYPE_LABELS.find((x) => x.id === userType)!, [userType])

  const handleLogin = async () => {
    const username = form.username.trim()
    const password = form.password.trim()
    const captcha = form.captcha.trim()
    if (!username || !password) {
      setError('请输入用户名和密码')
      return
    }
    if (captcha !== expectedCaptcha) {
      setError('验证码错误')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch('/ecm/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, captcha, userType }),
      })
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const msg =
          typeof data === 'object' && data && 'error' in data
            ? String((data as { error?: unknown }).error ?? '')
            : '登录失败'
        throw new Error(msg)
      }
      const id = typeof data === 'object' && data && 'id' in data ? String((data as { id?: unknown }).id ?? '') : ''
      const uname =
        typeof data === 'object' && data && 'username' in data ? String((data as { username?: unknown }).username ?? '') : username
      sessionStorage.setItem('ecm_user', JSON.stringify({ id, username: uname }))
      window.location.href = nextPath(userType)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async () => {
    const username = form.username.trim()
    const password = form.password.trim()
    const captcha = form.captcha.trim()
    if (!username || !password) {
      setError('请输入用户名和密码')
      return
    }
    if (captcha !== expectedCaptcha) {
      setError('验证码错误')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch('/ecm/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, captcha, userType }),
      })
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const msg =
          typeof data === 'object' && data && 'error' in data
            ? String((data as { error?: unknown }).error ?? '')
            : '注册失败'
        throw new Error(msg)
      }
      const id = typeof data === 'object' && data && 'id' in data ? String((data as { id?: unknown }).id ?? '') : ''
      const uname =
        typeof data === 'object' && data && 'username' in data ? String((data as { username?: unknown }).username ?? '') : username
      sessionStorage.setItem('ecm_user', JSON.stringify({ id, username: uname }))
      window.location.href = nextPath(userType)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="loginShell">
      <div className="loginBackdrop" />
      <main className="loginMain">
        <section className="loginCard">
          <div className="loginTitleRow">
            <div>
              <div className="loginTitle">ECM探索导师</div>
              <div className="loginSub">统一登录入口（NotebookLM 风格浅色）</div>
            </div>
          </div>

          <div className="loginTypeTabs" role="tablist" aria-label="用户类型">
            {USER_TYPE_LABELS.map((t) => (
              <button
                key={t.id}
                type="button"
                className={t.id === userType ? 'loginTab active' : 'loginTab'}
                onClick={() => setUserType(t.id)}
                disabled={loading}
                role="tab"
                aria-selected={t.id === userType}
              >
                {t.title}
              </button>
            ))}
          </div>

          <div className="loginHint">
            当前入口：<b>{typeMeta.title}</b>（{typeMeta.desc}）
          </div>

          <div className="loginForm">
            <label className="loginField">
              <span>用户名</span>
              <input
                value={form.username}
                onChange={(e) => setForm((p) => ({ ...p, username: e.target.value }))}
                placeholder="请输入用户名"
                disabled={loading}
              />
            </label>
            <label className="loginField">
              <span>密码</span>
              <input
                value={form.password}
                onChange={(e) => setForm((p) => ({ ...p, password: e.target.value }))}
                placeholder="请输入密码"
                type="password"
                disabled={loading}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void handleLogin()
                }}
              />
            </label>
            <label className="loginField">
              <span>验证码</span>
              <input
                value={form.captcha}
                onChange={(e) => setForm((p) => ({ ...p, captcha: e.target.value }))}
                placeholder="请输入验证码"
                disabled={loading}
              />
            </label>
            {error ? <div className="error">登录错误：{error}</div> : null}
            <div className="loginActions">
              <button className="loginSecondary" type="button" onClick={() => void handleRegister()} disabled={loading}>
                {loading ? '处理中…' : '注册'}
              </button>
              <button className="loginPrimary" type="button" onClick={() => void handleLogin()} disabled={loading}>
                {loading ? '登录中…' : '登录'}
              </button>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}

export default LoginApp

