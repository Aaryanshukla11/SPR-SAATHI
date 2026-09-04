import { app, shell, BrowserWindow, ipcMain, screen, session, Menu, MenuItem } from 'electron'
import { join } from 'path'
import * as path from 'path'
import { spawn, ChildProcess } from 'child_process'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import icon from '../../resources/icon.png?asset'

let pyProc: ChildProcess | null = null
let pyPort: number | null = null
let mainWindow: BrowserWindow | null = null

let isQuitting = false

function startPythonProcess(): void {
  if (pyProc && !pyProc.killed) {
    try {
      pyProc.kill()
    } catch (e) {}
    pyProc = null
  }
  pyPort = null

  // During dev, the app runs from desktop/out/main/index.js, so app.getAppPath() resolves to desktop/
  // agent folder is ../agent relative to desktop/
  const agentDir = path.resolve(app.getAppPath(), '../agent')
  const mainPy = path.join(agentDir, 'main.py')
  
  console.log(`[Main Process] Spawning Python process. Cwd: ${agentDir}, Script: ${mainPy}`)
  
  const rootDir = path.resolve(agentDir, '..')
  const env = { ...process.env, PYTHONPATH: rootDir }
  
  // Use 'python' executable (we verified Python 3.13.7 is available in the environment)
  pyProc = spawn('python', ['-u', mainPy], {
    cwd: agentDir,
    env: env,
    stdio: ['pipe', 'pipe', 'inherit']
  })
  
  pyProc.stdout?.on('data', (data) => {
    const output = data.toString()
    console.log(`[Python Stdout]: ${output.trim()}`)
    const match = output.match(/PORT:\s*(\d+)/)
    if (match) {
      pyPort = parseInt(match[1], 10)
      console.log(`[Main Process] Discovered Python server port: ${pyPort}`)
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('backend-port-updated', pyPort)
      }
    }
  })
  
  pyProc.on('error', (err) => {
    console.error('[Main Process] Failed to start Python agent:', err)
    pyPort = -1
  })
  
  pyProc.on('close', (code) => {
    console.log(`[Main Process] Python agent exited with code ${code}`)
    pyPort = -1
    if (!isQuitting) {
      console.log('[Main Process] Auto-restarting Python agent...')
      setTimeout(() => {
        if (!isQuitting) startPythonProcess()
      }, 1000)
    }
  })

  // Set startup timeout (15 seconds)
  const STARTUP_TIMEOUT_MS = 15000
  setTimeout(() => {
    if (pyPort === null) {
      console.error(`[Main Process] Python backend startup timed out after ${STARTUP_TIMEOUT_MS}ms.`)
      pyPort = -1
      if (pyProc) {
        console.log('[Main Process] Terminating timed-out Python process...')
        pyProc.kill()
      }
    }
  }, STARTUP_TIMEOUT_MS)
}

function createWindow(): void {
  const primaryDisplay = screen.getPrimaryDisplay()
  const screenWidth = primaryDisplay.bounds.width
  
  // Calculate exactly 25% width of the monitor screen
  const panelWidth = Math.floor(screenWidth * 0.25)
  
  // Use work area height so it docks nicely without overlap with the bottom Windows taskbar
  const panelHeight = primaryDisplay.workArea.height

  // Create the browser window.
  mainWindow = new BrowserWindow({
    width: panelWidth,
    height: panelHeight,
    x: screenWidth - panelWidth,
    y: 0,
    resizable: false,
    maximizable: false,
    alwaysOnTop: true,
    show: false,
    autoHideMenuBar: true,
    title: 'ORBIT',
    ...(process.platform === 'linux' ? { icon } : {}),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false
    }
  })

  mainWindow.on('ready-to-show', () => {
    if (mainWindow) {
      mainWindow.show()
    }
  })

  // Enable right-click context menu for cut, copy, paste, and selectAll
  mainWindow.webContents.on('context-menu', (_, params) => {
    const menu = new Menu()
    if (params.isEditable) {
      menu.append(new MenuItem({ role: 'undo' }))
      menu.append(new MenuItem({ role: 'redo' }))
      menu.append(new MenuItem({ type: 'separator' }))
      menu.append(new MenuItem({ role: 'cut' }))
      menu.append(new MenuItem({ role: 'copy' }))
      menu.append(new MenuItem({ role: 'paste' }))
      menu.append(new MenuItem({ type: 'separator' }))
      menu.append(new MenuItem({ role: 'selectAll' }))
    } else if (params.selectionText) {
      menu.append(new MenuItem({ role: 'copy' }))
      menu.append(new MenuItem({ role: 'selectAll' }))
    }
    if (menu.items.length > 0) {
      menu.popup()
    }
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // HMR for renderer base on electron-vite cli.
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

app.whenReady().then(() => {
  // Set app user model id for windows
  electronApp.setAppUserModelId('com.electron')

  // Register standard Edit application menu to enable global Ctrl+C, Ctrl+V, Ctrl+X, Ctrl+A
  const editTemplate: Electron.MenuItemConstructorOptions[] = [
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' }
      ]
    }
  ]
  const appMenu = Menu.buildFromTemplate(editTemplate)
  Menu.setApplicationMenu(appMenu)

  // Set permission request handler for media/microphone access
  session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
    if (permission === 'media') {
      callback(true) // Approve media capture requests (microphone)
    } else {
      callback(false)
    }
  })

  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  // Register IPC handlers
  ipcMain.handle('get-backend-port', async () => {
    if (pyPort !== null && pyPort > 0) {
      return pyPort
    }

    // Check if active backend (e.g. 51733 or standard) is already responding
    const candidatePorts = [51733, 8000, 8080]
    for (const p of candidatePorts) {
      try {
        const res = await fetch(`http://127.0.0.1:${p}/api/health`, { signal: AbortSignal.timeout(300) })
        if (res.ok) {
          pyPort = p
          return p
        }
      } catch (e) {}
    }

    // Asynchronously poll until Python port is resolved
    return new Promise((resolve) => {
      let attempts = 0
      const checkInterval = setInterval(async () => {
        attempts++
        if (pyPort !== null && pyPort > 0) {
          clearInterval(checkInterval)
          resolve(pyPort)
          return
        }
        for (const p of candidatePorts) {
          try {
            const res = await fetch(`http://127.0.0.1:${p}/api/health`, { signal: AbortSignal.timeout(250) })
            if (res.ok) {
              clearInterval(checkInterval)
              pyPort = p
              resolve(p)
              return
            }
          } catch (e) {}
        }
        if (attempts > 30) {
          clearInterval(checkInterval)
          resolve(pyPort || -1)
        }
      }, 200)
    })
  })

  ipcMain.on('set-always-on-top', (_, alwaysOnTop: boolean) => {
    if (mainWindow) {
      mainWindow.setAlwaysOnTop(alwaysOnTop)
    }
  })

  ipcMain.handle('restart-backend', async () => {
    console.log('[Main Process] Manual restart of Python agent requested.')
    startPythonProcess()
    return true
  })

  // Spawn Python Agent Runtime
  startPythonProcess()

  createWindow()

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// Clean up child process on exit
app.on('will-quit', () => {
  isQuitting = true
  if (pyProc) {
    console.log('[Main Process] Terminating Python process...')
    pyProc.kill()
  }
})

