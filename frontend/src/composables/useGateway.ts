import { ref } from 'vue'
import axios from 'axios'
import { useWebSocket } from './useWebSocket'
import { useToasts } from './useToasts'

const gatewayRunning = ref(false)
const gatewayPartial = ref(false)
const gatewayStarting = ref(false)
const gatewayError = ref<string | null>(null)
const stpListening = ref(false)
const bridgeListening = ref(false)
let isInitialized = false

export function useGateway() {
  const { on } = useWebSocket()
  const { addToast } = useToasts()

  async function fetchStatus() {
    try {
      const res = await axios.get('/api/gateway/status')
      const data = res.data
      gatewayRunning.value = Boolean(data.running)
      gatewayPartial.value = Boolean(data.partial)
      gatewayStarting.value = Boolean(data.starting)
      gatewayError.value = data.error || null
      stpListening.value = Boolean(data.stp_listening)
      bridgeListening.value = Boolean(data.bridge_listening)
    } catch (err: any) {
      console.warn('Failed to fetch gateway status', err)
    }
  }

  if (!isInitialized) {
    isInitialized = true
    fetchStatus()

    on('gateway_status_changed', (data: any) => {
      if (!data) return
      gatewayRunning.value = Boolean(data.running)
      gatewayPartial.value = Boolean(data.partial)
      gatewayStarting.value = Boolean(data.starting)
      gatewayError.value = data.error || null
      stpListening.value = Boolean(data.stp_listening)
      bridgeListening.value = Boolean(data.bridge_listening)
    })
  }

  async function startGateway(): Promise<boolean> {
    gatewayStarting.value = true
    gatewayError.value = null
    try {
      const res = await axios.post('/api/gateway/start')
      const data = res.data
      gatewayRunning.value = Boolean(data.running)
      gatewayPartial.value = Boolean(data.partial)
      gatewayStarting.value = Boolean(data.starting)
      gatewayError.value = data.error || null
      stpListening.value = Boolean(data.stp_listening)
      bridgeListening.value = Boolean(data.bridge_listening)
      if (data.running) {
        addToast('Passerelle Modal H3 démarrée !', 'success', 3000)
      }
      return Boolean(gatewayRunning.value)
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Impossible de démarrer la passerelle'
      gatewayError.value = msg
      gatewayRunning.value = false
      gatewayStarting.value = false
      addToast(msg, 'error', 4500)
      return false
    } finally {
      gatewayStarting.value = false
    }
  }

  async function stopGateway(): Promise<boolean> {
    gatewayStarting.value = false
    try {
      const res = await axios.post('/api/gateway/stop')
      const data = res.data
      gatewayRunning.value = false
      gatewayPartial.value = false
      gatewayStarting.value = false
      gatewayError.value = null
      stpListening.value = false
      bridgeListening.value = false
      addToast('Passerelle Modal H3 arrêtée', 'info', 2500)
      return true
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Erreur lors de l’arrêt de la passerelle'
      addToast(msg, 'error', 3500)
      return false
    }
  }

  return {
    gatewayRunning,
    gatewayPartial,
    gatewayStarting,
    gatewayError,
    stpListening,
    bridgeListening,
    fetchStatus,
    startGateway,
    stopGateway,
  }
}
