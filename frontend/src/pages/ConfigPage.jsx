import { useEffect, useState, useRef, Fragment } from 'react'
import axios from 'axios'

/* ---- 轻量 Toast（无第三方依赖，3s 自动消失） ---- */
function Toast({ toast }) {
  if (!toast) return null
  const ok = toast.type === 'success'
  return (
    <div
      className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded-lg shadow-lg text-sm text-white ${ok ? 'bg-green-600' : 'bg-red-600'}`}
      role="status"
    >
      {ok ? '✓ ' : '✗ '}{toast.msg}
    </div>
  )
}

/* ---- 可复用的 Tag 输入组件 ---- */
function TagInput({ tags = [], onChange, placeholder = '输入后回车添加' }) {
  const [input, setInput] = useState('')
  const add = () => {
    const v = input.trim()
    if (v && !tags.includes(v)) { onChange([...tags, v]); setInput('') }
  }
  return (
    <div className="flex flex-wrap gap-1.5 items-center">
      {tags.map((t, i) => (
        <span key={i} className="inline-flex items-center bg-blue-50 text-blue-700 text-xs px-2 py-1 rounded-full">
          {t}
          <button className="ml-1 text-blue-400 hover:text-red-500" onClick={() => onChange(tags.filter((_, j) => j !== i))}>&times;</button>
        </span>
      ))}
      <input
        className="border-none outline-none text-sm py-1 min-w-[120px] flex-1 bg-transparent"
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
        placeholder={tags.length === 0 ? placeholder : ''}
      />
    </div>
  )
}

/* ---- 话题卡片（可折叠） ---- */
function TopicCard({ topic, onChange, onDelete }) {
  const [open, setOpen] = useState(!topic.name) // 新话题默认展开
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div
        className="flex items-center justify-between px-4 py-2.5 bg-gray-50 cursor-pointer select-none"
        onClick={() => setOpen(!open)}
      >
        <span className="text-sm font-medium text-gray-700">
          {open ? '▾' : '▸'} {topic.name || '（新话题）'}
        </span>
        <button
          className="text-xs text-red-400 hover:text-red-600"
          onClick={e => { e.stopPropagation(); onDelete() }}
        >删除</button>
      </div>
      {open && (
        <div className="px-4 py-3 space-y-3">
          <div>
            <label className="block text-sm text-gray-600 mb-1">话题名称</label>
            <input
              className="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={topic.name || ''}
              onChange={e => onChange({ ...topic, name: e.target.value })}
              placeholder="例：大模型竞争格局"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">描述</label>
            <textarea
              className="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-[80px]"
              value={topic.description || ''}
              onChange={e => onChange({ ...topic, description: e.target.value })}
              placeholder="话题背景描述，将用于 LLM 分析时的上下文"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">关键词</label>
            <div className="border border-gray-200 rounded-lg px-3 py-2">
              <TagInput
                tags={topic.keywords || []}
                onChange={keywords => onChange({ ...topic, keywords })}
                placeholder="输入后回车添加"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}


/* ---- 网站信源管理 ---- */
const EMPTY_SOURCE = { name: '', institution: '', tier: 2, type: 'rss', url: '', selector: '', use_proxy: true }

function SourcesSection({ sources, onChange, proxyUrl, onProxyUrlChange }) {
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ ...EMPTY_SOURCE })
  const [editIdx, setEditIdx] = useState(null)

  const addSource = () => {
    if (!form.name || !form.url) return
    if (editIdx !== null) {
      const updated = [...sources]
      updated[editIdx] = { ...form }
      onChange(updated)
      setEditIdx(null)
    } else {
      onChange([...sources, { ...form }])
    }
    setForm({ ...EMPTY_SOURCE })
    setAdding(false)
  }

  const startEdit = (idx) => {
    setForm({ ...sources[idx] })
    setEditIdx(idx)
    setAdding(true)
  }

  const cancel = () => { setAdding(false); setEditIdx(null); setForm({ ...EMPTY_SOURCE }) }

  const formCard = (
    <div className="border border-blue-200 rounded-lg p-4 mb-4 bg-blue-50/30 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <input className="border border-gray-200 rounded px-2 py-1.5 text-sm" placeholder="名称 *" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
        <input className="border border-gray-200 rounded px-2 py-1.5 text-sm" placeholder="机构" value={form.institution} onChange={e => setForm({ ...form, institution: e.target.value })} />
      </div>
      <input className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm font-mono" placeholder="URL *" value={form.url} onChange={e => setForm({ ...form, url: e.target.value })} />
      <div className="grid grid-cols-3 gap-2">
        <select className="border border-gray-200 rounded px-2 py-1.5 text-sm" value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}>
          <option value="rss">RSS</option>
          <option value="scrape">Scrape</option>
        </select>
        <select className="border border-gray-200 rounded px-2 py-1.5 text-sm" value={form.tier} onChange={e => setForm({ ...form, tier: parseInt(e.target.value) })}>
          <option value={1}>Tier 1</option>
          <option value={2}>Tier 2</option>
          <option value={3}>Tier 3</option>
        </select>
        <input className="border border-gray-200 rounded px-2 py-1.5 text-sm" placeholder="CSS selector" value={form.selector || ''} onChange={e => setForm({ ...form, selector: e.target.value })} />
      </div>
      <label className="flex items-center gap-2 text-sm text-gray-600 pt-1 select-none">
        <input
          type="checkbox"
          className="w-4 h-4 accent-blue-600"
          checked={form.use_proxy !== false}
          onChange={e => setForm({ ...form, use_proxy: e.target.checked })}
        />
        走代理
      </label>
      <div className="flex gap-2 pt-1">
        <button onClick={addSource} className="bg-blue-600 text-white px-3 py-1 rounded text-sm hover:bg-blue-700">{editIdx !== null ? '更新' : '添加'}</button>
        <button onClick={cancel} className="text-sm text-gray-500 hover:text-gray-700">取消</button>
      </div>
    </div>
  )

  return (
    <section className="bg-white rounded-xl border border-gray-100 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-medium text-gray-800">网站信源 <span className="text-sm text-gray-400 font-normal">({sources.length})</span></h3>
        {!adding && (
          <button onClick={() => setAdding(true)} className="text-sm text-blue-600 hover:text-blue-800">+ 添加信源</button>
        )}
      </div>

      {/* 全局代理地址 */}
      <div className="mb-4">
        <label className="block text-sm text-gray-600 mb-1">代理地址</label>
        <input
          className="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={proxyUrl || ''}
          onChange={e => onProxyUrlChange(e.target.value)}
          placeholder="例：http://127.0.0.1:10809"
        />
        <p className="text-xs text-gray-400 mt-1">勾选了"走代理"的信源（含微信 / Twitter）将通过此地址采集；未勾选的直连。</p>
      </div>

      {/* 新增信源表单；编辑时表单内联在对应行下方 */}
      {adding && editIdx === null && formCard}

      {/* 信源表格 */}
      {sources.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100">
                <th className="pb-2 font-medium">名称</th>
                <th className="pb-2 font-medium">类型</th>
                <th className="pb-2 font-medium">Tier</th>
                <th className="pb-2 font-medium w-14">代理</th>
                <th className="pb-2 font-medium w-16">操作</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s, idx) => (
                <Fragment key={idx}>
                <tr className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="py-1.5">
                    <div className="font-medium text-gray-800">{s.name}</div>
                    <div className="text-xs text-gray-400 truncate max-w-[200px]">{s.url}</div>
                  </td>
                  <td className="py-1.5"><span className={`text-xs px-1.5 py-0.5 rounded ${s.type === 'rss' ? 'bg-green-50 text-green-700' : 'bg-orange-50 text-orange-700'}`}>{s.type}</span></td>
                  <td className="py-1.5 text-gray-600">{s.tier}</td>
                  <td className="py-1.5">
                    <input
                      type="checkbox"
                      className="w-4 h-4 accent-blue-600"
                      checked={s.use_proxy !== false}
                      onChange={e => onChange(sources.map((x, i) => i === idx ? { ...x, use_proxy: e.target.checked } : x))}
                      title="是否通过代理采集该信源"
                    />
                  </td>
                  <td className="py-1.5">
                    <div className="flex gap-2">
                      <button onClick={() => startEdit(idx)} className="text-xs text-blue-500 hover:text-blue-700">编辑</button>
                      <button onClick={() => onChange(sources.filter((_, i) => i !== idx))} className="text-xs text-red-400 hover:text-red-600">删除</button>
                    </div>
                  </td>
                </tr>
                {adding && editIdx === idx && (
                  <tr><td colSpan={5} className="py-2">{formCard}</td></tr>
                )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

/* ---- 微信公众号列表 ---- */
function WechatSourcesTable({ sources, onChange }) {
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ name: '', institution: '', tier: 2, indicator: 'industry', nickname: '', use_proxy: false })

  const addSource = () => {
    if (!form.name || !form.nickname) return
    onChange([...sources, { ...form }])
    setForm({ name: '', institution: '', tier: 2, indicator: 'industry', nickname: '', use_proxy: false })
    setAdding(false)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-gray-600 font-medium">公众号列表 <span className="text-gray-400 font-normal">({sources.length})</span></span>
        {!adding && (
          <button onClick={() => setAdding(true)} className="text-sm text-blue-600 hover:text-blue-800">+ 添加公众号</button>
        )}
      </div>

      {adding && (
        <div className="border border-blue-200 rounded-lg p-3 mb-3 bg-blue-50/30 space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <input className="border border-gray-200 rounded px-2 py-1.5 text-sm" placeholder="名称 *" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
            <input className="border border-gray-200 rounded px-2 py-1.5 text-sm" placeholder="机构" value={form.institution} onChange={e => setForm({ ...form, institution: e.target.value })} />
            <input className="border border-gray-200 rounded px-2 py-1.5 text-sm" placeholder="公众号昵称 *" value={form.nickname} onChange={e => setForm({ ...form, nickname: e.target.value })} />
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-600 select-none">
            <input
              type="checkbox"
              className="w-4 h-4 accent-blue-600"
              checked={form.use_proxy === true}
              onChange={e => setForm({ ...form, use_proxy: e.target.checked })}
            />
            走代理（微信为国内站，通常无需）
          </label>
          <div className="flex gap-2">
            <button onClick={addSource} className="bg-blue-600 text-white px-3 py-1 rounded text-sm hover:bg-blue-700">添加</button>
            <button onClick={() => setAdding(false)} className="text-sm text-gray-500 hover:text-gray-700">取消</button>
          </div>
        </div>
      )}

      {sources.length > 0 && (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-100">
              <th className="pb-2 font-medium">名称</th>
              <th className="pb-2 font-medium">机构</th>
              <th className="pb-2 font-medium">昵称</th>
              <th className="pb-2 font-medium w-14">代理</th>
              <th className="pb-2 font-medium w-12">操作</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s, idx) => (
              <tr key={idx} className="border-b border-gray-50 hover:bg-gray-50">
                <td className="py-1.5 text-gray-800">{s.name}</td>
                <td className="py-1.5 text-gray-600">{s.institution}</td>
                <td className="py-1.5 text-gray-600">{s.nickname}</td>
                <td className="py-1.5">
                  <input
                    type="checkbox"
                    className="w-4 h-4 accent-blue-600"
                    checked={s.use_proxy === true}
                    onChange={e => onChange(sources.map((x, i) => i === idx ? { ...x, use_proxy: e.target.checked } : x))}
                    title="是否通过代理采集该公众号"
                  />
                </td>
                <td className="py-1.5">
                  <button onClick={() => onChange(sources.filter((_, i) => i !== idx))} className="text-xs text-red-400 hover:text-red-600">删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

/* ---- Twitter/X 账号管理 ---- */
function TwitterSection({ accounts, onChange, useProxy, onUseProxyChange }) {
  const [status, setStatus] = useState(null)
  const [form, setForm] = useState({ username: '', password: '', email: '', email_password: '' })
  const [adding, setAdding] = useState(false)
  const [browserLogging, setBrowserLogging] = useState(false)
  const [collecting, setCollecting] = useState(false)
  const [msg, setMsg] = useState('')
  const handleRef = useRef(null)
  const displayRef = useRef(null)

  const refreshStatus = () => axios.get('/api/twitter/status').then(r => setStatus(r.data)).catch(() => {})

  useEffect(() => { refreshStatus() }, [])

  const addAccount = async () => {
    if (!form.username || !form.password || !form.email) {
      setMsg('用户名、密码、邮箱均为必填')
      return
    }
    try {
      setMsg('登录中...')
      const r = await axios.post('/api/twitter/add-account', form)
      setMsg(r.data.message)
      setForm({ username: '', password: '', email: '', email_password: '' })
      setAdding(false)
      await refreshStatus()
    } catch (e) {
      setMsg(e.response?.data?.message || '添加失败')
    }
  }

  const browserLogin = async () => {
    setBrowserLogging(true)
    setMsg('正在打开浏览器，请在弹出的窗口中登录 X/Twitter...')
    try {
      const r = await axios.post('/api/twitter/login', {}, { timeout: 320000 })
      setMsg(r.data.message)
      await refreshStatus()
    } catch (e) {
      setMsg(e.response?.data?.message || '浏览器登录失败')
    } finally {
      setBrowserLogging(false)
    }
  }

  const collectOnly = async () => {
    setCollecting(true)
    setMsg('X 采集已启动，请查看进度推送...')
    try {
      await axios.post('/api/twitter/collect')
    } catch (e) {
      setMsg(e.response?.data?.message || '启动失败')
    } finally {
      setCollecting(false)
    }
  }

  const addMonitorAccount = () => {
    const h = handleRef.current?.value?.trim()
    const d = displayRef.current?.value?.trim()
    if (!h) return
    onChange([...accounts, { handle: h, display_name: d || h }])
    if (handleRef.current) handleRef.current.value = ''
    if (displayRef.current) displayRef.current.value = ''
  }

  return (
    <section className="bg-white rounded-xl border border-gray-100 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-medium text-gray-800">
          Twitter / X 账号监控
          <span className="ml-2 text-sm text-gray-400 font-normal">({accounts.length} 个账号)</span>
        </h3>
        <span className={`text-xs px-2 py-0.5 rounded-full ${status?.status === 'configured' ? 'bg-green-50 text-green-600' : 'bg-yellow-50 text-yellow-600'}`}>
          {status?.status === 'configured' ? '小号已配置' : '未配置小号'}
        </span>
      </div>

      {/* 走代理开关 */}
      <label className="flex items-center gap-2 text-sm text-gray-600 mb-3 select-none">
        <input
          type="checkbox"
          className="w-4 h-4 accent-blue-600"
          checked={useProxy !== false}
          onChange={e => onUseProxyChange(e.target.checked)}
        />
        走代理（采集 X 推文时通过上方"代理地址"）
      </label>

      {/* 监控账号列表 */}
      <div className="space-y-1.5 mb-3">
        {accounts.map((acct, i) => (
          <div key={acct.handle} className="flex items-center justify-between text-sm py-1.5 px-3 bg-gray-50 rounded-lg">
            <span className="text-gray-700">{acct.display_name} <span className="text-gray-400">@{acct.handle}</span></span>
            <button className="text-xs text-red-400 hover:text-red-600" onClick={() => onChange(accounts.filter((_, j) => j !== i))}>删除</button>
          </div>
        ))}
        {accounts.length === 0 && <p className="text-sm text-gray-400">暂无监控账号</p>}
      </div>

      {/* 添加监控账号 */}
      <div className="flex gap-2 mb-4">
        <input
          ref={handleRef}
          className="flex-1 border border-gray-200 rounded px-2 py-1.5 text-sm"
          placeholder="Handle（如 OpenAI）"
          onKeyDown={e => { if (e.key === 'Enter') addMonitorAccount() }}
        />
        <input
          ref={displayRef}
          className="flex-1 border border-gray-200 rounded px-2 py-1.5 text-sm"
          placeholder="显示名称"
        />
        <button
          className="text-sm text-blue-600 hover:text-blue-800 px-2"
          onClick={addMonitorAccount}
        >+ 添加</button>
      </div>

      {/* X 小号凭证 */}
      <div className="border-t border-gray-100 pt-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-gray-600">X 小号凭证（用于采集）</span>
          {!adding && !browserLogging && (
            <div className="flex gap-2">
              <button
                className="text-xs text-emerald-600 hover:text-emerald-800 border border-emerald-200 px-2 py-0.5 rounded"
                onClick={browserLogin}
                disabled={browserLogging}
              >
                浏览器登录
              </button>
              <button
                className="text-xs text-blue-600 hover:text-blue-800"
                onClick={() => { setAdding(true); setMsg('') }}
              >
                {status?.status === 'configured' ? '重新配置' : '+ 账号密码'}
              </button>
            </div>
          )}
        </div>
        {browserLogging && (
          <p className="text-xs text-emerald-600 mb-2">浏览器已打开，请完成登录后等待自动保存...</p>
        )}
        {adding && (
          <div className="space-y-2 mb-2">
            <div className="grid grid-cols-2 gap-2">
              <input className="border border-gray-200 rounded px-2 py-1.5 text-sm" placeholder="用户名 *" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} />
              <input className="border border-gray-200 rounded px-2 py-1.5 text-sm" placeholder="密码 *" type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} />
              <input className="border border-gray-200 rounded px-2 py-1.5 text-sm" placeholder="注册邮箱 *" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} />
              <input className="border border-gray-200 rounded px-2 py-1.5 text-sm" placeholder="邮箱密码（可选）" type="password" value={form.email_password} onChange={e => setForm({ ...form, email_password: e.target.value })} />
            </div>
            <div className="flex gap-2">
              <button className="text-sm bg-blue-600 text-white px-3 py-1.5 rounded hover:bg-blue-700" onClick={addAccount}>登录</button>
              <button className="text-sm text-gray-500 hover:text-gray-700" onClick={() => { setAdding(false); setMsg('') }}>取消</button>
            </div>
          </div>
        )}
        {msg && <p className="text-xs text-gray-500 mt-1">{msg}</p>}
      </div>

      {/* 测试采集（已隐藏） */}
      {false && (
      <div className="border-t border-gray-100 pt-3 mt-3">
        <button
          className="text-sm text-purple-600 hover:text-purple-800 border border-purple-200 px-3 py-1.5 rounded disabled:opacity-50"
          onClick={collectOnly}
          disabled={collecting || status?.status !== 'configured'}
          title={status?.status !== 'configured' ? '请先配置小号凭证' : '仅采集 X/Twitter 推文（测试用）'}
        >
          {collecting ? '采集中...' : '仅采集 X 新闻'}
        </button>
        {status?.status !== 'configured' && (
          <span className="ml-2 text-xs text-gray-400">需先配置小号凭证</span>
        )}
      </div>
      )}
    </section>
  )
}

export function ConfigPage() {
  const [config, setConfig] = useState(null)
  const [toast, setToast] = useState(null)
  const [saving, setSaving] = useState(false)

  const showToast = (type, msg) => {
    setToast({ type, msg })
    setTimeout(() => setToast(null), 3000)
  }
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [wechatStatus, setWechatStatus] = useState(null)
  const [wechatLogging, setWechatLogging] = useState(false)
  const [wechatCollecting, setWechatCollecting] = useState(false)

  useEffect(() => {
    axios.get('/api/config').then(r => setConfig(r.data))
    axios.get('/api/wechat/status').then(r => setWechatStatus(r.data)).catch(() => {})
  }, [])

  const testLLM = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await axios.post('/api/llm/test', config.llm)
      setTestResult(res.data)
    } catch (e) {
      setTestResult({ status: 'error', message: e.message })
    } finally {
      setTesting(false)
    }
  }

  const wechatLogin = async () => {
    setWechatLogging(true)
    try {
      await axios.post('/api/wechat/login')
      const r = await axios.get('/api/wechat/status')
      setWechatStatus(r.data)
    } catch (e) {
      setWechatStatus({ status: 'error', message: e.response?.data?.message || e.message })
    } finally {
      setWechatLogging(false)
    }
  }

  const save = async () => {
    setSaving(true)
    try {
      await axios.put('/api/config', config)
      showToast('success', '配置已保存')
    } catch (e) {
      showToast('error', '保存失败：' + (e.response?.data?.detail || e.response?.data?.message || e.message))
    } finally {
      setSaving(false)
    }
  }

  if (!config) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-gray-400">加载配置中...</p>
      </div>
    )
  }

  return (
    <div className="flex-1 bg-gray-50 p-6">
      <Toast toast={toast} />
      <div className="max-w-2xl mx-auto space-y-4">
        <h2 className="text-lg font-bold text-gray-900 mb-6">系统配置</h2>

        {/* LLM 配置 */}
        <section className="bg-white rounded-xl border border-gray-100 p-5">
          <h3 className="font-medium text-gray-800 mb-4">LLM 配置</h3>
          <div className="space-y-3">
            <div>
              <label className="block text-sm text-gray-600 mb-1">Provider</label>
              <select
                className="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={config.llm?.provider || 'claude'}
                onChange={e => setConfig({ ...config, llm: { ...config.llm, provider: e.target.value } })}
              >
                <option value="claude">Claude (Anthropic)</option>
                <option value="openai">OpenAI / MiniMax / 兼容接口</option>
                <option value="ollama">Ollama (本地)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Model</label>
              <input
                className="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={config.llm?.model || ''}
                onChange={e => setConfig({ ...config, llm: { ...config.llm, model: e.target.value } })}
                placeholder="例：claude-sonnet-4-6"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">API Key</label>
              <input
                type="password"
                className="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
                value={config.llm?.api_key === '***' ? '' : (config.llm?.api_key || '')}
                onChange={e => setConfig({ ...config, llm: { ...config.llm, api_key: e.target.value } })}
                placeholder="留空则使用环境变量"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">API Base URL <span className="text-gray-400 font-normal">（可选，留空用默认）</span></label>
              <input
                className="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
                value={config.llm?.base_url || ''}
                onChange={e => setConfig({ ...config, llm: { ...config.llm, base_url: e.target.value } })}
                placeholder="例：https://api.openai.com/v1"
              />
            </div>
          </div>

          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={testLLM}
              disabled={testing}
              className="bg-gray-100 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-200 disabled:opacity-50 transition-colors"
            >
              {testing ? '测试中...' : '测试连通性'}
            </button>
            {testResult && (
              <span className={`text-sm font-medium ${testResult.status === 'ok' ? 'text-green-600' : 'text-red-500'}`}>
                {testResult.status === 'ok'
                  ? `✓ 连通正常（返回：${testResult.reply}）`
                  : `✗ 连接失败：${testResult.message}`}
              </span>
            )}
          </div>
        </section>

        {/* 监控话题 */}
        <section className="bg-white rounded-xl border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-medium text-gray-800">监控话题</h3>
            <button
              onClick={() => setConfig({
                ...config,
                topics: [...(config.topics || []), { name: '', description: '', keywords: [] }]
              })}
              className="text-sm text-blue-600 hover:text-blue-800"
            >+ 添加话题</button>
          </div>
          <div className="space-y-3">
            {(config.topics || []).map((topic, idx) => (
              <TopicCard
                key={idx}
                topic={topic}
                onChange={t => {
                  const topics = [...config.topics]
                  topics[idx] = t
                  setConfig({ ...config, topics })
                }}
                onDelete={() => {
                  const topics = config.topics.filter((_, i) => i !== idx)
                  setConfig({ ...config, topics })
                }}
              />
            ))}
            {(!config.topics || config.topics.length === 0) && (
              <p className="text-sm text-gray-400">暂无话题，点击"+ 添加话题"创建</p>
            )}
          </div>
        </section>


        {/* 关键词 */}
        <section className="bg-white rounded-xl border border-gray-100 p-5">
          <h3 className="font-medium text-gray-800 mb-4">采集预筛关键词</h3>
          <div className="space-y-3">
            <div>
              <label className="block text-sm text-gray-600 mb-1.5">基础关键词</label>
              <div className="border border-gray-200 rounded-lg px-3 py-2 max-h-40 overflow-y-auto">
                <TagInput
                  tags={config.keywords?.base || []}
                  onChange={base => setConfig({ ...config, keywords: { ...config.keywords, base } })}
                  placeholder="输入关键词后回车"
                />
              </div>
              <p className="text-xs text-gray-400 mt-1">用于采集阶段预筛，匹配标题或摘要中的 AI 相关关键词</p>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1.5">自定义关键词</label>
              <div className="border border-gray-200 rounded-lg px-3 py-2">
                <TagInput
                  tags={config.keywords?.custom || []}
                  onChange={custom => setConfig({ ...config, keywords: { ...config.keywords, custom } })}
                  placeholder="添加自定义关键词"
                />
              </div>
            </div>
          </div>
        </section>

        {/* 新闻类别 */}
        <section className="bg-white rounded-xl border border-gray-100 p-5">
          <h3 className="font-medium text-gray-800 mb-4">新闻类别</h3>
          <div className="border border-gray-200 rounded-lg px-3 py-2">
            <TagInput
              tags={config.categories || []}
              onChange={categories => setConfig({ ...config, categories })}
              placeholder="输入类别后回车"
            />
          </div>
          <p className="text-xs text-gray-400 mt-1">LLM 分析时将从这些类别中选择，用于新闻分类标签</p>
        </section>

        {/* 网站信源 */}
        <SourcesSection
          sources={config.sources?.websites || []}
          onChange={websites => setConfig({ ...config, sources: { ...config.sources, websites } })}
          proxyUrl={config.sources?.proxy_url || ''}
          onProxyUrlChange={proxy_url => setConfig({ ...config, sources: { ...config.sources, proxy_url } })}
        />

        {/* 采集配置 */}
        <section className="bg-white rounded-xl border border-gray-100 p-5">
          <h3 className="font-medium text-gray-800 mb-4">采集配置</h3>
          <div className="space-y-3">
            <div>
              <label className="block text-sm text-gray-600 mb-1">每信源最大抓取数</label>
              <input
                type="number"
                min="1"
                max="50"
                className="block w-32 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={config.collection?.max_per_source || 10}
                onChange={e => setConfig({ ...config, collection: { ...config.collection, max_per_source: parseInt(e.target.value) } })}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">语义去重阈值 (0-1，越高越严格)</label>
              <input
                type="number"
                step="0.05"
                min="0"
                max="1"
                className="block w-32 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={config.dedup?.semantic_threshold || 0.85}
                onChange={e => setConfig({ ...config, dedup: { ...config.dedup, semantic_threshold: parseFloat(e.target.value) } })}
              />
            </div>
          </div>
        </section>

        {/* 微信公众号 */}
        <section className="bg-white rounded-xl border border-gray-100 p-5">
          <h3 className="font-medium text-gray-800 mb-4">微信公众号</h3>
          {/* 凭证状态 + 操作按钮 */}
          <div className="flex items-center gap-3 mb-3">
            <span className={`inline-block w-2.5 h-2.5 rounded-full ${
              wechatStatus?.status === 'saved' ? 'bg-yellow-500' : 'bg-gray-300'
            }`} />
            <span className="text-sm text-gray-600">
              {wechatStatus?.status === 'saved'
                ? `已保存 session（${wechatStatus.saved_at?.slice(0, 16).replace('T', ' ') || ''}）`
                : wechatStatus?.status === 'error'
                  ? `错误：${wechatStatus.message}`
                  : '尚未登录'}
            </span>
          </div>
          <p className="text-xs text-gray-400 mb-3">
            点击扫码登录后，将弹出浏览器窗口，请用微信扫码登录公众号后台，登录成功后手动关闭浏览器窗口。
          </p>
          <div className="flex gap-3 mb-4">
            <button
              onClick={wechatLogin}
              disabled={wechatLogging}
              className="bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              {wechatLogging ? '等待扫码中...' : '扫码登录'}
            </button>
            {/* 仅采集微信（已隐藏） */}
            {false && (
            <button
              onClick={async () => {
                setWechatCollecting(true)
                try {
                  await axios.post('/api/wechat/collect', {}, { timeout: 300000 })
                } catch (e) {
                  alert('采集失败: ' + (e.response?.data?.message || e.message))
                } finally {
                  setWechatCollecting(false)
                }
              }}
              disabled={wechatCollecting || wechatStatus?.status !== 'saved'}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {wechatCollecting ? '采集中...' : '仅采集微信'}
            </button>
            )}
          </div>
          {/* 公众号列表 */}
          <WechatSourcesTable
            sources={config.sources?.wechat || []}
            onChange={wechat => setConfig({ ...config, sources: { ...config.sources, wechat } })}
          />
        </section>

        {/* Twitter/X 账号监控 */}
        <TwitterSection
          accounts={config.sources?.twitter?.accounts || []}
          onChange={accounts => {
            const twitter = { ...(config.sources?.twitter || {}), accounts }
            setConfig({ ...config, sources: { ...config.sources, twitter } })
          }}
          useProxy={config.sources?.twitter?.use_proxy !== false}
          onUseProxyChange={use_proxy => {
            const twitter = { ...(config.sources?.twitter || {}), use_proxy }
            setConfig({ ...config, sources: { ...config.sources, twitter } })
          }}
        />

        {/* 定时任务 */}
        <section className="bg-white rounded-xl border border-gray-100 p-5">
          <h3 className="font-medium text-gray-800 mb-4">定时任务</h3>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="scheduler-enabled"
                className="w-4 h-4 accent-blue-600"
                checked={config.scheduler?.enabled || false}
                onChange={e => setConfig({ ...config, scheduler: { ...config.scheduler, enabled: e.target.checked } })}
              />
              <label htmlFor="scheduler-enabled" className="text-sm text-gray-600">启用定时采集</label>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Cron 表达式</label>
              <input
                className="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={config.scheduler?.cron || '0 8 * * *'}
                onChange={e => setConfig({ ...config, scheduler: { ...config.scheduler, cron: e.target.value } })}
              />
              <p className="text-xs text-gray-400 mt-1">
                示例：每天08:00 = "0 8 * * *" | 每6小时 = "0 */6 * * *"
              </p>
            </div>
          </div>
        </section>

        <div className="sticky bottom-0 -mx-1 mt-2 py-3 bg-gray-50/95 backdrop-blur border-t border-gray-200 flex justify-end">
          <button
            onClick={save}
            disabled={saving}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow"
          >
            {saving ? '保存中...' : '保存配置'}
          </button>
        </div>
      </div>
    </div>
  )
}
