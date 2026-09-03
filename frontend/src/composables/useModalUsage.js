import { computed, ref } from 'vue'
import axios from 'axios'
import { useWebSocket } from './useWebSocket'

const snapshot = ref(null)
const loading = ref(false)
const error = ref('')
const routingSaving = ref(false)
const routingError = ref('')
let refreshPromise = null
let realtimeStarted = false

function beginRealtime() {
  if (realtimeStarted) return
  realtimeStarted = true
  const { on } = useWebSocket()
  const refresh = () => refreshUsage()
  on('generation_job_queued', refresh)
  on('generation_job_started', refresh)
  on('generation_job_completed', refresh)
  on('generation_job_failed', refresh)
  on('generation_job_cancelled', refresh)
  on('websocket_reconnected', refresh)
}

async function refreshUsage() {
  if (refreshPromise) return refreshPromise
  loading.value = !snapshot.value
  refreshPromise = axios.get('/api/modal/usage?limit=100')
    .then(({ data }) => {
      snapshot.value = data
      error.value = ''
      return data
    })
    .catch((err) => {
      error.value = err?.response?.data?.detail || err?.message || 'Impossible de charger les données Modal.'
      throw err
    })
    .finally(() => {
      loading.value = false
      refreshPromise = null
    })
  return refreshPromise
}

async function updateRouting(mode, accountId = null) {
  routingSaving.value = true
  routingError.value = ''
  try {
    const { data } = await axios.patch('/api/modal/routing', {
      mode,
      account_id: mode === 'fixed' ? accountId : null,
    })
    if (snapshot.value) snapshot.value = { ...snapshot.value, routing: data }
    await refreshUsage()
    return data
  } catch (err) {
    routingError.value = err?.response?.data?.detail || err?.message || 'Impossible de modifier le routage Modal.'
    throw err
  } finally {
    routingSaving.value = false
  }
}

function formatCurrency(value) {
  return new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value || 0))
}

function formatDuration(seconds) {
  if (seconds == null) return '—'
  const total = Math.max(0, Math.round(Number(seconds)))
  if (total < 60) return `${total}s`
  return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, '0')}s`
}

export function useModalUsage() {
  beginRealtime()
  const accounts = computed(() => snapshot.value?.accounts || [])
  const generations = computed(() => snapshot.value?.generations || [])
  const summary = computed(() => snapshot.value?.summary || {
    spent: 0,
    budget: 0,
    remaining: 0,
    active_jobs: 0,
    generation_count: 0,
  })
  const routing = computed(() => snapshot.value?.routing || {
    mode: 'auto',
    account_id: null,
    effective_account_id: null,
    fixed_account_valid: null,
    route_accounts_configured: [],
  })
  return {
    snapshot,
    accounts,
    generations,
    summary,
    routing,
    loading,
    error,
    routingSaving,
    routingError,
    refreshUsage,
    updateRouting,
    formatCurrency,
    formatDuration,
  }
}
