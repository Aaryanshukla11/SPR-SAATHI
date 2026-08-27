import { app, shell, BrowserWindow, ipcMain, screen } from 'electron'
import { join } from 'path'
import * as path from 'path'
import { spawn, ChildProcess } from 'child_process'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import icon from '../../resources/icon.png?asset'

let pyProc: ChildProcess | null = null
let pyPort: number | null = null
let mainWindow: BrowserWindow | null = null

function startPythonProcess(): void {
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
    }
  })
  
  pyProc.on('error', (err) => {
    console.error('[Main Process] Failed to start Python agent:', err)
    pyPort = -1
  })
  
  pyProc.on('close', (code) => {
    console.log(`[Main Process] Python agent exited with code ${code}`)
    pyPort = -1
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
    title: 'SPR SAATHI',
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

  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  // Register IPC handlers
  ipcMain.handle('get-backend-port', async () => {
    if (pyPort !== null) {
      return pyPort
    }
    // Asynchronously poll until Python port is resolved
    return new Promise((resolve) => {
      const checkInterval = setInterval(() => {
        if (pyPort !== null) {
          clearInterval(checkInterval)
          resolve(pyPort)
        }
      }, 100)
    })
  })

  ipcMain.on('set-always-on-top', (_, alwaysOnTop: boolean) => {
    if (mainWindow) {
      mainWindow.setAlwaysOnTop(alwaysOnTop)
    }
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
  if (pyProc) {
    console.log('[Main Process] Terminating Python process...')
    pyProc.kill()
  }
})

