import { useState, useEffect, useRef, useMemo } from 'react'
import orbitLogo from './assets/orbit-logo.png'

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
    active_window?: ActiveWindow | null
    screen_width?: number
    screen_height?: number
    cursor_x?: number
    cursor_y?: number
    screenshot_dimensions?: { width: number; height: number }
    scale_factors?: { scale_x: number; scale_y: number }
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

interface AttachmentItem {
  id: string
  filename: string
  file_type: string
  size_str: string
  size_bytes?: number
  file_path?: string
  extracted_text?: string
  image_base64?: string
  is_image?: boolean
  preview_url?: string
}

interface OrbitLaymanStep {
  id: string
  text: string
  status: 'completed' | 'running' | 'failed' | 'pending'
}

interface OrbitMessage {
  id: string
  sender: 'user' | 'orbit'
  type: 'user_prompt' | 'task_progress' | 'info'
  text?: string
  taskText?: string
  task_id?: string
  timestamp: string
  attachments?: AttachmentItem[]
  
  // Real-time task progress state
  status?: 'planning' | 'acting' | 'waiting_user' | 'paused' | 'completed' | 'failed' | 'cancelled'
  currentLaymanStatus?: string
  laymanSteps?: OrbitLaymanStep[]
  elapsedSeconds?: number
  startTime?: number
  question?: string
  questionAnswer?: string
  errorMessage?: string
}

interface OfflineModelSpec {
  name: string;
  tag: string;
  specs: string;
  isDefault?: boolean;
  isInstalled?: boolean;
  isVision?: boolean;
  sizeGb?: number;
}

const offlineModelsCatalog: OfflineModelSpec[] = [
  { name: 'Qwen2.5 7B', tag: 'qwen2.5:latest', specs: 'Size: 4.7 GB • Params: 7.6B • Tool Calling Supported', isDefault: false },
  { name: 'Qwen2.5-Coder 0.5B', tag: 'qwen2.5-coder:0.5b', specs: 'Size: 0.4 GB • Req: 2GB RAM / Integrated GPU • 16k Context', isDefault: true },
  { name: 'Qwen2.5-Coder 1.5B', tag: 'qwen2.5-coder:1.5b', specs: 'Size: 1.0 GB • Req: 4GB RAM / 2GB VRAM • 16k Context', isDefault: true },
  { name: 'Qwen2.5-Coder 3B', tag: 'qwen2.5-coder:3b', specs: 'Size: 2.0 GB • Req: 6GB RAM / 4GB VRAM • 32k Context', isDefault: true },
  { name: 'Qwen2.5-Coder 7B', tag: 'qwen2.5-coder:7b', specs: 'Size: 4.7 GB • Req: 8GB VRAM / 16System RAM • 32k Context', isDefault: false },
  { name: 'Qwen2.5-Coder 14B', tag: 'qwen2.5-coder:14b', specs: 'Size: 9.0 GB • Req: 16GB VRAM / 32GB System RAM • 32k Context', isDefault: false },
  { name: 'Qwen2.5-Coder 32B', tag: 'qwen2.5-coder:32b', specs: 'Size: 20.0 GB • Req: 24GB+ VRAM / 64GB System RAM • 32k Context', isDefault: false },
  { name: 'Llama 3.2 Vision 11B', tag: 'llama3.2-vision:latest', specs: 'Size: 7.8 GB • Vision Capable • 131k Context', isDefault: false, isVision: true },
  { name: 'StarCoder2 15B', tag: 'starcoder2', specs: 'Size: 9.5 GB • Req: 16GB VRAM / 32GB System RAM • 16k Context', isDefault: false },
  { name: 'DeepSeek-Coder-V2-Lite 16B', tag: 'deepseek-coder-v2', specs: 'Size: 8.9 GB • Req: 16GB VRAM / 32GB System RAM • 32k Context', isDefault: false }
];

function App(): React.JSX.Element {
  // Connection and Dynamic Port State
  const [port, setPort] = useState<number | null>(null)
  const [backendStatus, setBackendStatus] = useState<'connecting' | 'connected' | 'disconnected' | 'unavailable'>('connecting')
  const [reconnectAttempts, setReconnectAttempts] = useState(0)
  const [activeTab, setActiveTab] = useState<'control' | 'security' | 'workspace' | 'skills' | 'settings' | 'logs'>('control')
  const [takeoverLoading, setTakeoverLoading] = useState(false)
  const [installedApps, setInstalledApps] = useState<{name: string, version: string, publisher: string, key: string}[]>([])
  const [searchQuery, setSearchQuery] = useState('')

  // System Health Metrics (Phase 19)
  const [systemMetrics, setSystemMetrics] = useState<{
    status?: string
    memory?: { rss_mb: number; vms_mb?: number }
    system?: { cpu_percent: number; memory_percent?: number }
    agent?: { status: string; task_id?: string }
  } | null>(null)

  // Workspace & Memory State (Phases 6 & 8)
  const [workspaceSubTab, setWorkspaceSubTab] = useState<'memory' | 'files'>('memory')
  const [memoryItems, setMemoryItems] = useState<Array<{
    id: string
    key: string
    content: string
    memory_type: string
    tags: string[]
    created_at?: string
  }>>([])
  const [memoryQuery, setMemoryQuery] = useState('')
  const [newMemKey, setNewMemKey] = useState('')
  const [newMemContent, setNewMemContent] = useState('')
  const [newMemType, setNewMemType] = useState('preference_memory')
  const [newMemTags, setNewMemTags] = useState('user, preference')
  const [memoryMessage, setMemoryMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null)
  const [workspaceFiles, setWorkspaceFiles] = useState<Array<{
    file_id: string
    path: string
    filename: string
    size_bytes: number
    mime_type?: string
    task_id?: string
    created_at?: string
  }>>([])
  const [workspaceQuery, setWorkspaceQuery] = useState('')

  // File & Context Attachments State
  const [attachments, setAttachments] = useState<AttachmentItem[]>([])
  const [showAddContextMenu, setShowAddContextMenu] = useState(false)
  const [isUploadingContext, setIsUploadingContext] = useState(false)
  const [isDraggingOver, setIsDraggingOver] = useState(false)
  const addContextMenuRef = useRef<HTMLDivElement | null>(null)
  const mediaFileInputRef = useRef<HTMLInputElement | null>(null)
  const folderInputRef = useRef<HTMLInputElement | null>(null)

  // Skills & Specialists State (Phases 5 & 12)
  const [skillsSubTab, setSkillsSubTab] = useState<'skills' | 'specialists'>('skills')
  const [registeredSkills, setRegisteredSkills] = useState<Array<{
    name: string
    description: string
    parameters?: any
  }>>([])
  const [specialistsList, setSpecialistsList] = useState<Array<{
    name: string
    type: string
    capabilities: string[]
    description?: string
  }>>([])
  const [specialistTaskInput, setSpecialistTaskInput] = useState('')
  const [specialistSelected, setSpecialistSelected] = useState('kairo_coding')
  const [specialistLoading, setSpecialistLoading] = useState(false)
  const [specialistResult, setSpecialistResult] = useState<any | null>(null)

  // Voice Input State
  const [voiceState, setVoiceState] = useState<'idle' | 'listening' | 'processing' | 'transcribing' | 'ready' | 'error'>('idle')
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const [micPermission, setMicPermission] = useState<'prompt' | 'granted' | 'denied'>(() => {
    return (localStorage.getItem('mic-permission') as any) || 'prompt'
  })
  const [showMicPrompt, setShowMicPrompt] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const audioContextRef = useRef<AudioContext | null>(null)
  const animationFrameRef = useRef<number | null>(null)

  // Settings
  const [selectedProvider, setSelectedProvider] = useState<'api' | 'local'>(() => {
    return (localStorage.getItem('spr_saathi_provider') as 'api' | 'local') || 'local'
  })
  const [selectedModel, setSelectedModel] = useState<string>(() => {
    return localStorage.getItem('spr_saathi_model') || 'qwen2.5:latest'
  })

  // Operating Mode State ('chat' = Conversational Chatbot, 'saathi' = Autonomous Computer Agent)
  const [appMode, setAppMode] = useState<'chat' | 'saathi'>(() => {
    return (localStorage.getItem('spr_saathi_mode') as 'chat' | 'saathi') || 'saathi'
  })

  // Chatbot Mode Message History & State
  const [chatMessages, setChatMessages] = useState<Array<{ id: string; sender: 'user' | 'assistant'; text: string; timestamp: string; attachments?: AttachmentItem[] }>>(() => {
    try {
      const saved = localStorage.getItem('spr_saathi_chat_history')
      if (saved) return JSON.parse(saved)
    } catch (e) {}
    return [
      {
        id: 'welcome',
        sender: 'assistant',
        text: "✨ Started a **New Chat**! How can I help you today?\n\nFeel free to ask questions, brainstorm ideas, request explanations, or generate code.",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
    ]
  })
  const [chatLoading, setChatLoading] = useState(false)
  const chatEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    try {
      localStorage.setItem('spr_saathi_chat_history', JSON.stringify(chatMessages.slice(-50)))
    } catch (e) {}
    if (appMode === 'chat') {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [chatMessages, appMode])

  // ORBIT Autonomous Agent Chat & Live Progress State
  const [orbitMessages, setOrbitMessages] = useState<OrbitMessage[]>(() => {
    try {
      const saved = localStorage.getItem('spr_saathi_orbit_history')
      if (saved) return JSON.parse(saved)
    } catch (e) {}
    return [
      {
        id: 'orbit_welcome',
        sender: 'orbit',
        type: 'info',
        text: "👋 Hi! I'm **ORBIT**, your autonomous computer assistant.\n\nTell me what you'd like me to do on your computer (e.g. *\"Open Paint and draw a portrait of Mahatma Gandhi\"* or *\"Organize my files\"*).\n\nIf anything is unclear, I'll ask you questions right here before or while doing the task, and I'll keep you updated in real-time every step of the way!",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
    ]
  })
  const [inlineClarificationAnswer, setInlineClarificationAnswer] = useState('')
  const orbitChatEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    try {
      localStorage.setItem('spr_saathi_orbit_history', JSON.stringify(orbitMessages.slice(-50)))
    } catch (e) {}
    if (appMode === 'saathi') {
      orbitChatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [orbitMessages, appMode])

  // Helper to format digital seconds timer
  const formatTimer = (seconds: number) => {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${m}:${s < 10 ? '0' : ''}${s}`
  }

  // Helper to safely update the active task_progress card in orbitMessages
  const updateLastTaskCard = (
    messages: OrbitMessage[],
    updater: (card: OrbitMessage) => OrbitMessage
  ): OrbitMessage[] => {
    const lastIdx = messages.map(m => m.type).lastIndexOf('task_progress')
    if (lastIdx === -1) return messages
    const updated = [...messages]
    updated[lastIdx] = updater(updated[lastIdx])
    return updated
  }


  // Conversation History State
  const [activeSessionId, setActiveSessionId] = useState<string | null>(() => {
    return localStorage.getItem('spr_saathi_active_session_id') || null
  })
  const [conversations, setConversations] = useState<Array<{
    id: string
    title: string
    created_at: string
    updated_at: string
    model: string
    message_count: number
    snippet?: string
  }>>([])
  const [showHistoryDrawer, setShowHistoryDrawer] = useState(false)
  const [historySearchQuery, setHistorySearchQuery] = useState('')
  const [historyLoading, setHistoryLoading] = useState(false)

  // Model Manager State
  const [managerTab, setManagerTab] = useState<'offline' | 'online'>('offline')
  const [installedOllamaModels, setInstalledOllamaModels] = useState<string[]>([])
  const [installedOllamaDetails, setInstalledOllamaDetails] = useState<OfflineModelSpec[]>([])
  const [apiKeyVisible, setApiKeyVisible] = useState(false)
  const [cloudProvider, setCloudProvider] = useState<'gemini' | 'openai' | 'anthropic'>('gemini')
  const [cloudModel, setCloudModel] = useState('Gemini 3.5 Flash')
  const [cloudApiKey, setCloudApiKey] = useState('')
  const [managerMessage, setManagerMessage] = useState<{type: 'success' | 'error', text: string} | null>(null)

  // Dynamic offline model classifications combining detected Ollama models + catalog
  const installedList: OfflineModelSpec[] = useMemo(() => {
    const list: OfflineModelSpec[] = []
    const seenTags = new Set<string>()

    // 1. Add all rich model details if available from API
    for (const det of installedOllamaDetails) {
      const tagKey = det.tag.toLowerCase()
      if (!seenTags.has(tagKey)) {
        seenTags.add(tagKey)
        list.push(det)
      }
    }

    // 2. Add EVERY raw model string returned by Ollama (e.g. qwen2.5:latest, llama3.2-vision:latest)
    for (const rawName of installedOllamaModels) {
      if (!rawName || rawName.toLowerCase().includes('embed')) continue
      const tagKey = rawName.toLowerCase()
      const alreadyPresent = Array.from(seenTags).some(t => t === tagKey || (t.startsWith(tagKey) && !t.includes('coder') && !tagKey.includes('coder')))
      if (!alreadyPresent && !seenTags.has(tagKey)) {
        seenTags.add(tagKey)
        const catalogMatch = offlineModelsCatalog.find(
          c => c.tag.toLowerCase() === tagKey || (c.tag.toLowerCase().startsWith(tagKey) && c.tag.toLowerCase().includes('coder') === tagKey.includes('coder'))
        )
        if (catalogMatch) {
          list.push({ ...catalogMatch, tag: rawName, isInstalled: true })
        } else {
          const isVis = tagKey.includes('vision') || tagKey.includes('vl') || tagKey.includes('llava')
          list.push({
            name: rawName,
            tag: rawName,
            specs: isVis ? 'Vision Capable • Local Ollama Model' : 'Local Ollama Model • Tool Calling',
            isDefault: false,
            isInstalled: true,
            isVision: isVis
          })
        }
      }
    }

    return list
  }, [installedOllamaDetails, installedOllamaModels])

  const extendedList: OfflineModelSpec[] = useMemo(() => {
    return offlineModelsCatalog.filter(cat => {
      return !installedOllamaModels.some(
        m => m.toLowerCase().includes(cat.tag.toLowerCase()) || cat.tag.toLowerCase().includes(m.toLowerCase())
      )
    })
  }, [installedOllamaModels])

  const [configuredKeys, setConfiguredKeys] = useState<{openai: boolean, gemini: boolean, anthropic: boolean}>({
    openai: false,
    gemini: false,
    anthropic: false
  })

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

  // Real-time execution timer for active task progress card
  useEffect(() => {
    let timer: NodeJS.Timeout | null = null
    const isTaskActive = agentState.status === 'running' || agentState.status === 'planning' || agentState.status === 'acting' || agentState.status === 'waiting_user' || agentState.status === 'waiting_permission' || agentState.status === 'verifying'
    
    if (isTaskActive) {
      timer = setInterval(() => {
        setOrbitMessages(prev => {
          const lastIdx = prev.map(m => m.type).lastIndexOf('task_progress')
          if (lastIdx === -1) return prev
          const target = prev[lastIdx]
          if (target.status === 'completed' || target.status === 'failed' || target.status === 'cancelled') return prev
          
          const nextSeconds = (target.elapsedSeconds || 0) + 1
          const updated = [...prev]
          updated[lastIdx] = { ...target, elapsedSeconds: nextSeconds }
          return updated
        })
      }, 1000)
    }

    return () => {
      if (timer) clearInterval(timer)
    }
  }, [agentState.status])

  // Text Inputs & Event logs
  const [taskInput, setTaskInput] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [feed, setFeed] = useState<FeedItem[]>([])
  const [activePrompt, setActivePrompt] = useState<PermissionRequest | null>(null)
  const [userQuestion, setUserQuestion] = useState<string | null>(null)

  const respondUserQuestion = async (response: string) => {
    if (port === null || !response.trim()) return
    const replyText = response.trim()
    try {
      // 1. Post user reply bubble into orbitMessages
      const replyMsg: OrbitMessage = {
        id: `orbit_reply_${Date.now()}`,
        sender: 'user',
        type: 'user_prompt',
        text: replyText,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
      
      setOrbitMessages(prev => {
        const withUser = [...prev, replyMsg]
        return updateLastTaskCard(withUser, card => ({
          ...card,
          status: 'acting',
          questionAnswer: replyText,
          currentLaymanStatus: `⚡ Processing your clarification: "${replyText}"...`
        }))
      })

      const res = await fetch(`http://127.0.0.1:${port}/api/task/respond_question`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ response: replyText })
      })
      if (res.ok) {
        setUserQuestion(null)
        setInlineClarificationAnswer('')
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

    if (window.api.onBackendPortUpdated) {
      const unsub = window.api.onBackendPortUpdated((newPort) => {
        console.log(`[Renderer] Received updated backend port: ${newPort}`)
        setPort(newPort)
        setBackendStatus('connecting')
      })
      return unsub
    }
    return undefined
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
        
        // Sync saved model with backend
        const savedProvider = (localStorage.getItem('spr_saathi_provider') as 'api' | 'local') || selectedProvider
        const savedModel = localStorage.getItem('spr_saathi_model') || selectedModel
        fetch(`http://127.0.0.1:${port}/api/config/model`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider: savedProvider, model_name: savedModel })
        }).catch(console.error)
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
              setOrbitMessages(prev => updateLastTaskCard(prev, card => ({
                ...card,
                status: 'planning',
                currentLaymanStatus: data.message || '🧠 Orbit is analyzing your request and planning the desktop actions...'
              })))
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
              {
                const laymanAct = data.payload?.layman_action || data.message
                if (laymanAct) {
                  setOrbitMessages(prev => updateLastTaskCard(prev, card => ({
                    ...card,
                    currentLaymanStatus: laymanAct
                  })))
                }
              }
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
              {
                const laymanDesc = data.payload?.layman_action || data.message || 'Executing action...'
                setOrbitMessages(prev => updateLastTaskCard(prev, card => {
                  const existingSteps = card.laymanSteps || []
                  const updatedSteps: OrbitLaymanStep[] = existingSteps.map(s => s.status === 'running' ? { ...s, status: 'completed' } : s)
                  updatedSteps.push({
                    id: `step_${Date.now()}_${Math.random()}`,
                    text: laymanDesc,
                    status: 'running'
                  })
                  return {
                    ...card,
                    status: 'acting',
                    currentLaymanStatus: laymanDesc,
                    laymanSteps: updatedSteps
                  }
                }))
              }
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
              setOrbitMessages(prev => updateLastTaskCard(prev, card => ({
                ...card,
                status: 'paused',
                currentLaymanStatus: '⏸️ Paused - You have taken manual control.'
              })))
              addFeedItem('takeover', data.message, timestamp)
              break
            case 'control.release_requested':
            case 'task.resuming':
              setAgentState((prev) => ({ 
                ...prev, 
                status: 'resuming'
              }))
              setOrbitMessages(prev => updateLastTaskCard(prev, card => ({
                ...card,
                status: 'acting',
                currentLaymanStatus: '⚡ Resuming desktop control...'
              })))
              addFeedItem('observe', data.message, timestamp)
              break
            case 'task.resumed':
              setAgentState((prev) => ({ 
                ...prev, 
                takeover_active: false, 
                status: 'running'
              }))
              setOrbitMessages(prev => updateLastTaskCard(prev, card => ({
                ...card,
                status: 'acting',
                currentLaymanStatus: '⚡ Orbit has resumed your task.'
              })))
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
              setOrbitMessages(prev => updateLastTaskCard(prev, card => ({
                ...card,
                status: 'cancelled',
                currentLaymanStatus: '🛑 Task stopped by user.'
              })))
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
              setOrbitMessages(prev => updateLastTaskCard(prev, card => {
                const existingSteps = card.laymanSteps || []
                const updatedSteps: OrbitLaymanStep[] = existingSteps.map(s => s.status === 'running' ? { ...s, status: 'failed' } : s)
                return {
                  ...card,
                  status: 'failed',
                  currentLaymanStatus: `⚠️ ${data.message || 'Task stopped due to an issue.'}`,
                  errorMessage: data.message,
                  laymanSteps: updatedSteps
                }
              }))
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
              setOrbitMessages(prev => updateLastTaskCard(prev, card => {
                const existingSteps = card.laymanSteps || []
                const updatedSteps: OrbitLaymanStep[] = existingSteps.map(s => ({ ...s, status: 'completed' }))
                return {
                  ...card,
                  status: 'completed',
                  currentLaymanStatus: `🎉 All done! ${data.message || 'Task completed successfully.'}`,
                  laymanSteps: updatedSteps
                }
              }))
              addFeedItem('success', data.message, timestamp)
              break
            case 'tool.completed':
              setAgentState((prev) => ({
                ...prev,
                steps: prev.steps.map((s) => s.status === 'running' ? { ...s, status: 'completed' } : s)
              }))
              setOrbitMessages(prev => updateLastTaskCard(prev, card => {
                const existingSteps = card.laymanSteps || []
                const updatedSteps: OrbitLaymanStep[] = existingSteps.map(s => s.status === 'running' ? { ...s, status: 'completed' } : s)
                return {
                  ...card,
                  laymanSteps: updatedSteps
                }
              }))
              addFeedItem('success', data.message, timestamp)
              break
            case 'task.waiting_user':
              setAgentState((prev) => ({ ...prev, status: 'waiting_user' }))
              {
                const q = data.payload?.question || data.message || 'I need clarification to proceed.'
                setUserQuestion(q)
                setOrbitMessages(prev => updateLastTaskCard(prev, card => ({
                  ...card,
                  status: 'waiting_user',
                  question: q,
                  currentLaymanStatus: '❓ Orbit needs clarification from you to proceed.'
                })))
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

  // Fetch installed applications helper
  const fetchInstalledApps = async () => {
    if (port === null) return
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/config/installed_apps`)
      const data = await res.json()
      if (Array.isArray(data)) {
        setInstalledApps(data)
      }
    } catch (e) {
      console.error('[Renderer] Error fetching installed apps:', e)
    }
  }

  // Fetch installed applications when port resolved or when tab changes to security
  useEffect(() => {
    fetchInstalledApps()
  }, [port, activeTab])

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
      startAudioRecording()
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
    if (voiceState === 'listening') {
      stopAudioRecording()
      return
    }

    if (micPermission === 'denied') {
      setVoiceState('error')
      setVoiceError('Microphone access is denied. Please enable it in Windows settings.')
      return
    }
    if (micPermission === 'prompt') {
      setShowMicPrompt(true)
      return
    }
    startAudioRecording()
  }

  const startAudioRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop())
        
        const audioBlob = new Blob(audioChunksRef.current, { type: mediaRecorder.mimeType || 'audio/webm' })
        await transcribeAndSubmit(audioBlob)
      }

      try {
        const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)()
        audioContextRef.current = audioContext
        const source = audioContext.createMediaStreamSource(stream)
        const analyser = audioContext.createAnalyser()
        analyser.fftSize = 256
        source.connect(analyser)

        const bufferLength = analyser.frequencyBinCount
        const dataArray = new Uint8Array(bufferLength)

        let lastActiveTime = Date.now()
        const silenceThreshold = 15
        const silenceDuration = 1800 // 1.8 seconds

        const checkVolume = () => {
          if (!mediaRecorderRef.current || mediaRecorderRef.current.state !== 'recording') return

          analyser.getByteFrequencyData(dataArray)
          let sum = 0
          for (let i = 0; i < bufferLength; i++) {
            sum += dataArray[i]
          }
          const average = sum / bufferLength

          if (average > silenceThreshold) {
            lastActiveTime = Date.now()
          } else if (Date.now() - lastActiveTime > silenceDuration) {
            console.log('[Voice] Auto-stopping due to silence')
            stopAudioRecording()
            return
          }

          animationFrameRef.current = requestAnimationFrame(checkVolume)
        }

        animationFrameRef.current = requestAnimationFrame(checkVolume)
      } catch (e) {
        console.error('Audio analyser setup failed:', e)
      }

      mediaRecorder.start()
      setVoiceState('listening')
      setVoiceError(null)
    } catch (e) {
      console.error('Failed to start audio recording:', e)
      setVoiceState('error')
      setVoiceError('Could not access microphone. Ensure permissions are allowed.')
    }
  }

  const stopAudioRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop()
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(console.error)
      audioContextRef.current = null
    }
    if (animationFrameRef.current !== null) {
      cancelAnimationFrame(animationFrameRef.current)
      animationFrameRef.current = null
    }
  }

  const transcribeAndSubmit = async (audioBlob: Blob) => {
    setVoiceState('processing')
    setVoiceError(null)

    if (port === null) {
      setVoiceState('error')
      setVoiceError('Backend not connected.')
      return
    }

    try {
      const formData = new FormData()
      formData.append('file', audioBlob, 'audio.webm')

      const res = await fetch(`http://127.0.0.1:${port}/api/task/transcribe`, {
        method: 'POST',
        body: formData,
      })

      if (!res.ok) {
        const errorData = await res.json()
        throw new Error(errorData.detail || 'Failed to transcribe audio.')
      }

      const data = await res.json()
      const transcript = data.transcription

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
    } catch (e: any) {
      console.error('Transcription error:', e)
      setVoiceState('error')
      setVoiceError(e.message || 'Failed to transcribe audio.')
    }
  }

  // Conversation History Handlers
  const loadConversations = async () => {
    if (port === null) return
    try {
      setHistoryLoading(true)
      const res = await fetch(`http://127.0.0.1:${port}/api/conversations`)
      if (res.ok) {
        const data = await res.json()
        setConversations(data.conversations || [])
      }
    } catch (e) {
      console.error('Failed to load conversations:', e)
    } finally {
      setHistoryLoading(false)
    }
  }

  const handleSelectConversation = async (sessionId: string) => {
    if (port === null) return
    try {
      setChatLoading(true)
      const res = await fetch(`http://127.0.0.1:${port}/api/conversations/${sessionId}`)
      if (res.ok) {
        const data = await res.json()
        const conv = data.conversation
        if (conv && Array.isArray(conv.messages)) {
          const mapped = conv.messages.map((m: any) => ({
            id: m.id || `msg_${Date.now()}_${Math.random()}`,
            sender: (m.role === 'user' ? 'user' : 'assistant') as 'user' | 'assistant',
            text: m.content,
            timestamp: m.timestamp ? new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''
          }))
          setChatMessages(mapped.length > 0 ? mapped : [
            {
              id: 'welcome',
              sender: 'assistant' as const,
              text: `📂 Opened conversation: **${conv.title || 'Untitled'}**.\n\nYou can continue this conversation below.`,
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            }
          ])
          setActiveSessionId(sessionId)
          localStorage.setItem('spr_saathi_active_session_id', sessionId)
          setAppMode('chat')
          localStorage.setItem('spr_saathi_mode', 'chat')
          setActiveTab('control')
          setShowHistoryDrawer(false)
        }
      }
    } catch (e) {
      console.error('Failed to load conversation messages:', e)
    } finally {
      setChatLoading(false)
    }
  }

  const handleNewChat = () => {
    setActiveSessionId(null)
    localStorage.removeItem('spr_saathi_active_session_id')
    setAppMode('chat')
    localStorage.setItem('spr_saathi_mode', 'chat')
    setActiveTab('control')
    setTaskInput('')
    setAttachments([])
    setChatMessages([
      {
        id: `welcome_${Date.now()}`,
        sender: 'assistant' as const,
        text: "✨ Started a **New Chat**! How can I help you today?\n\nFeel free to ask questions, brainstorm ideas, request explanations, or generate code.",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
    ])
    setShowHistoryDrawer(false)
    setShowChatOptionsMenu(false)
    if (port !== null) {
      fetch(`http://127.0.0.1:${port}/api/chat/clear`, { method: 'POST' }).catch(() => {})
    }
  }

  const handleDeleteConversation = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (port === null) return
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/conversations/${sessionId}`, { method: 'DELETE' })
      if (res.ok) {
        setConversations(prev => prev.filter(c => c.id !== sessionId))
        if (activeSessionId === sessionId) {
          handleNewChat()
        }
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err)
    }
  }

  const filteredConversations = useMemo(() => {
    if (!historySearchQuery.trim()) return conversations
    const q = historySearchQuery.toLowerCase()
    return conversations.filter(c => 
      c.title.toLowerCase().includes(q) || 
      (c.snippet && c.snippet.toLowerCase().includes(q))
    )
  }, [conversations, historySearchQuery])

  useEffect(() => {
    if (port !== null && appMode === 'chat') {
      loadConversations()
    }
  }, [port, appMode])

  // Chat Options & Rename State
  const chatOptionsRef = useRef<HTMLDivElement | null>(null)
  const [showChatOptionsMenu, setShowChatOptionsMenu] = useState(false)
  const [isRenamingChat, setIsRenamingChat] = useState(false)
  const [chatRenameInput, setChatRenameInput] = useState('')

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (chatOptionsRef.current && !chatOptionsRef.current.contains(e.target as Node)) {
        setShowChatOptionsMenu(false)
      }
      if (addContextMenuRef.current && !addContextMenuRef.current.contains(e.target as Node)) {
        setShowAddContextMenu(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const formatFileSize = (bytes: number): string => {
    if (!bytes || bytes <= 0) return '0 B'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const detectFileTypeFromFilename = (filename: string, mimeType?: string): string => {
    const ext = filename.split('.').pop()?.toLowerCase() || ''
    if (mimeType?.startsWith('image/') || ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg'].includes(ext)) return 'image'
    if (ext === 'pdf' || mimeType?.includes('pdf')) return 'pdf'
    if (['doc', 'docx'].includes(ext) || mimeType?.includes('word')) return 'docx'
    if (['txt', 'md', 'json', 'csv', 'py', 'ts', 'tsx', 'js', 'jsx', 'html', 'css', 'yaml', 'yml', 'log', 'xml', 'ini', 'env'].includes(ext)) return 'text'
    return 'file'
  }

  const handleFilesUpload = async (fileList: FileList | File[]) => {
    if (!fileList || fileList.length === 0) return
    setIsUploadingContext(true)
    setShowAddContextMenu(false)

    try {
      const filesArray = Array.from(fileList)

      // 1. Immediately create client-side attachment items so the file shows up in Orbit instantly!
      const initialItems: AttachmentItem[] = await Promise.all(
        filesArray.map(async (file, idx) => {
          const isImg = Boolean(file.type?.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name))
          let preview: string | undefined = undefined
          let imgB64: string | undefined = undefined
          let txtContent: string | undefined = undefined

          if (isImg) {
            try {
              preview = URL.createObjectURL(file)
              imgB64 = await new Promise<string>((resolve) => {
                const reader = new FileReader()
                reader.onloadend = () => {
                  const res = reader.result as string
                  const base64 = res.includes(',') ? res.split(',')[1] : res
                  resolve(base64)
                }
                reader.onerror = () => resolve('')
                reader.readAsDataURL(file)
              })
            } catch (e) {
              console.warn('Image preview creation error:', e)
            }
          } else if (file.size < 500000 && /\.(txt|md|json|csv|py|ts|tsx|js|jsx|html|css|yaml|yml|log|xml|ini|env)$/i.test(file.name)) {
            try {
              txtContent = await file.text()
            } catch (e) {
              console.warn('Text extraction error:', e)
            }
          }

          const absPath = (file as any).path || ''
          const ftype = detectFileTypeFromFilename(file.name, file.type)

          return {
            id: `att_${Date.now()}_${idx}_${Math.random().toString(36).slice(2, 7)}`,
            filename: file.name,
            file_type: ftype,
            size_bytes: file.size,
            size_str: formatFileSize(file.size),
            file_path: absPath,
            image_base64: imgB64,
            extracted_text: txtContent,
            is_image: isImg,
            preview_url: preview
          }
        })
      )

      // Add to attachments immediately!
      setAttachments(prev => [...prev, ...initialItems])

      // 2. Also attempt backend upload & enrichment if backend port is available
      if (port !== null) {
        try {
          const formData = new FormData()
          filesArray.forEach(f => {
            formData.append('files', f)
          })

          const res = await fetch(`http://127.0.0.1:${port}/api/context/upload`, {
            method: 'POST',
            body: formData
          })

          if (res.ok) {
            const data = await res.json()
            if (data.files && Array.isArray(data.files)) {
              setAttachments(prev => prev.map(item => {
                const matched = data.files.find((f: any) => f.filename === item.filename)
                if (matched) {
                  return {
                    ...item,
                    ...matched,
                    // Preserve client-side image preview and Base64 if needed
                    preview_url: item.preview_url || matched.preview_url,
                    image_base64: item.image_base64 || matched.image_base64
                  }
                }
                return item
              }))
            }
          }
        } catch (backendErr) {
          console.warn('Backend context upload skipped, retained client-side attachments:', backendErr)
        }
      }
    } catch (e) {
      console.error('Failed to process context files:', e)
    } finally {
      setIsUploadingContext(false)
      if (mediaFileInputRef.current) mediaFileInputRef.current.value = ''
      if (folderInputRef.current) folderInputRef.current.value = ''
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDraggingOver(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDraggingOver(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDraggingOver(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesUpload(e.dataTransfer.files)
    }
  }

  const handleRenameActiveConversation = async (newTitle: string) => {
    if (!activeSessionId || !port || !newTitle.trim()) return
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/conversations/${activeSessionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle.trim() })
      })
      if (res.ok) {
        setConversations(prev => prev.map(c => c.id === activeSessionId ? { ...c, title: newTitle.trim() } : c))
      }
    } catch (e) {
      console.error('Failed to rename conversation:', e)
    }
  }

  const handleCopyChatTranscript = () => {
    const text = chatMessages.map(m => `[${m.sender === 'user' ? 'User' : 'ORBIT'} - ${m.timestamp}]\n${m.text}`).join('\n\n')
    navigator.clipboard.writeText(text)
    setShowChatOptionsMenu(false)
  }

  // Chatbot Mode Messaging Handlers
  const handleSendChatMessage = async (inputCommand?: string) => {
    const command = inputCommand !== undefined ? inputCommand : taskInput
    if ((!command.trim() && attachments.length === 0) || port === null || chatLoading) return

    const currentAttachments = [...attachments]
    const userMsg = {
      id: `msg_${Date.now()}`,
      sender: 'user' as const,
      text: command,
      attachments: currentAttachments.length > 0 ? currentAttachments : undefined,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }

    setChatMessages(prev => [...prev, userMsg])
    if (inputCommand === undefined) {
      setTaskInput('')
      setAttachments([])
    }
    setChatLoading(true)

    try {
      const historyPayload = chatMessages.slice(-10).map(m => ({
        role: m.sender === 'user' ? 'user' : 'assistant',
        content: m.text
      }))

      const res = await fetch(`http://127.0.0.1:${port}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: command || "Please analyze the attached document(s) and provide an overview.",
          history: historyPayload,
          session_id: activeSessionId || undefined,
          attachments: currentAttachments.length > 0 ? currentAttachments : undefined
        })
      })

      if (res.ok) {
        const data = await res.json()
        if (data.session_id && data.session_id !== activeSessionId) {
          setActiveSessionId(data.session_id)
          localStorage.setItem('spr_saathi_active_session_id', data.session_id)
        }
        const assistantMsg = {
          id: `msg_ai_${Date.now()}`,
          sender: 'assistant' as const,
          text: data.response || "I have received your message.",
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
        setChatMessages(prev => [...prev, assistantMsg])
        loadConversations()
      } else {
        const data = await res.json().catch(() => ({}))
        const errorMsg = {
          id: `msg_err_${Date.now()}`,
          sender: 'assistant' as const,
          text: `⚠️ **Error**: ${data.detail || "Failed to generate AI response. Please verify model service."}`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
        setChatMessages(prev => [...prev, errorMsg])
      }
    } catch (e: any) {
      const errorMsg = {
        id: `msg_err_${Date.now()}`,
        sender: 'assistant' as const,
        text: `⚠️ **Connection Error**: ${e.message || "Failed to connect to backend service."}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
      setChatMessages(prev => [...prev, errorMsg])
    } finally {
      setChatLoading(false)
    }
  }

  const handleClearChat = async () => {
    setActiveSessionId(null)
    localStorage.removeItem('spr_saathi_active_session_id')
    setAppMode('chat')
    localStorage.setItem('spr_saathi_mode', 'chat')
    setActiveTab('control')
    setTaskInput('')
    setAttachments([])
    setChatMessages([
      {
        id: `welcome_${Date.now()}`,
        sender: 'assistant',
        text: "🧹 Conversation context cleared. How can I help you today?",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
    ])
    if (port !== null) {
      fetch(`http://127.0.0.1:${port}/api/chat/clear`, { method: 'POST' }).catch(() => {})
    }
  }

  // Markdown rendering helpers for Chatbot conversation view
  const renderInlineStyles = (raw: string) => {
    const parts = raw.split(/(\*\*.*?\*\*|`.*?`)/g)
    return parts.map((part, pIdx) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={pIdx}>{part.slice(2, -2)}</strong>
      }
      if (part.startsWith('`') && part.endsWith('`')) {
        return <code key={pIdx} className="chat-inline-code">{part.slice(1, -1)}</code>
      }
      return part
    })
  }

  const renderTextWithFormatting = (text: string, keyPrefix: string) => {
    const lines = text.split('\n')
    return (
      <div key={keyPrefix} className="chat-text-paragraph">
        {lines.map((line, lIdx) => {
          if (!line.trim()) {
            return <div key={`${keyPrefix}_line_${lIdx}`} style={{ height: '6px' }} />
          }
          if (line.startsWith('### ')) {
            return <h4 key={`${keyPrefix}_line_${lIdx}`} className="chat-heading-3">{line.replace('### ', '')}</h4>
          }
          if (line.startsWith('## ')) {
            return <h3 key={`${keyPrefix}_line_${lIdx}`} className="chat-heading-2">{line.replace('## ', '')}</h3>
          }
          if (line.startsWith('# ')) {
            return <h2 key={`${keyPrefix}_line_${lIdx}`} className="chat-heading-1">{line.replace('# ', '')}</h2>
          }
          if (line.startsWith('- ') || line.startsWith('* ')) {
            return (
              <div key={`${keyPrefix}_line_${lIdx}`} className="chat-bullet-item">
                <span className="chat-bullet-dot">•</span>
                <span>{renderInlineStyles(line.substring(2))}</span>
              </div>
            )
          }
          return (
            <p key={`${keyPrefix}_line_${lIdx}`} className="chat-line">
              {renderInlineStyles(line)}
            </p>
          )
        })}
      </div>
    )
  }

  const renderFormattedMarkdown = (content: string) => {
    const codeBlockRegex = /```(\w+)?\n([\s\S]*?)```/g
    const parts: React.ReactNode[] = []
    let lastIndex = 0
    let match: RegExpExecArray | null

    while ((match = codeBlockRegex.exec(content)) !== null) {
      const precedingText = content.substring(lastIndex, match.index)
      if (precedingText) {
        parts.push(renderTextWithFormatting(precedingText, `txt_${lastIndex}`))
      }
      const lang = match[1] || 'code'
      const code = match[2]
      const codeKey = `code_${match.index}`
      parts.push(
        <div key={codeKey} className="chat-code-block">
          <div className="chat-code-header">
            <span className="chat-code-lang">{lang}</span>
            <button
              className="chat-code-copy-btn"
              onClick={() => {
                navigator.clipboard.writeText(code)
              }}
              title="Copy code"
            >
              📋 Copy
            </button>
          </div>
          <pre className="chat-code-pre">
            <code>{code}</code>
          </pre>
        </div>
      )
      lastIndex = match.index + match[0].length
    }

    if (lastIndex < content.length) {
      parts.push(renderTextWithFormatting(content.substring(lastIndex), `txt_${lastIndex}`))
    }

    return parts
  }

  // API wrappers (Unified Task Submission)
  const triggerStartTask = async (inputCommand?: string) => {
    const command = inputCommand !== undefined ? inputCommand : taskInput
    if ((!command.trim() && attachments.length === 0) || port === null) return
    const currentAttachments = [...attachments]
    const taskText = command.trim() || (currentAttachments.length > 0 ? `Inspect and process attached file(s): ${currentAttachments.map(a => a.filename).join(', ')}` : '')
    
    // 1. Post User message & Live Task Progress card into Orbit chat thread
    const userMsgId = `orbit_user_${Date.now()}`
    const taskCardId = `orbit_card_${Date.now()}`

    const userMsg: OrbitMessage = {
      id: userMsgId,
      sender: 'user',
      type: 'user_prompt',
      text: taskText,
      attachments: currentAttachments.length > 0 ? currentAttachments : undefined,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }

    const liveCard: OrbitMessage = {
      id: taskCardId,
      sender: 'orbit',
      type: 'task_progress',
      taskText: taskText,
      status: 'planning',
      currentLaymanStatus: '🧠 Orbit is analyzing your request and preparing the desktop workspace...',
      laymanSteps: [
        { id: 'step_init', text: 'Received instruction and preparing workspace', status: 'completed' }
      ],
      elapsedSeconds: 0,
      startTime: Date.now(),
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }

    setOrbitMessages(prev => [...prev, userMsg, liveCard])
    if (inputCommand === undefined) {
      setTaskInput('')
      setAttachments([])
    }

    addFeedItem('user', taskText, new Date().toISOString())
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/task/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          task: taskText,
          attachments: currentAttachments.length > 0 ? currentAttachments : undefined
        })
      })
      const data = await res.json()
      if (res.ok) {
        setAgentState((prev) => ({
          ...prev,
          current_task: taskText,
          task_id: data.task_id,
          steps: [],
          error_message: null
        }))
      } else {
        addFeedItem('error', `Start Failed: ${data.detail}`, new Date().toISOString())
        setOrbitMessages(prev => {
          const lastIdx = prev.map(m => m.id).lastIndexOf(taskCardId)
          if (lastIdx === -1) return prev
          const updated = [...prev]
          updated[lastIdx] = {
            ...updated[lastIdx],
            status: 'failed',
            currentLaymanStatus: `⚠️ Could not start: ${data.detail || 'Service unavailable'}`,
            errorMessage: data.detail || 'Service unavailable'
          }
          return updated
        })
      }
    } catch (e: any) {
      addFeedItem('error', `Network Error: ${e}`, new Date().toISOString())
      setOrbitMessages(prev => {
        const lastIdx = prev.map(m => m.id).lastIndexOf(taskCardId)
        if (lastIdx === -1) return prev
        const updated = [...prev]
        updated[lastIdx] = {
          ...updated[lastIdx],
          status: 'failed',
          currentLaymanStatus: '⚠️ Could not reach agent runtime service.',
          errorMessage: String(e)
        }
        return updated
      })
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

  const handleNewOrbitChat = () => {
    triggerStopTask()
    setUserQuestion(null)
    setActivePrompt(null)
    setAgentState({
      status: 'idle',
      current_task: null,
      task_id: null,
      active_step_id: null,
      steps: [],
      takeover_active: false,
      error_message: null
    })
    setOrbitMessages([
      {
        id: `orbit_welcome_${Date.now()}`,
        sender: 'orbit',
        type: 'info',
        text: "✨ Started a **New ORBIT Session**! What task would you like me to perform on your computer?",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
    ])
    setTaskInput('')
    setAttachments([])
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


  const handleModelChange = async (provider: 'api' | 'local', model: string, apiKey?: string) => {
    setSelectedProvider(provider)
    setSelectedModel(model)
    try {
      localStorage.setItem('spr_saathi_provider', provider)
      localStorage.setItem('spr_saathi_model', model)
    } catch (e) {}

    if (port === null) return
    try {
      const body: any = { provider, model_name: model }
      if (apiKey) {
        body.api_key = apiKey
      }
      await fetch(`http://127.0.0.1:${port}/api/config/model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
      addFeedItem('observe', `Configured model provider to [${provider.toUpperCase()}] ${model}`, new Date().toISOString())
      await fetchConfiguredKeys()
    } catch (e) {
      console.error('Config model error:', e)
    }
  }

  const fetchConfiguredKeys = async () => {
    if (port === null) return
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/config/keys`)
      if (res.ok) {
        const data = await res.json()
        setConfiguredKeys(data)
      }
    } catch (e) {
      console.error('Fetch configured keys error:', e)
    }
  }

  const fetchOllamaModels = async () => {
    if (port === null) return
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/config/ollama_models`)
      if (res.ok) {
        const data = await res.json()
        if (data.status === 'success') {
          if (Array.isArray(data.models)) {
            setInstalledOllamaModels(data.models)
          }
          if (Array.isArray(data.model_details)) {
            const detected: OfflineModelSpec[] = data.model_details
              .filter((m: any) => !m.is_embedding)
              .map((m: any) => ({
                name: m.name,
                tag: m.tag || m.name,
                specs: m.specs || `Size: ${m.size_gb} GB`,
                isDefault: false,
                isInstalled: true,
                isVision: m.is_vision,
                sizeGb: m.size_gb
              }))
            setInstalledOllamaDetails(detected)
          }
        }
      }
    } catch (e) {
      console.error('Fetch Ollama models error:', e)
    }
  }

  const fetchAgentState = async () => {
    if (port === null) return
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/state`)
      if (res.ok) {
        const data = await res.json()
        setAgentState(data)
      }
    } catch (e) {
      console.error('Fetch agent state error:', e)
    }
  }

  const fetchSystemMetrics = async () => {
    if (port === null) return
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/system/metrics`)
      if (res.ok) {
        const data = await res.json()
        setSystemMetrics(data)
      }
    } catch (e) {}
  }

  const fetchMemories = async () => {
    if (port === null) return
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/memory`)
      if (res.ok) {
        const data = await res.json()
        setMemoryItems(Array.isArray(data) ? data : [])
      }
    } catch (e) {
      console.error('Fetch memory error:', e)
    }
  }

  const fetchWorkspaceFiles = async () => {
    if (port === null) return
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/workspace/files`)
      if (res.ok) {
        const data = await res.json()
        setWorkspaceFiles(Array.isArray(data) ? data : [])
      }
    } catch (e) {
      console.error('Fetch workspace files error:', e)
    }
  }

  const fetchSkillsAndSpecialists = async () => {
    if (port === null) return
    try {
      const [skillsRes, specRes] = await Promise.all([
        fetch(`http://127.0.0.1:${port}/api/skills`),
        fetch(`http://127.0.0.1:${port}/api/specialists`)
      ])
      if (skillsRes.ok) {
        const data = await skillsRes.json()
        setRegisteredSkills(Array.isArray(data) ? data : [])
      }
      if (specRes.ok) {
        const data = await specRes.json()
        setSpecialistsList(Array.isArray(data) ? data : [])
      }
    } catch (e) {
      console.error('Fetch skills/specialists error:', e)
    }
  }

  const handleCreateMemory = async () => {
    if (!newMemKey.trim() || !newMemContent.trim() || port === null) return
    try {
      const tags = newMemTags.split(',').map(t => t.trim()).filter(Boolean)
      const res = await fetch(`http://127.0.0.1:${port}/api/memory`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          key: newMemKey.trim(),
          content: newMemContent.trim(),
          memory_type: newMemType,
          tags
        })
      })
      if (res.ok) {
        setNewMemKey('')
        setNewMemContent('')
        setMemoryMessage({ type: 'success', text: 'Memory saved successfully!' })
        fetchMemories()
      } else {
        setMemoryMessage({ type: 'error', text: 'Failed to save memory item.' })
      }
    } catch (e) {
      setMemoryMessage({ type: 'error', text: `Network error: ${e}` })
    }
  }

  const handleDeleteMemory = async (memId: string) => {
    if (port === null) return
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/memory/${memId}`, { method: 'DELETE' })
      if (res.ok) {
        fetchMemories()
      }
    } catch (e) {
      console.error('Delete memory error:', e)
    }
  }

  const handleDelegateSpecialist = async () => {
    if (!specialistTaskInput.trim() || port === null || specialistLoading) return
    setSpecialistLoading(true)
    setSpecialistResult(null)
    try {
      const res = await fetch(`http://127.0.0.1:${port}/api/specialists/delegate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: specialistTaskInput.trim(),
          specialist_name: specialistSelected
        })
      })
      if (res.ok) {
        const data = await res.json()
        setSpecialistResult(data)
      } else {
        const err = await res.json()
        setSpecialistResult({ status: 'failed', error: err.detail || 'Delegation failed.' })
      }
    } catch (e) {
      setSpecialistResult({ status: 'failed', error: String(e) })
    } finally {
      setSpecialistLoading(false)
    }
  }

  useEffect(() => {
    fetchConfiguredKeys()
    fetchOllamaModels()
    fetchSystemMetrics()
  }, [port])

  useEffect(() => {
    if (port === null) return
    const metricsInterval = setInterval(fetchSystemMetrics, 6000)
    return () => clearInterval(metricsInterval)
  }, [port])

  useEffect(() => {
    if (activeTab === 'settings') {
      fetchOllamaModels()
      fetchConfiguredKeys()
      setManagerMessage(null)
    } else if (activeTab === 'workspace') {
      fetchMemories()
      fetchWorkspaceFiles()
      setMemoryMessage(null)
    } else if (activeTab === 'skills') {
      fetchSkillsAndSpecialists()
    }
  }, [activeTab, port])

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

  // Reload / Refresh Handler (General / Chatbot)
  const handleReload = async () => {
    if (refreshing) return
    setRefreshing(true)
    try {
      if (backendStatus === 'disconnected' || backendStatus === 'unavailable') {
        setReconnectAttempts((prev) => prev + 1)
      }
      await Promise.allSettled([
        fetchOllamaModels(),
        fetchConfiguredKeys(),
        fetchAgentState(),
        fetchInstalledApps()
      ])
    } catch (e) {
      console.error('Reload error:', e)
    } finally {
      setTimeout(() => setRefreshing(false), 800)
    }
  }

  // Dedicated ORBIT AI Reload & Reset Handler
  const handleReloadOrbit = async () => {
    if (refreshing) return
    setRefreshing(true)
    try {
      if (backendStatus === 'disconnected' || backendStatus === 'unavailable') {
        setReconnectAttempts((prev) => prev + 1)
      }
      // 1. Abort/stop active agent execution if any task is running
      if (port !== null) {
        await fetch(`http://127.0.0.1:${port}/api/task/stop`, { method: 'POST' }).catch(() => {})
      }
      // 2. Clear client-side agent state, steps, inputs, and attachments
      setAgentState({
        status: 'idle',
        current_task: null,
        task_id: null,
        active_step_id: null,
        steps: [],
        takeover_active: false,
        error_message: null,
        computer_state: null
      })
      setActivePrompt(null)
      setUserQuestion(null)
      setTaskInput('')
      setAttachments([])
      setOrbitMessages(prev => [
        ...prev,
        {
          id: `orbit_reload_${Date.now()}`,
          sender: 'orbit',
          type: 'info',
          text: "🔄 **ORBIT AI reloaded and reset to standby.** Ready for your next desktop instruction!",
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ])

      // 3. Re-query backend for state, metrics, models
      if (port !== null) {
        await Promise.allSettled([
          fetchAgentState(),
          fetchSystemMetrics(),
          fetchOllamaModels(),
          fetchInstalledApps()
        ])
      }
      addFeedItem('observe', 'ORBIT AI reloaded and reset to standby.', new Date().toISOString())
    } catch (e) {
      console.error('Failed to reload ORBIT AI:', e)
    } finally {
      setTimeout(() => setRefreshing(false), 600)
    }
  }

  // Active status visualizer matching
  const status = agentState.status

  return (
    <div className="app-container">
      {/* Top 6-Icon Navigation Tab Bar */}
      <nav className="top-tab-bar">
        <button 
          className={`top-tab-btn ${activeTab === 'control' ? 'active' : ''}`}
          onClick={() => setActiveTab('control')}
          title="Dashboard & Chat"
          aria-label="Dashboard & Chat"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="7" height="7" rx="1.5" />
            <rect x="14" y="3" width="7" height="7" rx="1.5" />
            <rect x="14" y="14" width="7" height="7" rx="1.5" />
            <rect x="3" y="14" width="7" height="7" rx="1.5" />
          </svg>
        </button>
        <button 
          className={`top-tab-btn ${activeTab === 'security' ? 'active' : ''}`}
          onClick={() => setActiveTab('security')}
          title="Security & Permissions"
          aria-label="Security & Permissions"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
        </button>
        <button 
          className={`top-tab-btn ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
          title="Settings & Models"
          aria-label="Settings & Models"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06-.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
        <button 
          className={`top-tab-btn ${activeTab === 'logs' ? 'active' : ''}`}
          onClick={() => setActiveTab('logs')}
          title="Execution Logs"
          aria-label="Execution Logs"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="4 17 10 11 4 5" />
            <line x1="12" y1="19" x2="20" y2="19" />
          </svg>
        </button>
      </nav>

      {/* Sub-Header Row */}
      <div className="app-sub-header">
        {/* Left: Mode Toggle Pill [ Chatbot   SPR SAATHI ] */}
        <div className="sub-header-left">
          <div className="mode-toggle-pill-container">
            <button
              type="button"
              className={`mode-pill-btn ${appMode === 'chat' ? 'active' : ''}`}
              onClick={() => {
                setAppMode('chat')
                localStorage.setItem('spr_saathi_mode', 'chat')
              }}
              title="Chatbot Mode"
            >
              Chatbot
            </button>
            <button
              type="button"
              className={`mode-pill-btn ${appMode === 'saathi' ? 'active' : ''}`}
              onClick={() => {
                setAppMode('saathi')
                localStorage.setItem('spr_saathi_mode', 'saathi')
              }}
              title="ORBIT Mode"
            >
              <img src={orbitLogo} alt="" className="orbit-pill-icon" />
              <span>ORBIT</span>
            </button>
          </div>
        </div>

        {/* Center: Status Pill or Inline Rename Input */}
        <div className="sub-header-center">
          {isRenamingChat ? (
            <input
              type="text"
              className="sub-header-rename-input"
              value={chatRenameInput}
              onChange={(e) => setChatRenameInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  if (chatRenameInput.trim() && activeSessionId) {
                    handleRenameActiveConversation(chatRenameInput.trim())
                  }
                  setIsRenamingChat(false)
                } else if (e.key === 'Escape') {
                  setIsRenamingChat(false)
                }
              }}
              onBlur={() => {
                if (chatRenameInput.trim() && activeSessionId) {
                  handleRenameActiveConversation(chatRenameInput.trim())
                }
                setIsRenamingChat(false)
              }}
              autoFocus
            />
          ) : (
            <div 
              className="sub-header-status-badge"
              title={
                appMode === 'saathi'
                  ? `ORBIT Status: ${status ? status.replace('_', ' ') : 'Agent Ready'} • CPU: ${Math.round(systemMetrics?.system?.cpu_percent || 0)}% (Click to reload ORBIT AI)`
                  : systemMetrics?.system
                  ? `Status: ${chatLoading ? 'Thinking...' : 'Chat Ready'} • CPU: ${Math.round(systemMetrics.system.cpu_percent)}% • RAM: ${Math.round(systemMetrics.memory?.rss_mb || 0)}MB (Click to reload)`
                  : activeSessionId && conversations.find(c => c.id === activeSessionId)
                  ? `${conversations.find(c => c.id === activeSessionId)?.title} (Click to reload)`
                  : 'Click to reload status'
              }
              onClick={() => {
                if (appMode === 'saathi') {
                  handleReloadOrbit()
                } else {
                  handleReload()
                }
              }}
              onDoubleClick={(e) => {
                e.stopPropagation()
                if (activeSessionId && appMode === 'chat') {
                  const cur = conversations.find(c => c.id === activeSessionId)?.title || ''
                  setChatRenameInput(cur)
                  setIsRenamingChat(true)
                }
              }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                {appMode === 'saathi' && (
                  <img src={orbitLogo} alt="" className="orbit-pill-icon" style={{ width: '11px', height: '11px' }} />
                )}
                {backendStatus !== 'connected'
                  ? backendStatus === 'connecting'
                    ? 'Connecting...'
                    : backendStatus === 'unavailable'
                    ? 'Backend unavailable'
                    : 'Disconnected'
                  : appMode === 'chat'
                  ? chatLoading
                    ? 'Thinking...'
                    : 'Chat Ready'
                  : status
                  ? status.replace('_', ' ')
                  : 'Agent Ready'}
              </span>
            </div>
          )}
        </div>

        {/* Right: Actions (🔄 Reload   + New   🕒 History   ••• More   ✕ Reset) */}
        <div className="sub-header-right">
          <div className="sub-header-actions">
            {/* Dedicated Reload Button (Context-Aware: Reloads Orbit AI or Chatbot) */}
            <button 
              className={`sub-header-icon-btn ${refreshing ? 'spinning' : ''}`}
              onClick={() => {
                if (appMode === 'saathi') {
                  handleReloadOrbit()
                } else {
                  handleReload()
                }
              }}
              title={appMode === 'saathi' ? "Reload ORBIT AI" : "Reload Chatbot & Models"}
              aria-label={appMode === 'saathi' ? "Reload ORBIT AI" : "Reload Chatbot & Models"}
            >
              <svg className={refreshing ? 'spin-icon' : ''} width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
              </svg>
            </button>

            {/* New Session / New Chat */}
            <button 
              className="sub-header-icon-btn"
              onClick={() => {
                if (appMode === 'saathi') {
                  handleNewOrbitChat()
                } else {
                  handleNewChat()
                }
              }}
              title={appMode === 'saathi' ? "New ORBIT Session" : "New Chat"}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <line x1="5" y1="12" x2="19" y2="12"></line>
              </svg>
            </button>

            {/* Conversation History Drawer Toggle */}
            <button 
              className={`sub-header-icon-btn ${showHistoryDrawer ? 'active' : ''}`}
              onClick={() => {
                setShowHistoryDrawer(!showHistoryDrawer)
                if (!showHistoryDrawer) {
                  loadConversations()
                }
              }}
              title="Conversation History"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                <path d="M3 3v5h5"/>
                <path d="M12 7v5l4 2"/>
              </svg>
            </button>

            {/* More Options Dropdown */}
            <div className="chatbot-more-menu-wrapper" ref={chatOptionsRef}>
              <button 
                className={`sub-header-icon-btn ${showChatOptionsMenu ? 'active' : ''}`}
                onClick={() => setShowChatOptionsMenu(!showChatOptionsMenu)}
                title="More options"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="5" cy="12" r="1.6"/>
                  <circle cx="12" cy="12" r="1.6"/>
                  <circle cx="19" cy="12" r="1.6"/>
                </svg>
              </button>

              {showChatOptionsMenu && (
                <div className="chatbot-options-dropdown">
                  {appMode === 'saathi' ? (
                    <>
                      <button 
                        className="chatbot-dropdown-item"
                        onClick={() => {
                          handleReloadOrbit()
                          setShowChatOptionsMenu(false)
                        }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
                        </svg>
                        <span>Reload ORBIT AI</span>
                      </button>

                      <button 
                        className="chatbot-dropdown-item"
                        onClick={() => {
                          handleReloadOrbit()
                          setShowChatOptionsMenu(false)
                        }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="3 6 5 6 21 6"></polyline>
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                        <span>Reset ORBIT Agent</span>
                      </button>

                      <div className="chatbot-dropdown-divider" />

                      <button 
                        className="chatbot-dropdown-item"
                        onClick={() => {
                          setActiveTab('logs')
                          setShowChatOptionsMenu(false)
                        }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="4 17 10 11 4 5" />
                          <line x1="12" y1="19" x2="20" y2="19" />
                        </svg>
                        <span>View Execution Logs</span>
                      </button>

                      <button 
                        className="chatbot-dropdown-item"
                        onClick={() => {
                          setActiveTab('workspace')
                          setShowChatOptionsMenu(false)
                        }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                        </svg>
                        <span>Files & Memory Workspace</span>
                      </button>

                      <button 
                        className="chatbot-dropdown-item"
                        onClick={() => {
                          setActiveTab('skills')
                          setShowChatOptionsMenu(false)
                        }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                        </svg>
                        <span>Skills & AI Specialists</span>
                      </button>
                    </>
                  ) : (
                    <>
                      <button 
                        className="chatbot-dropdown-item"
                        onClick={() => {
                          setActiveTab('workspace')
                          setShowChatOptionsMenu(false)
                        }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                        </svg>
                        <span>Files & Memory Workspace</span>
                      </button>

                      <button 
                        className="chatbot-dropdown-item"
                        onClick={() => {
                          setActiveTab('skills')
                          setShowChatOptionsMenu(false)
                        }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                        </svg>
                        <span>Skills & AI Specialists</span>
                      </button>

                      <div className="chatbot-dropdown-divider" />

                      {activeSessionId && (
                        <button 
                          className="chatbot-dropdown-item"
                          onClick={() => {
                            const cur = conversations.find(c => c.id === activeSessionId)?.title || ''
                            setChatRenameInput(cur)
                            setIsRenamingChat(true)
                            setShowChatOptionsMenu(false)
                          }}
                        >
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M12 20h9"></path>
                            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
                          </svg>
                          <span>Rename Chat</span>
                        </button>
                      )}
                      <button 
                        className="chatbot-dropdown-item"
                        onClick={handleCopyChatTranscript}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
                        <span>Copy Transcript</span>
                      </button>
                      <button 
                        className="chatbot-dropdown-item"
                        onClick={() => {
                          handleClearChat()
                          setShowChatOptionsMenu(false)
                        }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="3 6 5 6 21 6"></polyline>
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                        <span>Clear Context</span>
                      </button>
                      {activeSessionId && (
                        <button 
                          className="chatbot-dropdown-item danger"
                          onClick={(e) => {
                            handleDeleteConversation(activeSessionId, e)
                            setShowChatOptionsMenu(false)
                          }}
                        >
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M3 6h18m-2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                          </svg>
                          <span>Delete Conversation</span>
                        </button>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>

            {/* Reset / Clear Button */}
            <button 
              className="sub-header-icon-btn"
              onClick={() => {
                if (appMode === 'saathi') {
                  handleReloadOrbit()
                } else {
                  handleClearChat()
                }
              }}
              title={appMode === 'saathi' ? "Reset ORBIT AI Session" : "Close / Clear Chat"}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Main Content Scroll Panel */}
      <main className={`app-content ${(appMode === 'chat' || appMode === 'saathi') && activeTab === 'control' ? 'chat-mode' : 'panel-mode'}`}>
        {activeTab === 'control' ? (
          appMode === 'chat' ? (
            /* Chatbot Conversational Interface */
            <div className="chatbot-view-container">

              {/* Conversation History Sliding Drawer */}
              {showHistoryDrawer && (
                <div className="chatbot-history-drawer-backdrop" onClick={() => setShowHistoryDrawer(false)}>
                  <div className="chatbot-history-drawer" onClick={(e) => e.stopPropagation()}>
                    <div className="chatbot-history-drawer-header">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '14px' }}>💬</span>
                        <span style={{ fontWeight: 600, fontSize: '13px', color: '#f4f4f5' }}>Past Conversations</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <button 
                          className="chatbot-drawer-new-btn"
                          onClick={handleNewChat}
                          title="Start a new chat"
                        >
                          + New
                        </button>
                        <button 
                          className="chatbot-drawer-close-btn"
                          onClick={() => setShowHistoryDrawer(false)}
                          title="Close history"
                        >
                          ✕
                        </button>
                      </div>
                    </div>

                    <div className="chatbot-history-search-bar">
                      <input 
                        type="text"
                        placeholder="Search conversations..."
                        value={historySearchQuery}
                        onChange={(e) => setHistorySearchQuery(e.target.value)}
                        className="chatbot-history-search-input"
                      />
                    </div>

                    <div className="chatbot-history-list">
                      {historyLoading ? (
                        <div className="chatbot-history-empty">Loading conversations...</div>
                      ) : filteredConversations.length === 0 ? (
                        <div className="chatbot-history-empty">
                          {historySearchQuery ? 'No matching conversations found.' : 'No saved conversations yet. Chat to build history!'}
                        </div>
                      ) : (
                        filteredConversations.map(conv => {
                          const isActive = activeSessionId === conv.id
                          const formattedDate = conv.updated_at
                            ? new Date(conv.updated_at).toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + new Date(conv.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                            : ''
                          return (
                            <div 
                              key={conv.id}
                              className={`chatbot-history-item ${isActive ? 'active' : ''}`}
                              onClick={() => handleSelectConversation(conv.id)}
                            >
                              <div className="chatbot-history-item-top">
                                <div className="chatbot-history-item-title" title={conv.title}>
                                  <span className="chatbot-history-icon">💬</span>
                                  <span>{conv.title || 'Untitled Conversation'}</span>
                                </div>
                                <button 
                                  className="chatbot-history-delete-btn"
                                  onClick={(e) => handleDeleteConversation(conv.id, e)}
                                  title="Delete conversation"
                                >
                                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                    <polyline points="3 6 5 6 21 6"></polyline>
                                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                  </svg>
                                </button>
                              </div>
                              {conv.snippet && (
                                <div className="chatbot-history-item-snippet">
                                  {conv.snippet}
                                </div>
                              )}
                              <div className="chatbot-history-item-meta">
                                <span>{formattedDate}</span>
                                <span className="chatbot-history-badge">{conv.message_count || 0} msgs</span>
                              </div>
                            </div>
                          )
                        })
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div className="chat-messages-scroll">
                {chatMessages.map(msg => (
                  <div key={msg.id} className={`chat-message-row ${msg.sender}`}>
                    <div className={`chat-avatar ${msg.sender === 'assistant' ? 'orbit' : ''}`}>
                      {msg.sender === 'user' ? '👤' : <img src={orbitLogo} alt="ORBIT" className="chat-orbit-avatar-img" />}
                    </div>
                    <div className="chat-bubble-content">
                      <div className="chat-bubble-header">
                        <span className="chat-sender-name">{msg.sender === 'user' ? 'You' : 'ORBIT'}</span>
                        <span className="chat-timestamp">{msg.timestamp}</span>
                      </div>
                      {msg.attachments && msg.attachments.length > 0 && (
                        <div className="chat-msg-attachments">
                          {msg.attachments.map(att => (
                            <div key={att.id} className="chat-msg-att-badge">
                              <span className="chat-msg-att-icon">
                                {att.file_type === 'pdf' ? '📄' : att.file_type === 'docx' ? '📝' : att.is_image ? '🖼️' : att.file_type === 'folder' ? '📁' : '📎'}
                              </span>
                              <span className="chat-msg-att-name" title={att.filename}>{att.filename}</span>
                              <span className="chat-msg-att-size">{att.size_str}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="chat-bubble-text">
                        {renderFormattedMarkdown(msg.text)}
                      </div>
                    </div>
                  </div>
                ))}
                {chatLoading && (
                  <div className="chat-message-row assistant">
                    <div className="chat-avatar orbit">
                      <img src={orbitLogo} alt="ORBIT" className="chat-orbit-avatar-img" />
                    </div>
                    <div className="chat-bubble-content">
                      <div className="chat-typing-indicator">
                        <span></span>
                        <span></span>
                        <span></span>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            </div>
          ) : (
            /* ORBIT Conversational Agent Interface */
            <div className="orbit-view-container">
              <div className="orbit-messages-scroll">
                {orbitMessages.map((msg) => {
                  if (msg.sender === 'user') {
                    return (
                      <div key={msg.id} className="chat-message-row user">
                        <div className="chat-bubble-content">
                          <div className="chat-bubble-header">
                            <span className="chat-sender-name">You</span>
                            <span className="chat-timestamp">{msg.timestamp}</span>
                          </div>
                          {msg.attachments && msg.attachments.length > 0 && (
                            <div className="chat-msg-attachments">
                              {msg.attachments.map(att => (
                                <div key={att.id} className="chat-msg-att-badge">
                                  <span className="chat-msg-att-icon">
                                    {att.file_type === 'pdf' ? '📄' : att.file_type === 'docx' ? '📝' : att.is_image ? '🖼️' : att.file_type === 'folder' ? '📁' : '📎'}
                                  </span>
                                  <span className="chat-msg-att-name" title={att.filename}>{att.filename}</span>
                                  <span className="chat-msg-att-size">{att.size_str}</span>
                                </div>
                              ))}
                            </div>
                          )}
                          <div className="chat-bubble-text">
                            {msg.text}
                          </div>
                        </div>
                      </div>
                    )
                  }

                  // Assistant / ORBIT message
                  return (
                    <div key={msg.id} className="chat-message-row assistant">
                      <div className="chat-avatar orbit">
                        <img src={orbitLogo} alt="ORBIT" className="chat-orbit-avatar-img" />
                      </div>
                      <div className="chat-bubble-content">
                        <div className="chat-bubble-header">
                          <span className="chat-sender-name">ORBIT</span>
                          <span className="chat-timestamp">{msg.timestamp}</span>
                        </div>

                        {msg.type === 'info' && (
                          <div className="chat-bubble-text">
                            {renderFormattedMarkdown(msg.text || '')}
                          </div>
                        )}

                        {msg.type === 'task_progress' && (
                          <div className={`live-task-card ${msg.status === 'waiting_user' ? 'waiting' : msg.status === 'completed' ? 'completed' : msg.status === 'failed' ? 'failed' : 'active'}`}>
                            {/* Card Header */}
                            <div className="live-task-card-header">
                              <div className="live-task-header-left">
                                <div className={`live-pulse-beacon ${msg.status === 'waiting_user' ? 'waiting' : msg.status === 'completed' ? 'completed' : msg.status === 'failed' ? 'failed' : msg.status === 'planning' ? 'planning' : 'active'}`} />
                                <span className="live-task-title">
                                  {msg.status === 'completed' ? 'Task Completed' : msg.status === 'failed' ? 'Task Stopped' : msg.status === 'waiting_user' ? 'Clarification Required' : 'Executing Task'}
                                </span>
                                <span className={`live-task-status-tag ${msg.status === 'waiting_user' ? 'waiting' : msg.status === 'completed' ? 'completed' : msg.status === 'failed' ? 'failed' : msg.status === 'planning' ? 'planning' : 'active'}`}>
                                  {msg.status === 'waiting_user' ? 'Needs input' : msg.status || 'active'}
                                </span>
                              </div>
                              <div className="live-task-timer" title="Elapsed execution time">
                                <span>⏱️</span>
                                <span>{formatTimer(msg.elapsedSeconds || 0)}</span>
                              </div>
                            </div>

                            {/* User Task Prompt Quote */}
                            {msg.taskText && (
                              <div style={{ fontSize: '11.5px', color: '#94a3b8', fontStyle: 'italic', borderLeft: '2px solid rgba(56, 189, 248, 0.35)', paddingLeft: '8px' }}>
                                "{msg.taskText}"
                              </div>
                            )}

                            {/* Prominent Layman Activity Banner */}
                            <div className={`live-task-current-activity ${msg.status === 'waiting_user' ? 'waiting' : msg.status === 'completed' ? 'completed' : msg.status === 'failed' ? 'failed' : ''}`}>
                              {msg.status !== 'completed' && msg.status !== 'failed' && <div className="live-task-activity-shimmer" />}
                              <span className="live-task-activity-text">
                                {msg.currentLaymanStatus || 'Orbit is actively working on your computer...'}
                              </span>
                            </div>

                            {/* Progressive Layman Steps Timeline */}
                            {msg.laymanSteps && msg.laymanSteps.length > 0 && (
                              <div className="live-task-steps-trail">
                                {msg.laymanSteps.map((step, sIdx) => (
                                  <div key={step.id || sIdx} className={`live-task-step-item ${step.status}`}>
                                    <span className={`live-step-badge ${step.status}`}>
                                      {step.status === 'completed' ? '✓' : step.status === 'running' ? '⏳' : step.status === 'failed' ? '✗' : '•'}
                                    </span>
                                    <span>{step.text}</span>
                                  </div>
                                ))}
                              </div>
                            )}

                            {/* Interactive Clarification Question Box */}
                            {msg.status === 'waiting_user' && (msg.question || userQuestion) && (
                              <div className="live-task-question-card">
                                <div className="live-task-question-header">
                                  <span>❓</span>
                                  <span>ORBIT needs clarification to proceed:</span>
                                </div>
                                <div className="live-task-question-text">
                                  {msg.question || userQuestion}
                                </div>
                                {!msg.questionAnswer ? (
                                  <div className="live-task-question-form">
                                    <input
                                      type="text"
                                      className="live-task-question-input"
                                      placeholder="Type your answer here..."
                                      value={inlineClarificationAnswer}
                                      onChange={(e) => setInlineClarificationAnswer(e.target.value)}
                                      onKeyDown={(e) => {
                                        if (e.key === 'Enter' && inlineClarificationAnswer.trim()) {
                                          respondUserQuestion(inlineClarificationAnswer)
                                        }
                                      }}
                                      autoFocus
                                    />
                                    <button
                                      type="button"
                                      className="live-task-question-submit-btn"
                                      onClick={() => {
                                        if (inlineClarificationAnswer.trim()) {
                                          respondUserQuestion(inlineClarificationAnswer)
                                        }
                                      }}
                                    >
                                      Send Reply ➔
                                    </button>
                                  </div>
                                ) : (
                                  <div style={{ fontSize: '11.5px', color: '#4ade80' }}>
                                    ✓ Answered: "{msg.questionAnswer}"
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Quick Controls Toolbar */}
                            <div className="live-task-controls-bar">
                              {msg.status === 'failed' && (
                                <button
                                  type="button"
                                  className="live-btn-control retry"
                                  onClick={() => triggerStartTask(msg.taskText)}
                                >
                                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
                                  Try Again
                                </button>
                              )}
                              {msg.status !== 'completed' && msg.status !== 'failed' && (
                                <>
                                  <button
                                    type="button"
                                    className={`live-btn-control ${agentState.takeover_active ? 'takeover-active' : ''}`}
                                    onClick={toggleTakeover}
                                    title={agentState.takeover_active ? "Release control back to Orbit" : "Take manual mouse & keyboard control"}
                                  >
                                    {agentState.takeover_active ? '▶ Resume Orbit' : '✋ Take Control'}
                                  </button>
                                  <button
                                    type="button"
                                    className="live-btn-control stop"
                                    onClick={triggerStopTask}
                                    title="Stop agent execution"
                                  >
                                    ■ Stop
                                  </button>
                                </>
                              )}
                              {msg.status === 'completed' && (
                                <button
                                  type="button"
                                  className="live-btn-control"
                                  onClick={handleNewOrbitChat}
                                >
                                  + New Task
                                </button>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}

                {/* Standby Hero when only welcome message exists and status is idle */}
                {orbitMessages.length === 1 && status === 'idle' && (
                  <div className="orbit-hero-container">
                    <div className="orbit-standby-logo-wrapper">
                      <div className="orbit-standby-logo-glow" />
                      <img src={orbitLogo} alt="ORBIT" className="orbit-standby-logo-img" />
                    </div>
                    <div className="orbit-hero-title">
                      ORBIT Autonomous Assistant
                    </div>
                    <div className="orbit-hero-subtitle">
                      Enter any instruction below. ORBIT will automate desktop tasks, open apps like Paint, create drawings, manage files, and ask clarifying questions if anything is unclear.
                    </div>
                    <div className="orbit-hero-suggestions">
                      <button 
                        type="button" 
                        className="orbit-suggestion-chip"
                        onClick={() => triggerStartTask("Open Paint and draw a portrait of Mahatma Gandhi.")}
                      >
                        🎨 Open Paint & draw portrait of Mahatma Gandhi
                      </button>
                      <button 
                        type="button" 
                        className="orbit-suggestion-chip"
                        onClick={() => triggerStartTask("Open Notepad and draft meeting notes template.")}
                      >
                        📝 Open Notepad & draft meeting notes
                      </button>
                      <button 
                        type="button" 
                        className="orbit-suggestion-chip"
                        onClick={() => triggerStartTask("Open File Explorer and show Downloads.")}
                      >
                        📁 Show Downloads in File Explorer
                      </button>
                    </div>
                  </div>
                )}

                {/* Security Authorization Prompt Overlay */}
                {activePrompt && (
                  <section className="permission-overlay" style={{ marginTop: '12px' }}>
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

                <div ref={orbitChatEndRef} />
              </div>
            </div>
          )
        ) : activeTab === 'security' ? (
          <>
            {/* Security & Applications Access Control Panel */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              
              {/* Scope Policies (Global) */}
              <section className="settings-panel" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-glass)', borderRadius: '12px', padding: '12px 14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <div className="section-title" style={{ margin: 0 }}>Scope Access Policies</div>
                  <div style={{ fontSize: '10px', color: 'var(--color-text-secondary)', background: 'rgba(255, 255, 255, 0.05)', padding: '2px 8px', borderRadius: '10px' }}>
                    {Object.keys(permissions).length} Scopes Active
                  </div>
                </div>
                <div className="permissions-grid" style={{ display: 'flex', flexDirection: 'column', gap: '4px', maxHeight: '185px', overflowY: 'auto', paddingRight: '4px' }}>
                  {Object.keys(permissions).map((scope) => {
                    const scopeIcons: Record<string, string> = {
                      mouse: '🖱️',
                      keyboard: '⌨️',
                      applications: '📦',
                      filesystem: '📁',
                      browser: '🌐',
                      terminal: '💻',
                      powershell: '⚡',
                      windows: '🪟',
                      computer: '🖥️'
                    }
                    const val = permissions[scope]
                    return (
                      <div 
                        key={scope} 
                        className="permission-row" 
                        style={{ 
                          display: 'flex', 
                          justifyContent: 'space-between', 
                          alignItems: 'center',
                          padding: '5px 8px',
                          borderRadius: '6px',
                          background: 'rgba(255, 255, 255, 0.015)',
                          border: '1px solid rgba(255, 255, 255, 0.025)',
                          transition: 'background 0.15s ease'
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.04)'}
                        onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.015)'}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '12px', opacity: 0.85 }}>{scopeIcons[scope.toLowerCase()] || '🛡️'}</span>
                          <span style={{ textTransform: 'capitalize', fontSize: '11.5px', fontWeight: 600, color: '#e2e8f0' }}>{scope}</span>
                        </div>
                        <select
                          className="settings-select"
                          style={{ 
                            padding: '3px 8px', 
                            fontSize: '10.5px', 
                            fontWeight: 600,
                            borderRadius: '6px', 
                            background: val === 'allow' ? 'rgba(16, 185, 129, 0.12)' : val === 'deny' ? 'rgba(239, 68, 68, 0.12)' : 'rgba(245, 158, 11, 0.12)',
                            color: val === 'allow' ? '#34d399' : val === 'deny' ? '#f87171' : '#fbbf24',
                            border: `1px solid ${val === 'allow' ? 'rgba(16, 185, 129, 0.25)' : val === 'deny' ? 'rgba(239, 68, 68, 0.25)' : 'rgba(245, 158, 11, 0.25)'}`,
                            cursor: 'pointer',
                            outline: 'none'
                          }}
                          value={val}
                          onChange={(e) => handlePermissionChange(scope, e.target.value as any)}
                        >
                          <option value="allow" style={{ background: '#15171f', color: '#34d399' }}>Allow</option>
                          <option value="prompt" style={{ background: '#15171f', color: '#fbbf24' }}>Prompt</option>
                          <option value="deny" style={{ background: '#15171f', color: '#f87171' }}>Deny</option>
                        </select>
                      </div>
                    )
                  })}
                </div>
              </section>

              {/* Installed Applications access configuration */}
              <section style={{ display: 'flex', flexDirection: 'column', background: 'var(--bg-card)', border: '1px solid var(--border-glass)', borderRadius: '12px', padding: '14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <div className="section-title" style={{ margin: 0 }}>Installed System Software</div>
                  <div style={{ fontSize: '10px', color: 'var(--color-text-secondary)', background: 'rgba(255, 255, 255, 0.05)', padding: '2px 8px', borderRadius: '10px' }}>
                    {installedApps.length} Apps Found
                  </div>
                </div>

                {/* Search Box */}
                <input
                  type="text"
                  placeholder="Search applications (e.g. mspaint, calc, cmd, Blender...)"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '7px 10px',
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
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '260px', overflowY: 'auto', paddingRight: '4px' }}>
                  {(() => {
                    const DEFAULT_SYSTEM_APPS = [
                      { name: 'Paint', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'mspaint.exe' },
                      { name: 'Calculator', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'calc.exe' },
                      { name: 'Notepad', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'notepad.exe' },
                      { name: 'File Explorer', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'explorer.exe' },
                      { name: 'Command Prompt', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'cmd.exe' },
                      { name: 'Windows PowerShell', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'powershell.exe' },
                      { name: 'Task Manager', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'taskmgr.exe' },
                      { name: 'Snipping Tool', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'snippingtool.exe' },
                      { name: 'Registry Editor', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'regedit.exe' },
                      { name: 'Control Panel', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'control.exe' },
                      { name: 'Windows Settings', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'ms-settings:' },
                      { name: 'Device Manager', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'devmgmt.msc' },
                      { name: 'Services', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'services.msc' },
                      { name: 'Resource Monitor', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'resmon.exe' },
                      { name: 'Character Map', version: 'System Tool', publisher: 'Microsoft Corporation', key: 'charmap.exe' }
                    ]

                    const merged = [...installedApps]
                    const seen = new Set(merged.map(a => (a.name || '').toLowerCase()))
                    for (const def of DEFAULT_SYSTEM_APPS) {
                      if (!seen.has(def.name.toLowerCase())) {
                        seen.add(def.name.toLowerCase())
                        merged.push(def)
                      }
                    }

                    const query = searchQuery.toLowerCase().trim()
                    const aliasMap: Record<string, string[]> = {
                      mspaint: ['paint', 'mspaint', 'pbrush'],
                      paint: ['mspaint', 'paint', 'pbrush'],
                      calc: ['calculator', 'calc'],
                      calculator: ['calc', 'calculator'],
                      notepad: ['notepad', 'editor', 'txt'],
                      cmd: ['command prompt', 'cmd', 'terminal'],
                      powershell: ['windows powershell', 'powershell', 'pwsh'],
                      explorer: ['file explorer', 'explorer'],
                      taskmgr: ['task manager', 'taskmgr'],
                      snip: ['snipping tool', 'snip'],
                      regedit: ['registry editor', 'regedit'],
                      control: ['control panel', 'control']
                    }

                    const filtered = merged.filter(app => {
                      if (!query) return true
                      const name = (app.name || '').toLowerCase()
                      const pub = (app.publisher || '').toLowerCase()
                      const key = (app.key || '').toLowerCase()

                      // 1. Direct name, publisher, key match
                      if (name.includes(query) || pub.includes(query) || key.includes(query)) return true

                      // 2. Token match
                      const tokens = query.split(/\s+/).filter(Boolean)
                      if (tokens.length > 1 && tokens.every(t => name.includes(t) || pub.includes(t) || key.includes(t))) return true

                      // 3. Alias dictionary matching
                      for (const [trigger, matches] of Object.entries(aliasMap)) {
                        if (query === trigger || query.includes(trigger) || trigger.includes(query)) {
                          if (matches.some(m => name.includes(m) || key.includes(m))) return true
                        }
                      }

                      return false
                    }).sort((a, b) => a.name.localeCompare(b.name))

                    if (filtered.length === 0) {
                      return (
                        <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', textAlign: 'center', padding: '20px' }}>
                          No matching applications found for "{searchQuery}".
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
                          key={app.key || app.name} 
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
                  })()}
                </div>
              </section>

              {/* Audit logs trail */}
              <section className="settings-panel" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-glass)', borderRadius: '12px', padding: '14px' }}>
                <div className="section-title" style={{ marginBottom: '8px' }}>Security Audit Trail</div>
                <div style={{ maxHeight: '100px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {auditLogs.length === 0 ? (
                    <div style={{ fontSize: '10px', color: 'var(--color-text-secondary)', fontStyle: 'italic' }}>No security events logged.</div>
                  ) : (
                    auditLogs.slice(-10).reverse().map((log, idx) => (
                      <div key={idx} style={{ fontSize: '9.5px', background: 'rgba(255,255,255,0.02)', padding: '4px 8px', borderRadius: '4px', display: 'flex', justifyContent: 'space-between' }}>
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
        ) : activeTab === 'workspace' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', height: '100%', overflow: 'hidden' }}>
            <div style={{ padding: '4px 4px 10px 4px', borderBottom: '1px solid rgba(255, 255, 255, 0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '14px', fontWeight: 700, color: '#ffffff', marginBottom: '4px' }}>Workspace & Persistent Memory</div>
                <div style={{ fontSize: '10.5px', color: '#64748b', lineHeight: '14px' }}>Manage agent knowledge, learned user preferences, and sandboxed workspace files</div>
              </div>
              <button
                type="button"
                onClick={() => setActiveTab('control')}
                title="Back to Dashboard & Chat"
                style={{
                  background: 'rgba(255, 255, 255, 0.06)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: '#cbd5e1',
                  cursor: 'pointer',
                  padding: '5px 12px',
                  borderRadius: '6px',
                  fontSize: '11.5px',
                  fontWeight: 500,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <span>✕</span> Back to Chat
              </button>
            </div>

            <div className="subnav-pills">
              <button 
                className={`subnav-btn ${workspaceSubTab === 'memory' ? 'active' : ''}`}
                onClick={() => setWorkspaceSubTab('memory')}
              >
                🧠 Persistent Memory ({memoryItems.length})
              </button>
              <button 
                className={`subnav-btn ${workspaceSubTab === 'files' ? 'active' : ''}`}
                onClick={() => setWorkspaceSubTab('files')}
              >
                📁 Workspace Files ({workspaceFiles.length})
              </button>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', paddingRight: '4px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {memoryMessage && (
                <div style={{
                  padding: '8px 12px',
                  borderRadius: '6px',
                  fontSize: '11.5px',
                  background: memoryMessage.type === 'success' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                  color: memoryMessage.type === 'success' ? '#34d399' : '#f87171',
                  border: `1px solid ${memoryMessage.type === 'success' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`
                }}>
                  {memoryMessage.text}
                </div>
              )}

              {workspaceSubTab === 'memory' ? (
                <>
                  {/* Add New Memory Card */}
                  <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-glass)', borderRadius: '10px', padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <div style={{ fontSize: '11.5px', fontWeight: 600, color: '#e4e4e7' }}>Add Memory Note / Preference</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                      <input 
                        type="text"
                        placeholder="Memory key (e.g. coding_style)"
                        value={newMemKey}
                        onChange={(e) => setNewMemKey(e.target.value)}
                        style={{ padding: '6px 10px', background: 'var(--bg-input)', border: '1px solid var(--border-glass)', borderRadius: '6px', color: '#fff', fontSize: '11px', outline: 'none' }}
                      />
                      <select 
                        value={newMemType}
                        onChange={(e) => setNewMemType(e.target.value)}
                        style={{ padding: '6px 10px', background: 'var(--bg-input)', border: '1px solid var(--border-glass)', borderRadius: '6px', color: '#c084fc', fontSize: '11px', outline: 'none' }}
                      >
                        <option value="preference_memory">Preference Memory</option>
                        <option value="context_memory">Context Memory</option>
                        <option value="instruction_memory">Instruction Memory</option>
                        <option value="episodic_memory">Episodic Memory</option>
                      </select>
                    </div>
                    <textarea 
                      placeholder="Memory content (e.g. User prefers Python with strict typing and pytest fixtures)"
                      value={newMemContent}
                      onChange={(e) => setNewMemContent(e.target.value)}
                      rows={2}
                      style={{ padding: '8px 10px', background: 'var(--bg-input)', border: '1px solid var(--border-glass)', borderRadius: '6px', color: '#fff', fontSize: '11.5px', outline: 'none', resize: 'vertical' }}
                    />
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <input 
                        type="text"
                        placeholder="Tags comma-separated (e.g. style, python)"
                        value={newMemTags}
                        onChange={(e) => setNewMemTags(e.target.value)}
                        style={{ flex: 1, padding: '6px 10px', background: 'var(--bg-input)', border: '1px solid var(--border-glass)', borderRadius: '6px', color: '#fff', fontSize: '11px', outline: 'none' }}
                      />
                      <button 
                        className="btn btn-primary"
                        onClick={handleCreateMemory}
                        style={{ padding: '6px 14px', fontSize: '11px', fontWeight: 600, borderRadius: '6px' }}
                      >
                        Save Memory
                      </button>
                    </div>
                  </div>

                  {/* Search Bar */}
                  <input 
                    type="text"
                    placeholder="Search memories by keyword..."
                    value={memoryQuery}
                    onChange={(e) => setMemoryQuery(e.target.value)}
                    style={{ padding: '7px 10px', background: 'var(--bg-input)', border: '1px solid var(--border-glass)', borderRadius: '6px', color: '#fff', fontSize: '11.5px', outline: 'none' }}
                  />

                  {/* Memories List */}
                  {memoryItems.filter(m => !memoryQuery || m.key.toLowerCase().includes(memoryQuery.toLowerCase()) || m.content.toLowerCase().includes(memoryQuery.toLowerCase())).length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '24px', fontSize: '11px', color: '#64748b' }}>
                      No persistent memories stored yet. Add memories above or let the agent learn from your tasks.
                    </div>
                  ) : (
                    memoryItems
                      .filter(m => !memoryQuery || m.key.toLowerCase().includes(memoryQuery.toLowerCase()) || m.content.toLowerCase().includes(memoryQuery.toLowerCase()))
                      .map((mem) => (
                        <div key={mem.id} className="memory-item-card">
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <span style={{ fontWeight: 600, fontSize: '12px', color: '#ffffff' }}>{mem.key}</span>
                              <span className="memory-type-badge">{mem.memory_type.replace('_', ' ')}</span>
                            </div>
                            <button 
                              onClick={() => handleDeleteMemory(mem.id)}
                              style={{ background: 'transparent', border: 'none', color: '#71717a', cursor: 'pointer', padding: '2px', borderRadius: '4px', fontSize: '11px' }}
                              title="Delete memory"
                            >
                              🗑️
                            </button>
                          </div>
                          <div style={{ fontSize: '11.5px', color: '#d4d4d8', lineHeight: 1.45 }}>{mem.content}</div>
                          {mem.tags && mem.tags.length > 0 && (
                            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '2px' }}>
                              {mem.tags.map((t, idx) => (
                                <span key={idx} className="tag-chip">#{t}</span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))
                  )}
                </>
              ) : (
                <>
                  {/* Workspace Files Filter */}
                  <input 
                    type="text"
                    placeholder="Search workspace files..."
                    value={workspaceQuery}
                    onChange={(e) => setWorkspaceQuery(e.target.value)}
                    style={{ padding: '7px 10px', background: 'var(--bg-input)', border: '1px solid var(--border-glass)', borderRadius: '6px', color: '#fff', fontSize: '11.5px', outline: 'none' }}
                  />

                  {workspaceFiles.filter(f => !workspaceQuery || f.filename.toLowerCase().includes(workspaceQuery.toLowerCase())).length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '24px', fontSize: '11px', color: '#64748b' }}>
                      No files currently tracked in the agent workspace.
                    </div>
                  ) : (
                    workspaceFiles
                      .filter(f => !workspaceQuery || f.filename.toLowerCase().includes(workspaceQuery.toLowerCase()))
                      .map((file) => (
                        <div key={file.file_id || file.filename} className="memory-item-card">
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: 600, fontSize: '12px', color: '#38bdf8' }}>📄 {file.filename}</span>
                            <span style={{ fontSize: '10px', color: '#a1a1aa' }}>
                              {Math.round(file.size_bytes / 1024)} KB
                            </span>
                          </div>
                          <div style={{ fontSize: '10.5px', color: '#71717a', fontFamily: 'monospace' }}>
                            {file.path}
                          </div>
                          {file.task_id && (
                            <div style={{ fontSize: '9.5px', color: '#a78bfa' }}>
                              Generated by task: {file.task_id}
                            </div>
                          )}
                        </div>
                      ))
                  )}
                </>
              )}
            </div>
          </div>
        ) : activeTab === 'skills' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', height: '100%', overflow: 'hidden' }}>
            <div style={{ padding: '4px 4px 10px 4px', borderBottom: '1px solid rgba(255, 255, 255, 0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '14px', fontWeight: 700, color: '#ffffff', marginBottom: '4px' }}>Skills & AI Specialists (KAIRO)</div>
                <div style={{ fontSize: '10.5px', color: '#64748b', lineHeight: '14px' }}>Discover registered system skills and delegate multi-step autonomous tasks to specialists</div>
              </div>
              <button
                type="button"
                onClick={() => setActiveTab('control')}
                title="Back to Dashboard & Chat"
                style={{
                  background: 'rgba(255, 255, 255, 0.06)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: '#cbd5e1',
                  cursor: 'pointer',
                  padding: '5px 12px',
                  borderRadius: '6px',
                  fontSize: '11.5px',
                  fontWeight: 500,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <span>✕</span> Back to Chat
              </button>
            </div>

            <div className="subnav-pills">
              <button 
                className={`subnav-btn ${skillsSubTab === 'skills' ? 'active' : ''}`}
                onClick={() => setSkillsSubTab('skills')}
              >
                ⚡ Skills Library ({registeredSkills.length})
              </button>
              <button 
                className={`subnav-btn ${skillsSubTab === 'specialists' ? 'active' : ''}`}
                onClick={() => setSkillsSubTab('specialists')}
              >
                🤖 AI Specialists ({specialistsList.length})
              </button>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', paddingRight: '4px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {skillsSubTab === 'skills' ? (
                registeredSkills.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '24px', fontSize: '11px', color: '#64748b' }}>
                    Loading skills catalog...
                  </div>
                ) : (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '8px' }}>
                    {registeredSkills.map((skill) => (
                      <div key={skill.name} className="skill-card">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span style={{ fontSize: '14px' }}>🛠️</span>
                          <span style={{ fontWeight: 600, fontSize: '12px', color: '#ffffff' }}>{skill.name}</span>
                        </div>
                        <div style={{ fontSize: '11px', color: '#a1a1aa', lineHeight: 1.4 }}>
                          {skill.description}
                        </div>
                        {skill.parameters && (
                          <div style={{ fontSize: '9.5px', color: '#64748b', fontFamily: 'monospace', marginTop: '2px' }}>
                            Params: {Object.keys(skill.parameters.properties || {}).join(', ') || 'none'}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )
              ) : (
                <>
                  {/* Specialist Delegation Box */}
                  <div style={{ background: 'linear-gradient(180deg, rgba(167, 139, 250, 0.08) 0%, rgba(20, 20, 24, 0.95) 100%)', border: '1px solid rgba(167, 139, 250, 0.3)', borderRadius: '12px', padding: '14px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ fontSize: '12.5px', fontWeight: 700, color: '#ffffff', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span>⚡</span> Specialist Delegation Terminal
                      </div>
                      <select 
                        value={specialistSelected}
                        onChange={(e) => setSpecialistSelected(e.target.value)}
                        style={{ padding: '4px 8px', background: '#18181b', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '6px', color: '#c084fc', fontSize: '11px', outline: 'none' }}
                      >
                        <option value="kairo_coding">KAIRO-AI Coding Specialist</option>
                        <option value="research">Research Specialist</option>
                        <option value="data_analysis">Data Analysis Specialist</option>
                      </select>
                    </div>

                    <textarea 
                      placeholder="Enter a task to delegate (e.g. 'Write a Python script to calculate Fibonacci sequence and test it')"
                      value={specialistTaskInput}
                      onChange={(e) => setSpecialistTaskInput(e.target.value)}
                      rows={2}
                      style={{ padding: '8px 10px', background: 'var(--bg-input)', border: '1px solid var(--border-glass)', borderRadius: '6px', color: '#fff', fontSize: '11.5px', outline: 'none', resize: 'vertical' }}
                    />

                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                      <button 
                        className="btn btn-primary"
                        onClick={handleDelegateSpecialist}
                        disabled={specialistLoading || !specialistTaskInput.trim()}
                        style={{ padding: '6px 14px', fontSize: '11px', fontWeight: 600, borderRadius: '6px' }}
                      >
                        {specialistLoading ? 'Specialist Working...' : 'Delegate Task'}
                      </button>
                    </div>

                    {specialistResult && (
                      <div style={{ marginTop: '6px', padding: '10px', background: '#09090b', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.08)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '11px', fontWeight: 600, color: specialistResult.status === 'success' ? '#34d399' : '#f87171' }}>
                            {specialistResult.status === 'success' ? '✔ Task Completed & Verified' : '✖ Delegation Failed'}
                          </span>
                          {specialistResult.specialist && (
                            <span style={{ fontSize: '10px', color: '#a1a1aa' }}>Specialist: {specialistResult.specialist}</span>
                          )}
                        </div>
                        {specialistResult.summary && (
                          <div style={{ fontSize: '11.5px', color: '#e4e4e7' }}>{specialistResult.summary}</div>
                        )}
                        {specialistResult.code_artifacts && Object.entries(specialistResult.code_artifacts).map(([fname, code]) => (
                          <div key={fname} style={{ marginTop: '4px' }}>
                            <div style={{ fontSize: '10.5px', fontWeight: 600, color: '#38bdf8', marginBottom: '2px' }}>📄 {fname}</div>
                            <pre style={{ margin: 0, padding: '8px', background: '#111114', borderRadius: '6px', fontSize: '10.5px', color: '#f4f4f5', overflowX: 'auto' }}>
                              <code>{String(code)}</code>
                            </pre>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Specialists Cards */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {specialistsList.map((spec) => (
                      <div key={spec.name} className={`specialist-card ${spec.name.includes('KAIRO') ? 'kairo' : ''}`}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontWeight: 600, fontSize: '12.5px', color: '#ffffff' }}>{spec.name}</span>
                          <span style={{ fontSize: '10px', color: '#34d399', background: 'rgba(52, 211, 153, 0.1)', padding: '2px 6px', borderRadius: '4px' }}>Ready</span>
                        </div>
                        <div style={{ fontSize: '11px', color: '#a1a1aa', lineHeight: 1.45 }}>
                          {spec.description || 'Specialized agent orchestrator capable of multi-step autonomous execution.'}
                        </div>
                        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                          {spec.capabilities.map((cap, i) => (
                            <span key={i} className="tag-chip">⚡ {cap}</span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        ) : activeTab === 'settings' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', height: '100%', overflow: 'hidden' }}>
            
            {/* Header info */}
            <div style={{ padding: '4px 4px 10px 4px', borderBottom: '1px solid rgba(255, 255, 255, 0.06)' }}>
              <div style={{ fontSize: '14px', fontWeight: 700, color: '#ffffff', marginBottom: '4px' }}>Kairo-AI Model Manager</div>
              <div style={{ fontSize: '10.5px', color: '#64748b', lineHeight: '14px' }}>Select hardware-tuned offline models or configure cloud API credentials</div>
            </div>

            {/* Tabs */}
            <div className="model-manager-tabs" style={{ borderRadius: '8px', overflow: 'hidden' }}>
              <button 
                className={`model-manager-tab ${managerTab === 'offline' ? 'active' : ''}`}
                onClick={() => {
                  setManagerTab('offline');
                  setManagerMessage(null);
                }}
              >
                Offline Models Zone
              </button>
              <button 
                className={`model-manager-tab ${managerTab === 'online' ? 'active' : ''}`}
                onClick={() => {
                  setManagerTab('online');
                  setManagerMessage(null);
                }}
              >
                Online Cloud Models Zone (API Keys)
              </button>
            </div>

            {/* Content Area */}
            <div className="model-manager-content" style={{ flex: 1, overflowY: 'auto', padding: '12px 4px 4px 4px' }}>
              {managerMessage && (
                <div style={{
                  padding: '8px 12px',
                  borderRadius: '6px',
                  fontSize: '11.5px',
                  marginBottom: '12px',
                  background: managerMessage.type === 'success' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                  color: managerMessage.type === 'success' ? '#34d399' : '#f87171',
                  border: `1px solid ${managerMessage.type === 'success' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`
                }}>
                  {managerMessage.text}
                </div>
              )}

              {managerTab === 'offline' ? (
                <div>
                  <div className="model-category-header">Installed Models</div>
                  {installedList.length === 0 ? (
                    <div style={{ fontSize: '11px', color: '#64748b', padding: '10px 14px', background: '#16171d', borderRadius: '8px', border: '1px dashed rgba(255,255,255,0.06)', marginBottom: '12px' }}>
                      No installed Ollama models detected on your system. Run 'ollama run &lt;model&gt;' to install.
                    </div>
                  ) : (
                    installedList.map(model => (
                      <div key={model.name} className="model-item-card">
                        <div className="model-item-info">
                          <div className="model-item-title-row">
                            <span className="model-item-title">{model.name}</span>
                            {model.isVision && (
                              <span className="model-item-badge" style={{ background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', border: '1px solid rgba(56, 189, 248, 0.3)' }}>
                                👁️ Vision
                              </span>
                            )}
                            <span className="model-item-badge installed">Installed</span>
                          </div>
                          <div className="model-item-specs">{model.specs}</div>
                        </div>
                        {selectedProvider === 'local' && selectedModel === model.name ? (
                          <span className="model-active-btn">Active</span>
                        ) : (
                          <button 
                            className="model-switch-btn" 
                            onClick={() => {
                              handleModelChange('local', model.name);
                              setManagerMessage({type: 'success', text: `Switched to ${model.name}!`});
                            }}
                          >
                            Switch
                          </button>
                        )}
                      </div>
                    ))
                  )}

                  <div className="model-category-header">Extended Offline Models</div>
                  {extendedList.length === 0 ? (
                    <div style={{ fontSize: '11px', color: '#64748b', padding: '10px 14px', background: '#16171d', borderRadius: '8px', border: '1px dashed rgba(255,255,255,0.06)' }}>
                      All supported offline models are installed on your system!
                    </div>
                  ) : (
                    extendedList.map(model => (
                      <div key={model.name} className="model-item-card">
                        <div className="model-item-info">
                          <div className="model-item-title-row">
                            <span className="model-item-title">{model.name}</span>
                          </div>
                          <div className="model-item-specs">{model.specs}</div>
                        </div>
                        {selectedProvider === 'local' && selectedModel === model.name ? (
                          <span className="model-active-btn">Active</span>
                        ) : (
                          <button 
                            className="model-switch-btn" 
                            onClick={() => {
                              handleModelChange('local', model.name);
                              setManagerMessage({type: 'success', text: `Switched to ${model.name}!`});
                            }}
                          >
                            Switch
                          </button>
                        )}
                      </div>
                    ))
                  )}
                </div>
              ) : (
                <div className="cloud-setup-form">
                  <div className="form-group">
                    <label className="form-label">Cloud Provider:</label>
                    <select 
                      className="form-select"
                      value={cloudProvider}
                      onChange={(e) => {
                        const prov = e.target.value as any;
                        setCloudProvider(prov);
                        if (prov === 'gemini') {
                          setCloudModel('Gemini 3.5 Flash');
                        } else if (prov === 'openai') {
                          setCloudModel('OpenAI GPT-4o');
                        } else {
                          setCloudModel('Claude 3.5 Sonnet');
                        }
                      }}
                    >
                      <option value="openai">OpenAI Cloud API</option>
                      <option value="gemini">Gemini Cloud API</option>
                      <option value="anthropic">Anthropic Cloud API</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Select Cloud Model:</label>
                    <select 
                      className="form-select"
                      value={cloudModel}
                      onChange={(e) => setCloudModel(e.target.value)}
                    >
                      {cloudProvider === 'openai' && (
                        <>
                          <option value="OpenAI GPT-4o">OpenAI GPT-4o (125k context)</option>
                          <option value="OpenAI GPT-4o-mini">OpenAI GPT-4o-mini (128k context)</option>
                        </>
                      )}
                      {cloudProvider === 'gemini' && (
                        <>
                          <option value="Gemini 3.5 Flash">Gemini 3.5 Flash (1M context)</option>
                          <option value="Gemini 3.5 Flash Medium">Gemini 3.5 Flash Medium</option>
                          <option value="Gemini 1.5 Pro">Gemini 1.5 Pro (2M context)</option>
                        </>
                      )}
                      {cloudProvider === 'anthropic' && (
                        <>
                          <option value="Claude 3.5 Sonnet">Claude 3.5 Sonnet (200k context)</option>
                          <option value="Claude 3.5 Haiku">Claude 3.5 Haiku (200k context)</option>
                        </>
                      )}
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">API Key:</label>
                    <div className="form-input-container">
                      <input 
                        type={apiKeyVisible ? 'text' : 'password'}
                        className="form-input"
                        placeholder={cloudProvider === 'openai' ? 'sk-...' : cloudProvider === 'gemini' ? 'AIzaSy...' : 'sk-ant/...'}
                        value={cloudApiKey}
                        onChange={(e) => setCloudApiKey(e.target.value)}
                      />
                      <button 
                        className="form-toggle-btn"
                        onClick={() => setApiKeyVisible(!apiKeyVisible)}
                      >
                        {apiKeyVisible ? 'Hide' : 'Show'}
                      </button>
                    </div>
                    <span className="form-info-text">
                      API keys are stored securely in VS Code SecretStorage and locked to workspace root.
                    </span>
                  </div>

                  <button 
                    className="form-submit-btn"
                    disabled={!cloudApiKey.trim()}
                    onClick={async () => {
                      await handleModelChange('api', cloudModel, cloudApiKey);
                      setManagerMessage({type: 'success', text: `API Key saved & activated ${cloudModel}!`});
                      setCloudApiKey('');
                    }}
                  >
                    Save API Key & Activate Cloud Model
                  </button>

                </div>
              )}
            </div>

          </div>
        ) : (
          /* Console Event Logs & System Diagnostics */
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', height: '100%', minHeight: 0 }}>
            {/* Live Computer State Card (Shifted from Orbit) */}
            <div 
              style={{ 
                background: 'var(--bg-card)', 
                border: '1px solid var(--border-glass)', 
                borderRadius: '12px', 
                padding: '12px 14px', 
                fontSize: '12px', 
                display: 'flex', 
                flexDirection: 'column', 
                gap: '8px',
                flexShrink: 0
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div className="section-title" style={{ margin: 0, fontSize: '11px' }}>🖥️ Computer State</div>
                {agentState.computer_state ? (
                  <span style={{ fontSize: '9.5px', color: '#34d399', background: 'rgba(52, 211, 153, 0.12)', padding: '2px 8px', borderRadius: '10px', fontWeight: 600 }}>Active Stream</span>
                ) : (
                  <span style={{ fontSize: '9.5px', color: 'var(--color-text-muted)', background: 'rgba(255, 255, 255, 0.04)', padding: '2px 8px', borderRadius: '10px' }}>Standby</span>
                )}
              </div>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                <div style={{ background: 'rgba(255, 255, 255, 0.02)', padding: '6px 10px', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.03)' }}>
                  <div style={{ color: 'var(--color-text-muted)', fontSize: '9.5px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>Screen Resolution</div>
                  <div style={{ fontWeight: 600, fontSize: '11.5px', color: '#f4f4f5', marginTop: '2px' }}>
                    {agentState.computer_state ? `${agentState.computer_state.screen_width} × ${agentState.computer_state.screen_height}` : '1920 × 1080'}
                  </div>
                </div>
                
                <div style={{ background: 'rgba(255, 255, 255, 0.02)', padding: '6px 10px', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.03)' }}>
                  <div style={{ color: 'var(--color-text-muted)', fontSize: '9.5px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>Cursor Coordinates</div>
                  <div style={{ fontWeight: 600, fontSize: '11.5px', color: 'var(--color-act)', marginTop: '2px' }}>
                    {agentState.computer_state ? `${agentState.computer_state.cursor_x}, ${agentState.computer_state.cursor_y}` : 'Default / Centered'}
                  </div>
                </div>
              </div>

              {agentState.computer_state?.active_window && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', background: 'rgba(255, 255, 255, 0.02)', padding: '6px 10px', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.03)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: 'var(--color-text-muted)', fontSize: '9.5px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>Foreground Window</span>
                    <span style={{ fontFamily: 'monospace', fontSize: '10px', color: '#94a3b8' }}>{agentState.computer_state.active_window.process}</span>
                  </div>
                  <div style={{ fontWeight: 600, color: '#ffffff', fontSize: '11.5px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={agentState.computer_state.active_window.title}>
                    {agentState.computer_state.active_window.title}
                  </div>
                </div>
              )}
            </div>

            {/* Loop Activity visualizer in Execution Log Panel */}
            <section className="loop-visualizer" style={{ flexShrink: 0, padding: '10px 14px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <div className="section-title" style={{ margin: 0, fontSize: '11px' }}>Agent Autonomous Loop</div>
                <div style={{ fontSize: '10px', fontWeight: 600, color: status === 'idle' ? 'var(--color-text-muted)' : 'var(--color-act)', textTransform: 'capitalize' }}>
                  {status ? status.replace('_', ' ') : 'Idle'}
                </div>
              </div>
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

            {/* Console Event Logs */}
            <section className="event-feed" style={{ flex: 1, minHeight: 0 }}>
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
          </div>
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
                    ORBIT is paused. You control the computer.
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
                  stopAudioRecording()
                }}
              >
                Cancel
              </button>
            )}
          </div>
        )}

        {/* Hidden inputs for uploading media/files and folders */}
        <input 
          type="file" 
          ref={mediaFileInputRef} 
          style={{ display: 'none' }} 
          multiple 
          accept=".pdf,.doc,.docx,.txt,.md,.json,.csv,.png,.jpg,.jpeg,.webp,.py,.ts,.js,.html,.css,*/*" 
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              handleFilesUpload(e.target.files)
            }
          }} 
        />
        <input 
          type="file" 
          ref={folderInputRef} 
          // @ts-ignore
          webkitdirectory="true" 
          directory="" 
          multiple 
          style={{ display: 'none' }} 
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              handleFilesUpload(e.target.files)
            }
          }} 
        />

        {/* Natural Language Prompt Input */}
        <div 
          className={`input-container-premium ${isDraggingOver ? 'drag-over' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {/* Attachment Chips Tray */}
          {(attachments.length > 0 || isUploadingContext) && (
            <div className="attachment-chips-tray">
              {attachments.map(att => (
                <div key={att.id} className={`attachment-chip ${att.file_type}`}>
                  {att.is_image && att.preview_url ? (
                    <img src={att.preview_url} alt="" className="attachment-chip-thumb" />
                  ) : (
                    <span className={`attachment-chip-badge ${att.file_type}`}>
                      {att.file_type === 'pdf' ? 'PDF' : att.file_type === 'docx' ? 'DOC' : att.file_type === 'folder' ? 'DIR' : att.file_type === 'image' ? 'IMG' : 'FILE'}
                    </span>
                  )}
                  <span className="attachment-chip-name" title={att.filename}>{att.filename}</span>
                  <span className="attachment-chip-size">{att.size_str}</span>
                  <button 
                    type="button" 
                    className="attachment-chip-remove"
                    onClick={() => setAttachments(prev => prev.filter(a => a.id !== att.id))}
                    title="Remove attachment"
                  >
                    ✕
                  </button>
                </div>
              ))}
              {isUploadingContext && (
                <div className="attachment-chip uploading">
                  <span className="attachment-upload-spinner" />
                  <span>Processing...</span>
                </div>
              )}
            </div>
          )}

          <textarea
            className="chat-textarea"
            placeholder={
              appMode === 'chat'
                ? "Ask anything, @ to mention, / for actions"
                : status === 'waiting_user'
                ? "Type your answer to Orbit's question..."
                : "Tell ORBIT what to do on your computer (e.g. Open Paint and draw Gandhi)..."
            }
            value={taskInput}
            onChange={(e) => setTaskInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                if (appMode === 'chat') {
                  handleSendChatMessage()
                } else {
                  if (status === 'waiting_user' && taskInput.trim()) {
                    respondUserQuestion(taskInput)
                    setTaskInput('')
                  } else {
                    triggerStartTask()
                  }
                }
              }
            }}
            rows={1}
          />
          
          <div className="input-actions-row">
            <div className="input-actions-left">
              {/* + Button & Add Context Popup Menu */}
              <div className="add-context-container" ref={addContextMenuRef}>
                <button
                  type="button"
                  className={`btn-add-context ${showAddContextMenu ? 'active' : ''}`}
                  onClick={() => setShowAddContextMenu(prev => !prev)}
                  title="Add Context (Media, Folder, Mentions, Actions)"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"></line>
                    <line x1="5" y1="12" x2="19" y2="12"></line>
                  </svg>
                </button>

                {showAddContextMenu && (
                  <div className="add-context-menu">
                    <div className="add-context-header">Actions & Context</div>
                    
                    {/* New Chat */}
                    <button
                      type="button"
                      className="add-context-item"
                      onClick={() => {
                        setShowAddContextMenu(false)
                        if (appMode === 'saathi') {
                          handleNewOrbitChat()
                        } else {
                          handleNewChat()
                        }
                      }}
                    >
                      <span className="add-context-icon">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="12" y1="5" x2="12" y2="19"></line>
                          <line x1="5" y1="12" x2="19" y2="12"></line>
                        </svg>
                      </span>
                      <span className="add-context-label">New Chat</span>
                    </button>

                    {/* Media */}
                    <button
                      type="button"
                      className="add-context-item"
                      onClick={() => {
                        setShowAddContextMenu(false)
                        mediaFileInputRef.current?.click()
                      }}
                    >
                      <span className="add-context-icon">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                          <circle cx="8.5" cy="8.5" r="1.5"/>
                          <polyline points="21 15 16 10 5 21"/>
                        </svg>
                      </span>
                      <span className="add-context-label">Media</span>
                    </button>

                    {/* Mentions */}
                    <button
                      type="button"
                      className="add-context-item"
                      onClick={() => {
                        setShowAddContextMenu(false)
                        setTaskInput(prev => (prev ? `${prev} @` : '@'))
                      }}
                    >
                      <span className="add-context-icon">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="12" cy="12" r="4"/>
                          <path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-3.92 7.94"/>
                        </svg>
                      </span>
                      <span className="add-context-label">Mentions</span>
                    </button>

                    {/* Actions */}
                    <button
                      type="button"
                      className="add-context-item"
                      onClick={() => {
                        setShowAddContextMenu(false)
                        setTaskInput(prev => (prev ? `${prev} /` : '/'))
                      }}
                    >
                      <span className="add-context-icon">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="9 11 12 14 22 4"/>
                          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                        </svg>
                      </span>
                      <span className="add-context-label">Actions</span>
                    </button>

                    {/* Folder */}
                    <button
                      type="button"
                      className="add-context-item"
                      onClick={() => {
                        setShowAddContextMenu(false)
                        folderInputRef.current?.click()
                      }}
                    >
                      <span className="add-context-icon">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                        </svg>
                      </span>
                      <span className="add-context-label">Folder</span>
                    </button>
                  </div>
                )}
              </div>

              {/* Model Dropdown Container */}
              <div className="model-dropdown-container" title="Select AI Model">
                <span className="model-select-label">
                  {selectedModel}{selectedProvider === 'local' && !installedList.some(m => m.name.toLowerCase() === selectedModel.toLowerCase()) ? ' (Active)' : ''}
                </span>
                <span className="dropdown-chevron">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="18 15 12 9 6 15"></polyline>
                  </svg>
                </span>
                <select
                  className="model-select-overlay"
                  value={`${selectedProvider}:${selectedModel}`}
                  onChange={(e) => {
                    const [provider, modelName] = e.target.value.split(':')
                    handleModelChange(provider as 'api' | 'local', modelName)
                  }}
                >
                  {/* Cloud/API Models */}
                  {(configuredKeys.gemini || selectedModel === 'Gemini 3.7 Flash High' || selectedModel === 'Gemini 3.5 Flash') && (
                    <option value="api:Gemini 3.7 Flash High">Gemini 3.7 Flash High</option>
                  )}
                  {(configuredKeys.gemini || selectedModel === 'Gemini 3.5 Flash') && (
                    <option value="api:Gemini 3.5 Flash">Gemini 3.5 Flash</option>
                  )}
                  {(configuredKeys.gemini || selectedModel === 'Gemini 3.5 Flash Medium') && (
                    <option value="api:Gemini 3.5 Flash Medium">Gemini 3.5 Flash Medium</option>
                  )}
                  {(configuredKeys.gemini || selectedModel === 'Gemini 1.5 Pro') && (
                    <option value="api:Gemini 1.5 Pro">Gemini 1.5 Pro</option>
                  )}
                  {(configuredKeys.openai || selectedModel === 'OpenAI GPT-4o') && (
                    <option value="api:OpenAI GPT-4o">OpenAI GPT-4o</option>
                  )}
                  {(configuredKeys.openai || selectedModel === 'OpenAI GPT-4o-mini') && (
                    <option value="api:OpenAI GPT-4o-mini">OpenAI GPT-4o-mini</option>
                  )}
                  {(configuredKeys.anthropic || selectedModel === 'Claude 3.5 Sonnet') && (
                    <option value="api:Claude 3.5 Sonnet">Claude 3.5 Sonnet</option>
                  )}
                  {(configuredKeys.anthropic || selectedModel === 'Claude 3.5 Haiku') && (
                    <option value="api:Claude 3.5 Haiku">Claude 3.5 Haiku</option>
                  )}
                  
                  {/* Local/Offline Models */}
                  {installedList.map(model => (
                    <option key={model.name} value={`local:${model.name}`}>
                      {model.name} {model.isVision ? '👁️ (Vision)' : '(Local)'}
                    </option>
                  ))}
                  {/* If active local model is not in list, keep it visible */}
                  {selectedProvider === 'local' && !installedList.some(m => m.name.toLowerCase() === selectedModel.toLowerCase()) && (
                    <option value={`local:${selectedModel}`}>
                      {selectedModel} (Active)
                    </option>
                  )}
                </select>
              </div>
            </div>
            
            <div className="input-actions-right">
              <button 
                className={`mic-button-premium ${voiceState}`} 
                title="Voice input"
                onClick={handleMicClick}
              >
                {voiceState === 'listening' ? (
                  <span className="mic-wave-container">
                    <span className="mic-wave-dot"></span>
                    <span className="mic-wave-dot"></span>
                    <span className="mic-wave-dot"></span>
                  </span>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                    <line x1="12" y1="19" x2="12" y2="23"></line>
                    <line x1="8" y1="23" x2="16" y2="23"></line>
                  </svg>
                )}
              </button>
              
              <button 
                className="btn-send-premium"
                title={appMode === 'chat' ? "Send message" : status === 'waiting_user' ? "Send clarification answer" : "Send command"}
                onClick={() => {
                  if (appMode === 'chat') {
                    handleSendChatMessage()
                  } else {
                    if (status === 'waiting_user' && taskInput.trim()) {
                      respondUserQuestion(taskInput)
                      setTaskInput('')
                    } else {
                      triggerStartTask()
                    }
                  }
                }}
                disabled={
                  appMode === 'chat'
                    ? (chatLoading || (!taskInput.trim() && attachments.length === 0))
                    : (status === 'waiting_user'
                        ? !taskInput.trim()
                        : ((status !== 'idle' && status !== 'completed' && status !== 'error' && status !== 'stopped' && status !== 'cancelled' && status !== 'failed') || (!taskInput.trim() && attachments.length === 0))
                      )
                }
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="5" y1="12" x2="19" y2="12"></line>
                  <polyline points="12 5 19 12 12 19"></polyline>
                </svg>
              </button>
            </div>
          </div>
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
              ORBIT requests access to your microphone to transcribe voice commands.
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
