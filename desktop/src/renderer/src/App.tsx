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
  const [backendStatus, setBackendStatus] = useState<'connecting' | 'connected' | 'disconnected' | 'unavailable'>('connecting')
  const [reconnectAttempts, setReconnectAttempts] = useState(0)
  const [activeTab, setActiveTab] = useState<'control' | 'security' | 'settings' | 'logs'>('control')
  const [showLoopActivity, setShowLoopActivity] = useState(false)
  const [takeoverLoading, setTakeoverLoading] = useState(false)
  const [installedApps, setInstalledApps] = useState<{name: string, version: string, publisher: string, key: string}[]>([])
  const [searchQuery, setSearchQuery] = useState('')

  // Voice Input State
  const [voiceState, setVoiceState] = useState<'idle' | 'listening' | 'processing' | 'transcribing' | 'ready' | 'error'>('idle')
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const [micPermission, setMicPermission] = useState<'prompt' | 'granted' | 'denied'>(() => {
    return (localStorage.getItem('mic-permission') as any) || 'prompt'
  })
  const [showMicPrompt, setShowMicPrompt] = useState(false)
  const recognitionRef = useRef<any>(null)

  // Settings
  const [selectedProvider, setSelectedProvider] = useState<'api' | 'local'>('api')
  const [selectedModel, setSelectedModel] = useState('Gemini 3.5 Flash')

  // Permission levels per category
  const [permissions, setPermissions] = useState<Record<string, 'allow' | 'deny' | 'prompt'>>({
    mouse: 'prompt',
    keyboard: 'prompt',
    applications: 'prompt',
    filesystem: 'prompt',
    browser: 'prompt',
    terminal: 'deny',
    powershell: 'deny'
  })

  // Specific application overrides settings
  const [appPermissions, setAppPermissions] = useState<Record<string, 'allow' | 'deny' | 'prompt'>>({})

  // Audit Logs
  interface AuditLogItem {
    timestamp: string
    task_id: string
    request_id: string
    scope: string
    resource: string
    action: string
    decision: string
    source: string
  }
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([])

  const fetchAuditLogs = async () => {
    if (port === null) return
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/permissions/audit`)
      if (res.ok) {
        const logs = await res.json()
        setAuditLogs(logs)
      }
    } catch (e) {
      console.error('Fetch audit logs error:', e)
    }
  }

  // Poll audit logs when security panel is open
  useEffect(() => {
    if (activeTab === 'security' && port !== null) {
      fetchAuditLogs()
      const interval = setInterval(fetchAuditLogs, 4000)
      return () => clearInterval(interval)
    }
    return undefined
  }, [activeTab, port])

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
  const [userQuestion, setUserQuestion] = useState<string | null>(null)

  const respondUserQuestion = async (response: string) => {
    if (port === null) return
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/task/respond_question`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ response })
      })
      if (res.ok) {
        setUserQuestion(null)
      }
    } catch (e) {
      console.error('Respond user question error:', e)
    }
  }

  const feedEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // 1. Resolve Dynamic Backend Port
  useEffect(() => {
    window.api.getBackendPort()
      .then((p) => {
        if (p === -1) {
          console.error('[Renderer] Port resolution failed.')
          setBackendStatus('unavailable')
        } else {
          console.log(`[Renderer] Resolved backend port: ${p}`)
          setPort(p)
        }
      })
      .catch((err) => {
        console.error('[Renderer] Failed to resolve port:', err)
        setBackendStatus('unavailable')
      })
  }, [])

  // 2. Connect WebSocket when port is resolved
  useEffect(() => {
    if (port === null) return
    let isMounted = true
    let ws: WebSocket | null = null
    let readinessTimer: NodeJS.Timeout | null = null

    const startConnection = async () => {
      setBackendStatus('connecting')
      
      // Readiness loop: poll /api/health up to 5 times
      let isReady = false
      for (let i = 0; i < 5; i++) {
        if (!isMounted) return
        try {
          console.log(`[Renderer] Health check attempt ${i + 1}...`)
          const res = await fetch(`http://127.0.0.1:${port}/api/health`)
          if (res.ok) {
            const data = await res.json()
            if (data.status === 'ok') {
              isReady = true
              break
            }
          }
        } catch (e) {
          console.log(`[Renderer] Health check ${i + 1} failed, retrying...`)
        }
        // Wait 1.5s between retries (total timeout of 7.5 seconds)
        await new Promise((resolve) => setTimeout(resolve, 1500))
      }

      if (!isReady) {
        console.error('[Renderer] Backend failed health check readiness loop.')
        if (isMounted) {
          setBackendStatus('unavailable')
        }
        return
      }

      const wsUrl = `ws://127.0.0.1:${port}/ws`
      console.log(`[Renderer] Connecting to WebSocket: ${wsUrl}`)
      
      ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        if (!isMounted) return
        setBackendStatus('connected')
        setReconnectAttempts(0) // Reset attempts on success
        addFeedItem('success', 'Connected to Agent Runtime.', new Date().toISOString())
      }

      ws.onmessage = (event) => {
        if (!isMounted) return
        try {
          const data = JSON.parse(event.data)
          const timestamp = data.timestamp || new Date().toISOString()
          
          switch (data.event_type) {
            case 'status_change':
              if (data.payload?.state) {
                setAgentState(data.payload.state)
              }
              if (data.payload?.policies) {
                setPermissions(data.payload.policies.policies || {})
                setAppPermissions(data.payload.policies.app_policies || {})
              }
              addFeedItem('observe', data.message, timestamp)
              break
            case 'permission.updated':
              if (data.payload?.policies) {
                setPermissions(data.payload.policies.policies || {})
                setAppPermissions(data.payload.policies.app_policies || {})
              }
              fetchAuditLogs()
              break
            case 'observe':
            case 'task.observation':
              setAgentState((prev) => {
                const nextState = { ...prev, status: 'running' }
                if (data.payload?.active_window) {
                  nextState.computer_state = {
                    screen_width: data.payload.screen?.width || 1920,
                    screen_height: data.payload.screen?.height || 1080,
                    cursor_x: data.payload.cursor?.x || 0,
                    cursor_y: data.payload.cursor?.y || 0,
                    active_window: data.payload.active_window
                  }
                }
                return nextState
              })
              addFeedItem('observe', data.message, timestamp)
              break
            case 'plan':
            case 'task.planning':
              setAgentState((prev) => ({ ...prev, status: 'planning' }))
              addFeedItem('plan', data.message, timestamp)
              break
            case 'task.plan_updated':
              if (data.payload?.steps) {
                setAgentState((prev) => ({
                  ...prev,
                  steps: data.payload.steps.map((s: any) => ({
                    step_id: s.step_id || s.id,
                    description: s.description,
                    status: s.status || 'pending',
                    tool_call: s.tool_call || null
                  }))
                }))
              }
              break
            case 'task.decision':
              addFeedItem('act', `Decision: ${data.message}`, timestamp)
              break
            case 'permission_required':
              setAgentState((prev) => ({ ...prev, status: 'waiting_permission' }))
              if (data.payload) {
                setActivePrompt({
                  request_id: data.payload.request_id,
                  tool_name: data.payload.tool_name,
                  arguments: data.payload.arguments
                })
              }
              addFeedItem('takeover', data.message, timestamp)
              break
            case 'tool.requested':
              setAgentState((prev) => ({ ...prev, status: 'waiting_permission' }))
              addFeedItem('takeover', data.message, timestamp)
              break
            case 'act':
            case 'tool.started':
              setAgentState((prev) => ({ ...prev, status: 'acting' }))
              if (data.payload?.tool_call) {
                const tc = data.payload.tool_call
                setAgentState((prev) => ({
                  ...prev,
                  active_step_id: tc.call_id,
                  steps: prev.steps.map((s) => 
                    s.step_id === tc.call_id || s.description.toLowerCase().includes(tc.tool_name.toLowerCase()) ? { ...s, status: 'running', tool_call: tc } : s
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
            case 'task.paused':
            case 'control.takeover_started':
              setAgentState((prev) => ({ 
                ...prev, 
                takeover_active: true, 
                status: 'paused'
              }))
              addFeedItem('takeover', data.message, timestamp)
              break
            case 'control.release_requested':
            case 'task.resuming':
              setAgentState((prev) => ({ 
                ...prev, 
                status: 'resuming'
              }))
              addFeedItem('observe', data.message, timestamp)
              break
            case 'task.resumed':
              setAgentState((prev) => ({ 
                ...prev, 
                takeover_active: false, 
                status: 'running'
              }))
              addFeedItem('success', data.message, timestamp)
              break
            case 'stop':
            case 'task.cancelled':
              setAgentState((prev) => ({ 
                ...prev, 
                status: 'cancelled',
                steps: prev.steps.map((s) => s.status === 'running' || s.status === 'pending' ? { ...s, status: 'cancelled' } : s)
              }))
              setActivePrompt(null)
              setUserQuestion(null)
              addFeedItem('error', data.message, timestamp)
              break
            case 'log':
              addFeedItem('observe', data.message, timestamp)
              break
            case 'error':
            case 'task.failed':
            case 'tool.failed':
              setAgentState((prev) => ({ 
                ...prev, 
                status: 'failed',
                error_message: data.message,
                steps: prev.steps.map((s) => s.status === 'running' ? { ...s, status: 'failed' } : s)
              }))
              setActivePrompt(null)
              setUserQuestion(null)
              addFeedItem('error', data.message, timestamp)
              break
            case 'task_completed':
            case 'task.completed':
              setAgentState((prev) => ({ 
                ...prev, 
                status: 'completed',
                steps: prev.steps.map((s) => s.status === 'running' || s.status === 'pending' ? { ...s, status: 'completed' } : s)
              }))
              setActivePrompt(null)
              setUserQuestion(null)
              addFeedItem('success', data.message, timestamp)
              break
            case 'tool.completed':
              setAgentState((prev) => ({
                ...prev,
                steps: prev.steps.map((s) => s.status === 'running' ? { ...s, status: 'completed' } : s)
              }))
              addFeedItem('success', data.message, timestamp)
              break
            case 'task.waiting_user':
              setAgentState((prev) => ({ ...prev, status: 'waiting_user' }))
              if (data.payload?.question) {
                setUserQuestion(data.payload.question)
              }
              addFeedItem('takeover', data.message, timestamp)
              break
          }
        } catch (err) {
          console.error('[WS] Failed to parse message:', err)
        }
      }

      ws.onclose = () => {
        if (!isMounted) return
        setBackendStatus('disconnected')
        addFeedItem('error', 'Agent Runtime disconnected. Reconnecting...', new Date().toISOString())
        
        // Bounded reconnect loop (attempts 1 to 5)
        const maxReconnects = 5
        if (reconnectAttempts < maxReconnects) {
          const delay = (reconnectAttempts + 1) * 3000
          console.log(`[Renderer] Reconnecting WebSocket in ${delay}ms (Attempt ${reconnectAttempts + 1}/${maxReconnects})`)
          readinessTimer = setTimeout(() => {
            setReconnectAttempts((prev) => prev + 1)
          }, delay)
        } else {
          console.error('[Renderer] Bounded reconnect attempts exhausted.')
          setBackendStatus('unavailable')
        }
      }

      ws.onerror = (e) => {
        console.error('[WS] Socket error:', e)
      }
    }

    startConnection()

    return () => {
      isMounted = false
      if (ws) {
        ws.close()
      }
      if (readinessTimer) {
        clearTimeout(readinessTimer)
      }
    }
  }, [port, reconnectAttempts])

  // Fetch installed applications when port resolved
  useEffect(() => {
    if (port === null) return
    fetch(`http://127.0.0.1:${port}/api/config/installed_apps`)
      .then((res) => res.json())
      .then((data) => {
        if (Array.isArray(data)) {
          setInstalledApps(data)
        }
      })
      .catch((e) => console.error('[Renderer] Error fetching installed apps:', e))
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

  // Voice Input Actions
  const handleAllowMic = async () => {
    setShowMicPrompt(false)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((track) => track.stop())
      
      setMicPermission('granted')
      localStorage.setItem('mic-permission', 'granted')
      startSpeechRecognition()
    } catch (e) {
      console.error('Microphone permission check error:', e)
      setMicPermission('denied')
      localStorage.setItem('mic-permission', 'denied')
      setVoiceState('error')
      setVoiceError('Microphone access denied. Check Windows microphone permissions.')
    }
  }

  const handleDenyMic = () => {
    setShowMicPrompt(false)
    setMicPermission('denied')
    localStorage.setItem('mic-permission', 'denied')
    setVoiceState('error')
    setVoiceError('Voice input was disabled by user.')
  }

  const handleMicClick = () => {
    if (micPermission === 'denied') {
      setVoiceState('error')
      setVoiceError('Microphone access is denied. Please enable it in Windows settings.')
      return
    }
    if (micPermission === 'prompt') {
      setShowMicPrompt(true)
      return
    }
    startSpeechRecognition()
  }

  const startSpeechRecognition = () => {
    const SpeechRecognition = 
      (window as any).SpeechRecognition || 
      (window as any).webkitSpeechRecognition || 
      (window as any).MockSpeechRecognition

    if (!SpeechRecognition) {
      setVoiceState('error')
      setVoiceError('Speech recognition is not supported in this client.')
      return
    }

    setVoiceState('listening')
    setVoiceError(null)

    const recognition = new SpeechRecognition()
    recognitionRef.current = recognition
    recognition.continuous = false
    recognition.interimResults = false
    recognition.lang = 'en-US'

    recognition.onstart = () => {
      setVoiceState('listening')
    }

    recognition.onerror = (event: any) => {
      console.error('[Speech] Error:', event.error)
      setVoiceState('error')
      if (event.error === 'not-allowed') {
        setVoiceError('Microphone permission denied.')
      } else if (event.error === 'no-speech') {
        setVoiceError('No speech detected. Please try again.')
      } else {
        setVoiceError(`Transcription failed: ${event.error}`)
      }
    }

    recognition.onend = () => {
      setVoiceState((prev) => (prev === 'listening' ? 'idle' : prev))
    }

    recognition.onresult = (event: any) => {
      setVoiceState('processing')
      const transcript = event.results[0][0].transcript
      console.log('[Speech] Transcribed text:', transcript)
      
      if (transcript && transcript.trim()) {
        setVoiceState('transcribing')
        setTaskInput(transcript)
        setVoiceState('ready')
        
        // Auto submit command
        setTimeout(() => {
          triggerStartTask(transcript)
          setVoiceState('idle')
        }, 800)
      } else {
        setVoiceState('error')
        setVoiceError('No speech detected. Please try again.')
      }
    }

    recognition.start()
  }

  // API wrappers (Unified Task Submission)
  const triggerStartTask = async (inputCommand?: string) => {
    const command = inputCommand !== undefined ? inputCommand : taskInput
    if (!command.trim() || port === null) return
    try {
      addFeedItem('user', command, new Date().toISOString())
      const res = await fetch(`http://127.0.0.1:${port}/api/task/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: command })
      })
      const data = await res.json()
      if (res.ok) {
        setAgentState((prev) => ({
          ...prev,
          current_task: command,
          task_id: data.task_id,
          steps: [],
          error_message: null
        }))
        if (inputCommand === undefined) {
          setTaskInput('')
        }
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
    if (port === null || takeoverLoading) return
    setTakeoverLoading(true)
    const endpoint = agentState.takeover_active ? 'release' : 'takeover'
    try {
      await fetch(`http://127.0.0.1:${port}/api/control/${endpoint}`, { method: 'POST' })
    } catch (e) {
      console.error('Takeover request error:', e)
    } finally {
      setTakeoverLoading(false)
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
      await fetch(`http://127.0.0.1:${port}/api/permissions/${scope}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level })
      })
      fetchAuditLogs()
    } catch (e) {
      console.error('Config permission error:', e)
    }
  }

  const handleAppPermissionChange = async (appId: string, level: 'allow' | 'deny' | 'prompt') => {
    const normalizedAppId = appId.toLowerCase().trim()
    if (level === 'prompt') {
      setAppPermissions((prev) => {
        const copy = { ...prev }
        delete copy[normalizedAppId]
        return copy
      })
      if (port === null) return
      try {
        await fetch(`http://127.0.0.1:${port}/api/permissions/application/${appId}`, {
          method: 'DELETE'
        })
        fetchAuditLogs()
      } catch (e) {
        console.error('Delete app override error:', e)
      }
      return
    }

    setAppPermissions((prev) => ({ ...prev, [normalizedAppId]: level }))
    if (port === null) return
    try {
      await fetch(`http://127.0.0.1:${port}/api/permissions/application/${appId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level })
      })
      fetchAuditLogs()
    } catch (e) {
      console.error('Config app permission error:', e)
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
          {backendStatus === 'connected' ? (
            <div className={`header-status connected ${status}`}>
              <span className={`status-dot ${status}`}></span>
              <span>{status.replace('_', ' ')}</span>
            </div>
          ) : backendStatus === 'connecting' ? (
            <div className="header-status connecting">
              <span className="status-dot connecting"></span>
              <span>Connecting...</span>
            </div>
          ) : backendStatus === 'unavailable' ? (
            <div className="header-status unavailable">
              <span className="status-dot unavailable"></span>
              <span>Backend unavailable</span>
            </div>
          ) : (
            <div className="header-status disconnected">
              <span className="status-dot disconnected"></span>
              <span>Disconnected</span>
            </div>
          )}
        </div>
        <div className="header-actions">
          <span className="model-badge">AI: {selectedModel}</span>
        </div>
      </header>

      {/* Tab Selector Bar */}
      <div className="tab-selector-bar">
        <button 
          className={`tab-button ${activeTab === 'control' ? 'active' : ''}`}
          onClick={() => setActiveTab('control')}
          title="Control Panel"
        >
          <span className="tab-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="7" height="9" />
              <rect x="14" y="3" width="7" height="5" />
              <rect x="14" y="12" width="7" height="9" />
              <rect x="3" y="16" width="7" height="5" />
            </svg>
          </span>
          <span className="tab-label">Control Panel</span>
        </button>
        <button 
          className={`tab-button ${activeTab === 'security' ? 'active' : ''}`}
          onClick={() => setActiveTab('security')}
          title="Security & Apps"
        >
          <span className="tab-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </span>
          <span className="tab-label">Security & Apps</span>
        </button>
        <button 
          className={`tab-button ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
          title="Settings"
        >
          <span className="tab-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </span>
          <span className="tab-label">Settings</span>
        </button>
        <button 
          className={`tab-button ${activeTab === 'logs' ? 'active' : ''}`}
          onClick={() => setActiveTab('logs')}
          title="Execution Logs"
        >
          <span className="tab-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="4 17 10 11 4 5" />
              <line x1="12" y1="19" x2="20" y2="19" />
            </svg>
          </span>
          <span className="tab-label">
            Execution Logs 
            {feed.length > 0 && (
              <span style={{ marginLeft: '4px', padding: '1px 5px', background: 'rgba(255, 255, 255, 0.1)', borderRadius: '10px', fontSize: '9px' }}>
                {feed.length}
              </span>
            )}
          </span>
        </button>
      </div>

      {/* Main Content Scroll Panel */}
      <main className="app-content">
        {activeTab === 'control' ? (
          <>
            {/* Dynamic Status Button at the top of Control Panel */}
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '16px' }}>
              <div 
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 20px',
                  borderRadius: '20px',
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-glass)',
                  color: '#ffffff',
                  fontSize: '13px',
                  fontWeight: 600,
                  boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                  cursor: 'pointer',
                  textTransform: 'uppercase',
                  transition: 'background 0.2s ease, border-color 0.2s ease'
                }}
                onClick={() => setShowLoopActivity(!showLoopActivity)}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.2)'
                  e.currentTarget.style.background = 'rgba(255,255,255,0.03)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border-glass)'
                  e.currentTarget.style.background = 'var(--bg-card)'
                }}
              >
                {status === 'observing' ? (
                  <>
                    <span style={{ display: 'inline-block', animation: 'spin 2s linear infinite' }}>🔍</span>
                    <span>Observing System</span>
                  </>
                ) : status === 'planning' ? (
                  <>
                    <span style={{ display: 'inline-block', animation: 'pulse 1s infinite' }}>📋</span>
                    <span>Planning Action</span>
                  </>
                ) : status === 'checking_permission' ? (
                  <>
                    <span>🛡️</span>
                    <span>Checking Permissions</span>
                  </>
                ) : status === 'acting' ? (
                  <>
                    <span style={{ display: 'inline-block', animation: 'pulse 0.5s infinite' }}>⚡</span>
                    <span>Executing Action</span>
                  </>
                ) : status === 'verifying' ? (
                  <>
                    <span style={{ color: 'var(--color-success)' }}>✔</span>
                    <span>Verifying Results</span>
                  </>
                ) : status === 'waiting_user' ? (
                  <>
                    <span style={{ display: 'inline-block', animation: 'pulse 1.2s infinite', color: 'var(--color-act)' }}>❓</span>
                    <span>Waiting for User Response</span>
                  </>
                ) : status === 'completed' ? (
                  <>
                    <span style={{ color: '#10b981' }}>🎉</span>
                    <span>Task Completed</span>
                  </>
                ) : status === 'failed' || status === 'error' ? (
                  <>
                    <span style={{ color: '#ef4444' }}>❌</span>
                    <span>Task Failed</span>
                  </>
                ) : status === 'stopped' ? (
                  <>
                    <span style={{ color: '#f59e0b' }}>🛑</span>
                    <span>Task Stopped</span>
                  </>
                ) : (
                  <>
                    <span style={{ color: '#10b981' }}>●</span>
                    <span>Agent Idle</span>
                  </>
                )}
                <span style={{ marginLeft: '4px', fontSize: '10px', color: 'var(--color-text-secondary)' }}>
                  {showLoopActivity ? '▲' : '▼'}
                </span>
              </div>
            </div>

            {/* Collapsible Loop Activity visualizer */}
            {showLoopActivity && (
              <section className="loop-visualizer" style={{ marginBottom: '16px', animation: 'slide-in 0.2s ease-out' }}>
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
            )}

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
                <div className="section-title" style={{ color: 'var(--color-takeover)' }}>Security Check Required</div>
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

            {/* Clarification Prompt Overlay */}
            {status === 'waiting_user' && (
              <section className="permission-overlay" style={{ borderColor: 'var(--color-act)' }}>
                <div className="section-title" style={{ color: 'var(--color-act)' }}>Clarification Required</div>
                <div className="prompt-text" style={{ marginBottom: '10px' }}>
                  <strong>The Agent asks:</strong>
                  <div style={{ marginTop: '6px', padding: '10px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px', border: '1px solid var(--border-glass)' }}>
                    {userQuestion || "I need clarification to proceed. Please respond below."}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
                  <input 
                    id="userClarificationResponse"
                    placeholder="Type your response here..."
                    style={{ flex: 1, padding: '8px 12px', borderRadius: '8px', border: '1px solid var(--border-glass)', background: 'var(--bg-card)', color: 'var(--color-text)', outline: 'none' }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        respondUserQuestion(e.currentTarget.value)
                        e.currentTarget.value = ''
                      }
                    }}
                  />
                  <button 
                    className="btn btn-primary"
                    onClick={() => {
                      const input = document.getElementById('userClarificationResponse') as HTMLInputElement
                      if (input) {
                        respondUserQuestion(input.value)
                        input.value = ''
                      }
                    }}
                  >
                    Send
                  </button>
                </div>
              </section>
            )}

          </>
        ) : activeTab === 'security' ? (
          <>
            {/* Security & Applications Access Control Panel */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', height: '100%', overflow: 'hidden' }}>
              
              {/* Scope Policies (Global) */}
              <section className="settings-panel" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-glass)', borderRadius: '12px', padding: '12px' }}>
                <div className="section-title" style={{ marginBottom: '8px' }}>Scope Access Policies</div>
                <div className="permissions-grid" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {Object.keys(permissions).map((scope) => (
                    <div key={scope} className="permission-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ textTransform: 'capitalize', fontSize: '11px', fontWeight: 600 }}>{scope}:</span>
                      <select
                        className="settings-select"
                        style={{ padding: '2px 4px', fontSize: '11px', borderRadius: '4px' }}
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
              </section>

              {/* Installed Applications access configuration */}
              <section style={{ display: 'flex', flexDirection: 'column', flex: 1, background: 'var(--bg-card)', border: '1px solid var(--border-glass)', borderRadius: '12px', padding: '12px', overflow: 'hidden' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <div className="section-title" style={{ margin: 0 }}>Installed System Software</div>
                  <div style={{ fontSize: '10px', color: 'var(--color-text-secondary)' }}>
                    {installedApps.length} Apps Found
                  </div>
                </div>

                {/* Search Box */}
                <input
                  type="text"
                  placeholder="Search applications (e.g. Blender, Edge...)"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '6px 10px',
                    background: 'var(--bg-input)',
                    border: '1px solid var(--border-glass)',
                    borderRadius: '6px',
                    color: '#ffffff',
                    fontSize: '11.5px',
                    outline: 'none',
                    marginBottom: '10px'
                  }}
                />

                {/* Scrollable list */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', overflowY: 'auto', flex: 1, paddingRight: '4px' }}>
                  {installedApps.length === 0 ? (
                    <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textAlign: 'center', padding: '20px' }}>
                      Loading installed system applications...
                    </div>
                  ) : (
                    (() => {
                      const filtered = installedApps.filter(app => 
                        app.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                        (app.publisher && app.publisher.toLowerCase().includes(searchQuery.toLowerCase()))
                      )
                      if (filtered.length === 0) {
                        return (
                          <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textAlign: 'center', padding: '20px' }}>
                            No matching applications found.
                          </div>
                        )
                      }
                      return filtered.map(app => {
                        // Find active permission setting matching this app name
                        const getAppRule = () => {
                           const normApp = app.name.toLowerCase().trim()
                           if (appPermissions[normApp]) return appPermissions[normApp]
                           for (const k of Object.keys(appPermissions)) {
                             const normKey = k.replace('.exe', '').trim()
                             const normName = normApp.replace('.exe', '').trim()
                             if (normKey && normName && (normKey.includes(normName) || normName.includes(normKey))) {
                               return appPermissions[k]
                             }
                           }
                           return 'prompt'
                        }
                        const currentVal = getAppRule()

                        return (
                          <div 
                            key={app.key} 
                            style={{ 
                              display: 'flex', 
                              justifyContent: 'space-between', 
                              alignItems: 'center', 
                              padding: '8px 10px', 
                              background: 'rgba(255, 255, 255, 0.01)', 
                              border: '1px solid rgba(255, 255, 255, 0.02)', 
                              borderRadius: '6px',
                              transition: 'border-color 0.2s ease'
                            }}
                            onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--border-glass)'}
                            onMouseLeave={(e) => e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.02)'}
                          >
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', maxWidth: '65%' }}>
                              <span style={{ fontSize: '11.5px', fontWeight: 600, color: '#ffffff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={app.name}>
                                {app.name}
                              </span>
                              <span style={{ fontSize: '9.5px', color: 'var(--color-text-secondary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {app.version ? `${app.version} | ` : ''}{app.publisher || 'Unknown Publisher'}
                              </span>
                            </div>

                            <select
                              className="settings-select"
                              style={{ padding: '2px 4px', fontSize: '10.5px', borderRadius: '4px' }}
                              value={currentVal}
                              onChange={(e) => handleAppPermissionChange(app.name, e.target.value as any)}
                            >
                              <option value="allow">Allow</option>
                              <option value="prompt">Prompt</option>
                              <option value="deny">Deny</option>
                            </select>
                          </div>
                        )
                      })
                    })()
                  )}
                </div>
              </section>

              {/* Audit logs trail */}
              <section className="settings-panel" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-glass)', borderRadius: '12px', padding: '12px' }}>
                <div className="section-title" style={{ marginBottom: '8px' }}>Security Audit Trail</div>
                <div style={{ maxHeight: '80px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {auditLogs.length === 0 ? (
                    <div style={{ fontSize: '10px', color: 'var(--color-text-secondary)', fontStyle: 'italic' }}>No security events logged.</div>
                  ) : (
                    auditLogs.slice(-5).reverse().map((log, idx) => (
                      <div key={idx} style={{ fontSize: '9.5px', background: 'rgba(255,255,255,0.02)', padding: '3px 6px', borderRadius: '4px', display: 'flex', justifyContent: 'space-between' }}>
                        <span>{log.resource} ({log.scope})</span>
                        <span style={{ color: log.decision.includes('allow') ? 'var(--color-success)' : 'var(--color-danger)', fontWeight: 600 }}>
                          {log.decision.toUpperCase()}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </section>
            </div>
          </>
        ) : activeTab === 'settings' ? (
          <>
            {/* Configuration Settings Panel */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              
              {/* Model Provider Config */}
              <section className="settings-panel" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-glass)', borderRadius: '12px', padding: '12px' }}>
                <div className="section-title">AI Brain Configuration</div>
                <div className="settings-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '11px', fontWeight: 600 }}>Active Model:</span>
                  <select 
                    className="settings-select"
                    style={{ padding: '4px 8px', fontSize: '11px', borderRadius: '4px' }}
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
              </section>
            </div>
          </>
        ) : (
          /* Console Event Logs */
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
        )}
      </main>

      {/* Footer Interface controls */}
      <footer className="app-footer">
        
        {/* Start / Stop / Takeover Buttons */}
        <div className="action-row" style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '8px', width: '100%' }}>
          {status !== 'idle' && status !== 'completed' && status !== 'error' && status !== 'stopped' && (
            <>
              {agentState.takeover_active ? (
                <div style={{ background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.25)', borderRadius: '12px', padding: '10px 12px', textAlign: 'center', width: '100%' }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: '#fbbf24', marginBottom: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
                    <span style={{ fontSize: '12px' }}>🟡</span> HUMAN CONTROL
                  </div>
                  <div style={{ fontSize: '10.5px', color: 'var(--color-text-secondary)', marginBottom: '8px' }}>
                    SPR SAATHI is paused. You control the computer.
                  </div>
                  <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                    <button 
                      className="btn btn-primary"
                      onClick={toggleTakeover}
                      disabled={takeoverLoading}
                      style={{ padding: '4px 10px', fontSize: '11px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px', borderRadius: '6px' }}
                    >
                      <span>▶</span> RELEASE CONTROL
                    </button>
                    <button 
                      className="btn btn-danger"
                      onClick={triggerStopTask}
                      style={{ padding: '4px 10px', fontSize: '11px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px', borderRadius: '6px' }}
                    >
                      <span>■</span> STOP TASK
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ background: 'rgba(255, 255, 255, 0.02)', border: '1px solid var(--border-glass)', borderRadius: '12px', padding: '10px 12px', textAlign: 'center', width: '100%' }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--color-text-primary)', marginBottom: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
                    <span style={{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', background: '#3b82f6', animation: 'pulse 1.5s infinite' }}></span> AI Working
                  </div>
                  <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                    <button 
                      className="btn btn-secondary"
                      onClick={toggleTakeover}
                      disabled={takeoverLoading}
                      style={{ padding: '4px 10px', fontSize: '11px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px', borderRadius: '6px' }}
                    >
                      <span>🖐</span> TAKE CONTROL
                    </button>
                    <button 
                      className="btn btn-danger"
                      onClick={triggerStopTask}
                      style={{ padding: '4px 10px', fontSize: '11px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px', borderRadius: '6px' }}
                    >
                      <span>■</span> STOP
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Voice Status Alert Bar */}
        {voiceState !== 'idle' && (
          <div 
            className={`voice-status-bar ${voiceState}`} 
            style={{ 
              fontSize: '12px', 
              padding: '6px 12px', 
              borderRadius: '8px', 
              background: voiceState === 'error' ? 'rgba(239, 68, 68, 0.1)' : 'rgba(255, 255, 255, 0.05)', 
              color: voiceState === 'error' ? 'var(--color-error)' : 'var(--color-text-secondary)', 
              marginBottom: '8px', 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'center' 
            }}
          >
            <span>
              {voiceState === 'listening' && '🎙️ Listening...'}
              {voiceState === 'processing' && '⚙️ Processing voice...'}
              {voiceState === 'transcribing' && '✍️ Transcribing...'}
              {voiceState === 'ready' && '✅ Voice ready'}
              {voiceState === 'error' && `❌ ${voiceError || 'Voice error occurred'}`}
            </span>
            {voiceState === 'listening' && (
              <button 
                style={{ background: 'none', border: 'none', color: 'var(--color-error)', cursor: 'pointer', fontSize: '11px', fontWeight: 600 }}
                onClick={() => {
                  setVoiceState('idle')
                  if (recognitionRef.current) {
                    recognitionRef.current.abort()
                  }
                }}
              >
                Cancel
              </button>
            )}
          </div>
        )}

        {/* Natural Language Prompt Input */}
        <div className="input-container">
          <input
            type="text"
            className="chat-input"
            placeholder="ask anything"
            value={taskInput}
            onChange={(e) => setTaskInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && triggerStartTask()}
            disabled={status !== 'idle' && status !== 'completed' && status !== 'error' && status !== 'stopped'}
          />
          <button 
            className="mic-button" 
            title="Voice input"
            onClick={handleMicClick}
            style={{ color: voiceState === 'listening' ? '#10b981' : undefined }}
          >
            🎤
          </button>
          <button 
            className="btn-send"
            title="Send command"
            onClick={() => triggerStartTask()}
            disabled={(status !== 'idle' && status !== 'completed' && status !== 'error' && status !== 'stopped') || !taskInput.trim()}
          >
            →
          </button>
        </div>
      </footer>

      {/* Microphone Access Permission Overlay */}
      {showMicPrompt && (
        <div 
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            zIndex: 1000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px'
          }}
        >
          <div 
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-glass)',
              borderRadius: '16px',
              padding: '20px',
              maxWidth: '320px',
              width: '100%',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
              boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)'
            }}
          >
            <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--color-text-primary)' }}>
              🎤 Microphone Access Required
            </div>
            <div style={{ fontSize: '13px', color: 'var(--color-text-secondary)', lineHeight: '18px' }}>
              SPR SAATHI requests access to your microphone to transcribe voice commands.
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button 
                className="btn btn-primary" 
                style={{ flex: 1 }}
                onClick={handleAllowMic}
              >
                Allow
              </button>
              <button 
                className="btn btn-secondary" 
                style={{ flex: 1 }}
                onClick={handleDenyMic}
              >
                Deny
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
