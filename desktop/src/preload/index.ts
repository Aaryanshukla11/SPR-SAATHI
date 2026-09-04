import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

// Custom APIs for renderer
const api = {
  getBackendPort: () => ipcRenderer.invoke('get-backend-port'),
  setAlwaysOnTop: (alwaysOnTop: boolean) => ipcRenderer.send('set-always-on-top', alwaysOnTop),
  restartBackend: () => ipcRenderer.invoke('restart-backend'),
  onBackendPortUpdated: (callback: (port: number) => void) => {
    const listener = (_: any, port: number) => callback(port)
    ipcRenderer.on('backend-port-updated', listener)
    return () => ipcRenderer.removeListener('backend-port-updated', listener)
  }
}

// Use `contextBridge` APIs to expose Electron APIs to
// renderer only if context isolation is enabled, otherwise
// just add to the DOM global.
if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('api', api)
  } catch (error) {
    console.error(error)
  }
} else {
  // @ts-ignore (define in dts)
  window.electron = electronAPI
  // @ts-ignore (define in dts)
  window.api = api
}

