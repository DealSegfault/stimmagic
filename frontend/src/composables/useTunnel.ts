import { ref, readonly } from 'vue'
import axios from 'axios'
import { useWebSocket } from './useWebSocket'
import { useToasts } from './useToasts'

const tunnelRunning = ref(false)
const tunnelStarting = ref(false)
const tunnelUrl = ref<string | null>(null)
const tunnelError = ref<string | null>(null)
const tunnelInstalled = ref(true)
const tunnelPort = ref(9192)
let isInitialized = false

export function useTunnel() {
  const { on } = useWebSocket()
  const { addToast } = useToasts()

  async function fetchStatus() {
    try {
      const res = await axios.get('/api/tunnel/status')
      const data = res.data
      tunnelRunning.value = Boolean(data.running && data.url)
      tunnelStarting.value = Boolean(data.starting)
      tunnelUrl.value = data.url || null
      tunnelError.value = data.error || null
      tunnelInstalled.value = data.installed ?? true
      if (data.port) tunnelPort.value = data.port
    } catch (err: any) {
      console.warn('Failed to fetch tunnel status', err)
    }
  }

  if (!isInitialized) {
    isInitialized = true
    fetchStatus()

    on('tunnel_status_changed', (data: any) => {
      if (!data) return
      tunnelRunning.value = Boolean(data.running && data.url)
      tunnelStarting.value = Boolean(data.starting)
      tunnelUrl.value = data.url || null
      tunnelError.value = data.error || null
      tunnelInstalled.value = data.installed ?? true
      if (data.port) tunnelPort.value = data.port
    })
  }

  async function startTunnel(port?: number): Promise<boolean> {
    tunnelStarting.value = true
    tunnelError.value = null
    try {
      const targetPort = port || tunnelPort.value || 9192
      const res = await axios.post('/api/tunnel/start', { port: targetPort })
      const data = res.data
      tunnelRunning.value = Boolean(data.running && data.url)
      tunnelStarting.value = Boolean(data.starting)
      tunnelUrl.value = data.url || null
      tunnelError.value = data.error || null
      if (data.url) {
        addToast('Tunnel Cloudflare actif !', 'success', 3000)
      }
      return Boolean(tunnelRunning.value)
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Impossible de démarrer le tunnel'
      tunnelError.value = msg
      tunnelRunning.value = false
      tunnelStarting.value = false
      addToast(msg, 'error', 4500)
      return false
    } finally {
      tunnelStarting.value = false
    }
  }

  async function stopTunnel(): Promise<boolean> {
    tunnelStarting.value = false
    try {
      const res = await axios.post('/api/tunnel/stop')
      const data = res.data
      tunnelRunning.value = false
      tunnelStarting.value = false
      tunnelUrl.value = null
      tunnelError.value = null
      addToast('Tunnel Cloudflare arrêté', 'info', 2500)
      return true
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Erreur lors de l’arrêt du tunnel'
      addToast(msg, 'error', 3500)
      return false
    }
  }

  async function shareTunnelUrl(): Promise<void> {
    if (!tunnelUrl.value) {
      addToast('Aucun tunnel actif à partager', 'error', 3000)
      return
    }

    const url = tunnelUrl.value
    if (typeof navigator !== 'undefined' && navigator.share) {
      try {
        await navigator.share({
          title: 'Stimma Remote Access',
          text: 'Accédez à mon instance Stimma via ce tunnel Cloudflare :',
          url,
        })
        addToast('Lien partagé !', 'success', 2000)
        return
      } catch (err: any) {
        if (err.name === 'AbortError') {
          return // User cancelled the native share sheet
        }
      }
    }

    // Fallback to clipboard
    await copyTunnelUrl()
  }

  async function copyTunnelUrl(): Promise<void> {
    if (!tunnelUrl.value) return
    try {
      await navigator.clipboard.writeText(tunnelUrl.value)
      addToast('URL Cloudflare copiée dans le presse-papier !', 'success', 3000)
    } catch (err) {
      addToast('Impossible de copier l’URL', 'error', 3000)
    }
  }

  return {
    tunnelRunning: readonly(tunnelRunning),
    tunnelStarting: readonly(tunnelStarting),
    tunnelUrl: readonly(tunnelUrl),
    tunnelError: readonly(tunnelError),
    tunnelInstalled: readonly(tunnelInstalled),
    tunnelPort: readonly(tunnelPort),
    fetchStatus,
    startTunnel,
    stopTunnel,
    shareTunnelUrl,
    copyTunnelUrl,
  }
}
