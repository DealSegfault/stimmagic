<template>
  <div class="relative inline-flex items-center">
    <!-- Loupiote / Status Trigger Button -->
    <button
      type="button"
      class="group relative flex h-6 items-center gap-1.5 rounded-full px-1.5 py-0.5 transition-colors hover:bg-overlay-subtle"
      :title="tooltipText"
      @click.stop="isOpen = !isOpen"
    >
      <!-- Small Light (Loupiote) -->
      <span class="relative flex h-2.5 w-2.5 items-center justify-center">
        <span
          v-if="tunnelRunning"
          class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"
        />
        <span
          v-else-if="tunnelStarting"
          class="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75"
        />
        <span
          class="relative inline-flex h-2 w-2 rounded-full transition-colors"
          :class="tunnelRunning
            ? 'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.8)]'
            : (tunnelStarting ? 'bg-amber-400' : 'bg-rose-500/70')"
        />
      </span>

      <!-- Optional compact status pill text -->
      <span
        v-if="showLabel && tunnelRunning"
        class="font-mono text-[10px] font-medium text-emerald-400 uppercase tracking-wider"
      >
        Tunnel
      </span>
    </button>

    <!-- Popover Menu on click -->
    <div
      v-if="isOpen"
      ref="popoverRef"
      class="absolute left-0 top-full z-modal mt-1.5 w-72 overflow-hidden rounded-xl border border-edge bg-surface p-3 shadow-2xl transition-all"
    >
      <!-- Header -->
      <div class="flex items-center justify-between border-b border-edge-subtle pb-2">
        <div class="flex items-center gap-2">
          <span
            class="h-2 w-2 rounded-full"
            :class="tunnelRunning ? 'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.8)]' : 'bg-rose-500'"
          />
          <span class="text-xs font-bold text-content">
            Tunnel Cloudflare {{ tunnelRunning ? 'Actif' : 'Inactif' }}
          </span>
        </div>

        <button
          type="button"
          class="rounded p-1 text-content-muted hover:bg-overlay-light hover:text-content"
          @click="isOpen = false"
        >
          <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Body -->
      <div class="mt-2.5 space-y-2.5 text-xs">
        <!-- Active Tunnel State -->
        <template v-if="tunnelRunning && tunnelUrl">
          <div class="space-y-1">
            <label class="block text-[10px] font-medium uppercase tracking-wider text-content-muted">
              URL d'accès distant
            </label>
            <div class="rounded-md border border-edge bg-base px-2.5 py-1.5 font-mono text-[11px] text-content truncate select-all">
              {{ tunnelUrl }}
            </div>
          </div>

          <!-- Action Buttons -->
          <div class="flex items-center gap-1.5 pt-1">
            <button
              type="button"
              class="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-accent px-2.5 py-1.5 text-xs font-semibold text-accent-contrast shadow-sm hover:bg-accent-hover transition-colors"
              @click="handleShare"
            >
              <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="M7.217 10.907a2.25 2.25 0 1 0 0 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186 9.566-5.314m-9.566 7.5 9.566 5.314m0 0a2.25 2.25 0 1 0 3.935 2.186 2.25 2.25 0 0 0-3.935-2.186Zm0-12.814a2.25 2.25 0 1 0 3.933-2.185 2.25 2.25 0 0 0-3.933 2.185Z" />
              </svg>
              <span>AirDrop / Partager</span>
            </button>

            <button
              type="button"
              class="rounded-lg border border-edge bg-surface px-2.5 py-1.5 text-content-secondary hover:bg-overlay-light hover:text-content transition-colors"
              title="Copier l'URL"
              @click="copyTunnelUrl"
            >
              <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184" />
              </svg>
            </button>
          </div>
        </template>

        <!-- Inactive State -->
        <template v-else>
          <p class="text-[11px] text-content-muted leading-relaxed">
            Le tunnel Cloudflare est éteint. Activez-le pour partager votre instance ou la tester sur mobile.
          </p>
        </template>

        <!-- Toggle Button -->
        <button
          type="button"
          class="w-full rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors"
          :class="tunnelRunning
            ? 'border-rose-500/30 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20'
            : 'border-edge bg-surface-raised text-content hover:bg-overlay-light'"
          :disabled="tunnelStarting"
          @click="toggleTunnel"
        >
          {{ tunnelRunning ? 'Éteindre le tunnel' : (tunnelStarting ? 'Démarrage…' : 'Allumer le tunnel') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useTunnel } from '../composables/useTunnel'

const props = defineProps({
  showLabel: { type: Boolean, default: false }
})

const {
  tunnelRunning,
  tunnelStarting,
  tunnelUrl,
  startTunnel,
  stopTunnel,
  shareTunnelUrl,
  copyTunnelUrl
} = useTunnel()

const isOpen = ref(false)
const popoverRef = ref(null)

const tooltipText = computed(() => {
  if (tunnelRunning.value) return `Tunnel Cloudflare ACTIF : ${tunnelUrl.value || ''}`
  if (tunnelStarting.value) return 'Tunnel Cloudflare : Démarrage en cours…'
  return 'Tunnel Cloudflare : Inactif (cliquez pour gérer)'
})

async function toggleTunnel() {
  if (tunnelRunning.value) {
    await stopTunnel()
  } else {
    await startTunnel()
  }
}

async function handleShare() {
  await shareTunnelUrl()
}

function handleClickOutside(e) {
  if (isOpen.value && popoverRef.value && !popoverRef.value.contains(e.target) && !e.target.closest('.group')) {
    isOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>
