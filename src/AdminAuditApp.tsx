import { useCallback, useEffect, useMemo, useState } from 'react'
import './App.css'

const STORAGE_KEY = 'ecm_admin_secret'

function adminHeaders(secret: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-ECM-Admin-Secret': secret,
  }
}

type Overview = {
  users_count: number
  projects_count: number
  users: { id: string; username: string }[]
  analytics_counts: Record<string, number>
  recent_audit: AuditRow[]
}

type AuditRow = {
  id: number
  ts: number
  method: string
  path: string
  query: string
  ip: string
  user_agent: string
  user_id: string
  username: string
  status_code: number
}

export default function AdminAuditApp() {
  const [secret, setSecret] = useState(() => sessionStorage.getItem(STORAGE_KEY) ?? '')
  const [inputSecret, setInputSecret] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'overview' | 'audit' | 'projects' | 'analytics' | 'notes'>('overview')
  const [overview, setOverview] = useState<Overview | null>(null)
  const [auditItems, setAuditItems] = useState<AuditRow[]>([])
  const [projects, setProjects] = useState<unknown[]>([])
  const [notes, setNotes] = useState<unknown>(null)
  const [analyticsModule, setAnalyticsModule] = useState<'f1' | 'f2' | 'f3' | 'f4' | 'f5'>('f1')
  const [analyticsRows, setAnalyticsRows] = useState<unknown[]>([])
  const [loading, setLoading] = useState(false)

  const authed = useMemo(() => Boolean(secret.trim()), [secret])

  const saveSecret = useCallback(() => {
    const s = inputSecret.trim()
    if (!s) {
      setError('请输入管理密钥')
      return
    }
    sessionStorage.setItem(STORAGE_KEY, s)
    setSecret(s)
    setInputSecret('')
    setError(null)
  }, [inputSecret])

  const logout = useCallback(() => {
    sessionStorage.removeItem(STORAGE_KEY)
    setSecret('')
    setOverview(null)
    setAuditItems([])
    setProjects([])
    setNotes(null)
    setAnalyticsRows([])
  }, [])

  const fetchJson = useCallback(
    async (path: string, secretOverride?: string) => {
      const s = (secretOverride ?? secret).trim()
      const resp = await fetch(path, { headers: adminHeaders(s) })
      const data: unknown = await resp.json().catch(() => null)
      if (!resp.ok) {
        const err =
          typeof data === 'object' && data && 'error' in data
            ? String((data as { error?: unknown }).error ?? '')
            : '请求失败'
        const detail =
          typeof data === 'object' && data && 'detail' in data
            ? String((data as { detail?: unknown }).detail ?? '')
            : ''
        throw new Error([`HTTP ${resp.status}`, err, detail].filter(Boolean).join(' — '))
      }
      return data
    },
    [secret],
  )

  useEffect(() => {
    if (!authed) return
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError(null)
      try {
        if (tab === 'overview') {
          const o = (await fetchJson('/ecm/admin/overview')) as Overview
          if (!cancelled) setOverview(o)
        } else if (tab === 'audit') {
          const j = (await fetchJson('/ecm/admin/audit?limit=200')) as { items: AuditRow[] }
          if (!cancelled) setAuditItems(j.items ?? [])
        } else if (tab === 'projects') {
          const j = (await fetchJson('/ecm/admin/projects')) as { items: unknown[] }
          if (!cancelled) setProjects(j.items ?? [])
        } else if (tab === 'notes') {
          const j = await fetchJson('/ecm/admin/notes')
          if (!cancelled) setNotes(j)
        } else if (tab === 'analytics') {
          const j = (await fetchJson(`/ecm/admin/analytics/${analyticsModule}?limit=40`)) as { items: unknown[] }
          if (!cancelled) setAnalyticsRows(j.items ?? [])
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [authed, tab, analyticsModule, fetchJson])

  const ping = async () => {
    setLoading(true)
    setError(null)
    try {
      const s = authed ? secret : inputSecret.trim()
      if (!s) {
        setError('请输入管理密钥')
        return
      }
      await fetchJson('/ecm/admin/ping', s)
      setError(null)
      alert('密钥有效（ping ok）')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="loginShell">
      <div className="loginBackdrop" />
      <main className="loginMain" style={{ maxWidth: 1100, width: '100%' }}>
        <section className="loginCard" style={{ textAlign: 'left' }}>
          <div className="loginTitleRow">
            <div>
              <div className="loginTitle">审计与数据总览</div>
              <div className="loginSub">仅部署者使用：请勿公开链接。需在服务端设置 ECM_ADMIN_SECRET。</div>
            </div>
          </div>

          {!authed ? (
            <div className="loginForm">
              <label className="loginField">
                <span>管理密钥（ECM_ADMIN_SECRET）</span>
                <input
                  type="password"
                  value={inputSecret}
                  onChange={(e) => setInputSecret(e.target.value)}
                  placeholder="与 Railway 环境变量一致"
                  autoComplete="off"
                />
              </label>
              {error ? <div className="error">{error}</div> : null}
              <div className="loginActions">
                <button type="button" className="loginPrimary" onClick={() => void ping()} disabled={loading || !inputSecret.trim()}>
                  验证密钥
                </button>
                <button type="button" className="loginSecondary" onClick={saveSecret} disabled={loading}>
                  保存并进入
                </button>
              </div>
            </div>
          ) : (
            <>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
                <button type="button" className="loginSecondary" onClick={logout}>
                  清除本地密钥
                </button>
                <button type="button" className="loginSecondary" onClick={() => void ping()} disabled={loading}>
                  再测连通
                </button>
                <span style={{ fontSize: 12, opacity: 0.8 }}>密钥仅存于本机 sessionStorage</span>
              </div>

              <div className="loginTypeTabs" role="tablist" style={{ marginBottom: 12 }}>
                {(
                  [
                    ['overview', '总览'],
                    ['audit', '访问审计'],
                    ['projects', '项目'],
                    ['analytics', 'Analytics 样本'],
                    ['notes', '笔记元数据'],
                  ] as const
                ).map(([k, label]) => (
                  <button
                    key={k}
                    type="button"
                    className={tab === k ? 'loginTab active' : 'loginTab'}
                    onClick={() => setTab(k)}
                    disabled={loading}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {error ? <div className="error" style={{ marginBottom: 8 }}>{error}</div> : null}
              {loading ? <div style={{ fontSize: 13, marginBottom: 8 }}>加载中…</div> : null}

              {tab === 'overview' && overview ? (
                <div style={{ fontSize: 13, lineHeight: 1.6 }}>
                  <p>
                    用户数：<b>{overview.users_count}</b>　项目数：<b>{overview.projects_count}</b>
                  </p>
                  <p>
                    Analytics 行数：{Object.entries(overview.analytics_counts || {}).map(([t, c]) => (
                      <span key={t} style={{ marginRight: 12 }}>
                        {t}: <b>{c}</b>
                      </span>
                    ))}
                  </p>
                  <h4 style={{ margin: '12px 0 6px' }}>最近访问（含 IP / 路径）</h4>
                  <div style={{ maxHeight: 320, overflow: 'auto', border: '1px solid #e5e7eb', borderRadius: 8, padding: 8 }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                      <thead>
                        <tr>
                          <th style={{ textAlign: 'left' }}>时间</th>
                          <th style={{ textAlign: 'left' }}>IP</th>
                          <th style={{ textAlign: 'left' }}>用户</th>
                          <th style={{ textAlign: 'left' }}>请求</th>
                          <th style={{ textAlign: 'left' }}>状态</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(overview.recent_audit || []).map((r) => (
                          <tr key={r.id}>
                            <td>{new Date(r.ts).toLocaleString()}</td>
                            <td>{r.ip}</td>
                            <td>
                              {r.username || r.user_id || '—'}
                            </td>
                            <td>
                              {r.method} {r.path}
                              {r.query ? `?${r.query.slice(0, 80)}` : ''}
                            </td>
                            <td>{r.status_code}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}

              {tab === 'audit' ? (
                <div style={{ maxHeight: 480, overflow: 'auto', border: '1px solid #e5e7eb', borderRadius: 8, padding: 8 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                    <thead>
                      <tr>
                        <th style={{ textAlign: 'left' }}>时间</th>
                        <th style={{ textAlign: 'left' }}>IP</th>
                        <th style={{ textAlign: 'left' }}>UA</th>
                        <th style={{ textAlign: 'left' }}>用户</th>
                        <th style={{ textAlign: 'left' }}>路径</th>
                        <th style={{ textAlign: 'left' }}>状态</th>
                      </tr>
                    </thead>
                    <tbody>
                      {auditItems.map((r) => (
                        <tr key={r.id}>
                          <td>{new Date(r.ts).toLocaleString()}</td>
                          <td>{r.ip}</td>
                          <td title={r.user_agent}>{(r.user_agent || '').slice(0, 40)}…</td>
                          <td>{r.username || r.user_id || '—'}</td>
                          <td>
                            {r.method} {r.path}
                          </td>
                          <td>{r.status_code}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}

              {tab === 'projects' ? (
                <pre style={{ fontSize: 11, maxHeight: 480, overflow: 'auto', background: '#f9fafb', padding: 12, borderRadius: 8 }}>
                  {JSON.stringify(projects, null, 2)}
                </pre>
              ) : null}

              {tab === 'notes' ? (
                <pre style={{ fontSize: 11, maxHeight: 480, overflow: 'auto', background: '#f9fafb', padding: 12, borderRadius: 8 }}>
                  {JSON.stringify(notes, null, 2)}
                </pre>
              ) : null}

              {tab === 'analytics' ? (
                <div>
                  <div style={{ marginBottom: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {(['f1', 'f2', 'f3', 'f4', 'f5'] as const).map((m) => (
                      <button
                        key={m}
                        type="button"
                        className={analyticsModule === m ? 'loginTab active' : 'loginTab'}
                        onClick={() => setAnalyticsModule(m)}
                        disabled={loading}
                      >
                        {m.toUpperCase()}
                      </button>
                    ))}
                  </div>
                  <pre style={{ fontSize: 11, maxHeight: 480, overflow: 'auto', background: '#f9fafb', padding: 12, borderRadius: 8 }}>
                    {JSON.stringify(analyticsRows, null, 2)}
                  </pre>
                </div>
              ) : null}
            </>
          )}
        </section>
      </main>
    </div>
  )
}
