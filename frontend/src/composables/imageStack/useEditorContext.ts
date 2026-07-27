/**
 * An `EditorContext` backed by the op stack.
 *
 * The snapshot editor's plugin controls — crop with its aspect presets and
 * straighten, the whole annotate surface (curved arrows, neon, gradients,
 * stickers, text effects), retouch with its selection suite and brush engines,
 * finetune, filters, effects — are years of polish behind one narrow contract:
 * a flat `EditorState` in, `updateState(partial)` out. So v2 mounts THOSE
 * controls rather than re-authoring worse versions of them.
 *
 * What v2 changes is the document, not the controls. This adapter is the whole
 * translation:
 *
 *   plugin edits a field  →  routed to the op that owns that family of fields
 *   op params             →  presented back as a flat EditorState
 *
 * Which op owns which fields is the ONE piece of knowledge here:
 *
 *   crop / rotation / rotation90 / flipX / flipY  → the Crop step
 *   finetune + filter + effects fields            → the Develop step
 *   annotations / decorations / redactions / …    → the Annotate step
 *   retouchLayerData                              → a Retouch layer step
 *   selectionMaskData                             → the live selection, not a step
 *   everything else                               → tool settings, session-only
 *
 * That last bucket matters: most of `EditorState` is tool preferences (brush
 * settings, wand tolerance, text font, stroke colour). Those are not document
 * state and must never become steps.
 */

import { computed, reactive, ref, shallowRef, watch } from 'vue'
import { DEFAULT_EDITOR_STATE } from '@stimma/image-editor'
import { newOpId } from './opId'
import { developLabel } from './developSections'
import type { Op } from './types'

/** Fields that belong to the Crop step. */
const CROP_FIELDS = ['crop', 'rotation', 'rotation90', 'flipX', 'flipY'] as const

/** Fields that belong to the Develop step — finetune, filter and effects. */
const DEVELOP_FIELDS = [
  'brightness', 'contrast', 'saturation', 'exposure', 'temperature', 'gamma',
  'colorMatrix', 'filter',
  'blur', 'sharpen', 'noise', 'glow', 'pixelate', 'chromaticAberration',
  'motionBlur', 'motionBlurAngle', 'vignette', 'clarity',
  'splitToningEnabled', 'splitToningShadowHue', 'splitToningShadowSat',
  'splitToningHighlightHue', 'splitToningHighlightSat', 'splitToningBalance',
  'gradientMapEnabled', 'gradientMapShadowColor', 'gradientMapHighlightColor',
  'gradientMapIntensity',
  'colorIsolationEnabled', 'colorIsolationHue', 'colorIsolationRange',
  'colorIsolationFeather',
  'halftone', 'halftoneAngle', 'vhs', 'glitch', 'glitchBlockSize',
  'ditherEnabled', 'ditherPalette',
] as const

/** Fields that belong to the Annotate step. */
const ANNOTATE_FIELDS = ['annotations', 'decorations', 'redactions', 'stickers'] as const

const CROP_SET = new Set<string>(CROP_FIELDS)
const DEVELOP_SET = new Set<string>(DEVELOP_FIELDS)
const ANNOTATE_SET = new Set<string>(ANNOTATE_FIELDS)

export type OwningKind = 'crop' | 'develop' | 'annotate' | 'retouch' | 'session'

export function ownerOf(field: string): OwningKind {
  if (CROP_SET.has(field)) return 'crop'
  if (DEVELOP_SET.has(field)) return 'develop'
  if (ANNOTATE_SET.has(field)) return 'annotate'
  if (field === 'retouchLayerData') return 'retouch'
  return 'session'
}

export interface EditorContextDeps {
  /** The op stack document API. */
  stack: any
  /** The composite the active step applies to — the plugins' source image. */
  inputImage: () => HTMLImageElement | null
  inputCanvas: () => HTMLCanvasElement | null
  /** Re-render after a document edit. */
  render: () => void
  /** Hash of the active step's input, for baking pixel-reading layers. */
  inputHash: () => string
}

export function useEditorContext(deps: EditorContextDeps) {
  /**
   * Tool settings. Not document state: they persist across steps within a
   * session and never become ops.
   */
  const session = reactive<Record<string, any>>({ ...DEFAULT_EDITOR_STATE })

  /** The step each family is currently editing, created on first change. */
  const targets = reactive<Record<string, string | null>>({
    crop: null, develop: null, annotate: null, retouch: null,
  })

  /** Live selection — a value the next gesture consumes, never a step. */
  const selectionMask = shallowRef<HTMLCanvasElement | string | null>(null)

  const imageSize = ref<{ width: number; height: number } | null>(null)

  function opParams(kind: OwningKind): Record<string, any> {
    const opId = targets[kind]
    if (!opId) return {}
    const op = deps.stack.opById(opId)
    return (op as any)?.params || {}
  }

  /**
   * The flat state the plugins read: session tool settings, overlaid with the
   * params of whichever steps are currently being edited.
   */
  const state = computed<any>(() => ({
    ...session,
    imageSize: imageSize.value,
    src: null,
    ...opParams('crop'),
    ...opParams('develop'),
    ...opParams('annotate'),
    selectionMaskData: selectionMask.value,
  }))

  function labelFor(kind: OwningKind, params: Record<string, any>): string {
    if (kind === 'crop') return 'Crop'
    if (kind === 'annotate') return 'Annotate'
    if (kind === 'retouch') return 'Retouch'
    return developLabel(params)
  }

  function execFor(kind: OwningKind) {
    if (kind === 'crop') return { kind: 'crop' }
    if (kind === 'develop') return { kind: 'develop' }
    if (kind === 'annotate') return { kind: 'annotate' }
    return { kind: 'retouch' }
  }

  function classFor(kind: OwningKind): Op['class'] {
    return kind === 'crop' || kind === 'develop' ? 'parametric' : 'container'
  }

  /** Route one family's changed fields into its step, creating it if needed. */
  function applyToOp(kind: OwningKind, patch: Record<string, any>) {
    if (!Object.keys(patch).length) return
    const existing = targets[kind]

    if (!existing) {
      const opId = newOpId()
      const params = { ...patch }
      deps.stack.addOp({
        id: opId,
        class: classFor(kind),
        enabled: true,
        label: labelFor(kind, params),
        exec: execFor(kind),
        params,
        ...(kind === 'annotate' || kind === 'retouch'
          ? { blend: { feather_px: 0, opacity: 1 } }
          : {}),
      } as any)
      targets[kind] = opId
      return
    }

    // A drag is one undo step, not one per tick.
    const coalesceKey = `${kind}:${Object.keys(patch).sort().join(',')}`
    deps.stack.setParams(existing, patch, coalesceKey)
    const op = deps.stack.opById(existing)
    if (op && kind === 'develop') {
      deps.stack.setLabel(existing, developLabel((op as any).params || {}))
    }
  }

  /**
   * The plugins' only write path. Fields are grouped by which step owns them,
   * so one `updateState` touching crop AND colour lands as two steps rather
   * than one confused one.
   */
  function updateState(partial: Record<string, any>) {
    const grouped: Record<string, Record<string, any>> = {}

    for (const [field, value] of Object.entries(partial)) {
      const owner = ownerOf(field)
      if (owner === 'session') {
        session[field] = value
        continue
      }
      if (owner === 'retouch') {
        // The retouch layer is a raster payload, not a param — the caller
        // persists it and tells us the ref.
        continue
      }
      grouped[owner] = grouped[owner] || {}
      grouped[owner][field] = value
    }

    if ('selectionMaskData' in partial) selectionMask.value = partial.selectionMaskData

    for (const [kind, patch] of Object.entries(grouped)) {
      applyToOp(kind as OwningKind, patch)
    }
    if (Object.keys(grouped).length) deps.render()
  }

  /** End the session: the next change starts new steps. */
  function endSession() {
    targets.crop = null
    targets.develop = null
    targets.annotate = null
    targets.retouch = null
  }

  /** Re-enter an existing step so the plugin edits THAT one. */
  function enterOp(op: Op) {
    const kind = (op as any).exec?.kind
    if (kind === 'crop') targets.crop = op.id
    else if (kind === 'develop') targets.develop = op.id
    else if (kind === 'annotate') targets.annotate = op.id
    else if (kind === 'retouch' || kind === 'paint') targets.retouch = op.id
  }

  const context = computed(() => ({
    state: state.value,
    updateState,
    // The journal already records every document edit; the plugins' own
    // history calls have nothing to add.
    pushHistory: () => {},
    getCanvas: () => deps.inputCanvas(),
    getImageElement: () => deps.inputImage(),
    storagePrefix: 'image-stack',
    retouch: {
      clearSelection: () => { selectionMask.value = null },
      fillSelection: () => {},
      clearPixels: () => {},
      featherSelection: () => {},
      invertSelection: () => {},
      hasSelection: () => !!selectionMask.value,
    },
  }))

  watch(() => deps.inputCanvas(), canvas => {
    imageSize.value = canvas ? { width: canvas.width, height: canvas.height } : null
  }, { immediate: true })

  return { context, state, session, targets, selectionMask, updateState, endSession, enterOp }
}
