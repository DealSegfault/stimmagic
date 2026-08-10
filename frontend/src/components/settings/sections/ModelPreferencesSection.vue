<template>
  <div class="space-y-6">
    <section>
      <div class="mb-3">
        <div class="flex items-center gap-3">
          <h3 class="text-xs font-semibold text-content-secondary">Preferences</h3>
        </div>
      </div>

      <div class="mt-6 max-w-[680px]">
        <SettingRow label="Theme" description="How Stimma looks on this device.">
          <div class="flex items-center gap-1.5">
            <button
              v-for="option in THEME_OPTIONS"
              :key="option.value"
              @click="selectTheme(option.value)"
              class="flex items-center gap-1.5 px-3 h-8 rounded-md transition-colors duration-150 text-xs font-medium"
              :class="themePreference === option.value
                ? 'bg-accent/10 text-accent-hi'
                : 'text-content-tertiary hover:text-content hover:bg-overlay-subtle'"
            >
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" :d="option.icon" />
              </svg>
              {{ option.label }}
            </button>
          </div>
        </SettingRow>

        <SettingRow
          label="Show generation previews"
          description="Show in-progress frames on generating items, for tools that provide them. Turning this off also stops the tool from producing them."
          :divider="true"
        >
          <label class="relative inline-flex flex-shrink-0 cursor-pointer items-center">
            <input
              type="checkbox"
              :checked="showGenerationPreviews"
              @change="updateGenerationPreviewsSetting($event.target.checked)"
              class="sr-only peer"
            />
            <div class="w-9 h-5 bg-surface-hover peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-accent"></div>
          </label>
        </SettingRow>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useTheme } from '../../../composables/useTheme'
import { useSettingsApi } from '../../../composables/useSettingsApi'
import SettingRow from '../SettingRow.vue'
import { setGenerationPreviews } from '../../../appConfig'

// Theme
const { themePreference, setTheme } = useTheme()
const { updateTheme, fetchSettings, updateGenerationPreviews } = useSettingsApi()

// Live generation previews (global). This section owns no other settings
// payload, so it reads its own value on mount rather than threading the whole
// settings object through the modal.
const showGenerationPreviews = ref(true)
onMounted(async () => {
  try {
    const settings = await fetchSettings()
    showGenerationPreviews.value = settings?.show_generation_previews !== false
  } catch (err) {
    console.error('Failed to load generation previews setting:', err)
  }
})

function updateGenerationPreviewsSetting(enabled) {
  showGenerationPreviews.value = enabled
  // Apply immediately app-wide; tool descriptors carry only the provider
  // capability, so the setting is ANDed client-side.
  setGenerationPreviews(enabled)
  updateGenerationPreviews(enabled).catch(err => {
    console.error('Failed to persist generation previews setting:', err)
  })
}

const THEME_OPTIONS = [
  { value: 'light', label: 'Light', icon: 'M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z' },
  { value: 'dark', label: 'Dark', icon: 'M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z' },
  { value: 'system', label: 'System', icon: 'M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25A2.25 2.25 0 015.25 3h13.5A2.25 2.25 0 0121 5.25z' },
]

function selectTheme(theme) {
  setTheme(theme)
  // Fire-and-forget persist to server
  updateTheme(theme).catch(err => console.error('Failed to persist theme:', err))
}
</script>
