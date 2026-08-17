<template>
  <div class="space-y-6">
    <!-- Section Title & Subtitle -->
    <div>
      <h3 class="text-base font-semibold text-content">Accès Distant & Tunnel Cloudflare</h3>
      <p class="mt-1 text-xs text-content-muted">
        Exposez temporairement votre instance locale en HTTPS sécurisé via <code class="rounded bg-overlay-faint px-1.5 py-0.5 font-mono text-[11px] text-content-secondary">cloudflared tunnel --url http://127.0.0.1:{{ tunnelPort }}</code>.
      </p>
    </div>

    <!-- Binary Missing Warning -->
    <div
      v-if="!tunnelInstalled"
      class="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-xs text-amber-200"
    >
      <div class="flex items-start gap-3">
        <svg class="h-5 w-5 flex-shrink-0 text-amber-400" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd" />
        </svg>
        <div class="space-y-1">
          <p class="font-semibold text-amber-300">L'exécutable <code class="font-mono">cloudflared</code> n'a pas été détecté.</p>
          <p class="text-content-muted">Installez Cloudflared sur votre machine avec la commande suivante dans votre terminal :</p>
          <div class="mt-2 rounded bg-black/40 px-2.5 py-1.5 font-mono text-[11px] text-content">
            brew install cloudflared
          </div>
        </div>
      </div>
    </div>

    <!-- Main Tunnel Control Card -->
    <div class="rounded-xl border border-edge bg-surface-raised/40 p-5 space-y-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <!-- Status Light Indicator -->
          <div class="relative flex h-4 w-4 items-center justify-center">
            <span
              class="absolute inline-flex h-full w-full rounded-full transition-opacity opacity-75"
              :class="tunnelRunning ? 'animate-ping bg-emerald-400' : (tunnelStarting ? 'animate-ping bg-amber-400' : 'bg-transparent')"
            />
            <span
              class="relative inline-flex h-3 w-3 rounded-full border border-surface shadow-sm"
              :class="tunnelRunning ? 'bg-emerald-500' : (tunnelStarting ? 'bg-amber-400 animate-pulse' : 'bg-rose-500')"
            />
          </div>

          <div>
            <div class="flex items-center gap-2">
              <span class="text-sm font-semibold text-content">
                {{ tunnelRunning ? 'Tunnel Actif' : (tunnelStarting ? 'Connexion en cours…' : 'Tunnel Inactif') }}
              </span>
              <span
                class="rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider"
                :class="tunnelRunning ? 'bg-emerald-500/15 text-emerald-400' : (tunnelStarting ? 'bg-amber-500/15 text-amber-400' : 'bg-overlay-subtle text-content-muted')"
              >
                {{ tunnelRunning ? 'HTTPS En Ligne' : (tunnelStarting ? 'Handshake' : 'Déconnecté') }}
              </span>
            </div>
            <p class="text-[11px] text-content-muted">
              {{ tunnelRunning ? 'Accessible depuis n’importe quel navigateur ou smartphone' : 'Aucun flux externe connecté' }}
            </p>
          </div>
        </div>

        <!-- Action Button (Start / Stop) -->
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold shadow-sm transition-all"
          :class="tunnelRunning
            ? 'border border-rose-500/30 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20'
            : 'bg-accent text-accent-contrast hover:bg-accent-hover disabled:opacity-40'"
          :disabled="tunnelStarting || !tunnelInstalled"
          @click="toggleTunnel"
        >
          <svg v-if="tunnelStarting" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <svg v-else-if="tunnelRunning" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M5.25 7.5A2.25 2.25 0 0 1 7.5 5.25h9a2.25 2.25 0 0 1 2.25 2.25v9a2.25 2.25 0 0 1-2.25 2.25h-9a2.25 2.25 0 0 1-2.25-2.25v-9Z" />
          </svg>
          <svg v-else class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 0 1 0 1.972l-11.54 6.347a1.125 1.125 0 0 1-1.667-.986V5.653Z" />
          </svg>
          <span>{{ tunnelRunning ? 'Arrêter le tunnel' : (tunnelStarting ? 'Démarrage…' : 'Démarrer le tunnel') }}</span>
        </button>
      </div>

      <!-- Live URL and Sharing Bar when running -->
      <div v-if="tunnelRunning && tunnelUrl" class="space-y-2 rounded-lg border border-edge bg-base/60 p-3">
        <div class="flex items-center justify-between text-[11px] text-content-secondary">
          <span class="font-medium">URL publique du tunnel :</span>
          <span class="font-mono text-[10px] text-content-muted">Port local {{ tunnelPort }}</span>
        </div>

        <div class="flex items-center gap-2">
          <input
            type="text"
            readonly
            :value="tunnelUrl"
            class="w-full rounded-md border border-edge bg-surface px-3 py-1.5 font-mono text-xs text-content focus:outline-none select-all"
            @click="$event.target.select()"
          />

          <!-- 1-Click AirDrop / Native Share -->
          <button
            type="button"
            class="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-accent-contrast hover:bg-accent-hover shadow-sm transition-colors whitespace-nowrap"
            title="Partager via AirDrop, Messages ou le menu natif"
            @click="shareTunnelUrl"
          >
            <!-- AirDrop / Share Icon -->
            <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M7.217 10.907a2.25 2.25 0 1 0 0 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186 9.566-5.314m-9.566 7.5 9.566 5.314m0 0a2.25 2.25 0 1 0 3.935 2.186 2.25 2.25 0 0 0-3.935-2.186Zm0-12.814a2.25 2.25 0 1 0 3.933-2.185 2.25 2.25 0 0 0-3.933 2.185Z" />
            </svg>
            <span>AirDrop / Partager</span>
          </button>

          <!-- Copy Button -->
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-md border border-edge bg-surface px-2.5 py-1.5 text-xs font-medium text-content-secondary hover:bg-overlay-light hover:text-content transition-colors whitespace-nowrap"
            title="Copier l'URL"
            @click="copyTunnelUrl"
          >
            <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184" />
            </svg>
            <span>Copier</span>
          </button>

          <!-- Open Link in new tab -->
          <a
            :href="tunnelUrl"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center justify-center rounded-md border border-edge bg-surface p-1.5 text-content-secondary hover:bg-overlay-light hover:text-content transition-colors"
            title="Ouvrir dans le navigateur"
          >
            <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
            </svg>
          </a>
        </div>
      </div>

      <!-- Error message if any -->
      <div v-if="tunnelError" class="rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-300">
        {{ tunnelError }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { useTunnel } from '../../../composables/useTunnel'

const {
  tunnelRunning,
  tunnelStarting,
  tunnelUrl,
  tunnelError,
  tunnelInstalled,
  tunnelPort,
  startTunnel,
  stopTunnel,
  shareTunnelUrl,
  copyTunnelUrl,
} = useTunnel()

function toggleTunnel() {
  if (tunnelRunning.value) {
    stopTunnel()
  } else {
    startTunnel()
  }
}
</script>
