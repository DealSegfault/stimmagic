<script setup lang="ts">
/**
 * The active mode's editing surface: the snapshot editor's own canvas and its
 * own plugin controls, over the composite the active step applies to.
 *
 * This is the parity move. The old editor's crop handles, rule-of-thirds grid,
 * straighten, shape manipulation, text editing, selection suite and brush
 * engines are all in `EditorCanvas` and the plugin control components. Mounting
 * them here means the ergonomics ARE the old ones — not a reimplementation
 * that drifts and loses the polish.
 *
 * What differs from the old editor is only the input and the output: the source
 * image is the composite BELOW the active step rather than the original file,
 * and every change lands in that step rather than in one flat document.
 */
import { computed, ref } from 'vue'
import {
  EditorCanvas,
  CropControls,
  FinetuneControls,
  FilterControls,
  EffectsControls,
  AnnotateControls,
  RetouchControls,
  ToolSidebar,
  DEFAULT_VIEW_TRANSFORM,
} from '@stimma/image-editor'
import type { FamilyId } from '../../composables/imageStack/toolFamilies'

const props = defineProps<{
  family: FamilyId
  sub: string | null
  /** The EditorContext adapter — plugins read and write through this. */
  editor: any
  sourceImage: HTMLImageElement | null
  retouchCanvas?: HTMLCanvasElement | null
}>()

const emit = defineEmits<{ resize: [{ width: number; height: number }] }>()

const viewTransform = ref({ ...DEFAULT_VIEW_TRANSFORM })

/**
 * Which control surface the active family shows. Develop spans three of the
 * old plugins because the stack's user-facing unit is a develop session, not a
 * plugin tab — the sub-tool chooses which of the three is in front.
 */
const controls = computed(() => {
  if (props.family === 'crop') return [CropControls]
  if (props.family === 'annotate') return [AnnotateControls]
  if (props.family === 'select' || props.family === 'paint') return [RetouchControls]
  if (props.family === 'develop') {
    if (props.sub === 'colour') return [FilterControls]
    if (props.sub === 'effects') return [EffectsControls]
    if (props.sub === 'film') return [FilterControls, EffectsControls]
    return [FinetuneControls]
  }
  return []
})

/**
 * The plugin whose tool rail to show. Annotate and retouch are tool-driven —
 * the rail picks the tool, the panel configures it — so mounting the panel
 * without the rail leaves it empty.
 */
const railPlugin = computed(() => {
  if (props.family === 'annotate') return 'annotate'
  if (props.family === 'select' || props.family === 'paint') return 'retouch'
  return null
})

/**
 * Crop is the one mode that must see the WHOLE frame while it works — the
 * handles live outside the crop rectangle.
 */
const viewMode = computed(() => (props.family === 'crop' ? 'full' : 'crop'))
</script>

<template>
  <!-- `stimma-editor` scopes the plugin stylesheet; the wrapper classes are the
       ones EditorCanvas's own layout expects, so the stage sizes itself the way
       it does in the snapshot editor rather than collapsing. -->
  <div class="stimma-editor flex h-full min-h-0">
    <ToolSidebar
      v-if="railPlugin"
      :active-plugin="railPlugin"
      :editor-context="editor"
    />

    <div class="stimma-editor__canvas-wrapper flex-1 min-w-0 min-h-0">
      <EditorCanvas
        :state="editor.state"
        :view-transform="viewTransform"
        :source-image="sourceImage"
        :view-mode="viewMode"
        :retouch-canvas="retouchCanvas || null"
        @resize="emit('resize', $event)"
      />
    </div>

    <!-- The plugin's own panel, unchanged. -->
    <aside
      v-if="controls.length"
      class="stimma-editor__panel w-72 shrink-0 border-l border-edge-subtle overflow-y-auto custom-scrollbar"
    >
      <component
        v-for="(controlComponent, index) in controls"
        :key="index"
        :is="controlComponent"
        :editor="editor"
      />
    </aside>
  </div>
</template>
