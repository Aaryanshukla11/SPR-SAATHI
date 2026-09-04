import { ElectronAPI } from '@electron-toolkit/preload'

declare global {
  interface Window {
    electron: ElectronAPI
    api: {
      getBackendPort: () => Promise<number>
      setAlwaysOnTop: (alwaysOnTop: boolean) => void
      restartBackend?: () => Promise<boolean>
      onBackendPortUpdated?: (callback: (port: number) => void) => () => void
    }
  }
}

