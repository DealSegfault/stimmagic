<template>
  <main class="h-full overflow-y-auto custom-scrollbar bg-base">
    <div class="mx-auto max-w-[1280px] px-6 py-8 lg:px-10">
      <header class="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p class="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-hi">Infrastructure</p>
          <h1 class="text-2xl font-semibold tracking-tight text-content">Modal usage</h1>
          <p class="mt-1.5 max-w-2xl text-sm text-content-tertiary">
            Suivi des générations, des budgets et de la répartition entre tes workspaces Modal.
          </p>
          <a
            href="https://modal.com/pricing"
            target="_blank"
            rel="noreferrer"
            class="mt-2 inline-flex text-xs text-accent-hi transition-colors hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
          >
            Tarifs standards Modal ↗
          </a>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-md border border-edge-subtle bg-surface px-3 py-2 text-xs font-medium text-content-secondary transition-colors hover:border-edge hover:bg-overlay-subtle hover:text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
          :disabled="loading"
          @click="refreshUsage"
        >
          <svg class="h-3.5 w-3.5" :class="loading ? 'animate-spin' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 11a8.1 8.1 0 0 0-14.9-4L3 10m0-6v6h6M4 13a8.1 8.1 0 0 0 14.9 4L21 14m0 6v-6h-6" />
          </svg>
          Actualiser
        </button>
      </header>

      <section v-if="error" class="mb-6 rounded-lg border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-300" role="alert">
        {{ error }}
      </section>

      <section v-if="loading && !snapshot" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-busy="true" aria-label="Chargement de l’usage Modal">
        <div v-for="index in 4" :key="index" class="h-28 animate-pulse rounded-lg border border-edge-subtle bg-surface" />
      </section>

      <template v-else>
        <section class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Résumé d’utilisation">
          <article v-for="card in summaryCards" :key="card.label" class="rounded-lg border border-edge-subtle bg-surface px-4 py-4">
            <div class="flex items-center justify-between gap-3">
              <p class="text-xs text-content-tertiary">{{ card.label }}</p>
              <span class="text-content-muted" aria-hidden="true">{{ card.icon }}</span>
            </div>
            <p class="mt-3 text-2xl font-semibold tracking-tight text-content">{{ card.value }}</p>
            <p v-if="card.detail" class="mt-1 text-[11px] text-content-muted">{{ card.detail }}</p>
          </article>
        </section>

        <section class="mt-8 rounded-lg border border-edge-subtle bg-surface p-5" aria-labelledby="modal-routing-title">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 id="modal-routing-title" class="text-sm font-semibold text-content">Routage des générations</h2>
              <p class="mt-1 max-w-2xl text-xs leading-5 text-content-muted">
                Choisis le compte pour les prochains jobs. Les jobs déjà lancés restent sur leur GPU.
                Les credentials restent uniquement côté gateway.
              </p>
            </div>
            <span class="inline-flex items-center gap-1.5 rounded-full border border-edge-subtle px-2.5 py-1 text-[11px] text-content-secondary">
              <span class="h-1.5 w-1.5 rounded-full" :class="routingStatusDot" />
              {{ routingStatusLabel }}
            </span>
          </div>

          <div class="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <label class="flex cursor-pointer items-start gap-3 rounded-md border px-3.5 py-3 transition-colors" :class="selectedRoutingMode === 'auto' ? 'border-accent/60 bg-accent/5' : 'border-edge-subtle hover:border-edge'">
              <input v-model="selectedRoutingMode" type="radio" value="auto" class="mt-0.5 accent-accent" />
              <span>
                <span class="block text-xs font-medium text-content">Automatique</span>
                <span class="mt-1 block text-[11px] leading-4 text-content-muted">Répartit les jobs sur les comptes disponibles, selon la charge et le budget.</span>
              </span>
            </label>
            <label class="flex cursor-pointer items-start gap-3 rounded-md border px-3.5 py-3 transition-colors" :class="selectedRoutingMode === 'fixed' ? 'border-accent/60 bg-accent/5' : 'border-edge-subtle hover:border-edge'">
              <input v-model="selectedRoutingMode" type="radio" value="fixed" class="mt-0.5 accent-accent" />
              <span class="min-w-0 flex-1">
                <span class="block text-xs font-medium text-content">Compte fixe</span>
                <select
                  v-model="selectedAccountId"
                  :disabled="selectedRoutingMode !== 'fixed'"
                  class="mt-2 w-full rounded border border-edge-subtle bg-base px-2.5 py-1.5 text-xs text-content disabled:cursor-not-allowed disabled:opacity-50"
                  aria-label="Compte Modal fixe"
                >
                  <option v-for="account in accounts" :key="account.id" :value="account.id" :disabled="!account.route_configured">
                    {{ account.label }}{{ account.route_configured ? '' : ' — route non configurée' }}
                  </option>
                </select>
              </span>
            </label>
          </div>

          <div class="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p v-if="routingError" class="text-xs text-red-300" role="alert">{{ routingError }}</p>
            <p v-else class="text-[11px] text-content-muted">
              Compte effectif : <span class="text-content-secondary">{{ effectiveRoutingLabel }}</span>
            </p>
            <button
              type="button"
              class="inline-flex items-center gap-2 rounded-md bg-accent px-3 py-2 text-xs font-medium text-base transition-colors hover:bg-accent-hi disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="routingSaving || (selectedRoutingMode === 'fixed' && !selectedAccountId)"
              @click="saveRouting"
            >
              <span v-if="routingSaving" class="h-3 w-3 animate-spin rounded-full border-2 border-base/40 border-t-base" />
              {{ routingSaving ? 'Enregistrement…' : 'Appliquer au prochain job' }}
            </button>
          </div>
        </section>

        <section class="mt-8">
          <div class="mb-3 flex items-baseline justify-between gap-3">
            <div>
              <h2 class="text-sm font-semibold text-content">Comptes et budgets</h2>
              <p class="mt-1 text-xs text-content-muted">Les secrets restent côté backend.</p>
            </div>
            <span class="text-xs text-content-muted">{{ accounts.length }} compte{{ accounts.length > 1 ? 's' : '' }}</span>
          </div>

          <div v-if="accounts.length" class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <article v-for="account in accounts" :key="account.id" class="rounded-lg border border-edge-subtle bg-surface p-4">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <h3 class="truncate text-sm font-medium text-content">{{ account.label }}</h3>
                  <p class="mt-0.5 truncate font-mono text-[11px] text-content-muted">{{ account.workspace || account.id }}</p>
                </div>
                <span class="inline-flex items-center gap-1.5 text-[11px] text-content-secondary">
                  <span class="h-1.5 w-1.5 rounded-full" :class="account.status === 'available' ? 'bg-emerald-400' : 'bg-amber-400'" />
                  {{ account.status === 'available' ? 'Disponible' : 'Budget atteint' }}
                </span>
              </div>
              <div class="mt-5 flex items-end justify-between gap-4">
                <div>
                  <p class="text-xl font-semibold text-content">{{ formatCurrency(account.spent) }}</p>
                  <p class="mt-0.5 text-[11px] text-content-muted">sur {{ formatCurrency(account.monthly_budget) }} ce mois</p>
                  <p class="mt-1 text-[10px]" :class="account.spend_source === 'modal_billing' ? 'text-emerald-300' : 'text-content-muted'">
                    {{ account.spend_source === 'modal_billing' ? 'Facturation Modal synchronisée' : 'Estimation locale' }}
                  </p>
                </div>
                <p class="text-right text-xs text-content-secondary">{{ account.active_jobs }} actif{{ account.active_jobs > 1 ? 's' : '' }}<br><span class="text-content-muted">{{ account.max_concurrency }} simultané{{ account.max_concurrency > 1 ? 's' : '' }}</span></p>
              </div>
              <p class="mt-3 text-[11px] text-content-muted">{{ account.gpu_type }} · {{ formatCurrency(account.gpu_hour_price) }}/h · {{ account.memory_gib }} GiB</p>
              <p v-if="account.actual_spent != null" class="mt-1 text-[10px] text-content-muted">
                Générations suivies : {{ formatCurrency(account.estimated_spent) }} · total workspace : {{ formatCurrency(account.actual_spent) }}
              </p>
              <p class="mt-2 text-[11px]" :class="account.route_configured ? 'text-emerald-300' : 'text-amber-300'">
                {{ account.route_configured ? 'Route gateway configurée' : 'Route gateway non configurée' }}
              </p>
              <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-overlay-subtle" role="progressbar" :aria-valuenow="budgetPercent(account)" aria-valuemin="0" aria-valuemax="100" :aria-label="`Budget de ${account.label}`">
                <div class="h-full rounded-full bg-accent transition-all" :style="{ width: `${budgetPercent(account)}%` }" />
              </div>
              <p class="mt-2 text-[11px] text-content-muted">{{ formatCurrency(account.remaining) }} restant</p>
            </article>
          </div>

          <div v-else class="rounded-lg border border-dashed border-edge-subtle bg-surface/50 px-6 py-10 text-center">
            <h3 class="text-sm font-medium text-content">Aucun compte Modal configuré</h3>
            <p class="mx-auto mt-2 max-w-md text-xs leading-5 text-content-tertiary">
              Crée <code class="font-mono text-content-secondary">~/.config/adp-comfy/modal-router.accounts.json</code> ou définis <code class="font-mono text-content-secondary">MODAL_ROUTER_ACCOUNTS_FILE</code> côté backend pour afficher tes workspaces.
            </p>
          </div>
        </section>

        <section class="mt-8">
          <div class="mb-3 flex items-baseline justify-between gap-3">
            <div>
              <h2 class="text-sm font-semibold text-content">Générations récentes</h2>
              <p class="mt-1 text-xs text-content-muted">Les lignes sont estimées à partir de la durée et des ressources ; le total du workspace est synchronisé avec Modal lorsque le CLI est disponible.</p>
            </div>
            <span class="text-xs text-content-muted">{{ generations.length }} affichée{{ generations.length > 1 ? 's' : '' }}</span>
          </div>

          <div v-if="generations.length" class="overflow-hidden rounded-lg border border-edge-subtle bg-surface">
            <div class="overflow-x-auto">
              <table class="w-full min-w-[760px] text-left text-xs">
                <thead class="border-b border-edge-subtle bg-overlay-faint text-[10px] uppercase tracking-[0.12em] text-content-muted">
                  <tr>
                    <th class="px-4 py-3 font-medium">Génération</th>
                    <th class="px-4 py-3 font-medium">Compte</th>
                    <th class="px-4 py-3 font-medium">Modèle</th>
                    <th class="px-4 py-3 font-medium">Statut</th>
                    <th class="px-4 py-3 text-right font-medium">Durée</th>
                    <th class="px-4 py-3 text-right font-medium">Coût</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-edge-subtle">
                  <tr v-for="generation in generations" :key="`${generation.profile_id}-${generation.job_id}`" class="text-content-secondary">
                    <td class="px-4 py-3 font-mono text-[11px] text-content-muted">#{{ generation.job_id }}</td>
                    <td class="px-4 py-3">{{ accountLabel(generation.account_id) }}</td>
                    <td class="max-w-[220px] truncate px-4 py-3 text-content" :title="generation.model_name || ''">{{ generation.model_name || generation.task_type || '—' }}</td>
                    <td class="px-4 py-3"><span class="inline-flex items-center gap-1.5"><span class="h-1.5 w-1.5 rounded-full" :class="statusColor(generation.status)" />{{ statusLabel(generation.status) }}</span></td>
                    <td class="px-4 py-3 text-right tabular-nums">{{ formatDuration(generation.duration_seconds) }}</td>
                    <td class="px-4 py-3 text-right font-medium tabular-nums text-content">{{ formatCurrency(generation.actual_cost ?? generation.estimated_cost) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div v-else class="rounded-lg border border-dashed border-edge-subtle bg-surface/50 px-6 py-10 text-center" role="status">
            <h3 class="text-sm font-medium text-content">Pas encore de génération suivie</h3>
            <p class="mt-2 text-xs text-content-tertiary">Les prochaines générations apparaîtront ici automatiquement.</p>
          </div>
        </section>
      </template>
    </div>
  </main>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useModalUsage } from '../composables/useModalUsage'

const {
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
} = useModalUsage()

const selectedRoutingMode = ref('auto')
const selectedAccountId = ref(null)
const routingDirty = ref(false)
const routingHydrated = ref(false)

watch([selectedRoutingMode, selectedAccountId], () => {
  if (routingHydrated.value) routingDirty.value = true
})
watch(routing, (value) => {
  if (routingDirty.value) return
  selectedRoutingMode.value = value.mode || 'auto'
  selectedAccountId.value = value.account_id || value.route_accounts_configured?.[0] || accounts.value[0]?.id || null
  routingHydrated.value = true
}, { immediate: true })

onMounted(() => {
  refreshUsage().catch(() => {})
})

const summaryCards = computed(() => [
  { label: 'Dépensé ce mois', value: formatCurrency(summary.value.spent), detail: `${summary.value.generation_count} génération${summary.value.generation_count > 1 ? 's' : ''}`, icon: '$' },
  { label: 'Budget disponible', value: formatCurrency(summary.value.remaining), detail: `sur ${formatCurrency(summary.value.budget)}`, icon: '↗' },
  { label: 'Générations actives', value: String(summary.value.active_jobs), detail: 'tous workspaces confondus', icon: '◌' },
  { label: 'Dernière synchro', value: snapshot.value ? 'À jour' : '—', detail: snapshot.value ? new Date(snapshot.value.updated_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : '', icon: '↻' },
])

const routingStatusLabel = computed(() => {
  if (routing.value.mode === 'fixed' && routing.value.fixed_account_valid === false) return 'Route fixe indisponible'
  if (routing.value.mode === 'fixed') return `Fixe · ${accountLabel(routing.value.account_id)}`
  return 'Auto'
})

const routingStatusDot = computed(() => {
  if (routing.value.mode === 'fixed' && routing.value.fixed_account_valid === false) return 'bg-red-400'
  return routing.value.mode === 'fixed' ? 'bg-accent' : 'bg-emerald-400'
})

const effectiveRoutingLabel = computed(() => {
  if (routing.value.effective_account_id) return accountLabel(routing.value.effective_account_id)
  return routing.value.mode === 'auto' ? 'déterminé au lancement' : '—'
})

async function saveRouting() {
  try {
    await updateRouting(selectedRoutingMode.value, selectedAccountId.value)
    routingDirty.value = false
  } catch {
    // The composable exposes the actionable API error beside the button.
  }
}

function budgetPercent(account) {
  if (!account.monthly_budget) return 0
  return Math.min(100, Math.max(0, (account.spent / account.monthly_budget) * 100))
}

function accountLabel(id) {
  if (id === 'unassigned') return 'Non assigné'
  return accounts.value.find((account) => account.id === id)?.label || id || 'Non assigné'
}

function statusLabel(status) {
  return { queued: 'En attente', assigned: 'Assignée', processing: 'En cours', completed: 'Terminée', failed: 'Échec', cancelled: 'Annulée' }[status] || status
}

function statusColor(status) {
  return { queued: 'bg-sky-400', assigned: 'bg-sky-400', processing: 'bg-accent', completed: 'bg-emerald-400', failed: 'bg-red-400', cancelled: 'bg-amber-400' }[status] || 'bg-content-muted'
}
</script>
