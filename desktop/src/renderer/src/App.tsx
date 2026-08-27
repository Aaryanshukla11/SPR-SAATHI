import { useState, useEffect, useRef } from 'react'

interface Step {
  step_id: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  tool_call: any
}

interface ActiveWindow {
  title: string
  process: string
  pid: number
  bounds: {
    x: number
    y: number
    width: number
    height: number
  }
}

interface AgentState {
  status: string
  current_task: string | null
  task_id: string | null
  active_step_id: string | null
  steps: Step[]
  takeover_active: boolean
  error_message: string | null
  computer_state?: {
    active_window: ActiveWindow | null
    screen_width: number
    screen_height: number
    cursor_x: number
    cursor_y: number
  } | null
}

interface FeedItem {
  id: string
  type: string
  message: string
  timestamp: string
}

interface PermissionRequest {
  request_id: string
  tool_name: string
  arguments: any
}

function App(): React.JSX.Element {
  // Connection and Dynamic Port State
  const [port, setPort] = useState<number | null>(null)
  const [isConnected, setIsConnected] = useState(false)

  // Settings
  const [alwaysOnTop, setAlwaysOnTop] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState<'api' | 'local'>('api')
  const [selectedModel, setSelectedModel] = useState('Gemini 3.5 Flash')
  const [showSettings, setShowSettings] = useState(false)
  
  // Permission levels per category
  const [permissions, setPermissions] = useState<Record<string, 'allow' | 'deny' | 'prompt'>>({
    computer: 'prompt',
    windows: 'allow',
    filesystem: 'prompt',
    terminal: 'prompt',
    browser: 'allow'
  })

  // Agent Loop & Task State
  const [agentState, setAgentState] = useState<AgentState>({
    status: 'idle',
    current_task: null,
    task_id: null,
    active_step_id: null,
    steps: [],
    takeover_active: false,
    error_message: null
  })

  // Text Inputs & Event logs
  const [taskInput, setTaskInput] = useState('')
  const [feed, setFeed] = useState<FeedItem[]>([])
  const [activePrompt, setActivePrompt] = useState<PermissionRequest | null>(null)

  const feedEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // 1. Resolve Dynamic Backend Port
  useEffect(() => {
    window.api.getBackendPort()
      .then((p) => {
        setPort(p)
        console.log(`[Renderer] Fetched backend port: ${p}`)
      })
      .catch((err) => console.error('[Renderer] Failed to get port:', err))
  }, [])

  // 2. Connect WebSocket when port is resolved
  useEffect(() => {
    if (port === null) return

    const wsUrl = `ws://127.0.0.1:${port}/ws`
    console.log(`[Renderer] Connecting to WebSocket: ${wsUrl}`)
    
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
      addFeedItem('success', 'Connected to Agent Runtime.', new Date().toISOString())
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        const timestamp = data.timestamp || new Date().toISOString()
        
        switch (data.event_type) {
          case 'status_change':
            if (data.payload?.state) {
              setAgentState(data.payload.state)
            }
            if (data.payload?.policies) {
              setPermissions(data.payload.policies)
            }
            addFeedItem('observe', data.message, timestamp)
            break
          case 'observe':
            setAgentState((prev) => ({ ...prev, status: 'observing' }))
            addFeedItem('observe', data.message, timestamp)
            break
          case 'plan':
            setAgentState((prev) => ({ ...prev, status: 'planning' }))
            if (data.payload?.steps) {
              setAgentState((prev) => ({
                ...prev,
                steps: data.payload.steps.map((desc: string, i: number) => ({
                  step_id: `step_${i + 1}`,
                  description: desc,
                  status: 'pending',
                  tool_call: null
                }))
              }))
            }
            addFeedItem('plan', data.message, timestamp)
            break
          case 'permission_required':
            setAgentState((prev) => ({ ...prev, status: 'checking_permission' }))
            if (data.payload) {
              setActivePrompt({
                request_id: data.payload.request_id,
                tool_name: data.payload.tool_name,
                arguments: data.payload.arguments
              })
            }
            addFeedItem('takeover', data.message, timestamp)
            break
          case 'act':
            setAgentState((prev) => ({ ...prev, status: 'acting' }))
            if (data.payload?.tool_call) {
              const tc = data.payload.tool_call
              setAgentState((prev) => ({
                ...prev,
                active_step_id: tc.call_id,
                steps: prev.steps.map((s) => 
                  s.description.includes(tc.tool_name) ? { ...s, status: 'running', tool_call: tc } : s
                )
              }))
            }
            addFeedItem('act', data.message, timestamp)
            break
          case 'verify':
            setAgentState((prev) => ({ ...prev, status: 'verifying' }))
            addFeedItem('verify', data.message, timestamp)
            break
          case 'takeover':
            const isTakeover = data.payload?.takeover_active ?? false
            setAgentState((prev) => ({ 
              ...prev, 
              takeover_active: isTakeover, 
              status: isTakeover ? 'takeover' : prev.status 
            }))
            addFeedItem('takeover', data.message, timestamp)
            break
          case 'stop':
            setAgentState((prev) => ({ 
              ...prev, 
              status: 'stopped',
              steps: prev.steps.map((s) => s.status === 'running' || s.status === 'pending' ? { ...s, status: 'cancelled' } : s)
            }))
            addFeedItem('error', data.message, timestamp)
            break
          case 'log':
            addFeedItem('observe', data.message, timestamp)
            break
          case 'error':
            setAgentState((prev) => ({ 
              ...prev, 
              status: 'error',
              error_message: data.message,
              steps: prev.steps.map((s) => s.status === 'running' ? { ...s, status: 'failed' } : s)
            }))
            addFeedItem('error', data.message, timestamp)
            break
          case 'task_completed':
            setAgentState((prev) => ({ 
              ...prev, 
              status: 'completed',
              steps: prev.steps.map((s) => s.status === 'running' ? { ...s, status: 'completed' } : s)
            }))
            addFeedItem('success', data.message, timestamp)
            break
        }
      } catch (err) {
        console.error('[WS] Failed to parse message:', err)
      }
    }

    ws.onclose = () => {
      setIsConnected(false)
      addFeedItem('error', 'Agent Runtime disconnected. Attempting reconnect...', new Date().toISOString())
      // Simple reconnect poll
      setTimeout(() => setPort((p) => p), 3000)
    }

    return () => {
      ws.close()
    }
  }, [port])

  // Sync Feed Scrolling
  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [feed])

  // Helper: Append event to local feed UI
  const addFeedItem = (type: string, message: string, timestamp: string) => {
    setFeed((prev) => [
      ...prev,
      {
        id: Math.random().toString(36).substr(2, 9),
        type,
        message,
        timestamp: new Date(timestamp).toLocaleTimeString()
      }
    ])
  }

  // API wrappers
  const triggerStartTask = async () => {
    if (!taskInput.trim() || port === null) return
    try {
      addFeedItem('user', taskInput, new Date().toISOString())
      const res = await fetch(`http://127.0.0.1:${port}/api/task/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: taskInput })
      })
      const data = await res.json()
      if (res.ok) {
        setAgentState((prev) => ({
          ...prev,
          current_task: taskInput,
          task_id: data.task_id,
          steps: [],
          error_message: null
        }))
        setTaskInput('')
      } else {
        addFeedItem('error', `Start Failed: ${data.detail}`, new Date().toISOString())
      }
    } catch (e) {
      addFeedItem('error', `Network Error: ${e}`, new Date().toISOString())
    }
  }

  const triggerStopTask = async () => {
    if (port === null) return
    try {
      await fetch(`http://127.0.0.1:${port}/api/task/stop`, { method: 'POST' })
    } catch (e) {
      console.error('Stop request error:', e)
    }
  }

  const toggleTakeover = async () => {
    if (port === null) return
    const endpoint = agentState.takeover_active ? 'release' : 'take'
    try {
      await fetch(`http://127.0.0.1:${port}/api/takeover/${endpoint}`, { method: 'POST' })
    } catch (e) {
      console.error('Takeover request error:', e)
    }
  }

  const respondPermission = async (decision: 'allow' | 'deny') => {
    if (port === null || !activePrompt) return
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/permission/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: activePrompt.request_id,
          decision
        })
      })
      if (res.ok) {
        setActivePrompt(null)
      }
    } catch (e) {
      console.error('Permission respond error:', e)
    }
  }

  const updateAlwaysOnTop = (val: boolean) => {
    setAlwaysOnTop(val)
    window.api.setAlwaysOnTop(val)
  }

  const handleModelChange = async (provider: 'api' | 'local', model: string) => {
    setSelectedProvider(provider)
    setSelectedModel(model)
    if (port === null) return
    try {
      await fetch(`http://127.0.0.1:${port}/api/config/model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, model_name: model })
      })
      addFeedItem('observe', `Configured model provider to [${provider.toUpperCase()}] ${model}`, new Date().toISOString())
    } catch (e) {
      console.error('Config model error:', e)
    }
  }

  const handlePermissionChange = async (scope: string, level: 'allow' | 'deny' | 'prompt') => {
    setPermissions((prev) => ({ ...prev, [scope]: level }))
    if (port === null) return
    try {
      await fetch(`http://127.0.0.1:${port}/api/config/permission`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope, level })
      })
    } catch (e) {
      console.error('Config permission error:', e)
    }
  }

  // Active status visualizer matching
  const status = agentState.status

  return (
    <div className="app-container">
      {/* Header Section */}
      <header className="app-header">
        <div className="header-top">
          <div className="logo-section">
            <div className="logo-dot"></div>
            <h1 className="app-title">SPR SAATHI</h1>
          </div>
          <div className={`header-status ${status}`}>
            <span className={`status-dot ${status}`}></span>
            {isConnected ? status.replace('_', ' ') : 'disconnected'}
          </div>
        </div>
        <div className="header-actions">
          <span className="model-badge">🤖 {selectedModel}</span>
          <label className="toggle-label">
            <input 
              type="checkbox" 
              checked={alwaysOnTop} 
              onChange={(e) => updateAlwaysOnTop(e.target.checked)} 
            />
            Pin Top
          </label>
        </div>
      </header>

      {/* Main Content Scroll Panel */}
      <main className="app-content">
        
        {/* OBSERVE → PLAN → CHECK → ACT → VERIFY Nodes */}
        <section className="loop-visualizer">
          <div className="section-title">Loop Activity</div>
          <div className="loop-steps-grid">
            <div className={`loop-step-node ${status === 'observing' ? 'active' : ''}`}>
              <div className="node-icon observe">🔍</div>
              <span>OBSERVE</span>
            </div>
            <div className={`loop-step-node ${status === 'planning' ? 'active' : ''}`}>
              <div className="node-icon plan">📋</div>
              <span>PLAN</span>
            </div>
            <div className={`loop-step-node ${status === 'checking_permission' ? 'active' : ''}`}>
              <div className="node-icon check">🛡️</div>
              <span>CHECK</span>
            </div>
            <div className={`loop-step-node ${status === 'acting' ? 'active' : ''}`}>
              <div className="node-icon act">⚡</div>
              <span>ACT</span>
            </div>
            <div className={`loop-step-node ${status === 'verifying' ? 'active' : ''}`}>
              <div className="node-icon verify">✔</div>
              <span>VERIFY</span>
            </div>
          </div>
        </section>

        {/* Computer State Card */}
        {agentState.computer_state && (
          <div 
            style={{ 
              background: 'var(--bg-card)', 
              border: '1px solid var(--border-glass)', 
              borderRadius: '12px', 
              padding: '12px', 
              fontSize: '12px', 
              display: 'flex', 
              flexDirection: 'column', 
              gap: '6px',
              animation: 'slide-in 0.2s ease-out'
            }}
          >
            <div className="section-title">Computer State</div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-text-secondary)' }}>Screen:</span>
              <span style={{ fontWeight: 600 }}>{agentState.computer_state.screen_width} × {agentState.computer_state.screen_height}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-text-secondary)' }}>Cursor:</span>
              <span style={{ fontWeight: 600, color: 'var(--color-act)' }}>{agentState.computer_state.cursor_x}, {agentState.computer_state.cursor_y}</span>
            </div>
            {agentState.computer_state.active_window && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>Active Window:</span>
                  <span style={{ fontWeight: 600, maxWidth: '180px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={agentState.computer_state.active_window.title}>
                    {agentState.computer_state.active_window.title}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>Process:</span>
                  <span style={{ fontFamily: 'monospace' }}>{agentState.computer_state.active_window.process}</span>
                </div>
              </>
            )}
          </div>
        )}

        {/* Dynamic Action Steps Checklist */}
        {agentState.steps.length > 0 && (
          <section className="steps-checklist">
            <div className="section-title">Execution Steps</div>
            {agentState.steps.map((step) => (
              <div 
                key={step.step_id} 
                className={`step-item ${step.status} ${agentState.active_step_id === step.step_id ? 'running' : ''}`}
              >
                <div className="step-indicator"></div>
                <div className="step-desc" title={step.description}>{step.description}</div>
              </div>
            ))}
          </section>
        )}

        {/* Permission Authorization Card */}
        {activePrompt && (
          <section className="permission-overlay">
            <div className="section-title" style={{ color: 'var(--color-takeover)' }}>🛡️ Security Check Required</div>
            <div className="prompt-text">
              Agent is requesting to use <strong>{activePrompt.tool_name}</strong>:
            </div>
            <div className="prompt-args">
              {JSON.stringify(activePrompt.arguments, null, 2)}
            </div>
            <div className="prompt-actions">
              <button className="btn btn-primary" onClick={() => respondPermission('allow')}>
                Allow Action
              </button>
              <button className="btn btn-danger" onClick={() => respondPermission('deny')}>
                Block Action
              </button>
            </div>
          </section>
        )}

        {/* Console Event Logs */}
        <section className="event-feed">
          <div className="section-title">Execution Log</div>
          <div className="feed-items">
            {feed.map((item) => (
              <div key={item.id} className={`feed-item ${item.type}`}>
                <div className="feed-time">{item.timestamp}</div>
                <div>{item.message}</div>
              </div>
            ))}
            <div ref={feedEndRef} />
          </div>
        </section>

        {/* Dynamic configuration (Expandable) */}
        <section className="settings-panel">
          <div 
            className="section-title" 
            style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between' }}
            onClick={() => setShowSettings(!showSettings)}
          >
            <span>⚙️ Configuration Settings</span>
            <span>{showSettings ? '▲' : '▼'}</span>
          </div>

          {showSettings && (
            <>
              {/* Model selection */}
              <div className="settings-row">
                <span>Model Provider:</span>
                <select 
                  className="settings-select"
                  value={`${selectedProvider}:${selectedModel}`}
                  onChange={(e) => {
                    const [provider, modelName] = e.target.value.split(':')
                    handleModelChange(provider as 'api' | 'local', modelName)
                  }}
                >
                  <option value="api:Gemini 3.5 Flash">Gemini 3.5 Flash (Cloud)</option>
                  <option value="api:OpenAI GPT-4o">OpenAI GPT-4o (Cloud)</option>
                  <option value="local:Llama 3 8B">Llama 3 8B (Local)</option>
                  <option value="local:Phi-4">Phi-4 (Local)</option>
                </select>
              </div>

              {/* Permission Policy overrides */}
              <div className="permissions-grid" style={{ marginTop: '8px' }}>
                <div className="section-title" style={{ fontSize: '10px' }}>Broker Policies</div>
                {Object.keys(permissions).map((scope) => (
                  <div key={scope} className="permission-row">
                    <span style={{ textTransform: 'capitalize' }}>{scope}:</span>
                    <select
                      className="settings-select"
                      style={{ padding: '2px 4px', fontSize: '11px' }}
                      value={permissions[scope]}
                      onChange={(e) => handlePermissionChange(scope, e.target.value as any)}
                    >
                      <option value="allow">Allow</option>
                      <option value="prompt">Prompt</option>
                      <option value="deny">Deny</option>
                    </select>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>

      </main>

      {/* Footer Interface controls */}
      <footer className="app-footer">
        
        {/* Start / Stop / Takeover Buttons */}
        <div className="action-row">
          {status !== 'idle' && status !== 'completed' && status !== 'error' && status !== 'stopped' && (
            <>
              <button 
                className={`btn ${agentState.takeover_active ? 'btn-primary' : 'btn-secondary'}`}
                onClick={toggleTakeover}
              >
                {agentState.takeover_active ? 'Resume Agent' : 'Take Control'}
              </button>
              <button className="btn btn-danger" onClick={triggerStopTask}>
                Stop Task
              </button>
            </>
          )}
        </div>

        {/* Natural Language Prompt Input */}
        <div className="input-container">
          <input
            type="text"
            className="chat-input"
            placeholder="Type a computer command..."
            value={taskInput}
            onChange={(e) => setTaskInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && triggerStartTask()}
            disabled={status !== 'idle' && status !== 'completed' && status !== 'error' && status !== 'stopped'}
          />
          <button 
            className="mic-button" 
            title="Voice input placeholder (Phase 1)"
            onClick={() => addFeedItem('error', 'Voice input is not implemented in Phase 0.', new Date().toISOString())}
          >
            🎤
          </button>
        </div>
      </footer>
    </div>
  )
}

export default App
