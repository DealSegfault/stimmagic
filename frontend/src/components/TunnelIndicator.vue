<template>
  <div class="relative inline-flex items-center">
    <!-- Loupiote / Status Trigger Button -->
    <button
      ref="triggerRef"
      type="button"
      class="group relative flex h-7 items-center gap-2 rounded-full border border-edge/60 bg-surface-raised/80 px-2 py-1 shadow-sm backdrop-blur-md transition-all hover:border-accent/40 hover:bg-overlay-light focus:outline-none focus-visible:ring-2 ring-accent/50 cursor-pointer"
      :title="tooltipText"
      @click.stop="togglePopover"
    >
      <!-- Small Glowing Light (Loupiote) -->
      <span class="relative flex h-2.5 w-2.5 items-center justify-center">
        <!-- Ping Animation when running or starting -->
        <span
          v-if="overallStatus === 'running'"
          class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"
        />
        <span
          v-else-if="overallStatus === 'starting' || overallStatus === 'partial'"
          class="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75"
        />
        <!-- Solid Dot -->
        <span
          class="relative inline-flex h-2 w-2 rounded-full transition-all duration-300"
          :class="{
            'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)]': overallStatus === 'running',
            'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.9)]': overallStatus === 'starting' || overallStatus === 'partial',
            'bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.6)]': overallStatus === 'stopped',
          }"
        />
      </span>

      <!-- Label -->
      <span class="font-mono text-[10px] font-semibold uppercase tracking-wider text-content-secondary group-hover:text-content">
        {{ statusBadgeLabel }}
      </span>

      <!-- Chevron -->
      <svg class="h-3 w-3 text-content-muted transition-transform group-hover:text-content" :class="{ 'rotate-180': isOpen }" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
      </svg>
    </button>

    <!-- Teleported Popover Dashboard (Avoids overflow-hidden / scroll clipping) -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-150 ease-out"
        enter-from-class="opacity-0 translate-y-1 scale-95"
        enter-to-class="opacity-100 translate-y-0 scale-100"
        leave-active-class="transition duration-100 ease-in"
        leave-from-class="opacity-100 translate-y-0 scale-100"
        leave-to-class="opacity-0 translate-y-1 scale-95"
      >
        <div
          v-if="isOpen"
          ref="popoverRef"
          :style="popoverStyle"
          class="fixed z-top w-84 overflow-hidden rounded-2xl border border-edge bg-surface/95 p-4 shadow-[0_12px_36px_rgba(0,0,0,0.6)] backdrop-blur-xl transition-all"
        >
          <!-- Header -->
          <div class="flex items-center justify-between border-b border-edge-subtle pb-3">
            <div class="flex items-center gap-2">
              <span
                class="h-2.5 w-2.5 rounded-full"
                :class="{
                  'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)]': overallStatus === 'running',
                  'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.9)]': overallStatus === 'starting' || overallStatus === 'partial',
                  'bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.6)]': overallStatus === 'stopped',
                }"
              />
              <span class="text-xs font-bold tracking-tight text-content">
                État des Modules & Services
              </span>
            </div>

            <div class="flex items-center gap-1">
              <button
                type="button"
                class="rounded-md p-1 text-content-muted hover:bg-overlay-light hover:text-content transition-colors"
                title="Actualiser l'état"
                @click="refreshAll"
              >
                <svg class="h-3.5 w-3.5" :class="{ 'animate-spin': isRefreshing }" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
                </svg>
              </button>
              <button
                type="button"
                class="rounded-md p-1 text-content-muted hover:bg-overlay-light hover:text-content transition-colors"
                @click="isOpen = false"
              >
                <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          <!-- Modules List -->
          <div class="mt-3 space-y-2.5 text-xs">
            <!-- Module 1: Passerelle Modal H3 & ComfyUI STP -->
            <div class="rounded-xl border border-edge/60 bg-base/60 p-3 transition-colors">
              <div class="flex items-start justify-between gap-2">
                <div class="space-y-0.5">
                  <div class="flex items-center gap-1.5 font-semibold text-content">
                    <span
                      class="h-2 w-2 rounded-full"
                      :class="gatewayRunning ? 'bg-emerald-400' : (gatewayStarting || gatewayPartial ? 'bg-amber-400 animate-pulse' : 'bg-rose-500')"
                    />
                    <span>Passerelle Modal H3</span>
                  </div>
                  <p class="text-[11px] text-content-muted">
                    {{ gatewayRunning ? 'Connecté (STP 8188 & Bridge 8190)' : (gatewayStarting ? 'Démarrage du superviseur…' : 'Arrêté — Génération H3 hors ligne') }}
                  </p>
                </div>

                <!-- Action Button -->
                <button
                  type="button"
                  class="flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-semibold transition-colors cursor-pointer"
                  :class="gatewayRunning
                    ? 'border border-rose-500/30 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20'
                    : 'border border-emerald-500/30 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25'"
                  :disabled="gatewayStarting"
                  @click="toggleGateway"
                >
                  <svg v-if="gatewayStarting" class="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <span>{{ gatewayRunning ? 'Arrêter' : (gatewayStarting ? 'En cours…' : 'Démarrer') }}</span>
                </button>
              </div>
            </div>

            <!-- Module 2: Tunnel Cloudflare -->
            <div class="rounded-xl border border-edge/60 bg-base/60 p-3 transition-colors">
              <div class="flex items-start justify-between gap-2">
                <div class="space-y-0.5">
                  <div class="flex items-center gap-1.5 font-semibold text-content">
                    <span
                      class="h-2 w-2 rounded-full"
                      :class="tunnelRunning ? 'bg-emerald-400' : (tunnelStarting ? 'bg-amber-400 animate-pulse' : 'bg-rose-500/60')"
                    />
                    <span>Tunnel Cloudflare</span>
                  </div>
                  <p class="text-[11px] text-content-muted">
                    {{ tunnelRunning ? 'Actif pour partage mobile/distant' : (tunnelStarting ? 'Ouverture du tunnel…' : 'Éteint (accès local uniquement)') }}
                  </p>
                </div>

                <!-- Action Button -->
                <button
                  type="button"
                  class="flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-semibold transition-colors cursor-pointer"
                  :class="tunnelRunning
                    ? 'border border-rose-500/30 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20'
                    : 'border border-edge bg-surface-raised text-content hover:bg-overlay-light'"
                  :disabled="tunnelStarting"
                  @click="toggleTunnel"
                >
                  <svg v-if="tunnelStarting" class="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <span>{{ tunnelRunning ? 'Éteindre' : (tunnelStarting ? 'En cours…' : 'Allumer') }}</span>
                </button>
              </div>

              <!-- Tunnel URL when running -->
              <div v-if="tunnelRunning && tunnelUrl" class="mt-2.5 space-y-1.5 pt-2 border-t border-edge-subtle">
                <div class="rounded-md border border-edge bg-surface px-2 py-1 font-mono text-[10px] text-content truncate select-all">
                  {{ tunnelUrl }}
                </div>
                <div class="flex items-center gap-1.5">
                  <button
                    type="button"
                    class="flex flex-1 items-center justify-center gap-1 rounded-md bg-accent px-2 py-1 text-[10px] font-semibold text-accent-contrast shadow-sm hover:bg-accent-hover transition-colors"
                    @click="handleShare"
                  >
                    <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M7.217 10.907a2.25 2.25 0 1 0 0 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186 9.566-5.314m-9.566 7.5 9.566 5.314m0 0a2.25 2.25 0 1 0 3.935 2.186 2.25 2.25 0 0 0-3.935-2.186Zm0-12.814a2.25 2.25 0 1 0 3.933-2.185 2.25 2.25 0 0 0-3.933 2.185Z" />
                    </svg>
                    <span>Partager</span>
                  </button>
                  <button
                    type="button"
                    class="rounded-md border border-edge bg-surface px-2 py-1 text-[10px] text-content-secondary hover:bg-overlay-light hover:text-content transition-colors"
                    title="Copier l'URL"
                    @click="copyTunnelUrl"
                  >
                    <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>

            <!-- Module 3: WebSocket STP & Serveur Local -->
            <div class="rounded-xl border border-edge/60 bg-base/60 p-3 transition-colors">
              <div class="flex items-center justify-between">
                <div class="space-y-0.5">
                  <div class="flex items-center gap-1.5 font-semibold text-content">
                    <span
                      class="h-2 w-2 rounded-full"
                      :class="wsConnected ? 'bg-emerald-400' : 'bg-rose-500'"
                    />
                    <span>Serveur & WebSocket Local</span>
                  </div>
                  <p class="text-[11px] text-content-muted">
                    {{ wsConnected ? 'Connecté (Port 9192 actif)' : 'Déconnecté du backend' }}
                  </p>
                </div>
                <span class="font-mono text-[10px] text-content-muted">Port 9192</span>
              </div>
            </div>
          </div>

          <!-- Quick Action: Tout Démarrer if any module stopped -->
          <div v-if="!gatewayRunning || !tunnelRunning" class="mt-3 pt-3 border-t border-edge-subtle">
            <button
              type="button"
              class="w-full rounded-xl bg-accent px-3 py-2 text-xs font-bold text-accent-contrast shadow hover:bg-accent-hover transition-colors flex items-center justify-center gap-2 cursor-pointer"
              @click="startAllModules"
            >
              <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 0 1 0 1.972l-11.54 6.347a1.125 1.125 0 0 1-1.667-.986V5.653Z" />
              </svg>
              <span>Démarrer tous les modules</span>
            </button>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, nextTick } from 'vue'
import { useTunnel } from '../composables/useTunnel'
import { useGateway } from '../composables/useGateway'
import { useWebSocket } from '../composables/useWebSocket'

const props = defineProps({
  showLabel: { type: Boolean, default: false }
})

const {
  tunnelRunning,
  tunnelStarting,
  tunnelUrl,
  fetchStatus: fetchTunnelStatus,
  startTunnel,
  stopTunnel,
  shareTunnelUrl,
  copyTunnelUrl
} = useTunnel()

const {
  gatewayRunning,
  gatewayPartial,
  gatewayStarting,
  fetchStatus: fetchGatewayStatus,
  startGateway,
  stopGateway
} = useGateway()

const { connected: wsConnected } = useWebSocket()

const isOpen = ref(false)
const isRefreshing = ref(false)
const triggerRef = ref(null)
const popoverRef = ref(null)
const popoverStyle = ref({})

const overallStatus = computed(() => {
  const isStarting = Boolean(gatewayStarting?.value || tunnelStarting?.value)
  if (isStarting) return 'starting'
  const isGwRunning = Boolean(gatewayRunning?.value)
  const isWsConn = Boolean(wsConnected?.value)
  if (isGwRunning && isWsConn) return 'running'
  if (isGwRunning || isWsConn || Boolean(gatewayPartial?.value)) return 'partial'
  return 'stopped'
})

const statusBadgeLabel = computed(() => {
  if (overallStatus.value === 'running') return 'En ligne'
  if (overallStatus.value === 'starting') return 'Lancement'
  if (overallStatus.value === 'partial') return 'Partiel'
  return 'Hors ligne'
})

const tooltipText = computed(() => {
  if (overallStatus.value === 'running') return 'Système et passerelle Modal H3 opérationnels (cliquez pour gérer)'
  if (overallStatus.value === 'starting') return 'Démarrage des services en cours…'
  return 'Modules arrêtés ou partiels (cliquez pour voir l’état et démarrer)'
})

function updatePopoverPosition() {
  if (!triggerRef.value) return
  const rect = triggerRef.value.getBoundingClientRect()
  popoverStyle.value = {
    top: `${rect.bottom + 8}px`,
    left: `${rect.left}px`,
  }
}

async function togglePopover() {
  isOpen.value = !isOpen.value
  if (isOpen.value) {
    await nextTick()
    updatePopoverPosition()
    await refreshAll()
  }
}

async function refreshAll() {
  isRefreshing.value = true
  await Promise.allSettled([
    fetchGatewayStatus?.(),
    fetchTunnelStatus?.(),
  ])
  setTimeout(() => {
    isRefreshing.value = false
  }, 400)
}

async function toggleGateway() {
  if (gatewayRunning.value) {
    await stopGateway()
  } else {
    await startGateway()
  }
}

async function toggleTunnel() {
  if (tunnelRunning.value) {
    await stopTunnel()
  } else {
    await startTunnel()
  }
}

async function startAllModules() {
  const tasks = []
  if (!gatewayRunning.value) tasks.push(startGateway())
  if (!tunnelRunning.value) tasks.push(startTunnel())
  await Promise.allSettled(tasks)
}

async function handleShare() {
  await shareTunnelUrl()
}

function handleClickOutside(e) {
  if (
    isOpen.value &&
    popoverRef.value &&
    !popoverRef.value.contains(e.target) &&
    triggerRef.value &&
    !triggerRef.value.contains(e.target)
  ) {
    isOpen.value = false
  }
}

function handleResize() {
  if (isOpen.value) {
    updatePopoverPosition()
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  window.addEventListener('resize', handleResize)
  window.addEventListener('scroll', handleResize, true)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('scroll', handleResize, true)
})
</script>
