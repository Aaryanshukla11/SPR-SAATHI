import { ElectronAPI } from '@electron-toolkit/preload'

declare global {
  interface Window {
    electron: ElectronAPI
    api: {
      getBackendPort: () => Promise<number>
      setAlwaysOnTop: (alwaysOnTop: boolean) => void
    }
  }
}

