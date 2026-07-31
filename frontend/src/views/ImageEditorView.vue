<script setup lang="ts">
/**
 * The image editor.
 *
 * The document is an ordered stack of ops over a base AssetRevision. Generative
 * steps submit through the existing job pipeline as context-owned candidates;
 * picking one composites client-side, taking only the pixels inside its mask.
 * Save materializes the composite as a new Revision — until then, nothing
 * outside this screen sees the stack (the rasterized-head invariant).
 *
 * Every step in the stack is a live parameter: reorderable, toggleable,
 * re-editable, with nothing pinning its position. There are no checkpoints and
 * no whole-image steps — a step that replaced the composite would occlude the
 * stack below it, which makes it a new base rather than a step, and new bases
 * belong to the version chain. The one operation that legitimately produces one
 * is the output stage's upscale, which runs at save.
 */
import { ref, computed, onMounted, onBeforeUnmount, onActivated, onDeactivated, watch, nextTick } from 'vue'
import axios from 'axios'
import {
  ArrowUturnLeftIcon,
  ArrowUturnRightIcon,
  ArrowsPointingInIcon,
  ChevronUpIcon,
  MinusIcon,
  PlusIcon,
} from '@heroicons/vue/24/outline'
import Button from '../components/ui/Button.vue'
import IconButton from '../components/ui/IconButton.vue'
import Tooltip from '../components/ui/Tooltip.vue'
import ConfirmDialog from '../components/ui/ConfirmDialog.vue'
import Spinner from '../components/ui/Spinner.vue'
import StatusDot from '../components/ui/StatusDot.vue'
import ImageCompareSlider from '../components/ImageCompareSlider.vue'
import BaseRow from '../imageEditor/components/BaseRow.vue'
import { DROP_LINE } from '../imageEditor/components/rowLayout'
import EditRow from '../imageEditor/components/EditRow.vue'
import EditorToolbar from '../imageEditor/components/EditorToolbar.vue'
import EditorSubbar from '../imageEditor/components/EditorSubbar.vue'
import StackPaintCanvas from '../imageEditor/components/StackPaintCanvas.vue'
import StackRetouchFeedback from '../imageEditor/components/StackRetouchFeedback.vue'
import StackSelectCanvas from '../imageEditor/components/StackSelectCanvas.vue'
import StackAnnotateCanvas from '../imageEditor/components/StackAnnotateCanvas.vue'
import OutputPanel from '../imageEditor/components/OutputPanel.vue'
import AdjustInspector from '../imageEditor/components/AdjustInspector.vue'
import AnnotationInspector from '../imageEditor/components/AnnotationInspector.vue'
import RetouchInspector from '../imageEditor/components/RetouchInspector.vue'
import ModelEditInspector from '../imageEditor/components/ModelEditInspector.vue'
import AnnotationIsland from '../imageEditor/components/AnnotationIsland.vue'
import SelectIsland from '../imageEditor/components/SelectIsland.vue'
import StackCropCanvas from '../imageEditor/components/StackCropCanvas.vue'
import ToolPicker from '../imageEditor/components/ToolPicker.vue'
import { useStackDocument, newOpId } from '../imageEditor/stack/useStackDocument'
import { useStackCandidates } from '../imageEditor/stack/useStackCandidates'
import { StackCompositor, stackHashes, canvasToBlob } from '../imageEditor/stack/useStackCompositor'
import {
  LiveAdjustPreview,
} from '../imageEditor/stack/liveAdjustPreview'
import type { AdjustmentValues } from '../imageEditor/stack/liveAdjustPreview'
import {
  headCacheHash,
  headCacheImageRef,
} from '../imageEditor/stack/headCache'
import { applyAnnotations } from '../imageEditor/stack/opExecutors'
import { useProvidersApi } from '../composables/useProvidersApi'
import { useMediaApi } from '../composables/useMediaApi'
import {
  nameStepFromCrop,
  regionCropBase64,
} from '../imageEditor/stack/nameStepFromRegion'
import { apiErrorMessage } from '../imageEditor/stack/errors'
import { DEFAULT_MASK_EXPAND_PERCENT, expandMaskCanvas } from '../imageEditor/stack/maskMorphology'
import { setEditorDirty } from '../imageEditor/stack/editorDirtyState'
import {
  readToolPrefs, writeToolPrefs, rememberSubTool,
  rememberedSubTool, rememberedIfValid,
} from '../imageEditor/stack/toolPrefs'
import { addRecentPrompt } from '../imageEditor/stack/promptHistory'
import {
  paintEngineSettings,
} from '../imageEditor/stack/paintEngineSettings'
import type {
  PaintEngineSettings, PaintRange,
} from '../imageEditor/stack/paintEngineSettings'
import { flattenWholeOps, hasWholeOps } from '../imageEditor/stack/flattenWholeOps'
import { blastRadius, deriveStackState, moveTargetForGap } from '../imageEditor/stack/stackState'
import { annotationBlockOrder } from '../imageEditor/stack/annotationBlockOrder'
import {
  finalResolutionFor, outputDimensions, outputLabel, outputOf, resampleLanczos,
} from '../imageEditor/stack/outputStage'
import {
  geometryBelow, coTransform, isIdentity, intersectsFrame, rewritePayload,
  transformShapes, multiply, applyToPoint, invert as invertMatrix,
  payloadToDocument as payloadToDocumentTransform,
} from '../imageEditor/stack/geometryTransform'
import type { Affine } from '../imageEditor/stack/geometryTransform'
import {
  DEFAULT_LINEAR_SOFTNESS,
  DEFAULT_RADIAL_FEATHER,
  gradientMaskCanvas,
  isGradientMask,
  transformGradientMask,
  withGradientSlider,
} from '../imageEditor/stack/regionMask'
import {
  combineAfterSelectionChange,
  selectionMatteAction,
} from '../imageEditor/stack/selectionLifecycle'
import { FragileEntryTracker } from '../imageEditor/stack/fragileEntries'
import {
  CROP_ASPECTS, cropRectForAspect, adjustLabel,
} from '../imageEditor/stack/adjustSections'
import { toneCurveHistogramFromCanvas } from '../imageEditor/stack/toneCurve'
import {
  familyById, TOOL_FAMILIES, SELECT_TOOLS, PAINT_ENGINES,
} from '../imageEditor/stack/toolFamilies'
import type { FamilyId, SelectionMode, SelectToolId } from '../imageEditor/stack/toolFamilies'
import { useSelection } from '../imageEditor/ported/useSelection'
import type {
  GenerativeOp,
  GradientMask,
  ModelReferenceImage,
  RetouchRegion,
  RetouchRegionKind,
  RetouchRegionSettings,
} from '../imageEditor/stack/types'
import { generateShapeId } from '../imageEditor/ported/shapes'
import type { AnnotateTool, Paint, Shape } from '../imageEditor/ported/shapeTypes'
import { textStyleOfShape, textStylePatch } from '../imageEditor/stack/textStyles'
import type { TextStyleId } from '../imageEditor/stack/textStyles'
import type { CropRect } from '../imageEditor/ported/useCropInteraction'
import {
  clampViewportPan,
  panForZoomAtPoint,
} from '../imageEditor/ported/viewportNavigation'
import { autoLevels, autoContrast, autoBalance } from '../imageEditor/ported/autoLevels'
import {
  FILTER_STRIP, AUTO_EDITS, levelEditById, stripEntryById, effectLookStepOf,
  photoAdjustmentRenderParams, photoAdjustmentGroup, PHOTO_ADJUSTMENT_CONTROLS,
} from '../imageEditor/stack/adjustSections'
import type { LevelEdit, StripEntry } from '../imageEditor/stack/adjustSections'
import { rgbToHslColor } from '../imageEditor/stack/pointColorMatch'
import { applyColorMatrix } from '../imageEditor/ported/colorMatrix'
import { FILTER_MATRICES } from '../imageEditor/ported/filterMatrices'
import { applyEffects } from '../imageEditor/ported/effects'
import { applyPhotographicAdjustments } from '../imageEditor/stack/photoAdjustments'
import type { BrushSettings } from '../imageEditor/ported/geometry'
import {
  copyModelReferenceImages,
  modelReferenceLimits,
  modelToolDefaults,
  sanitizeModelToolParams,
} from '../imageEditor/stack/modelToolParams'
import {
  REMOVE_COMPATIBLE_TASK_TYPES,
  removeCapableTools,
  removeRouteForTool,
} from '../imageEditor/stack/modelToolRouting'
import { isRunnableTool } from '../utils/toolHandoff'

const props = defineProps<{ assetId: string; revisionId?: string }>()

const stack = useStackDocument()
const { listAllTools } = useProvidersApi()
// <img> cannot send the X-Profile-ID header the profile middleware requires,
// which is why media URLs carry their database in the path.
const { getMediaFileUrl } = useMediaApi()

const loading = ref(true)
const error = ref<string | null>(null)
const baseInfo = ref<any>(null)
const initialToolPrefs = readToolPrefs()

/** Generate sub-tool modes. Repaint and Remove live under Retouch. */
type Mode = null | 'expand' | 'adjust' | 'crop'
const mode = ref<Mode>(null)
const candidateCount = ref(4)
/**
 * How far Remove/Repaint grow the mask past the selection edge at submit
 * (negative shrinks). Generation needs reach beyond the object or its outline
 * survives; the on-canvas selection itself stays exactly as drawn.
 */
const maskExpandPercent = ref(
  initialToolPrefs.maskExpandPercent ?? DEFAULT_MASK_EXPAND_PERCENT,
)
const selectedOpId = ref<string | null>(null)

const tools = ref<any[]>([])
const expandToolId = ref<string | null>(null)
const repaintToolId = ref<string | null>(null)
const removeToolId = ref<string | null>(null)
const cutoutToolId = ref<string | null>(null)
/** Session-owned defaults and edits, keyed by provider-scoped tool id. */
const modelToolParams = ref<Record<string, Record<string, any>>>({})
/** The open family and its active sub-tool. */
const family = ref<FamilyId | null>(null)
const sub = ref<string | null>(null)
const repaintPrompt = ref(initialToolPrefs.repaintPrompt ?? '')
const expandPrompt = ref(initialToolPrefs.expandPrompt ?? '')
/** Content-specific drafts; references never leak into Remove or across verbs. */
const repaintReferenceImages = ref<ModelReferenceImage[]>([])
const expandReferenceImages = ref<ModelReferenceImage[]>([])
const recentRepaintPrompts = ref([
  ...(initialToolPrefs.recentRepaintPrompts ?? []),
])
const prompt = computed({
  get: () =>
    family.value === 'retouch' && sub.value === 'repaint'
      ? repaintPrompt.value
      : expandPrompt.value,
  set: value => {
    if (family.value === 'retouch' && sub.value === 'repaint') {
      repaintPrompt.value = value
      writeToolPrefs({ repaintPrompt: value })
    } else {
      expandPrompt.value = value
      writeToolPrefs({ expandPrompt: value })
    }
  },
})
const referenceImages = computed<ModelReferenceImage[]>({
  get: () =>
    family.value === 'retouch' && sub.value === 'repaint'
      ? repaintReferenceImages.value
      : family.value === 'generate' && sub.value === 'expand'
        ? expandReferenceImages.value
        : [],
  set: value => {
    if (family.value === 'retouch' && sub.value === 'repaint') {
      repaintReferenceImages.value = value
    } else if (family.value === 'generate' && sub.value === 'expand') {
      expandReferenceImages.value = value
    }
  },
})
/** Expand grows the canvas and auto-masks the new border. */
const expandFactor = ref(1.25)
/**
 * Catalog tool picker for the active Generate sub-tool.
 *
 * The button set this and nothing rendered it, so clicking did nothing at all.
 * It uses the shared TaskTypeToolList, which is the same tool-and-provider row
 * that Send to tool and the rest of the app use — a second treatment for the
 * same list would be a second thing to keep in step.
 */
const toolPickerOpen = ref(false)
/** Where the trigger sits, so the menu opens under it rather than at the edge. */
const toolPickerLeft = ref(16)

/** Repaint and Expand share STP inpaint; Remove may use erase or inpaint. */
const activeTaskType = computed(() =>
  family.value === 'retouch' && sub.value === 'cutout'
    ? 'remove-background'
    : family.value === 'retouch' && sub.value === 'remove'
      ? 'erase-image'
      : 'inpaint-image'
)
const activeCompatibleTaskTypes = computed(() =>
  family.value === 'retouch' && sub.value === 'remove'
    ? [...REMOVE_COMPATIBLE_TASK_TYPES]
    : [activeTaskType.value]
)
const activeToolId = computed(() => {
  if (family.value === 'retouch' && sub.value === 'remove') return removeToolId.value
  if (family.value === 'retouch' && sub.value === 'repaint') return repaintToolId.value
  if (family.value === 'retouch' && sub.value === 'cutout') return cutoutToolId.value
  return expandToolId.value
})
const activeTool = computed(() =>
  tools.value.find(tool => tool.full_tool_id === activeToolId.value) ?? null
)
const activeToolLabel = computed(() => activeTool.value?.name ?? null)
const activeToolParamValues = computed(() =>
  activeToolId.value ? modelToolParams.value[activeToolId.value] ?? {} : {}
)
const activeReferenceLimits = computed(() =>
  family.value === 'retouch'
  && (sub.value === 'remove' || sub.value === 'cutout')
    ? { totalMin: 1, totalMax: 1, min: 0, max: 0 }
    : modelReferenceLimits(activeTool.value)
)

function ensureModelToolParams(tool: any) {
  if (!tool?.full_tool_id || modelToolParams.value[tool.full_tool_id]) return
  modelToolParams.value = {
    ...modelToolParams.value,
    [tool.full_tool_id]: modelToolDefaults(tool),
  }
}

function onOpenToolPicker(event: MouseEvent) {
  const button = event?.currentTarget as HTMLElement | undefined
  const host = (button?.closest('.flex-1') as HTMLElement) ?? null
  if (button && host) {
    toolPickerLeft.value =
      button.getBoundingClientRect().left - host.getBoundingClientRect().left
  }
  toolPickerOpen.value = !toolPickerOpen.value
}

function chooseTool(tool: any) {
  ensureModelToolParams(tool)
  if (family.value === 'retouch' && sub.value === 'remove') {
    removeToolId.value = tool.full_tool_id
    writeToolPrefs({ removeToolId: tool.full_tool_id })
  } else if (family.value === 'retouch' && sub.value === 'repaint') {
    repaintToolId.value = tool.full_tool_id
    writeToolPrefs({ repaintToolId: tool.full_tool_id })
  } else if (family.value === 'retouch' && sub.value === 'cutout') {
    cutoutToolId.value = tool.full_tool_id
    writeToolPrefs({ cutoutToolId: tool.full_tool_id })
  } else {
    expandToolId.value = tool.full_tool_id
    writeToolPrefs({ expandToolId: tool.full_tool_id })
  }
  toolPickerOpen.value = false
}

// -- selection --------------------------------------------------------------
//
// Selection is WORKSPACE state, not a mode. The model lives here — not in the
// overlay component — so it survives everything that unmounts the overlay
// (crop replaces the display box entirely). The rail on the left arms a tool;
// arming suspends the open family's pointer without ending its session.
const selModel = useSelection()
const selectRef = ref<InstanceType<typeof StackSelectCanvas> | null>(null)
/** The published mask: what consumers scope to. Kept in step with selModel. */
const selection = ref<HTMLCanvasElement | null>(null)
const armedSelectTool = ref<SelectToolId | null>(null)
const lastSelectTool = ref<SelectToolId>(
  (rememberedIfValid(
    readToolPrefs().selectTool,
    id => SELECT_TOOLS.some(tool => tool.id === id),
  ) as SelectToolId | undefined) ?? 'rect',
)
const selectCombine = ref<SelectionMode>('new')
const selectFeather = ref(0)
/** Magic wand extent and refinement settings. */
const selectTolerance = ref(8)
const selectSpread = ref(100)
const selectGrow = ref(0)
const selectAntialias = ref(true)
const selectBrushSize = ref(80)
/**
 * Falloff a NEW gradient starts with. Once one exists, the island slider edits
 * that gradient rather than this default — the ramp on the canvas is the thing
 * being tuned, and a slider that silently stopped affecting it would be a lie.
 */
const selectGradientSoftness = ref(DEFAULT_LINEAR_SOFTNESS)
const selectGradientFeather = ref(DEFAULT_RADIAL_FEATHER)
/**
 * The selection as created, anchored directly into permanent document space.
 * Its bitmap may be compact/current-frame storage, but every pixel has one
 * complete local → document affine. Crop and viewport geometry are projections
 * of that master, never part of its identity.
 */
let selectionMaster: HTMLCanvasElement | null = null
let selectionToDocument: Affine | null = null
/** What the live selection currently reflects, so sync is a no-op at rest. */
let selectionAppliedKey: string | null = null
/** Loading a saved mask into the palette must not immediately rewrite it. */
let suppressMaskedAdjustmentSync = false
/**
 * One-shot: a gradient gesture has just landed, so the raster mask the same
 * gesture publishes came from that ramp. Consumed by `onSelectionChange`,
 * which then keeps the geometry in `workspaceGradient` instead of treating
 * the selection as drawn pixels.
 */
let gradientGestureLanding = false
/**
 * The live selection's PARAMETRIC identity, when it has one: the whole
 * selection is a single un-combined gradient gesture. An Adjust click scopes
 * with this geometry — keeping the ramp's handles live on the step — instead
 * of freezing the rasterised copy. Any other gesture, combine, or geometry
 * change underneath falls back to the raster (`workspaceGradientKey` pins the
 * frame it was drawn in).
 */
let workspaceGradient: GradientMask | null = null
let workspaceGradientKey: string | null = null

// Retouch
const retouchRef = ref<InstanceType<typeof StackPaintCanvas> | null>(null)
const retouchOpId = ref<string | null>(null)
const retouchInput = ref<HTMLCanvasElement | null>(null)
const selectedRetouchRegionId = ref<string | null>(null)
const hoveredRetouchRegionId = ref<string | null>(null)
const selectedRetouchMask = ref<HTMLCanvasElement | null>(null)
const hoveredRetouchMask = ref<HTMLCanvasElement | null>(null)
const selectedRetouchSource = ref<{ x: number; y: number } | null>(null)
const selectedRetouchTarget = ref<{ x: number; y: number } | null>(null)
const hoveredRetouchSource = ref<{ x: number; y: number } | null>(null)
const hoveredRetouchTarget = ref<{ x: number; y: number } | null>(null)
const selectedRetouchIsPatch = ref(false)
const hoveredRetouchIsPatch = ref(false)
const hoveredRetouchOpId = ref<string | null>(null)
const allRetouchFeedback = ref<Array<{
  mask: HTMLCanvasElement
  source?: { x: number; y: number } | null
  target?: { x: number; y: number } | null
  isPatch?: boolean
}>>([])
const retouchBrush = ref<BrushSettings>(
  paintEngineSettings('heal', { brush: initialToolPrefs.retouchBrush }).brush
)

/** Retouch location feedback may be dismissed; a live selection may not. */
const selectedRetouchFeedbackVisible = ref(false)
const hasDismissibleCanvasFeedback = computed(() =>
  !!armedSelectTool.value || selectedRetouchFeedbackVisible.value
)

function dismissCanvasFeedback() {
  selectedRetouchFeedbackVisible.value = false
  disarmSelect()
}

function onViewportMatteClick(event: MouseEvent) {
  if (event.button !== 0) return
  if (annotateRef.value?.consumeCompletedGestureClick()) return
  // Empty matte means "nothing here". Give the click to the most visible
  // thing first: an existing pixel selection is deselected, without also
  // changing the selection tool the person deliberately chose. A second
  // empty-matte click, once there is no selection, releases that tool.
  selectedRetouchFeedbackVisible.value = false
  const action = selectionMatteAction(!!selection.value, !!armedSelectTool.value)
  if (action === 'clear-selection') clearSelection()
  else if (action === 'disarm-tool') disarmSelect()
  annotateRef.value?.clearSelection()
}

/**
 * Object Select owns the whole workspace, not only the image rectangle.
 *
 * Starting on the matte hands the same normalized (possibly out-of-bounds)
 * point to the annotation gesture. The overlay clips the marquee visually to
 * the image, while hit-testing counts every in-image shape the drag crosses.
 */
function onViewportMatteMouseDown(event: MouseEvent) {
  if (event.button !== 0 || spacePanHeld.value || annotateTool.value !== 'select') return
  annotateRef.value?.startMarqueeSelection(event)
}

// Paint
const paintRef = ref<InstanceType<typeof StackPaintCanvas> | null>(null)
const paintOpId = ref<string | null>(null)
const paintEngineId = ref(
  rememberedIfValid(
    initialToolPrefs.paintEngineId,
    id => PAINT_ENGINES.some(engine => engine.id === id && !engine.pending),
  ) ?? 'paint',
)
const paintSettingsByEngine = ref<Record<string, PaintEngineSettings>>(
  Object.fromEntries(PAINT_ENGINES.map(engine => [
    engine.id,
    paintEngineSettings(engine.id, initialToolPrefs.paintEngines?.[engine.id]),
  ])),
)

const activePaintSettings = computed(() =>
  paintSettingsByEngine.value[paintEngineId.value]
  ?? paintEngineSettings(paintEngineId.value),
)

let paintPrefsTimer: ReturnType<typeof setTimeout> | null = null

function persistPaintSettings() {
  if (paintPrefsTimer) clearTimeout(paintPrefsTimer)
  paintPrefsTimer = null
  writeToolPrefs({ paintEngines: paintSettingsByEngine.value })
}

function updateActivePaintSettings(patch: Partial<PaintEngineSettings>) {
  const engineId = paintEngineId.value
  paintSettingsByEngine.value = {
    ...paintSettingsByEngine.value,
    [engineId]: paintEngineSettings(engineId, {
      ...activePaintSettings.value,
      ...patch,
    }),
  }
  if (paintPrefsTimer) clearTimeout(paintPrefsTimer)
  paintPrefsTimer = setTimeout(persistPaintSettings, 150)
}

// Writable aliases keep the subbar and gesture surface simple while the actual
// values live in an independent, persisted record for every engine.
const paintBrush = computed<BrushSettings>({
  get: () => activePaintSettings.value.brush,
  set: value => updateActivePaintSettings({ brush: value }),
})
const paintColorRgb = computed({
  get: () => activePaintSettings.value.color,
  set: value => updateActivePaintSettings({ color: value }),
})
const paintExposure = computed({
  get: () => activePaintSettings.value.exposure,
  set: value => updateActivePaintSettings({ exposure: value }),
})
const paintRange = computed<PaintRange>({
  get: () => activePaintSettings.value.range,
  set: value => updateActivePaintSettings({ range: value }),
})
const paintStrength = computed({
  get: () => activePaintSettings.value.strength,
  set: value => updateActivePaintSettings({ strength: value }),
})
const paintSaturate = computed({
  get: () => activePaintSettings.value.saturate,
  set: value => updateActivePaintSettings({ saturate: value }),
})

// Annotate
const annotateRef = ref<InstanceType<typeof StackAnnotateCanvas> | null>(null)
const textStyle = ref<TextStyleId>('pill')
/**
 * The paint the next annotation starts with — a flat color or a gradient,
 * since a gradient is a color here and not a mode the shape is put into.
 */
const annotatePaint = ref<Paint>({ r: 255, g: 255, b: 255, a: 1 })
const selectedShapeId = ref<string | null>(null)
// The rest of the latent shape's initial conditions, sticky across shapes:
// stroke weight, fill, the universal effect and opacity all live in the
// sub-toolbar so a neon circle is one gesture, not draw-then-fix-three-knobs.
const annotateStrokeWidth = ref(8)
const annotateFillColor = ref<Paint | null>(null)
const annotateShapeEffect = ref<'none' | 'neon'>('none')
const annotateOpacity = ref(1)

/**
 * The sub-bar names a family of tools; the ported gesture code wants the
 * specific one. Shape and Text carry a second choice, so the mapping is not
 * one-to-one.
 */
const annotateTool = computed<AnnotateTool>(() => {
  // Outside the Annotate family the canvas only ever object-selects (the idle
  // state / island pointer); inside it, `sub = null` is select — where every
  // drawing tool lands after its one-shot creation.
  if (family.value !== 'annotate' || !sub.value) return 'select'
  if (sub.value === 'redact') return 'redact'
  if (sub.value === 'text') return 'text'
  if (sub.value === 'draw') return 'sharpie'
  if (sub.value === 'arrow') return 'arrow'
  if (sub.value === 'rectangle' || sub.value === 'ellipse' || sub.value === 'line') {
    return sub.value as AnnotateTool
  }
  return 'arrow'
})

/**
 * Object select is the workspace's IDLE state: with no family open and no
 * selection tool armed, the things you can click ARE the annotations, so
 * clicking one should just select it — no Annotate → Select → thing dance.
 * The island's pointer lights up to say so.
 */
const objectSelectActive = computed(() =>
  family.value === null && !armedSelectTool.value
)

/** The vector overlay currently owns annotation pixels and interactions. */
const annotationOverlayActive = computed(() =>
  family.value === 'annotate' || objectSelectActive.value
)

/** The island's pointer: leave whatever mode is open. Idle IS object select. */
function activatePointer() {
  disarmSelect()
  leaveMode()
}

/** The active Annotate step's shapes, or nothing until one exists. */
/**
 * One annotation, one step.
 *
 * An arrow and a text box are two things a user made and will want to reach
 * separately — to hide one, reorder it, or delete it without touching the
 * other. Accumulating them into a single 'Annotate' row made the stack lie
 * about how many edits there were and left no way to address any of them.
 * The rows are named for what they are: Rectangle, Text, Arrow.
 */
const annotateOps = computed(() =>
  (stack.doc.value?.edits || []).filter(op => (op as any).exec?.kind === 'annotate')
)

/**
 * The annotate ops the overlay is responsible for: the ENABLED ones.
 *
 * A hidden annotation is hidden everywhere. The overlay drawing it anyway left
 * a hidden shape on screen at full strength while the composite correctly
 * dropped it — so hiding a shape appeared to only weaken it (one of the two
 * copies went away) instead of removing it.
 */
const visibleAnnotateOps = computed(() => annotateOps.value.filter(op => op.enabled))

/** Permanent document shapes projected into the current head for interaction. */
const annotateShapes = computed<Shape[]>(() => {
  const doc = stack.doc.value
  if (!doc) return []
  const head = geometryBelow(doc, doc.edits.length)
  return visibleAnnotateOps.value.flatMap(op => {
    const anyOp = op as any
    const shapes = (anyOp.params?.shapes ?? []) as Shape[]
    if (!anyOp.shapes_in_document) return shapes
    return transformShapes(
      shapes,
      head.matrix,
      doc.canvas.width,
      doc.canvas.height,
      head.width,
      head.height,
    ) as Shape[]
  })
})

function opIdForShape(shapeId: string): string | null {
  const op = annotateOps.value.find(
    o => ((o as any).params?.shapes ?? []).some((s: Shape) => s.id === shapeId)
  )
  return op?.id ?? null
}

/** Rows read as what the user drew, not as the family they drew it in. */
function shapeLabel(shape: Shape): string {
  const type = shape.type === 'curved-arrow' ? 'arrow'
    : shape.type === 'path' ? 'drawing'
    : shape.type
  return type.charAt(0).toUpperCase() + type.slice(1)
}

// -- compositing -----------------------------------------------------------

const displayCanvas = ref<HTMLCanvasElement | null>(null)
const composite = ref<HTMLCanvasElement | null>(null)
const toneCurveHistogram = computed(() =>
  composite.value ? toneCurveHistogramFromCanvas(composite.value) : undefined,
)
const rendering = ref(false)
const viewportSize = ref({ width: 0, height: 0 })
const viewport = ref<HTMLElement | null>(null)

/** The image as of each step, keyed by op id — the Edits list's row previews. */
const stepPreviews = ref<Record<string, string>>({})

// Canvas snapshots can live here too. Paint rewrites a stable raster filename,
// and the immutable in-memory snapshot is a stronger source for the revision
// that just landed than asking WebKit to re-read an overwritten PNG.
const payloadCache = new Map<string, CanvasImageSource>()

function invalidatePayload(ref: string) {
  for (const key of payloadCache.keys()) {
    if (key.startsWith(`${ref}@`)) payloadCache.delete(key)
  }
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(`failed to load ${url}`))
    img.src = url
  })
}

async function loadStackPayload(ref: string, revision = 0) {
  const key = `${ref}@${revision}`
  const cached = payloadCache.get(key)
  if (cached) return cached
  const img = await loadImage(stack.payloadUrl(ref, revision))
  payloadCache.set(key, img)
  return img
}

async function loadStackBase() {
  // A flattened document supplies its own base pixels; everything else reads
  // the revision recorded by the recipe. The Asset's current revision may be
  // a flattened Save of this same stack and must never be substituted here.
  const ref = stack.doc.value?.base.payload_ref
  if (ref) return loadImage(stack.payloadUrl(ref))
  const mediaId = stack.doc.value?.base.media_id
  if (!mediaId) throw new Error('The image stack has no base media.')
  return loadImage(getMediaFileUrl(Number(mediaId)))
}

const compositor = new StackCompositor({
  loadPayload: loadStackPayload,
  loadBase: loadStackBase,
  onStepPreview: (opId, preview) => {
    // Only a render of the WHOLE document describes the steps truthfully; a
    // stage render with the annotate overlay's shapes held out would file
    // previews that are missing them.
    if (!emitPreviews) return
    if (bufferedStepPreviews) {
      bufferedStepPreviews[opId] = preview
      return
    }
    stepPreviews.value = { ...stepPreviews.value, [opId]: preview }
  },
})

/** Small, throwaway composites used only while a Retouch property is dragged. */
const retouchPreviewCompositor = new StackCompositor({
  loadPayload: loadStackPayload,
  loadBase: loadStackBase,
})

/**
 * Slider drags never replay the document. The pixels already on screen become
 * the preview baseline and a viewport-sized shader applies only the parameter
 * delta. Pointer-up performs the one authoritative source-resolution render.
 */
const liveAdjustPreview = new LiveAdjustPreview()
let liveAdjustOwner: string | null = null
let liveAdjustBase: AdjustmentValues = {}
let liveAdjustCurrent: AdjustmentValues = {}
let liveAdjustMask: HTMLCanvasElement | null = null
let liveAdjustFrame: number | null = null
let liveAdjustSetupRevision = 0
let liveAdjustReady = false

function cancelLiveAdjustPreview() {
  liveAdjustSetupRevision++
  if (liveAdjustFrame !== null) {
    cancelAnimationFrame(liveAdjustFrame)
    liveAdjustFrame = null
  }
  liveAdjustOwner = null
  liveAdjustBase = {}
  liveAdjustCurrent = {}
  liveAdjustMask = null
  liveAdjustReady = false
}

function drawLiveAdjustPreview() {
  liveAdjustFrame = null
  if (!liveAdjustReady) return
  const preview = liveAdjustPreview.render(liveAdjustCurrent)
  const target = displayCanvas.value
  if (!preview || !target) return
  target.width = preview.width
  target.height = preview.height
  const context = target.getContext('2d')!
  context.clearRect(0, 0, target.width, target.height)
  context.drawImage(preview, 0, 0)
}

function queueLiveAdjustFrame() {
  if (liveAdjustFrame !== null || !liveAdjustReady) return
  liveAdjustFrame = requestAnimationFrame(drawLiveAdjustPreview)
}

async function previewAdjustment(
  owner: string,
  base: AdjustmentValues,
  current: AdjustmentValues,
  options: {
    mask?: HTMLCanvasElement | null | Promise<HTMLCanvasElement | null>
    maskStrength?: number
  } = {},
) {
  liveAdjustCurrent = { ...current }
  if (liveAdjustOwner === owner && liveAdjustReady) {
    queueLiveAdjustFrame()
    return
  }
  if (liveAdjustOwner === owner) return

  cancelLiveAdjustPreview()
  liveAdjustOwner = owner
  liveAdjustBase = { ...base }
  liveAdjustCurrent = { ...current }
  const source = composite.value
  if (!source) return
  const revision = ++liveAdjustSetupRevision
  liveAdjustMask = options.mask ? await options.mask : null
  if (revision !== liveAdjustSetupRevision || liveAdjustOwner !== owner) return
  liveAdjustReady = liveAdjustPreview.begin(source, liveAdjustBase, {
    mask: liveAdjustMask,
    width: zoomedDisplayBox.value.width || displayBox.value.width,
    height: zoomedDisplayBox.value.height || displayBox.value.height,
    maskStrength: options.maskStrength,
  })
  queueLiveAdjustFrame()
}

/**
 * Restore the exact materialized head on a cold open. The recipe remains
 * authoritative; a missing hash-addressed PNG is simply a cache miss.
 */
async function restoreCachedHead(): Promise<boolean> {
  const doc = stack.doc.value
  if (!doc) return false
  // "Original image" is a trust boundary. When no edit contributes pixels,
  // always decode the immutable base; never let a persisted projection speak
  // for it, even if a cache file happens to have the same historical key.
  if (!doc.edits.some(op => op.enabled)) return false
  const hash = headCacheHash(doc)
  try {
    const image = await loadImage(stack.payloadUrl(headCacheImageRef(doc), hash))
    const restored = document.createElement('canvas')
    restored.width = image.naturalWidth
    restored.height = image.naturalHeight
    restored.getContext('2d')!.drawImage(image, 0, 0)
    compositor.prime(hash, restored, doc.edits.map(op => op.id))
    composite.value = restored
    return true
  } catch {
    return false
  }
}

let headCacheTimer: ReturnType<typeof setTimeout> | null = null
let headCacheRevision = 0
let headCacheWrite = Promise.resolve()

/**
 * Persist only after the person pauses. Lossless PNG encoding is deliberately
 * kept out of live slider and brush frames.
 */
function scheduleHeadCache(documentSnapshot: any, canvas: HTMLCanvasElement) {
  const revision = ++headCacheRevision
  const hash = headCacheHash(documentSnapshot)
  const name = `head-${hash}.png`
  if (headCacheTimer) clearTimeout(headCacheTimer)
  headCacheTimer = setTimeout(() => {
    headCacheTimer = null
    headCacheWrite = headCacheWrite.then(async () => {
      if (revision !== headCacheRevision || !stack.doc.value) return
      if (headCacheHash(stack.doc.value) !== hash) return
      await stack.uploadPayload(name, await canvasToBlob(canvas), 'cache')
    }).catch(cacheError => {
      // Cache loss changes only the next open's speed, never the document.
      console.warn('[imageStack] could not persist head cache', cacheError)
    })
  }, 1500)
}

/** Set only while rendering the full document — see onStepPreview. */
let emitPreviews = true
/** One reactive update per replay, not one per recomputed stack stage. */
let bufferedStepPreviews: Record<string, string> | null = null

type RenderOptions = {
  /**
   * Debounce destructive bursts while the rows update optimistically. Normal
   * renders use the next animation frame.
   */
  settleMs?: number
}

const RENDER_BURST_SETTLE_MS = 140
let renderRequested = false
let renderRunning = false
let renderRequestRevision = 0
let renderFrame: number | null = null
let renderTimer: ReturnType<typeof setTimeout> | null = null
let renderCycle: Promise<void> | null = null
let resolveRenderCycle: (() => void) | null = null

function ensureRenderCycle(): Promise<void> {
  if (!renderCycle) {
    renderCycle = new Promise(resolve => {
      resolveRenderCycle = resolve
    })
  }
  return renderCycle
}

function clearRenderSchedule() {
  if (renderFrame !== null) {
    cancelAnimationFrame(renderFrame)
    renderFrame = null
  }
  if (renderTimer) {
    clearTimeout(renderTimer)
    renderTimer = null
  }
}

function abandonScheduledRender() {
  clearRenderSchedule()
  renderRequested = false
  if (renderRunning) return
  const resolve = resolveRenderCycle
  resolveRenderCycle = null
  renderCycle = null
  resolve?.()
}

function scheduleRenderDrain(settleMs: number) {
  if (renderRunning) return

  if (settleMs > 0) {
    // An already scheduled animation-frame render is more urgent; do not turn
    // it into a delayed one. Repeated settled requests reset only each other.
    if (renderFrame !== null) return
    if (renderTimer) clearTimeout(renderTimer)
    renderTimer = setTimeout(() => {
      renderTimer = null
      void drainRenderQueue()
    }, settleMs)
    return
  }

  if (renderTimer) {
    clearTimeout(renderTimer)
    renderTimer = null
  }
  if (renderFrame !== null) return
  renderFrame = requestAnimationFrame(() => {
    renderFrame = null
    void drainRenderQueue()
  })
}

/**
 * The one doorway into full document rendering.
 *
 * Requests are coalesced, compositor work is serialized, and a render that
 * became stale while awaiting payloads may warm caches but cannot repaint the
 * UI over a newer document. Callers awaiting render wait until the queue has
 * reached the latest requested state.
 */
function render(options: RenderOptions = {}): Promise<void> {
  renderRequested = true
  renderRequestRevision++
  const cycle = ensureRenderCycle()
  scheduleRenderDrain(options.settleMs ?? 0)
  return cycle
}

/**
 * What the STAGE composites: the document, minus whatever a live overlay is
 * already drawing.
 *
 * While the annotation overlay is mounted, its canvas draws the enabled
 * annotations itself so they can be dragged, selected and restyled. This
 * includes the workspace's idle object-select state. Compositing them as
 * well drew every annotation twice — invisible for an opaque stroke, but a
 * neon glow compounds, so what you saw while editing was stronger than what
 * Save would write. The tool owns the layer it is editing; the stack renders
 * everything else. Save always flattens the real document (see save()).
 */
const displayDoc = computed(() => {
  const doc = stack.doc.value
  if (!doc || !annotationOverlayActive.value) return doc
  const drawnByOverlay = new Set(visibleAnnotateOps.value.map(op => op.id))
  if (!drawnByOverlay.size) return doc
  return { ...doc, edits: doc.edits.filter(op => !drawnByOverlay.has(op.id)) }
})

/** Drop previews for steps that no longer exist, so removals don't accumulate. */
function prunePreviews() {
  const live = new Set((stack.doc.value?.edits || []).map(op => op.id))
  const kept: Record<string, string> = {}
  for (const [opId, preview] of Object.entries(stepPreviews.value)) {
    if (live.has(opId)) kept[opId] = preview
  }
  stepPreviews.value = kept
}

async function renderSnapshot(requestRevision: number) {
  // Mutations can request a render before open() has assigned the base. The
  // later open path requests again once both halves are ready.
  if (!stack.doc.value || !baseInfo.value) return
  const liveDoc = displayDoc.value!
  const whole = liveDoc === stack.doc.value
  // The compositor awaits payloads. Snapshot the plain recipe so a mutation
  // arriving during that await cannot change the array underneath its loop.
  const doc = JSON.parse(JSON.stringify(liveDoc))
  bufferedStepPreviews = whole ? {} : null
  try {
    emitPreviews = whole
    const rendered = await compositor.render(doc)
    if (requestRevision !== renderRequestRevision) return
    composite.value = rendered
    if (whole && bufferedStepPreviews) {
      stepPreviews.value = { ...stepPreviews.value, ...bufferedStepPreviews }
    }
    if (whole) prunePreviews()
    if (
      whole
      && doc.edits.some((op: any) => op.enabled)
      && !compositor.failedOpIds.size
    ) {
      scheduleHeadCache(doc, rendered)
    }
    // The selection lives at the head, so whatever this render did to the
    // geometry under it (crop edits, toggles, an expand's new frame) is
    // carried into it here — the one funnel every such change passes through.
    syncSelectionGeometry()
    paint()
    samplePalette()
    if (family.value === 'filters') void renderFilterThumbs()
  } catch (err: any) {
    error.value = err?.message || 'Could not render the composite.'
  } finally {
    bufferedStepPreviews = null
    emitPreviews = true
  }
}

async function drainRenderQueue() {
  if (renderRunning) return
  clearRenderSchedule()
  renderRunning = true
  rendering.value = true
  try {
    while (renderRequested) {
      renderRequested = false
      const requestRevision = renderRequestRevision
      await renderSnapshot(requestRevision)
    }
  } finally {
    renderRunning = false
    rendering.value = false
    const resolve = resolveRenderCycle
    resolveRenderCycle = null
    renderCycle = null
    resolve?.()
    // A request cannot normally interleave with the synchronous cleanup above,
    // but keep the invariant explicit for future awaited teardown work.
    if (renderRequested) {
      ensureRenderCycle()
      scheduleRenderDrain(0)
    }
  }
}

/** Fit the composite into the viewport; the mask overlay uses the same box. */
/**
 * Fit the COMPOSITE into the viewport — not the document's base canvas.
 *
 * Geometry ops change the frame: a 16:9 base cropped square composites to a
 * square canvas. Fitting the base instead stretched that square back out to
 * 16:9, and because every overlay takes its size from this box, Select, Paint
 * and Annotate all drew into the same wrong aspect and their coordinates were
 * skewed with it.
 */
const displayBox = computed(() => {
  const doc = stack.doc.value
  const vp = viewportSize.value
  if (!doc || !vp.width || !vp.height) return { width: 0, height: 0 }
  const frame = composite.value ?? doc.canvas
  const scale = Math.min(vp.width / frame.width, vp.height / frame.height, 1)
  return {
    width: Math.round(frame.width * scale),
    height: Math.round(frame.height * scale),
  }
})

// -- viewport navigation ---------------------------------------------------

/**
 * Zoom is relative to the fitted view, matching the slideshow: 100% means
 * "fit/actual size, whichever is smaller". The image and every interactive
 * overlay share the zoomed display box, so their coordinate systems stay
 * locked; pan is the one CSS transform shared by the whole stage.
 */
const MIN_VIEW_ZOOM = 1
const MAX_VIEW_ZOOM = 10
const viewZoom = ref(1)
const viewPan = ref({ x: 0, y: 0 })
const viewPanning = ref(false)
const spacePanHeld = ref(false)
let viewPanStart = { pointerX: 0, pointerY: 0, panX: 0, panY: 0 }

const viewZoomLabel = computed(() => `${Math.round(viewZoom.value * 100)}%`)
const viewTransformStyle = computed(() => ({
  transform:
    `translate(calc(-50% + ${viewPan.value.x}px), calc(-50% + ${viewPan.value.y}px))`,
}))
const zoomedDisplayBox = computed(() => ({
  width: Math.round(displayBox.value.width * viewZoom.value),
  height: Math.round(displayBox.value.height * viewZoom.value),
}))

/** Crop owns a viewport-sized stage; every other family owns the fitted box. */
const viewContentSize = computed(() =>
  family.value === 'crop' ? viewportSize.value : displayBox.value
)

function clampViewPan() {
  viewPan.value = clampViewportPan(
    viewPan.value,
    viewZoom.value,
    viewContentSize.value,
    viewportSize.value,
  )
}

function resetView() {
  viewZoom.value = MIN_VIEW_ZOOM
  viewPan.value = { x: 0, y: 0 }
}

function setViewZoom(nextZoom: number, anchor?: { x: number; y: number }) {
  const clamped = Math.max(MIN_VIEW_ZOOM, Math.min(MAX_VIEW_ZOOM, nextZoom))
  if (clamped === viewZoom.value) return
  if (anchor) {
    viewPan.value = panForZoomAtPoint(viewPan.value, viewZoom.value, clamped, anchor)
  }
  viewZoom.value = clamped
  clampViewPan()
}

function zoomViewBy(direction: 1 | -1) {
  const factor = direction > 0 ? 1.25 : 1 / 1.25
  setViewZoom(viewZoom.value * factor)
}

function onViewportWheel(event: WheelEvent) {
  const element = viewport.value
  if (!element) return
  const rect = element.getBoundingClientRect()
  const anchor = {
    x: event.clientX - rect.left - rect.width / 2,
    y: event.clientY - rect.top - rect.height / 2,
  }
  const factor = event.deltaY > 0 ? 0.9 : 1.1
  setViewZoom(viewZoom.value * factor, anchor)
}

/**
 * Left drag belongs to the active image tool. Middle-drag mirrors slideshow,
 * while Space+left-drag is the editor-safe equivalent available in every tool.
 */
function startViewPan(event: PointerEvent) {
  const isMiddleButton = event.button === 1
  const isSpaceDrag = event.button === 0 && spacePanHeld.value
  if (!isMiddleButton && !isSpaceDrag) return

  viewPanning.value = true
  viewPanStart = {
    pointerX: event.clientX,
    pointerY: event.clientY,
    panX: viewPan.value.x,
    panY: viewPan.value.y,
  }
  viewport.value?.setPointerCapture(event.pointerId)
  event.preventDefault()
  event.stopPropagation()
}

function moveViewPan(event: PointerEvent) {
  if (!viewPanning.value) return
  viewPan.value = {
    x: viewPanStart.panX + event.clientX - viewPanStart.pointerX,
    y: viewPanStart.panY + event.clientY - viewPanStart.pointerY,
  }
  clampViewPan()
  event.preventDefault()
  event.stopPropagation()
}

function endViewPan(event: PointerEvent) {
  if (!viewPanning.value) return
  if (viewport.value?.hasPointerCapture(event.pointerId)) {
    viewport.value.releasePointerCapture(event.pointerId)
  }
  viewPanning.value = false
  event.preventDefault()
  event.stopPropagation()
}

function paint() {
  const target = displayCanvas.value
  const source = composite.value
  if (!target || !source) return
  // Assigning either canvas dimension reallocates and clears its full backing
  // store. Most renders keep the same geometry, so only resize when a crop or
  // expand actually changed it.
  if (target.width !== source.width || target.height !== source.height) {
    target.width = source.width
    target.height = source.height
  }
  const ctx = target.getContext('2d')!
  ctx.clearRect(0, 0, target.width, target.height)
  ctx.drawImage(source, 0, 0, target.width, target.height)
}

// -- candidates ------------------------------------------------------------

const candidates = useStackCandidates({
  documentId: () => stack.documentId.value,
  uploadPayload: stack.uploadPayload,
  attachCandidates: stack.attachCandidates,
  mediaFileUrl: (mediaId: number) => getMediaFileUrl(mediaId),
  onFirstCandidate: (opId, candidate) => {
    // A staged op with no pick contributes nothing, so the first arrival
    // auto-applies. Switching to another candidate afterwards is free.
    //
    // A RESAMPLED op always has a pick — that is what makes it a resample — so
    // the arrival replaces it. Without this the run completes, the candidate is
    // attached, and the canvas never changes: a paid click with no effect.
    const op = stack.opById(opId) as GenerativeOp | undefined
    const resampled = resampledOpIds.value.has(opId)
    if (op && (!op.picked || resampled)) stack.pickCandidate(opId, candidate.id)
    if (resampled) {
      const next = new Set(resampledOpIds.value)
      next.delete(opId)
      resampledOpIds.value = next
    }
    void render()
  },
})

const pendingByOp = computed(() => {
  const counts: Record<string, number> = {}
  for (const job of candidates.pending.value) {
    if (job.status === 'failed') continue
    counts[job.opId] = (counts[job.opId] || 0) + 1
  }
  return counts
})

const candidateThumbs = computed(() => {
  const thumbs: Record<string, Array<{ id: string; url: string }>> = {}
  for (const op of stack.ops.value) {
    const anyOp = op as any
    if (!anyOp.candidates?.length) continue
    thumbs[op.id] = anyOp.candidates
      .filter((c: any) => c.patch_ref)
      .map((c: any) => ({ id: c.id, url: stack.payloadUrl(c.patch_ref) }))
  }
  return thumbs
})

// -- derived stack state ----------------------------------------------------

/** Staleness is DERIVED, never stored. */
const stackState = computed(() => deriveStackState(stack.doc.value))

/** Which rows the currently hovered gesture would disturb. */
const intentOpId = ref<string | null>(null)
const preview = computed(() =>
  intentOpId.value ? blastRadius(stack.doc.value, intentOpId.value) : null
)
function previewStalenessOf(opId: string) {
  if (!preview.value) return null
  return preview.value.advisory.has(opId) ? ('advisory' as const) : null
}

/**
 * Rows the list shows, top-first. Every step is visible: nothing folds anything
 * any more, because nothing consumes anything.
 */
const visibleRows = computed(() => [...stackState.value.ops].reverse())

/** A payload whose geometry has moved it entirely off the frame. */
const outOfFrame = computed(() => {
  const doc = stack.doc.value
  const result: Record<string, boolean> = {}
  if (!doc) return result
  for (let index = 0; index < doc.edits.length; index++) {
    const op = doc.edits[index] as any
    if (!op.mask_ref && !op.raster_ref) continue
    const geometry = geometryBelow(doc, index)
    const canonical = (op.payload_to_document as Affine | undefined)
      ?? (op.payload_frame
        ? payloadToDocumentTransform(op.payload_frame) ?? undefined
        : undefined)
    const matrix = canonical
      ? multiply(geometry.matrix, canonical)
      : geometry.matrix
    result[op.id] = !intersectsFrame(
      matrix,
      op.payload_frame?.width ?? doc.canvas.width,
      op.payload_frame?.height ?? doc.canvas.height,
      geometry.width, geometry.height
    )
  }
  return result
})

// -- reorder ----------------------------------------------------------------

/**
 * Reorder is drag, and a drag must never be a guess.
 *
 * The whole gesture is expressed in GAPS, not rows: a gap `g` is the boundary
 * below edits[g] — the place the row would land. Hovering the top half of a
 * row targets the gap above it, the bottom half the gap below it, so every
 * pixel of the list belongs to exactly one landing place and the indicator
 * says which. Dropping ON a row (the old behaviour) could not express "above
 * or below", which is what made the drop feel like a coin flip.
 *
 * The list is drawn top-of-stack-first, so the gap ABOVE visible row i is
 * doc index i + 1.
 */
const dragOpId = ref<string | null>(null)
/** Gap the drop would land in, or null when there is no legal target. */
const dropGap = ref<number | null>(null)

/** The lowest visible row, whose bottom edge is the list's last gap. */
const lastVisibleIndex = computed(() =>
  visibleRows.value.length ? visibleRows.value[visibleRows.value.length - 1].index : null
)

function onDragStart(opId: string, event: DragEvent) {
  dragOpId.value = opId
  intentOpId.value = opId
  event.dataTransfer?.setData('text/plain', opId)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function onListDragOver(event: DragEvent) {
  const doc = stack.doc.value
  const source = dragOpId.value
  if (!doc || !source) return

  const row = (event.target as HTMLElement | null)?.closest?.('[data-op-id]') as HTMLElement | null
  const targetOpId = row?.dataset.opId
  const index = targetOpId ? doc.edits.findIndex(op => op.id === targetOpId) : -1
  if (!row || index < 0) {
    // Over the list's padding: no landing place, so no line. A line left
    // behind from the last row would be a lie.
    dropGap.value = null
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'none'
    return
  }

  const box = row.getBoundingClientRect()
  const gap = event.clientY < box.top + box.height / 2 ? index + 1 : index

  const legal = moveTargetForGap(doc, source, gap) !== null
  dropGap.value = legal ? gap : null
  // Say so on the cursor too: a line that simply isn't there reads as "not
  // hovering anything", not as "this move is blocked".
  if (event.dataTransfer) event.dataTransfer.dropEffect = legal ? 'move' : 'none'
}

/** Leaving the list entirely clears the line; moving between rows does not. */
function onListDragLeave(event: DragEvent) {
  const to = event.relatedTarget as Node | null
  const list = event.currentTarget as HTMLElement
  if (!to || !list.contains(to)) dropGap.value = null
}

function onDragEnd() {
  dragOpId.value = null
  dropGap.value = null
  intentOpId.value = null
}

async function onDrop() {
  const doc = stack.doc.value
  const source = dragOpId.value
  const gap = dropGap.value
  onDragEnd()
  if (!doc || !source || gap === null) return

  const toIndex = moveTargetForGap(doc, source, gap)
  if (toIndex === null) return

  const before = JSON.parse(JSON.stringify(doc))
  stack.moveOp(source, toIndex)
  await afterGeometryChange(before)
  void render()
}

// -- geometry co-transform ---------------------------------------------------

/**
 * Geometry changes never rewrite spatial payloads. Their permanent document
 * anchors make the compositor's projection authoritative.
 *
 * The only work left here is a one-time conversion of legacy annotation
 * vectors, which predate document-space storage.
 */
async function afterGeometryChange(before: any) {
  const doc = stack.doc.value
  if (!doc) return
  const hasGeometry = doc.edits.some(
    op => op.class === 'parametric' && (op as any).exec?.kind === 'crop'
  ) || before.edits.some(
    (op: any) => op.class === 'parametric' && op.exec?.kind === 'crop'
  )
  if (!hasGeometry) return

  for (let index = 0; index < doc.edits.length; index++) {
    const op = doc.edits[index] as any
    const shapes = op.exec?.kind === 'annotate' && !op.shapes_in_document
      ? op.params?.shapes ?? []
      : []
    if (!shapes.length) continue

    const previousIndex = before.edits.findIndex((candidate: any) => candidate.id === op.id)
    if (previousIndex < 0) continue

    const oldGeometry = geometryBelow(before, previousIndex)
    const documentFromOld = invertMatrix(oldGeometry.matrix)
    if (!documentFromOld) continue
    op.shapes_in_document = true
    op.params = {
      ...(op.params || {}),
      shapes: transformShapes(
        shapes,
        documentFromOld,
        oldGeometry.width,
        oldGeometry.height,
        doc.canvas.width,
        doc.canvas.height,
      ),
    }
    // Compatibility normalization is not a user gesture and must not add a
    // second Undo entry beside the crop move that exposed it.
    stack.touchOp(op.id)
  }
}

/**
 * The geometry a payload is being created in — its anchor.
 *
 * Stored on the op so the payload's pixels stay addressable in the ORIGINAL
 * image's coordinates no matter what happens to the crops below it. The
 * compositor carries it forward with `M_now ∘ M_created⁻¹`; without it there
 * is nothing to translate through, and a crop removed after the fact leaves
 * the payload at coordinates that meant something in a frame that is gone.
 *
 * `index` is where the op sits, or the top of the stack for one about to be
 * appended.
 */
function payloadFrame(index?: number) {
  const doc = stack.doc.value
  if (!doc) return undefined
  const at = index ?? doc.edits.length
  const geometry = geometryBelow(doc, at)
  return { matrix: geometry.matrix, width: geometry.width, height: geometry.height }
}

/**
 * Complete local-payload → permanent-document transform.
 *
 * Compact origins are folded in here at creation. No renderer is allowed to
 * recover position later from an authored frame plus a separate offset.
 */
function payloadTransform(
  index?: number,
  origin: [number, number] = [0, 0],
): Affine | undefined {
  const frame = payloadFrame(index)
  if (!frame) return undefined
  return payloadToDocumentTransform(frame, origin) ?? undefined
}

/**
 * Remove or disable a step, co-transforming anything above it.
 *
 * Dropping a crop is a geometry change exactly like adding one: every mask,
 * raster layer and annotation above it was authored in the cropped frame and
 * has to be carried back into the uncropped one, or it lands somewhere the
 * user never put it. Toggling a crop's eye is the same change, reversibly.
 */
async function removeOpWithGeometry(opId: string) {
  const removed = stack.opById(opId) as any
  const removedRegionIds = new Set<string>(
    removed?.exec?.kind === 'retouch-regions'
      ? (removed.regions ?? []).map((region: RetouchRegion) => region.id)
      : [],
  )
  if (
    (selectedRetouchRegionId.value && removedRegionIds.has(selectedRetouchRegionId.value))
    || (hoveredRetouchRegionId.value && removedRegionIds.has(hoveredRetouchRegionId.value))
  ) {
    selectedRetouchRegionId.value = null
    hoveredRetouchRegionId.value = null
    selectedRetouchFeedbackVisible.value = false
    void refreshRetouchFeedback()
  }
  if (hoveredRetouchOpId.value === opId) {
    hoveredRetouchOpId.value = null
    allRetouchFeedback.value = []
    allRetouchFeedbackRevision++
  }
  if (retouchOpId.value === opId) resetRetouchSession()
  const before = JSON.parse(JSON.stringify(stack.doc.value))
  stack.removeOp(opId)
  if (opId === cropOpId.value) cropOpId.value = null
  await afterGeometryChange(before)
  // The row disappears synchronously. Let a quick run of trash clicks settle
  // before touching full-resolution pixels so the burst becomes one replay.
  void render({ settleMs: RENDER_BURST_SETTLE_MS })
}

async function setEnabledWithGeometry(opId: string, enabled: boolean) {
  const before = JSON.parse(JSON.stringify(stack.doc.value))
  stack.setEnabled(opId, enabled)
  await afterGeometryChange(before)
  void render()
}

// -- running a generative step ---------------------------------------------

const canRun = computed(() => {
  if (!composite.value || busy.value) return false
  const referencesValid =
    referenceImages.value.length >= activeReferenceLimits.value.min
    && referenceImages.value.length <= activeReferenceLimits.value.max
  if (
    family.value === 'retouch'
    && (sub.value === 'remove' || sub.value === 'repaint')
  ) {
    return !!selection.value && !!activeToolId.value && referencesValid
  }
  // Remove background is whole-image: the model finds the subject itself.
  if (family.value === 'retouch' && sub.value === 'cutout') {
    return !!activeToolId.value
  }
  // Expand auto-masks the border it adds, so it has nothing to wait for
  // beyond a tool.
  if (mode.value === 'expand') return !!expandToolId.value && referencesValid
  return false
})

const busy = ref(false)

/**
 * Whether the composite can carry real transparency — an applied cutout step.
 * The stage then shows the standard checkerboard, because transparent pixels
 * rendered straight onto the matte read as "the image turned grey".
 */
const compositeHasCutout = computed(() =>
  (stack.doc.value?.edits ?? []).some(op =>
    op.enabled && (op as any).operation === 'cutout' && (op as any).picked,
  ),
)

/**
 * Tool families. Clicking one enters a MODE and opens its sub-toolbar; the step
 * is created on the first real gesture — a slider move, an aspect choice, an
 * explicit Run. Empty steps cannot exist, and Esc leaves a mode with nothing to
 * undo.
 */
function selectFamily(id: FamilyId) {
  // Changing modes takes the pointer back from the selection; the selection
  // itself survives — it is workspace state, and the chips in each family's
  // sub-bar say when it is scoping them.
  disarmSelect()
  toolPickerOpen.value = false
  // Clicking the active family leaves it — entering and leaving are the same
  // gesture, and leaving with nothing drawn leaves nothing to undo.
  if (family.value === id) { leaveMode(); return }
  leaveMode()
  family.value = id
  writeToolPrefs({ family: id })
  // Entering a family lands on the tool it was last left holding — the pick is
  // this person's way of working, not a property of the image. It only stands
  // while it still names one of the family's tools; the family's own default
  // covers a renamed or removed one.
  const spec = familyById(id)
  sub.value =
    rememberedIfValid(
      rememberedSubTool(id),
      subId => spec.subTools.some(tool => tool.id === subId && !tool.pending),
    ) ?? spec.defaultSub
  // Entering Annotate with a shape already selected means "work with that" —
  // land in select mode with its handles up, not with the arrow tool armed
  // (which hides the handles and turns the next click into a drawing).
  if (id === 'annotate' && selectedShapeId.value) sub.value = null
  if (id === 'generate') mode.value = (sub.value as Mode) ?? null
  // Paint entered with the Patch engine still up wants a selection.
  if (id === 'paint' && paintEngineId.value === 'patch' && !selection.value) {
    armSelectTool('lasso', true)
  }
  // Changing families ends a scoped step's mask-editing session: the armed
  // step belongs to the family flow that armed it, and gestures made in the
  // next family are new selections, not silent rewrites of that step's mask.
  disarmMaskedAdjustmentEditing()
  if (id === 'retouch') {
    retouchInput.value = composite.value
    discardFragileMaskedAdjustment()
  }
  if (id === 'retouch' && sub.value === 'patch' && !selection.value) {
    armSelectTool('lasso', true)
  } else if (
    id === 'retouch'
    && (sub.value === 'remove' || sub.value === 'repaint')
  ) {
    if (!selection.value) armSelectTool('brush', true)
  }
  // Entering an adjustment family starts fresh. Without this the panel kept
  // editing whatever was selected before, and a subbar click would judge the
  // wrong step for try-then-replace.
  if (id === 'levels' || id === 'filters') {
    selectedOpId.value = null
    selectedShapeId.value = null
  }
  if (id === 'filters') void renderFilterThumbs()
  if (id === 'crop') {
    // Each visit to Crop is its own step. Cropping twice is a real thing to
    // want — frame roughly, work, then tighten — and it stays non-destructive
    // because the earlier crop is still a row you can widen or delete. The
    // only time an existing crop is resumed is when its row is selected,
    // which enterParametricOp handles.
    cropOpId.value = null
    void renderCropInput()
  }
}

function selectSub(id: string) {
  // Switching sub-tools is reaching for the canvas: the selection tool lets go.
  disarmSelect()
  toolPickerOpen.value = false
  if (family.value === 'retouch') discardFragileMaskedAdjustment()
  sub.value = id
  if (family.value) rememberSubTool(family.value, id)
  if (family.value === 'generate') {
    mode.value = id as Mode
  }
  if (family.value === 'retouch' && id === 'patch' && !selection.value) {
    armSelectTool('lasso', true)
  } else if (
    family.value === 'retouch'
    && (id === 'remove' || id === 'repaint')
  ) {
    selectedRetouchRegionId.value = null
    if (!selection.value) armSelectTool('brush', true)
  }
}

/** Sub-toolbar state, flattened so the sub-bar stays a dumb renderer. */
const subbarState = computed(() => ({
  prompt: prompt.value,
  candidateCount: candidateCount.value,
  maskExpandPercent: maskExpandPercent.value,
  expandFactor: expandFactor.value,
  cropAspect: cropAspect.value,
  rotation: cropParamsOf().cropRotation ?? 0,
  flipX: !!cropParamsOf().flipX,
  flipY: !!cropParamsOf().flipY,
  engineId: paintEngineId.value,
  paintBrush: paintBrush.value,
  paintColor: paintColorRgb.value,
  paintExposure: paintExposure.value,
  paintRange: paintRange.value,
  paintStrength: paintStrength.value,
  paintSaturate: paintSaturate.value,
  retouchBrush: retouchBrush.value,
  activeTool: activeTool.value,
  toolParams: activeToolParamValues.value,
  recentRepaintPrompts: recentRepaintPrompts.value,
  referenceImages: referenceImages.value,
  referenceMin: activeReferenceLimits.value.min,
  referenceMax: activeReferenceLimits.value.max,
  textStyle: textStyle.value,
  annotatePaint: annotatePaint.value,
  annotateStrokeWidth: annotateStrokeWidth.value,
  annotateFillColor: annotateFillColor.value,
  annotateShapeEffect: annotateShapeEffect.value,
  annotateOpacity: annotateOpacity.value,
  selectedShapeId: selectedShapeId.value,
  // With a shape selected, the sub-bar shows THAT shape's control set — the
  // selection's status overrides the latent tool's initial conditions.
  selectedShapeKind: selectedShape.value?.type ?? null,
  imagePalette: imagePalette.value,
  appliedStripIds: appliedStripIds.value,
  filterThumbs: filterThumbs.value,
  // Adjust's scope chip: a live selection means the next added edit is scoped.
  hasSelection: !!selection.value,
}))

/**
 * Sub-bar keys that do NOT reach for the canvas: typing a prompt or setting a
 * factor keeps an armed selection tool armed (Repaint arms the brush and then
 * asks for a sentence). Everything else — engines, brushes, colors, annotate
 * styles, adjust actions — is the user picking family work up again, and the
 * selection tool must let go.
 */
const SUBBAR_KEEPS_SELECT = new Set([
  'prompt', 'candidateCount', 'maskExpandPercent', 'expandFactor', 'toolParamPatch',
  'removeRecentPrompt', 'referenceImages',
])

function onSubbarSet(patch: Record<string, any>, continuous = false) {
  if (Object.keys(patch).some(key => !SUBBAR_KEEPS_SELECT.has(key))) disarmSelect()
  if ('prompt' in patch) prompt.value = patch.prompt
  if ('candidateCount' in patch) candidateCount.value = patch.candidateCount
  if ('referenceImages' in patch) referenceImages.value = patch.referenceImages
  if ('maskExpandPercent' in patch) {
    maskExpandPercent.value = patch.maskExpandPercent
    writeToolPrefs({ maskExpandPercent: patch.maskExpandPercent })
  }
  if ('expandFactor' in patch) expandFactor.value = patch.expandFactor
  if ('removeRecentPrompt' in patch) {
    recentRepaintPrompts.value = recentRepaintPrompts.value.filter(
      entry => entry !== patch.removeRecentPrompt,
    )
    writeToolPrefs({ recentRepaintPrompts: recentRepaintPrompts.value })
  }
  if ('toolParamPatch' in patch && activeToolId.value) {
    modelToolParams.value = {
      ...modelToolParams.value,
      [activeToolId.value]: {
        ...activeToolParamValues.value,
        ...sanitizeModelToolParams(activeTool.value, patch.toolParamPatch),
      },
    }
  }
  if ('engineId' in patch) {
    paintEngineId.value = patch.engineId
    writeToolPrefs({ paintEngineId: patch.engineId })
    // Patch works FROM a selection: picking it with nothing selected arms the
    // lasso, the same way Repaint arms the selection brush.
    if (patch.engineId === 'patch' && !selection.value) armSelectTool('lasso', true)
  }
  if ('paintBrush' in patch) paintBrush.value = patch.paintBrush
  if ('paintColor' in patch) paintColorRgb.value = patch.paintColor
  if ('paintExposure' in patch) paintExposure.value = patch.paintExposure
  if ('paintRange' in patch) paintRange.value = patch.paintRange
  if ('paintStrength' in patch) paintStrength.value = patch.paintStrength
  if ('paintSaturate' in patch) paintSaturate.value = patch.paintSaturate
  if ('retouchBrush' in patch) {
    retouchBrush.value = paintEngineSettings('heal', { brush: patch.retouchBrush }).brush
    writeToolPrefs({ retouchBrush: retouchBrush.value })
  }
  if ('textStyle' in patch) {
    textStyle.value = patch.textStyle
    // Same act before or after: the strip arms the next text and, with one
    // selected, restyles it — the inspector's preset row writes the same patch.
    if (selectedShape.value?.type === 'text') {
      onShapeChange(textStylePatch(patch.textStyle, {
        glowIntensity: (selectedShape.value as any).glowIntensity,
      }))
    }
  }
  if ('annotatePaint' in patch) {
    annotatePaint.value = patch.annotatePaint
    if (selectedShape.value) {
      onShapeChange(selectedShape.value.type === 'text'
        ? { textColor: patch.annotatePaint }
        : { strokeColor: patch.annotatePaint })
    }
  }
  // The annotate strip is the latent shape's initial conditions, and — with a
  // shape selected — a compact remote for that shape: both views bind to the
  // same values, so setting neon before or after drawing is the same act.
  if ('annotateStrokeWidth' in patch) {
    annotateStrokeWidth.value = patch.annotateStrokeWidth
    if (selectedShape.value) onShapeChange({ strokeWidth: patch.annotateStrokeWidth })
  }
  if ('annotateFillColor' in patch) {
    annotateFillColor.value = patch.annotateFillColor
    if (selectedShape.value && 'backgroundColor' in (selectedShape.value as any)) {
      onShapeChange({ backgroundColor: patch.annotateFillColor ?? undefined })
    }
  }
  if ('annotateShapeEffect' in patch) {
    annotateShapeEffect.value = patch.annotateShapeEffect
    if (selectedShape.value && selectedShape.value.type !== 'text') {
      onShapeChange({
        style: patch.annotateShapeEffect === 'none'
          ? undefined
          : { effect: patch.annotateShapeEffect, glowIntensity: 70 },
      })
    }
  }
  if ('annotateOpacity' in patch) {
    annotateOpacity.value = patch.annotateOpacity
    if (selectedShape.value) {
      onShapeChange({ opacity: patch.annotateOpacity }, continuous)
    }
  }
  if ('deleteShape' in patch) annotateRef.value?.deleteSelected()
  if ('auto' in patch) runAuto(patch.auto)
  if ('applyFilter' in patch) applyStripEntry(patch.applyFilter)
  if ('addLevel' in patch) void addLevelEdit(patch.addLevel)
  if ('cropAspect' in patch) chooseAspect(patch.cropAspect)
  // Straighten and the lollipop are the same control: the crop window's tilt.
  if ('rotation' in patch) {
    void applyCropChange(
      { cropRotation: patch.rotation },
      cropGestureKey.value,
      continuous,
    )
  }
  if ('rotateQuarter' in patch) rotateQuarter()
  if ('flipX' in patch) void applyCropChange({ flipX: patch.flipX })
  if ('flipY' in patch) void applyCropChange({ flipY: patch.flipY })
  if ('newLayer' in patch) startNewPaintLayer()
}

/** One line of fact per mode: what to do, and what it will cost. */
/**
 * Only where the toolbar cannot speak for itself.
 *
 * A hint that narrates what the controls already show is noise — the tools are
 * the explanation. What survives is the Generate sub-tools, whose cost and
 * effect are not visible until they run.
 */
const subbarHint = computed(() => {
  if (family.value === 'generate') {
    if (sub.value === 'expand') return 'Grows the canvas · the new border is auto-masked'
  }
  return null
})

async function run() {
  if (!canRun.value || !stack.doc.value || !composite.value) return

  busy.value = true
  error.value = null
  try {
    const action =
      family.value === 'retouch' && sub.value === 'remove'
        ? 'remove'
        : family.value === 'retouch' && sub.value === 'repaint'
          ? 'repaint'
          : family.value === 'retouch' && sub.value === 'cutout'
            ? 'cutout'
            : 'expand'
    const toolId = activeToolId.value!
    const tool = activeTool.value
    if (!tool) throw new Error('That tool is no longer in the catalog.')
    const toolParams = sanitizeModelToolParams(tool, activeToolParamValues.value)
    const removeRoute = action === 'remove' ? removeRouteForTool(tool) : null
    if (action === 'remove' && !removeRoute) {
      throw new Error('That tool cannot remove or inpaint an image.')
    }
    const taskType = action === 'cutout'
      ? 'remove-background'
      : removeRoute?.taskType ?? 'inpaint-image'
    const submittedPrompt = action === 'cutout' ? '' : removeRoute?.prompt ?? prompt.value
    const submittedReferences = action === 'remove' || action === 'cutout'
      ? []
      : copyModelReferenceImages(referenceImages.value)

    // The op's input is the current head composite: Phase 1 appends on top,
    // so its input hash is the head hash.
    const { head } = stackHashes(stack.doc.value)

    const opId = newOpId()

    // What a tool is given is the real head composite, not the stage: the
    // stage can be holding a layer out while an overlay draws it (see
    // displayDoc), and a model must never be handed pixels the document does
    // not have.
    const headComposite = await compositor.render(stack.doc.value)

    // Expand grows the frame and auto-masks the border it added — the same
    // extend-pad invariant the prep flow uses — then fills it like any patch.
    let submitInput = headComposite
    let submitMask = selectionAsMask()
    if (action === 'expand') {
      const grown = growCanvas(headComposite, expandFactor.value)
      submitInput = grown.image
      submitMask = grown.borderMask
    }
    // A cutout has no drawn region — its "mask" is the whole frame. It exists
    // for the patch machinery (crop bounds, resample), not the wire:
    // remove-background tools declare no mask input, so none is uploaded.
    if (action === 'cutout') {
      submitMask = fullFrameMask(headComposite.width, headComposite.height)
    }
    if (!submitMask) throw new Error('There is nothing selected to work on.')

    // Remove/Repaint grow their mask copy past the selection edge: a crisp
    // object-hugging mask leaves the model repainting inside the outline it
    // was meant to replace. Expand's border mask is already sized on purpose.
    if (action === 'remove' || action === 'repaint') {
      expandMaskCanvas(submitMask, maskExpandPercent.value)
    }

    const maskPayloadRef = await stack.uploadPayload(
      `${opId}-mask.png`, await canvasToBlob(submitMask)
    )

    const label = action === 'remove'
      ? 'Remove object'
      : action === 'repaint'
        ? 'Regenerate'
        : action === 'cutout'
          ? 'Remove background'
          : 'Expand'

    const authoredFrame = payloadFrame()
    const authoredToDocument = payloadTransform()
    const op: GenerativeOp = {
      id: opId,
      class: 'patch',
      enabled: true,
      label,
      exec: { kind: 'tool', tool_id: toolId, task_type: taskType },
      operation: action,
      params: {
        ...toolParams,
        ...(submittedPrompt ? { prompt: submittedPrompt } : {}),
      },
      reference_images: submittedReferences,
      mask_ref: maskPayloadRef,
      // The mask, and the candidates generated for it, are anchored to the
      // frame they were made in.
      payload_to_document: authoredToDocument,
      payload_frame: authoredFrame,
      // A cutout matte is already soft where the model made it soft; a default
      // feather would eat the subject's edge.
      blend: { feather_px: action === 'cutout' ? 0 : 6, opacity: 1 },
      picked: null,
      candidates: [],
    }
    stack.addOp(op)
    selectedOpId.value = opId

    // Cut the naming crop HERE, while the mask and the composite it was sampled
    // against are still this step's. The request itself is fire-and-forget: a
    // name is a nicety and must never sit in front of the job.
    if (action === 'remove' || action === 'repaint') {
      const crop = regionCropBase64(submitInput, submitMask)
      if (crop) {
        void nameStepFromCrop(action, crop, submittedPrompt).then(label => {
          if (label) stack.annotateLabel(opId, label)
        })
      }
    }

    await candidates.submit({
      opId,
      tool,
      taskType,
      inputCanvas: submitInput,
      maskCanvas: submitMask,
      prompt: submittedPrompt,
      // Background removal is deterministic — N runs are N identical mattes.
      count: action === 'cutout' ? 1 : candidateCount.value,
      params: toolParams,
      referenceImages: submittedReferences,
      sampledInputHash: head,
      payloadToDocument: authoredToDocument,
    })
    if (action === 'repaint') {
      recentRepaintPrompts.value = addRecentPrompt(
        recentRepaintPrompts.value,
        submittedPrompt,
      )
      writeToolPrefs({
        repaintPrompt: submittedPrompt,
        recentRepaintPrompts: recentRepaintPrompts.value,
      })
    }

    // The patch now owns a COPY of the selection. Leaving its ants up would
    // obscure the result exactly when the person needs to judge it. A cutout
    // never consumed the selection, so it leaves it alone.
    if (action === 'remove' || action === 'repaint') {
      clearSelection()
      disarmSelect()
    }
    if (action === 'expand') mode.value = 'expand'
  } catch (err: any) {
    error.value = apiErrorMessage(err, 'Could not start the edit.')
  } finally {
    busy.value = false
  }
}

/**
 * Re-run a generative step against its CURRENT input.
 *
 * Old candidates are kept: switching back to one is free and restores the prior
 * look, which is what makes a resample safe to try.
 *
 * Two things this must NOT do, both of which it once did. It must not report
 * itself finished when the job is merely submitted — the work is the job, and a
 * spinner that stops at submission says "done, and nothing happened". And its
 * result must not be discarded because the step already has a pick: a resample
 * by definition targets a picked step, so the arriving candidate has to replace
 * that pick or the run cost money and changed nothing.
 */
const resampledOpIds = ref<Set<string>>(new Set())

/** Steps with a live job, whichever way it was started. */
const runningOpIds = computed(() => new Set(Object.keys(pendingByOp.value)))

async function resample(opId: string) {
  const doc = stack.doc.value
  const op = stack.opById(opId) as GenerativeOp | undefined
  if (!doc || !op || !composite.value) return

  const index = doc.edits.findIndex(o => o.id === opId)
  const inputHash = stackHashes(doc).inputs[index]
  const tool = tools.value.find(t => t.full_tool_id === op.exec.tool_id)
  if (!tool) {
    error.value = 'That tool is no longer in the catalog.'
    return
  }
  const referenceLimits = modelReferenceLimits(tool)
  const referenceCount = op.reference_images?.length ?? 0
  if (
    referenceCount < referenceLimits.min
    || referenceCount > referenceLimits.max
  ) {
    error.value = `That tool accepts ${referenceLimits.min}–${referenceLimits.max} reference images.`
    return
  }
  const maskRef = (op as any).mask_ref
  if (!maskRef) {
    error.value = 'That step has no mask to resample through.'
    return
  }

  error.value = null
  try {
    // The op's input composite, not the head: a step re-samples against what it
    // actually sits on.
    const inputCanvas = await compositor.renderUpTo(doc, index)
    const image = await loadImage(stack.payloadUrl(maskRef))
    const canonical = (op.payload_to_document as Affine | undefined)
      ?? (op.payload_frame
        ? payloadToDocumentTransform(op.payload_frame) ?? undefined
        : undefined)
    const now = geometryBelow(doc, index)
    const mask = canonical
      ? rewritePayload(
          image,
          multiply(now.matrix, canonical),
          inputCanvas.width,
          inputCanvas.height,
        )
      : (() => {
          const canvas = document.createElement('canvas')
          canvas.width = inputCanvas.width
          canvas.height = inputCanvas.height
          canvas.getContext('2d')!.drawImage(image, 0, 0, canvas.width, canvas.height)
          return canvas
        })()
    const resampledToDocument = payloadTransform(index)

    // Marked BEFORE the submit: the first candidate back auto-applies, which is
    // the only way the click has a visible result.
    resampledOpIds.value = new Set(resampledOpIds.value).add(opId)
    await candidates.submit({
      opId,
      tool,
      taskType: op.exec.task_type,
      inputCanvas,
      maskCanvas: mask,
      prompt: (op.params as any)?.prompt || '',
      count: candidateCount.value,
      params: sanitizeModelToolParams(tool, op.params),
      referenceImages: op.reference_images ?? [],
      sampledInputHash: inputHash,
      payloadToDocument: resampledToDocument,
    })
    if (
      op.operation === 'repaint'
      || (!op.operation && op.label === 'Repaint')
    ) {
      const submittedPrompt = (op.params as any)?.prompt || ''
      recentRepaintPrompts.value = addRecentPrompt(
        recentRepaintPrompts.value,
        submittedPrompt,
      )
      writeToolPrefs({
        repaintPrompt: submittedPrompt,
        recentRepaintPrompts: recentRepaintPrompts.value,
      })
    }
  } catch (err: any) {
    const next = new Set(resampledOpIds.value)
    next.delete(opId)
    resampledOpIds.value = next
    error.value = apiErrorMessage(err, 'Could not resample.')
  }
}

/** A white-everywhere mask: the whole frame is the region. */
function fullFrameMask(width: number, height: number): HTMLCanvasElement {
  const mask = document.createElement('canvas')
  mask.width = width
  mask.height = height
  const ctx = mask.getContext('2d')!
  ctx.fillStyle = '#fff'
  ctx.fillRect(0, 0, width, height)
  return mask
}

/**
 * Grow a canvas about its centre and return the border it added as a mask.
 * The border is what the model fills; the original pixels are preserved by the
 * patch composite exactly as with any other mask.
 */
function growCanvas(source: HTMLCanvasElement, factor: number) {
  const width = Math.round(source.width * factor)
  const height = Math.round(source.height * factor)
  const offsetX = Math.round((width - source.width) / 2)
  const offsetY = Math.round((height - source.height) / 2)

  const image = document.createElement('canvas')
  image.width = width
  image.height = height
  image.getContext('2d')!.drawImage(source, offsetX, offsetY)

  const borderMask = document.createElement('canvas')
  borderMask.width = width
  borderMask.height = height
  const maskCtx = borderMask.getContext('2d')!
  maskCtx.fillStyle = '#fff'
  maskCtx.fillRect(0, 0, width, height)
  maskCtx.fillStyle = '#000'
  maskCtx.fillRect(offsetX, offsetY, source.width, source.height)

  return { image, borderMask }
}

// -- adjust ----------------------------------------------------------------

/**
 * Fine-grained adjust steps, one rule for both doorways: every entry in the
 * Adjust and Filters sub-toolbars is an ADD. Clicking it creates its own
 * focused step — a Light, a Color, a Portra 400, a VHS — and the step's
 * controls live in its Properties. There is no session step and no latent
 * state: the click IS the creating gesture.
 *
 * Try-then-replace: a step that is still exactly as the click created it is
 * replaced when another entry is clicked, so paging through looks does not
 * leave a trail. Touch any of its properties and it sticks.
 */
const pristineSnapshots = new Map<string, string>()

function snapshotPristine(opId: string) {
  const op = stack.opById(opId) as any
  pristineSnapshots.set(opId, JSON.stringify(op?.params ?? {}))
}

async function replaceIfPristine() {
  const id = selectedOpId.value
  if (!id) return
  const snap = pristineSnapshots.get(id)
  if (snap === undefined) return
  const op = stack.opById(id) as any
  pristineSnapshots.delete(id)
  if (!op || JSON.stringify(op.params ?? {}) !== snap) return
  await removeOpWithGeometry(id)
}

function addAdjustOp(
  label: string,
  params: Record<string, any>,
  options: { pristine?: boolean } = {},
) {
  // A whole-image step takes over from any scoped step still armed for mask
  // edits; leaving it armed would route the next selection gesture into the
  // OLD step's mask.
  disarmMaskedAdjustmentEditing()
  const opId = newOpId()
  stack.addOp({
    id: opId, class: 'parametric', enabled: true,
    label, exec: { kind: 'adjust' }, params,
  } as any)
  selectedOpId.value = opId
  // pristine: false is for steps born DONE (the Autos): their values arrive
  // finished rather than as a doorway's defaults, so an untouched one is a
  // real edit, not a provisional landing place for the next click to replace.
  if (options.pristine !== false) snapshotPristine(opId)
  void render()
}

/**
 * Light, Color or Detail, from the Adjust bar. Scope comes from the workspace:
 * a live selection makes the step a scoped one (its own single-region
 * container); otherwise it is a whole-image parametric step. Either way the
 * click yields the edit's controls, never a brush.
 */
async function addLevelEdit(id: string) {
  const edit = levelEditById(id)
  if (!edit) return
  // Try-then-replace, both shapes: an untouched whole-image step and an
  // untouched scoped step are equally provisional landing places.
  await replaceIfPristine()
  discardFragileMaskedAdjustment()
  if (selection.value) {
    addScopedLevelEdit(edit)
    return
  }
  addAdjustOp(edit.label, { section: edit.id, ...(edit.seed ?? {}) })
}

/** The region kind the masked pipeline stores for a level edit's section. */
function maskedKindOf(edit: LevelEdit): Exclude<MaskedAdjustmentKind, 'adjust'> {
  const group = photoAdjustmentGroup(edit.id)
  return (group?.id ?? 'light') as Exclude<MaskedAdjustmentKind, 'adjust'>
}

/**
 * One scoped Adjust step from the live selection.
 *
 * A selection that IS a single gradient gesture scopes parametrically — the
 * step keeps the ramp's geometry and its handles stay live. Anything else
 * freezes the rasterised mask, consumed by copy like every region consumer.
 */
function addScopedLevelEdit(edit: LevelEdit) {
  disarmMaskedAdjustmentEditing()
  selectedRetouchRegionId.value = null
  hoveredRetouchRegionId.value = null
  void refreshRetouchFeedback()
  const opId = newOpId()
  const regionId = newOpId()
  maskedAdjustOpId = opId
  maskedAdjustRegionId = regionId
  maskedAdjustSpec = {
    kind: maskedKindOf(edit),
    label: edit.label,
    seed: edit.seed,
  }
  fragileRetouchRegions.mark(regionId)
  const gradient =
    workspaceGradient && workspaceGradientKey === selectionAppliedKey
      ? workspaceGradient
      : null
  if (gradient) {
    createScopedGradientStep(opId, regionId, gradient)
    return
  }
  if (selection.value) queueMaskedAdjustmentMask(selection.value)
}

/**
 * The gradient-scoped step, created synchronously: geometry, not pixels, so
 * there is no payload upload to wait for.
 */
function createScopedGradientStep(
  opId: string,
  regionId: string,
  gradient: GradientMask,
) {
  const spec = maskedAdjustSpec
  const frame = payloadFrame()
  const canonical = frame
    ? payloadToDocumentTransform(frame) ?? undefined
    : undefined
  const authored = authoredGradient(gradient, frame, canonical, -1)
  if (!authored) return
  const region: RetouchRegion = {
    id: regionId,
    kind: spec?.kind ?? 'light',
    enabled: true,
    mask: authored,
    payload_to_document: canonical,
    payload_frame: frame,
    sampled_input_hash: null,
    settings: { ...DEFAULT_RETOUCH_REGION_SETTINGS, ...(spec?.seed ?? {}) },
  }
  stack.addOp({
    id: opId,
    class: 'container',
    enabled: true,
    label: spec?.label ?? 'Adjust',
    exec: { kind: 'retouch-regions', version: 1 },
    defaults: { ...DEFAULT_RETOUCH_REGION_SETTINGS },
    regions: [region],
  } as any)
  selectedOpId.value = opId
  selectedRetouchRegionId.value = regionId
  // The ramp's guides say where it is; a second wash would double up.
  selectedRetouchFeedbackVisible.value = false
  void render().then(refreshRetouchInput)
}

/**
 * Selecting a Adjust row makes the inspector edit THAT row, which is how an
 * earlier session's step is re-entered rather than a new one being stacked.
 */
const selectedAdjustOp = computed(() => {
  const op = selectedOpId.value ? stack.opById(selectedOpId.value) : null
  return op && op.class === 'parametric' && (op as any).exec?.kind === 'adjust' ? op : null
})
const selectedModelOp = computed<GenerativeOp | null>(() => {
  const op = selectedOpId.value ? stack.opById(selectedOpId.value) : null
  return op?.class === 'patch' ? op as GenerativeOp : null
})
const selectedModelTool = computed(() => {
  const id = selectedModelOp.value?.exec.tool_id
  return id ? tools.value.find(tool => tool.full_tool_id === id) ?? null : null
})

function setSelectedModelParams(patch: Record<string, any>) {
  if (!selectedModelOp.value) return
  stack.setParams(selectedModelOp.value.id, patch)
}

function setSelectedModelReferences(images: ModelReferenceImage[]) {
  if (!selectedModelOp.value) return
  stack.setReferenceImages(selectedModelOp.value.id, images)
}

function setSelectedModelBlend(blend: Record<string, number>) {
  if (!selectedModelOp.value) return
  stack.setBlend(
    selectedModelOp.value.id,
    blend,
    `model-blend:${selectedModelOp.value.id}:${Object.keys(blend)[0] ?? 'value'}`,
  )
  scheduleRetouchSettingsPreview()
}

function commitSelectedModelBlend() {
  void commitRetouchSettingsRender()
}

/**
 * What the properties panel is showing: the selected step decides, and with
 * nothing selected there is nothing to show — the sub-toolbars are the door
 * to a first step now, not the inspector.
 */
const inspectorKind = computed<'annotation' | 'adjust' | 'retouch' | 'model' | null>(() => {
  // Properties belongs to a selected STEP, so it follows the Edits panel. The
  // Output panel carries its own controls and would otherwise be sharing the
  // sidebar with a second, unrelated control surface.
  if (sidebarTab.value !== 'edits') return null
  const op = selectedOpId.value ? (stack.opById(selectedOpId.value) as any) : null
  if (
    op?.exec?.kind === 'retouch-regions'
    && (op.regions ?? []).some(
      (region: RetouchRegion) => region.id === selectedRetouchRegionId.value,
    )
  ) return 'retouch'
  if (op?.exec?.kind === 'annotate') return 'annotation'
  if (op?.exec?.kind === 'adjust') return 'adjust'
  if (op?.class === 'patch' && op?.exec?.kind === 'tool') return 'model'
  return null
})

const showsAdjustInspector = computed(() => inspectorKind.value === 'adjust')

/**
 * Picking a filter IS applying it.
 *
 * Each click makes its own step, named for the preset, so the stack reads as
 * what was done rather than as a settings object — and stacking two filters is
 * a thing you can do and then reorder or remove. Clicking the ACTIVE filter
 * takes it off again, which is the only sensible meaning for pressing a
 * pressed button.
 */
/**
 * A thumbnail per preset, off the real picture, for the strip.
 *
 * Naming a filter tells you nothing — Kodachrome and Portra 400 are only
 * distinguishable by looking.
 */
const filterThumbs = ref<Record<string, string>>({})
const FILTER_THUMB = 128

async function renderFilterThumbs() {
  // The strip previews what a click DOES. With a still-pristine step selected
  // a click replaces it, so the tiles render off the composite WITHOUT that
  // step — otherwise every preview shows a stack that will never happen.
  // Cheap: the composite below the top op is already in the compositor cache.
  let source = composite.value
  const selected = selectedOpId.value
  if (selected && pristineSnapshots.has(selected) && stack.doc.value) {
    const op = stack.opById(selected) as any
    if (
      op?.exec?.kind === 'adjust' &&
      JSON.stringify(op.params ?? {}) === pristineSnapshots.get(selected)
    ) {
      source = await compositor.render({
        ...stack.doc.value,
        edits: stack.doc.value.edits.filter(edit => edit.id !== selected),
      })
    }
  }
  if (!source?.width) return

  const base = document.createElement('canvas')
  base.width = FILTER_THUMB
  base.height = FILTER_THUMB
  const ctx = base.getContext('2d', { willReadFrequently: true })
  if (!ctx) return
  const side = Math.min(source.width, source.height)
  ctx.drawImage(
    source,
    (source.width - side) / 2, (source.height - side) / 2, side, side,
    0, 0, FILTER_THUMB, FILTER_THUMB
  )
  const pixels = ctx.getImageData(0, 0, FILTER_THUMB, FILTER_THUMB)

  const tile = document.createElement('canvas')
  tile.width = FILTER_THUMB
  tile.height = FILTER_THUMB
  const tileCtx = tile.getContext('2d')!
  const out: Record<string, string> = {}
  for (const preset of FILTER_STRIP) {
    const copy = new ImageData(new Uint8ClampedArray(pixels.data), FILTER_THUMB, FILTER_THUMB)
    if (preset.effect?.key === 'colorizeAmount') {
      // Colorize lives in the photographic pipeline, not the effects one.
      applyPhotographicAdjustments(copy, {
        [preset.effect.key]: preset.effect.add, ...preset.seed,
      })
      tileCtx.putImageData(copy, 0, 0)
    } else if (preset.effect) {
      // A pixel look previews through the real effects pipeline, at the value
      // a click would add — the tile shows what the button DOES.
      tileCtx.putImageData(copy, 0, 0)
      const looked = applyEffects(tile, { [preset.effect.key]: preset.effect.add })
      if (looked !== tile) tileCtx.drawImage(looked, 0, 0, FILTER_THUMB, FILTER_THUMB)
    } else {
      const matrix = (FILTER_MATRICES as any)[preset.id]
      tileCtx.putImageData(matrix ? applyColorMatrix(copy, matrix) : copy, 0, 0)
    }
    out[preset.id] = tile.toDataURL()
  }
  filterThumbs.value = out
}

/**
 * The step a strip entry created, if one is on. Single-purpose steps only —
 * a migrated blob that happens to carry the same param must never be matched,
 * or clicking VHS in the strip would delete a whole legacy adjustment.
 */
function stripOpFor(entry: StripEntry): any | null {
  return (stack.doc.value?.edits || []).find(op => {
    const anyOp = op as any
    if (anyOp.exec?.kind !== 'adjust') return false
    const params = anyOp.params || {}
    const keys = Object.keys(params)
    if (entry.effect) {
      return keys.length > 0 && effectLookStepOf(params)?.id === entry.id
    }
    return params.filter === entry.id
      && keys.every(key => key === 'filter' || key === 'filterAmount')
  }) ?? null
}

/** What the strip highlights: entries whose step is on. */
const appliedStripIds = computed(() =>
  FILTER_STRIP.filter(entry => stripOpFor(entry)?.enabled).map(entry => entry.id)
)

/**
 * Picking from the strip IS applying it. A color-matrix preset makes a step
 * whose property is Amount; a pixel look (VHS, Glow…) makes a step carrying
 * that one effect param. Clicking the applied entry takes it off again, which
 * is the only sensible meaning for pressing a pressed button.
 */
function applyStripEntry(id: string) {
  const entry = stripEntryById(id)
  if (!entry) return
  const existing = stripOpFor(entry)
  if (existing) {
    pristineSnapshots.delete(existing.id)
    void removeOpWithGeometry(existing.id)
    return
  }
  void (async () => {
    await replaceIfPristine()
    discardFragileMaskedAdjustment()
    if (entry.effect) {
      addAdjustOp(entry.label, { [entry.effect.key]: entry.effect.add, ...entry.seed })
    } else addAdjustOp(entry.label, { filter: entry.id, filterAmount: 100 })
  })()
}

/**
 * The Autos: each reads the histogram of the composite and lands as a normal
 * Light step seeded with the values it chose — inspectable, adjustable and
 * deletable like anything else.
 */
function runAuto(kind: 'levels' | 'contrast' | 'balance') {
  const source = composite.value
  const patch = kind === 'levels' ? autoLevels(source)
    : kind === 'contrast' ? autoContrast(source)
    : autoBalance(source)
  // An auto that computes no change makes no step. The histogram is already
  // where it wants it, and a row that does nothing is worse than no row.
  if (!patch || Object.values(patch).every(value => value === 0)) return
  const label = AUTO_EDITS.find(auto => auto.id === kind)?.label ?? 'Auto'
  // Autos ALWAYS append. Try-then-replace exists for doorway clicks whose
  // step starts at identity; an Auto lands complete, with nothing for the
  // person to touch first — replacing anything on its way in (or being
  // replaced later for never having been touched) reads as steps vanishing.
  addAdjustOp(label, { section: 'tone', ...patch }, { pristine: false })
}

const adjustInspectorParams = computed<Record<string, any>>(
  () => (selectedAdjustOp.value as any)?.params || {}
)

function onAdjustInspectorChange(patch: Record<string, any>, coalesceKey: string) {
  const op = selectedAdjustOp.value as any
  if (!op) return
  const before = { ...(op.params || {}) }
  dismissCanvasFeedback()
  // Touching a step's properties is the substantive change that makes it
  // stick: the next strip or Adjust click stacks rather than replaces.
  pristineSnapshots.delete(op.id)
  stack.setParams(op.id, patch, coalesceKey)
  // Migrated blob steps rename by content; fine-grained steps keep the name
  // they were born with.
  const updated = (stack.opById(op.id) as any)?.params || {}
  if (isLegacyAdjustBlob(updated)) stack.setLabel(op.id, adjustLabel(updated))
  void previewAdjustment(`adjust:${op.id}`, before, updated)
}

async function commitAdjustInspectorChange() {
  cancelLiveAdjustPreview()
  await render()
  await stack.flush()
}

// -- scope conversions: whole-image step ⇄ scoped step -----------------------

/**
 * A scoped step's settings back into whole-image params: only the values that
 * differ from the projection's defaults, so the step reads as what it does.
 */
function scopedSettingsToParams(
  settings: Record<string, any> | undefined,
): Record<string, any> {
  const params: Record<string, any> = {}
  for (const control of PHOTO_ADJUSTMENT_CONTROLS) {
    const value = settings?.[control.key]
    if (value === undefined) continue
    if (control.kind === 'curve') {
      if (JSON.stringify(value) !== JSON.stringify(control.default)) {
        params[control.key] = value
      }
    } else if (
      typeof value === 'number' && Number.isFinite(value)
      && value !== control.default
    ) {
      params[control.key] = value
    }
  }
  return params
}

/** Whether the selected whole-image step can carry a mask (a level edit). */
const selectedAdjustScopeGroup = computed(() => {
  const op = selectedAdjustOp.value as any
  return op?.params?.section ? photoAdjustmentGroup(op.params.section) ?? null : null
})

/**
 * Convert the selected whole-image step into a scoped one, keeping its
 * values. One undo step. The mask is authored at the head of the stack, so
 * the step stays in place only while the geometry there matches its own;
 * otherwise it moves to the end, the one frame those pixels are true in.
 */
async function limitSelectedAdjustToSelection() {
  const op = selectedAdjustOp.value as any
  const mask = selection.value
  const group = selectedAdjustScopeGroup.value
  const doc = stack.doc.value
  if (!op || !mask || !group || !doc) return
  const index = doc.edits.findIndex(edit => edit.id === op.id)
  if (index < 0) return
  pristineSnapshots.delete(op.id)

  const headFrame = payloadFrame()
  const stepFrame = payloadFrame(index)
  const inPlace = JSON.stringify(headFrame) === JSON.stringify(stepFrame)
  const frame = inPlace ? stepFrame : headFrame
  const opId = newOpId()
  const regionId = newOpId()
  const { section: _section, ...values } = op.params ?? {}
  const settings: RetouchRegionSettings = {
    ...DEFAULT_RETOUCH_REGION_SETTINGS,
    ...values,
  }
  const kind = group.id as Exclude<MaskedAdjustmentKind, 'adjust'>

  const gradient =
    workspaceGradient && workspaceGradientKey === selectionAppliedKey
      ? workspaceGradient
      : null
  let region: RetouchRegion
  if (gradient) {
    const canonical = frame
      ? payloadToDocumentTransform(frame) ?? undefined
      : undefined
    const authored = authoredGradient(gradient, frame, canonical, inPlace ? index : -1)
    if (!authored) return
    region = {
      id: regionId,
      kind,
      enabled: true,
      mask: authored,
      payload_to_document: canonical,
      payload_frame: frame,
      sampled_input_hash: null,
      settings,
    }
  } else {
    const compact = compactSelectionMask(mask)
    if (!compact) return
    const maskRef = await stack.uploadPayload(
      `${opId}-${regionId}-mask-${newOpId()}.png`,
      await canvasToBlob(compact.mask),
    )
    payloadCache.set(`${maskRef}@0`, compact.mask)
    region = {
      id: regionId,
      kind,
      enabled: true,
      mask_ref: maskRef,
      payload_origin: compact.origin,
      payload_to_document: payloadTransform(
        inPlace ? index : undefined,
        compact.origin,
      ),
      payload_frame: frame,
      sampled_input_hash: null,
      settings,
    }
  }

  // Re-resolve after the await: the step may have been removed meanwhile.
  const current = stack.doc.value
  if (!current || !current.edits.some((edit: any) => edit.id === op.id)) return
  const container: any = {
    id: opId,
    class: 'container',
    enabled: op.enabled,
    label: op.label,
    exec: { kind: 'retouch-regions', version: 1 },
    defaults: { ...DEFAULT_RETOUCH_REGION_SETTINGS },
    regions: [region],
  }
  const edits = current.edits.flatMap((edit: any) =>
    edit.id === op.id ? (inPlace ? [container] : []) : [edit],
  )
  if (!inPlace) edits.push(container)
  stack.replaceEdits(edits)

  // Refining the selection keeps editing this step's mask.
  maskedAdjustOpId = opId
  maskedAdjustRegionId = regionId
  maskedAdjustSpec = null
  selectedOpId.value = opId
  selectedRetouchRegionId.value = regionId
  selectedRetouchFeedbackVisible.value = false
  await render()
  await refreshRetouchInput()
  await refreshRetouchFeedback()
}

/**
 * Convert the selected scoped step back to a whole-image one, keeping its
 * values and its place in the stack. The mask (and its blend dials) is what
 * is given up. One undo step.
 */
async function unscopeSelectedRegion() {
  const location = retouchRegionLocation(selectedRetouchRegionId.value)
  const doc = stack.doc.value
  if (!location || !doc) return
  const { op, region } = location
  if (!isMaskedAdjustmentKind(region.kind)) return
  const group = photoAdjustmentGroup(region.kind === 'adjust' ? 'light' : region.kind)
  const opId = newOpId()
  const step: any = {
    id: opId,
    class: 'parametric',
    enabled: op.enabled && region.enabled,
    label: op.regions.length === 1 ? op.label : group?.label ?? 'Adjust',
    exec: { kind: 'adjust' },
    params: {
      section: group?.section ?? 'tone',
      ...scopedSettingsToParams(region.settings),
    },
  }
  const edits = doc.edits.flatMap((edit: any) => {
    if (edit.id !== op.id) return [edit]
    const regions = (edit.regions ?? []).filter(
      (candidate: RetouchRegion) => candidate.id !== region.id,
    )
    return regions.length ? [{ ...edit, regions }, step] : [step]
  })
  disarmMaskedAdjustmentEditing()
  fragileRetouchRegions.forget(region.id)
  selectedRetouchRegionId.value = null
  selectedRetouchFeedbackVisible.value = false
  stack.replaceEdits(edits)
  selectedOpId.value = opId
  await render()
  await refreshRetouchInput()
  await refreshRetouchFeedback()
}

/**
 * Route the next selection gestures into the selected scoped step's mask.
 * Every completed gesture republishes the whole mask; combine modes apply
 * as the island says.
 */
function armScopedMaskEditing() {
  const location = retouchRegionLocation(selectedRetouchRegionId.value)
  if (!location || !isMaskedAdjustmentKind(location.region.kind)) return
  maskedAdjustOpId = location.op.id
  maskedAdjustRegionId = location.region.id
  maskedAdjustSpec = null
  armSelectTool(lastSelectTool.value ?? 'brush', true)
}

/**
 * A step from before the fine-grained split: no section marker, not a strip
 * step. Its inspector shows the full legacy surface, and its label tracks its
 * content because nothing else names it.
 */
function isLegacyAdjustBlob(params: Record<string, any>): boolean {
  if (!params || params.section) return false
  const keys = Object.keys(params)
  if (keys.length && keys.every(key => key === 'filter' || key === 'filterAmount')) return false
  if (keys.length && effectLookStepOf(params)) return false
  return true
}

// -- crop ---------------------------------------------------------------------

const cropOpId = ref<string | null>(null)
const cropAspect = ref<string>('free')

function cropParamsOf() {
  const op = cropOpId.value ? stack.opById(cropOpId.value) : null
  return (op as any)?.params || { rect: { x: 0.5, y: 0.5, width: 1, height: 1 } }
}

/**
 * @param live  A drag in progress. The crop itself updates every frame, but the
 *              co-transform — which reloads and rewrites every spatial payload
 *              above the crop — waits for the gesture to end. Running it per
 *              frame rewrote a dozen payloads per mouse move and made the drag
 *              lag far enough behind the pointer to land somewhere else.
 */
async function applyCropChange(
  patch: Record<string, any>,
  coalesceKey = 'crop',
  live = false
) {
  if (!stack.doc.value) return
  const before = liveCropBefore ?? JSON.parse(JSON.stringify(stack.doc.value))
  if (live && !liveCropBefore) liveCropBefore = before
  if (!cropOpId.value) {
    const opId = newOpId()
    stack.addOp({
      id: opId, class: 'parametric', enabled: true, label: 'Crop',
      exec: { kind: 'crop' },
      params: {
        rect: { x: 0.5, y: 0.5, width: 1, height: 1 },
        rotation: 0, cropRotation: 0, rotation90: 0,
        flipX: false, flipY: false, ...patch,
      },
    } as any)
    cropOpId.value = opId
    selectedOpId.value = opId
  } else {
    stack.setParams(cropOpId.value, patch, coalesceKey)
  }
  // StackCropCanvas already draws the moving crop directly from cropInput.
  // Replaying the document here is both invisible in Crop mode and expensive:
  // every pointer move invalidates the crop and everything above it.
  if (live) return
  // A geometry change moves every payload above it into a new space. `before`
  // is the document as it stood when the GESTURE started, so a drag rewrites
  // payloads once, from where they were, rather than in accumulating steps.
  liveCropBefore = null
  await afterGeometryChange(before)
  void render()
}

/** The document as it stood when the current crop drag began. */
let liveCropBefore: any = null

/**
 * The image the crop step sees. Rendering only the ops BELOW it is what lets
 * the region outside the crop be dimmed rather than gone — and what makes
 * widening the crop later reveal real pixels.
 */
const cropInput = ref<HTMLCanvasElement | null>(null)

async function renderCropInput() {
  const doc = stack.doc.value
  if (!doc || !baseInfo.value) return
  const index = cropOpId.value
    ? doc.edits.findIndex(op => op.id === cropOpId.value)
    : doc.edits.length
  try {
    cropInput.value = await compositor.renderUpTo(doc, index < 0 ? doc.edits.length : index)
  } catch {
    cropInput.value = composite.value
  }
}

/** The crop rectangle the overlay draws, defaulting to the whole frame. */
const cropRect = computed<CropRect>(() => {
  const params = cropParamsOf()
  const rect = params.rect ?? { x: 0.5, y: 0.5, width: 1, height: 1 }
  return {
    x: rect.x, y: rect.y, width: rect.width, height: rect.height,
    aspectRatio: cropAspectRatio.value,
    rotation: params.cropRotation ?? 0,
  }
})

/**
 * Locked ratio in PIXEL space, which is what the ported resize maths expects;
 * it divides through by the image's own ratio to work in normalized coords.
 */
const cropAspectRatio = computed<number | null>(() => {
  const preset = CROP_ASPECTS.find(a => a.id === cropAspect.value)
  if (!preset || preset.ratio == null) return null
  const frame = cropInput.value
  if (preset.ratio === -1) return frame ? frame.width / frame.height : null
  return preset.ratio
})

/** The selected annotation, whose properties the inspector edits. */
/**
 * The annotation whose properties the inspector edits.
 *
 * Not gated on being in Annotate: the row IS the annotation, so selecting it
 * anywhere should show what it is and let you change it. Entering the mode is
 * what makes it draggable on the canvas, which is a separate thing.
 */
const selectedShape = computed<Shape | null>(() => {
  if (!selectedShapeId.value) return null
  return annotateShapes.value.find(s => s.id === selectedShapeId.value) ?? null
})

/** The canvas owns marquee membership; the host still owns the primary shape. */
const selectedAnnotationShapes = computed<Shape[]>(() => {
  const canvasSelection = annotateRef.value?.selectedShapes
  if (canvasSelection?.length) return canvasSelection
  return selectedShape.value ? [selectedShape.value] : []
})

function onShapeChange(patch: Record<string, any>, continuous = false) {
  const id = selectedShapeId.value
  if (!id) return
  onAnnotationsChange(
    annotateShapes.value.map(s => (s.id === id ? { ...s, ...patch } as Shape : s))
  )
  if (!continuous) annotateGesture.value += 1
}

function onSelectedShapesChange(patch: Record<string, any>, continuous = false) {
  const selectedIds = new Set(selectedAnnotationShapes.value.map(shape => shape.id))
  if (!selectedIds.size) return
  onAnnotationsChange(
    annotateShapes.value.map(shape =>
      selectedIds.has(shape.id) ? { ...shape, ...patch } as Shape : shape
    )
  )
  if (!continuous) annotateGesture.value += 1
}

function commitSelectedShapesChange() {
  annotateGesture.value += 1
}

function onSubbarCommit(kind: 'crop' | 'annotation') {
  if (kind === 'crop') onCropCommit()
  else annotateGesture.value += 1
}

// -- the selected annotation AS an object ------------------------------------

/**
 * The floating strip carries the verbs that are about the annotation as an
 * object — where it sits in the pile, another one of it, no more of it — while
 * the inspector carries its properties. Both are needed: a strip that also
 * held settings would be a second inspector, and an inspector alone puts the
 * object's own verbs across the screen from the object.
 *
 * It hides while a text session owns the caret, along with the handles: during
 * editing the shape is a text field, and chrome sitting over it is in the way.
 * It hides during a gesture too — a move publishes nothing until the mouse
 * comes up, so a strip positioned from the document would sit where the shape
 * was grabbed and then jump to catch up.
 */
const annotationIslandVisible = computed(() =>
  selectedAnnotationShapes.value.length > 0 &&
  annotationOverlayActive.value &&
  !annotateRef.value?.editingText &&
  !annotateRef.value?.gestureActive
)

/** The frame the shapes are normalized against. */
const frameSize = computed(() => {
  const source = composite.value
  if (source) return { width: source.width, height: source.height }
  const canvas = stack.doc.value?.canvas
  return canvas ? { width: canvas.width, height: canvas.height } : null
})

/**
 * An annotation selection's z-order IS its block position in the stack.
 * Selected rows retain their internal order while the block crosses the
 * unselected annotation peers.
 */
function annotationOrder(direction: 'front' | 'back'): string[] | null {
  const doc = stack.doc.value
  if (!doc) return null
  const opIds = selectedAnnotationShapes.value.flatMap(shape => {
    const opId = opIdForShape(shape.id)
    return opId ? [opId] : []
  })
  return annotationBlockOrder(
    doc.edits.map(op => ({
      id: op.id,
      annotate: (op as any).exec?.kind === 'annotate',
    })),
    opIds,
    direction
  )
}

const canBringAnnotationToFront = computed(() => !!annotationOrder('front'))

const canSendAnnotationToBack = computed(() => !!annotationOrder('back'))

/**
 * Restack the annotation past its neighbours. Routed through the same
 * post-move path as a dragged row — the move cannot change geometry, but the
 * stack is the stack, and one path that co-transforms and re-renders is better
 * than a second that assumes it never has to.
 */
async function moveAnnotation(direction: 'front' | 'back') {
  const doc = stack.doc.value
  const order = annotationOrder(direction)
  if (!doc || !order) return

  const before = JSON.parse(JSON.stringify(doc))
  stack.reorderOps(order)
  await afterGeometryChange(before)
  void render()
}

/**
 * A copy of the selected annotation, offset so it reads as its own object.
 *
 * The offset goes through the geometry transformer rather than nudging x and
 * y: a brush path and a curved arrow keep their geometry in point arrays, and
 * moving a shape's anchor while its points stay put tears it in half.
 */
function duplicateAnnotation() {
  if (annotateRef.value) {
    annotateRef.value.duplicateSelected()
    return
  }
  const shape = selectedShape.value
  const frame = frameSize.value
  if (!shape || !frame) return

  const [clone] = transformShapes(
    // Shapes are pure JSON; a round trip both detaches the reactive proxy and
    // deep-copies the colors and style nested inside.
    [JSON.parse(JSON.stringify(shape))],
    [1, 0, 0, 1, 0.02 * frame.width, 0.02 * frame.height],
    frame.width, frame.height, frame.width, frame.height
  ) as Shape[]
  clone.id = generateShapeId()

  // One annotation, one step: handing the whole list back makes the copy a
  // step of its own at the top of the stack, exactly like drawing it would.
  onAnnotationsChange([...annotateShapes.value, clone])
  annotateGesture.value += 1
  selectedShapeId.value = clone.id
}

/** Put the caret in the selected text shape without hunting for a double-click. */
function editSelectedText() {
  const id = selectedShapeId.value
  if (id) annotateRef.value?.editText(id)
}

/**
 * Delete through the op, not the canvas: one shape is one step, so removing
 * the step IS the deletion — the same path the Delete key takes.
 */
function deleteSelectedAnnotation() {
  if (annotateRef.value) {
    annotateRef.value.deleteSelected()
    return
  }
  const id = selectedShapeId.value
  const opId = id ? opIdForShape(id) : null
  selectedShapeId.value = null
  if (opId) void removeOpWithGeometry(opId)
}

/**
 * Selecting a shape overrides the toolbar with THAT shape's status. The same
 * controls are a remote for the selection while one exists and initial
 * conditions when none does — showing next-shape defaults over a selected
 * shape made the toolbar lie about the thing with handles on it.
 */
watch(selectedShape, shape => {
  if (!shape) return
  const any = shape as any
  const stroke = any.strokeColor ?? any.textColor
  // Paint and all: the next shape inherits the selected one's gradient the
  // same way it inherits its color, because they are the same slot.
  if (stroke) annotatePaint.value = stroke
  if (typeof any.strokeWidth === 'number') annotateStrokeWidth.value = any.strokeWidth
  if ('backgroundColor' in any) annotateFillColor.value = any.backgroundColor ?? null
  annotateShapeEffect.value = any.style?.effect ?? 'none'
  if (shape.type === 'text') textStyle.value = textStyleOfShape(any)
  if (typeof any.opacity === 'number') annotateOpacity.value = any.opacity
})

/**
 * Colors sampled off the composite, so the pickers can offer the image's own
 * palette rather than only a fixed row of swatches.
 */
/**
 * The two splits in the right-hand column, both dragged and both remembered.
 *
 * How much room the stack deserves against the canvas, and Properties against
 * the stack, depends on what the user is doing — an Adjust panel wants height,
 * a long stack wants the opposite. Neither is a constant worth guessing.
 */
const sidebarWidth = ref(Number(localStorage.getItem('stimma_editor_sidebar')) || 320)
const propertiesHeight = ref(Number(localStorage.getItem('stimma_editor_properties')) || 0)
const sidebarEl = ref<HTMLElement | null>(null)

/**
 * Two fifths of the stack by default, measured rather than guessed — a pixel
 * constant is the wrong height on every window that is not the one it was
 * picked on. Only until the user drags it, after which their number wins.
 */
watch(sidebarEl, element => {
  if (!element || propertiesHeight.value) return
  propertiesHeight.value = Math.round(element.getBoundingClientRect().height * 0.4)
}, { flush: 'post' })

/** Drag along one axis, clamped, persisted on release. */
function startResize(
  event: PointerEvent,
  target: { value: number },
  key: string,
  axis: 'x' | 'y',
  min: number,
  max: number
) {
  event.preventDefault()
  const start = axis === 'x' ? event.clientX : event.clientY
  const startValue = target.value
  const onMove = (move: PointerEvent) => {
    const now = axis === 'x' ? move.clientX : move.clientY
    // Both handles sit on the leading edge of what they size, so the panel
    // grows as the pointer moves toward the origin.
    target.value = Math.max(min, Math.min(max, startValue + (start - now)))
  }
  const onUp = () => {
    localStorage.setItem(key, String(target.value))
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

const startSidebarResize = (event: PointerEvent) =>
  startResize(event, sidebarWidth, 'stimma_editor_sidebar', 'x', 260, 640)
const startPropertiesResize = (event: PointerEvent) =>
  startResize(event, propertiesHeight, 'stimma_editor_properties', 'y', 140, 760)

const imagePalette = ref<Array<{ r: number; g: number; b: number; a?: number }>>([])

function samplePalette() {
  const source = composite.value
  if (!source) return
  const scratch = document.createElement('canvas')
  scratch.width = 48
  scratch.height = 48
  const ctx = scratch.getContext('2d', { willReadFrequently: true })
  if (!ctx) return
  ctx.drawImage(source, 0, 0, 48, 48)
  const data = ctx.getImageData(0, 0, 48, 48).data
  // Coarse quantisation, most-common first: enough to surface the picture's
  // actual colors without pretending to be a clustering algorithm.
  const buckets = new Map<string, { r: number; g: number; b: number; n: number }>()
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] < 128) continue
    const key = `${data[i] >> 5}-${data[i + 1] >> 5}-${data[i + 2] >> 5}`
    const bucket = buckets.get(key)
    if (bucket) { bucket.r += data[i]; bucket.g += data[i + 1]; bucket.b += data[i + 2]; bucket.n++ }
    else buckets.set(key, { r: data[i], g: data[i + 1], b: data[i + 2], n: 1 })
  }
  imagePalette.value = [...buckets.values()]
    .sort((a, b) => b.n - a.n)
    .slice(0, 8)
    .map(c => ({ r: Math.round(c.r / c.n), g: Math.round(c.g / c.n), b: Math.round(c.b / c.n), a: 1 }))
}

/** A drag is many changes and one undo step. */
const cropGesture = ref(0)
const cropGestureKey = computed(() => `crop:${cropOpId.value}:${cropGesture.value}`)

function onCropRectChange(next: CropRect) {
  void applyCropChange(
    { rect: { x: next.x, y: next.y, width: next.width, height: next.height },
      cropRotation: next.rotation ?? 0 },
    cropGestureKey.value,
    true
  )
}

/** The drag ended: settle the geometry and start a new undo step. */
function onCropCommit() {
  cropGesture.value += 1
  void applyCropChange({}, cropGestureKey.value)
}

function chooseAspect(id: string) {
  cropAspect.value = id
  const preset = CROP_ASPECTS.find(a => a.id === id)
  const doc = stack.doc.value
  if (!doc) return
  const frame = cropInput.value ?? doc.canvas
  const ratio = preset?.ratio === -1
    ? frame.width / frame.height
    : preset?.ratio ?? null
  void applyCropChange({
    rect: cropRectForAspect(ratio, frame.width, frame.height),
  })
}

function rotateQuarter() {
  void applyCropChange({ rotation90: (((cropParamsOf().rotation90 ?? 0) + 1) % 4) as 0 | 1 | 2 | 3 })
}

function flip(axis: 'flipX' | 'flipY') {
  void applyCropChange({ [axis]: !cropParamsOf()[axis] })
}

// -- paint ---------------------------------------------------------------------

/**
 * The Paint layer this session is painting into. A layer IS a step, so
 * "New layer" simply forgets the current one and the next stroke creates the
 * next Paint row.
 */
let paintStrokeCommitQueue: Promise<void> = Promise.resolve()

async function commitPaintStroke(
  layer: HTMLCanvasElement,
  readsPixels: boolean,
  revision: number,
  opId: string,
) {
  if (!stack.doc.value) return
  const blob = await canvasToBlob(layer)
  const ref = await stack.uploadPayload(`${opId}-layer.png`, blob)
  let payloadRevision = 0

  if (!stack.opById(opId)) {
    const { head } = stackHashes(stack.doc.value)
    stack.addOp({
      id: opId,
      class: 'container',
      enabled: true,
      label: 'Paint',
      exec: { kind: 'paint' },
      raster_ref: ref,
      payload_to_document: payloadTransform(),
      payload_frame: payloadFrame(),
      blend: { feather_px: 0, opacity: 1 },
      // A pixel-reading engine baked what was underneath, so its layer carries
      // an advisory hash exactly like a generative patch.
      ...(readsPixels ? { sampled_input_hash: head } : {}),
    } as any)
    if (paintOpId.value === opId) selectedOpId.value = opId
  } else {
    const existing = stack.opById(opId) as any
    const opIndex = stack.doc.value.edits.findIndex(op => op.id === opId)
    // The uploaded layer is the current stage raster. Re-anchor that complete
    // payload into document space before replacing the old master pixels.
    existing.payload_to_document = payloadTransform(opIndex >= 0 ? opIndex : undefined)
    existing.payload_frame = payloadFrame(opIndex >= 0 ? opIndex : undefined)
    // The payload changed under the same ref; nudge the cache so the composite
    // picks it up.
    invalidatePayload(ref)
    stack.touchOp(opId)
    payloadRevision = (stack.opById(opId) as any)?._revision ?? 0
  }
  // The preview may only hand off after the compositor has rendered THIS
  // snapshot. Keeping it under the same ref@revision key loadAnchored requests
  // removes the stable-filename/browser-cache race entirely.
  payloadCache.set(`${ref}@${payloadRevision}`, layer)
  // The composite owns the stroke from here; the overlay handing off rather
  // than keeping a copy is what stops the halo and the paint that outlived
  // its own step being switched off.
  await render()
  if (paintOpId.value === opId) paintRef.value?.clearDisplay(revision)
}

/**
 * Pointer-up must stay cheap and synchronous: take the already-snapshotted
 * layer and queue its persistence. Serializing commits prevents two encodes
 * and uploads to the same raster_ref from finishing in reverse order.
 */
function onPaintStroke(
  layer: HTMLCanvasElement,
  readsPixels: boolean,
  revision: number,
) {
  // Reserve the step synchronously so another stroke emitted before the first
  // upload completes still targets this same layer.
  const opId = paintOpId.value || newOpId()
  paintOpId.value = opId
  paintStrokeCommitQueue = paintStrokeCommitQueue
    .then(() => commitPaintStroke(layer, readsPixels, revision, opId))
    .catch(err => {
      console.error('[imageStack] paint stroke commit failed', err)
      error.value = apiErrorMessage(err, 'Could not apply the paint stroke.')
    })
}

/**
 * Double-clicking a row re-enters THAT step rather than starting another: a
 * Paint layer keeps painting into itself, an Annotate step keeps accumulating
 * shapes, and a Crop reopens on its own input — which is what makes a second
 * crop a deliberate act rather than the only thing you can do.
 */
function enterContainerOp(op: any) {
  // Re-entering a step is canvas work: the selection tool lets the pointer go.
  disarmSelect()
  if (op.exec?.kind === 'crop') {
    family.value = 'crop'
    sub.value = null
    cropOpId.value = op.id
    cropAspect.value = 'free'
    void renderCropInput()
    return
  }
  if (op.class !== 'container') return
  if (op.exec?.kind === 'annotate') {
    // Re-entering an annotation means selecting it, since it is the step.
    family.value = 'annotate'
    sub.value = null
    selectedShapeId.value = (op.params?.shapes ?? [])[0]?.id ?? null
    return
  }
  if (op.exec?.kind === 'retouch-regions') {
    void enterRetouchOp(op.id)
    return
  }
  // Old documents used `retouch` (and, briefly, `sketch`) for raster Paint
  // layers. They remain re-enterable, but region-based Retouch will have its
  // own executor and must never be mistaken for a Paint layer.
  if (op.exec?.kind === 'paint' || op.exec?.kind === 'retouch' || op.exec?.kind === 'sketch') {
    void enterPaintOp(op.id)
  }
}

/**
 * Make the layer now, not on the next stroke.
 *
 * Clicking New layer and seeing nothing happen is the same as the button being
 * broken — and it made the first layer and every later one behave differently.
 * An empty layer composites as a no-op, so an unused one costs nothing but the
 * row that tells you it is there.
 */
async function startNewPaintLayer() {
  if (!stack.doc.value || !composite.value) return
  const opId = newOpId()
  const blank = document.createElement('canvas')
  blank.width = composite.value.width
  blank.height = composite.value.height
  const ref = await stack.uploadPayload(`${opId}-layer.png`, await canvasToBlob(blank))
  stack.addOp({
    id: opId,
    class: 'container',
    enabled: true,
    label: 'Paint',
    exec: { kind: 'paint' },
    raster_ref: ref,
    payload_to_document: payloadTransform(),
    payload_frame: payloadFrame(),
    blend: { feather_px: 0, opacity: 1 },
  } as any)
  paintOpId.value = opId
  selectedOpId.value = opId
  paintInitialLayer.value = null
  paintRef.value?.reset()
  void render()
}

function resetPaintSession() {
  paintOpId.value = null
  // Without this the next layer starts holding the previous one's pixels: the
  // canvas reloads `initialLayer` on any source change, so leaving it set
  // quietly copies the old strokes into the new step.
  paintInitialLayer.value = null
  paintRef.value?.reset()
}

/** Re-entering a Paint row paints into ITS layer rather than starting another. */
const paintInitialLayer = ref<HTMLCanvasElement | null>(null)

async function enterPaintOp(opId: string) {
  const op = stack.opById(opId) as any
  const doc = stack.doc.value
  if (!op?.raster_ref || !doc) return
  family.value = 'paint'
  paintOpId.value = opId
  const image = await loadImage(stack.payloadUrl(op.raster_ref, op._revision ?? 0))
  const index = doc.edits.findIndex(candidate => candidate.id === opId)
  const now = geometryBelow(doc, index >= 0 ? index : doc.edits.length)
  const canonical = (op.payload_to_document as Affine | undefined)
    ?? (op.payload_frame
      ? payloadToDocumentTransform(op.payload_frame) ?? undefined
      : undefined)
  const canvas = canonical
    ? rewritePayload(image, multiply(now.matrix, canonical), now.width, now.height)
    : (() => {
        const unanchored = document.createElement('canvas')
        unanchored.width = image.naturalWidth
        unanchored.height = image.naturalHeight
        unanchored.getContext('2d')!.drawImage(image, 0, 0)
        return unanchored
      })()
  paintInitialLayer.value = canvas
}

// -- retouch --------------------------------------------------------------------

const DEFAULT_RETOUCH_REGION_SETTINGS: RetouchRegionSettings = {
  opacity: 1,
  feather_px: 0,
  // The current Heal kernel performs its own local matching. These explicit,
  // adjustable finishing passes remain off until their renderers land.
  match_color: 0,
  match_noise: 0,
  ...photoAdjustmentRenderParams({}),
}

type MaskedAdjustmentKind =
  | 'light' | 'color' | 'detail'
  | 'mixer' | 'point' | 'grade'
  | 'adjust'
const MASKED_ADJUSTMENT_SUBS = [
  'light', 'color', 'detail', 'mixer', 'point', 'grade',
] as const

function isMaskedAdjustmentSub(value: string | null): value is Exclude<MaskedAdjustmentKind, 'adjust'> {
  return MASKED_ADJUSTMENT_SUBS.includes(value as any)
}

function isModelRetouchSub(value: string | null): value is 'remove' | 'repaint' | 'cutout' {
  return value === 'remove' || value === 'repaint' || value === 'cutout'
}

function isMaskedAdjustmentKind(value: RetouchRegionKind): value is MaskedAdjustmentKind {
  return value === 'adjust' || isMaskedAdjustmentSub(value)
}

interface RetouchGestureMetadata {
  tool: string
  source?: { x: number; y: number }
  target?: { x: number; y: number }
}

let retouchCommitQueue: Promise<void> = Promise.resolve()
let maskedAdjustCommitQueue: Promise<void> = Promise.resolve()
/** The one scoped-Adjust child whose mask the selection palette is editing. */
let maskedAdjustRegionId: string | null = null
/** Its container op — one single-region container per scoped Adjust step. */
let maskedAdjustOpId: string | null = null
/**
 * Creation-time identity for the armed scoped step: what an Adjust click
 * chose. Consumed by the mask commit when the region does not exist yet;
 * mask re-edits of an existing region carry no spec.
 */
let maskedAdjustSpec: {
  kind: Exclude<MaskedAdjustmentKind, 'adjust'>
  label: string
  seed?: Record<string, any>
} | null = null
const fragileRetouchRegions = new FragileEntryTracker()

/** Stop routing selection gestures into a scoped step's mask. */
function disarmMaskedAdjustmentEditing() {
  maskedAdjustRegionId = null
  maskedAdjustOpId = null
  maskedAdjustSpec = null
}

/**
 * Remove the current identity child before another masked tool takes its
 * place. Cancellation is recorded even when its mask upload is still in
 * flight, so that completion cannot resurrect the discarded child.
 */
function discardFragileMaskedAdjustment() {
  const regionId = maskedAdjustRegionId ?? selectedRetouchRegionId.value
  if (!fragileRetouchRegions.cancel(regionId)) return
  // Keep the tombstone until every already-queued mask publication for this
  // id has observed it. Clearing it immediately after removing a visible row
  // lets a slower second upload add the child back.
  const pendingPublications = maskedAdjustCommitQueue
  void pendingPublications.finally(() => {
    fragileRetouchRegions.forget(regionId!)
  })

  const location = retouchRegionLocation(regionId)
  if (location) {
    const regions = location.op.regions.filter(
      (region: RetouchRegion) => region.id !== regionId,
    )
    if (regions.length) {
      stack.setRegions(location.op.id, regions)
    } else {
      stack.removeOp(location.op.id)
      if (retouchOpId.value === location.op.id) retouchOpId.value = null
      if (selectedOpId.value === location.op.id) selectedOpId.value = null
    }
    void render().then(refreshRetouchInput)
  }

  if (selectedRetouchRegionId.value === regionId) {
    selectedRetouchRegionId.value = null
    selectedRetouchFeedbackVisible.value = false
  }
  if (hoveredRetouchRegionId.value === regionId) {
    hoveredRetouchRegionId.value = null
    hoveredRetouchMask.value = null
  }
  if (maskedAdjustRegionId === regionId) disarmMaskedAdjustmentEditing()
}

/**
 * Crop a repair to its alpha bounds and derive its retained mask.
 *
 * A spot repair should cost roughly the size of the spot, not two full-frame
 * PNGs. `payload_origin` puts both compact payloads back in authored space.
 */
function compactRetouchPayload(layer: HTMLCanvasElement): {
  result: HTMLCanvasElement
  mask: HTMLCanvasElement
  origin: [number, number]
} | null {
  const source = layer.getContext('2d', { willReadFrequently: true })!
  const full = source.getImageData(0, 0, layer.width, layer.height)
  let minX = layer.width
  let minY = layer.height
  let maxX = -1
  let maxY = -1
  for (let y = 0; y < layer.height; y++) {
    for (let x = 0; x < layer.width; x++) {
      if (full.data[(y * layer.width + x) * 4 + 3] === 0) continue
      minX = Math.min(minX, x)
      minY = Math.min(minY, y)
      maxX = Math.max(maxX, x)
      maxY = Math.max(maxY, y)
    }
  }
  if (maxX < minX || maxY < minY) return null

  const width = maxX - minX + 1
  const height = maxY - minY + 1
  const result = document.createElement('canvas')
  result.width = width
  result.height = height
  result.getContext('2d')!.drawImage(layer, minX, minY, width, height, 0, 0, width, height)

  const mask = document.createElement('canvas')
  mask.width = width
  mask.height = height
  const target = mask.getContext('2d')!
  const pixels = result.getContext('2d', { willReadFrequently: true })!
    .getImageData(0, 0, width, height)
  for (let i = 0; i < pixels.data.length; i += 4) {
    pixels.data[i] = 255
    pixels.data[i + 1] = 255
    pixels.data[i + 2] = 255
  }
  target.putImageData(pixels, 0, 0)
  return { result, mask, origin: [minX, minY] }
}

/** Retain only the authored alpha bounds of a workspace selection. */
function compactSelectionMask(sourceMask: HTMLCanvasElement): {
  mask: HTMLCanvasElement
  origin: [number, number]
} | null {
  const source = sourceMask.getContext('2d', { willReadFrequently: true })!
  const pixels = source.getImageData(0, 0, sourceMask.width, sourceMask.height)
  let minX = sourceMask.width
  let minY = sourceMask.height
  let maxX = -1
  let maxY = -1
  for (let y = 0; y < sourceMask.height; y++) {
    for (let x = 0; x < sourceMask.width; x++) {
      if (pixels.data[(y * sourceMask.width + x) * 4 + 3] === 0) continue
      minX = Math.min(minX, x)
      minY = Math.min(minY, y)
      maxX = Math.max(maxX, x)
      maxY = Math.max(maxY, y)
    }
  }
  if (maxX < minX || maxY < minY) return null

  const mask = document.createElement('canvas')
  mask.width = maxX - minX + 1
  mask.height = maxY - minY + 1
  mask.getContext('2d')!.drawImage(
    sourceMask,
    minX,
    minY,
    mask.width,
    mask.height,
    0,
    0,
    mask.width,
    mask.height,
  )
  return { mask, origin: [minX, minY] }
}

function copyCanvas(source: HTMLCanvasElement): HTMLCanvasElement {
  const copy = document.createElement('canvas')
  copy.width = source.width
  copy.height = source.height
  copy.getContext('2d')!.drawImage(source, 0, 0)
  return copy
}

/**
 * Save the workspace selection as a scoped Adjust step's mask.
 *
 * Creates the step's single-region container on the first publication; every
 * later completed selection gesture republishes the whole mask, so refinement
 * strokes replace the payload instead of creating more rows.
 */
async function commitMaskedAdjustmentMask(
  sourceMask: HTMLCanvasElement,
  opId: string,
  regionId: string,
  spec: typeof maskedAdjustSpec,
) {
  const doc = stack.doc.value
  if (!doc) return
  if (fragileRetouchRegions.isCancelled(regionId)) return
  const compact = compactSelectionMask(sourceMask)
  if (!compact) return

  const existingOp = stack.opById(opId) as any
  const existingRegions = (existingOp?.regions ?? []) as RetouchRegion[]
  const selected = existingRegions.find(
    region => region.id === regionId && isMaskedAdjustmentKind(region.kind),
  )
  const maskRef = await stack.uploadPayload(
    `${opId}-${regionId}-mask-${newOpId()}.png`,
    await canvasToBlob(compact.mask),
  )
  if (fragileRetouchRegions.isCancelled(regionId)) return
  payloadCache.set(`${maskRef}@0`, compact.mask)

  const opIndex = doc.edits.findIndex(op => op.id === opId)
  const region: RetouchRegion = {
    ...(selected ?? {}),
    id: regionId,
    kind: selected?.kind ?? spec?.kind ?? 'light',
    enabled: selected?.enabled ?? true,
    mask_ref: maskRef,
    // A republished raster replaces a parametric ramp outright — a region
    // holding both would render the stale gradient and ignore the pixels.
    mask: undefined,
    result_ref: undefined,
    payload_origin: compact.origin,
    payload_to_document: payloadTransform(
      opIndex >= 0 ? opIndex : undefined,
      compact.origin,
    ),
    payload_frame: payloadFrame(opIndex >= 0 ? opIndex : undefined),
    sampled_input_hash: null,
    settings: selected?.settings
      ? { ...selected.settings }
      : { ...DEFAULT_RETOUCH_REGION_SETTINGS, ...(spec?.seed ?? {}) },
  }

  if (!existingOp) {
    stack.addOp({
      id: opId,
      class: 'container',
      enabled: true,
      label: spec?.label ?? 'Adjust',
      exec: { kind: 'retouch-regions', version: 1 },
      defaults: { ...DEFAULT_RETOUCH_REGION_SETTINGS },
      regions: [region],
    } as any)
  } else if (selected) {
    stack.setRegions(
      opId,
      existingRegions.map(candidate => candidate.id === regionId ? region : candidate),
    )
  } else {
    stack.setRegions(opId, [...existingRegions, region])
  }

  selectedOpId.value = opId
  selectedRetouchRegionId.value = regionId
  // The workspace selection remains the visible source of truth after the
  // adjustment lands. Keep the region's separate diagnostic wash off so it
  // does not double up with the marching-ants feedback.
  selectedRetouchFeedbackVisible.value = false
  await render()
  await refreshRetouchInput()
  await refreshRetouchFeedback()
}

/** Publish the current mask to the ARMED scoped step (see the module vars). */
function queueMaskedAdjustmentMask(mask: HTMLCanvasElement) {
  const opId = maskedAdjustOpId
  const regionId = maskedAdjustRegionId
  if (!opId || !regionId) return
  const spec = maskedAdjustSpec
  // Snapshot synchronously: the workspace canvas is mutable and the next
  // gesture may arrive before this payload upload finishes.
  const snapshot = copyCanvas(mask)
  maskedAdjustCommitQueue = maskedAdjustCommitQueue
    .then(() => commitMaskedAdjustmentMask(snapshot, opId, regionId, spec))
    .catch(err => {
      console.error('[imageStack] masked adjustment commit failed', err)
      error.value = apiErrorMessage(err, 'Could not save the adjustment mask.')
    })
}

/**
 * The Heal engine produces pixels immediately for a responsive preview, but
 * persistence keeps the gesture as a child region: its own mask, result,
 * settings, authored frame, and sampling identity.
 */
async function commitRetouchRegion(
  result: HTMLCanvasElement,
  revision: number,
  opId: string,
  metadata: RetouchGestureMetadata,
) {
  const doc = stack.doc.value
  if (!doc) return

  const existing = stack.opById(opId) as any
  const regions = (existing?.regions ?? []) as RetouchRegion[]
  const compact = compactRetouchPayload(result)
  if (!compact) {
    retouchRef.value?.clearDisplay(revision)
    return
  }
  const regionId = newOpId()
  const [resultRef, maskRef] = await Promise.all([
    stack.uploadPayload(`${opId}-${regionId}-result.png`, await canvasToBlob(compact.result)),
    stack.uploadPayload(`${opId}-${regionId}-mask.png`, await canvasToBlob(compact.mask)),
  ])

  const opIndex = doc.edits.findIndex(op => op.id === opId)
  const hashes = stackHashes(doc)
  const sampledInputHash = opIndex >= 0 ? hashes.inputs[opIndex] : hashes.head
  const authoredToDocument = payloadTransform(opIndex >= 0 ? opIndex : undefined)
  const documentPoint = (point: { x: number; y: number } | undefined) => {
    if (!point || !authoredToDocument) return point
    const [x, y] = applyToPoint(authoredToDocument, point.x, point.y)
    return { x, y }
  }
  const region: RetouchRegion = {
    id: regionId,
    kind: metadata.tool === 'clone' || metadata.tool === 'patch' ? metadata.tool : 'heal',
    enabled: true,
    mask_ref: maskRef,
    result_ref: resultRef,
    payload_origin: compact.origin,
    payload_to_document: payloadTransform(
      opIndex >= 0 ? opIndex : undefined,
      compact.origin,
    ),
    payload_frame: payloadFrame(opIndex >= 0 ? opIndex : undefined),
    sampled_input_hash: sampledInputHash,
    ...(metadata.source ? { source: documentPoint(metadata.source) } : {}),
    ...(metadata.target ? { target: documentPoint(metadata.target) } : {}),
    points_in_document: !!authoredToDocument,
    settings: { ...DEFAULT_RETOUCH_REGION_SETTINGS },
  }

  // The result has a unique immutable ref, so revision zero is its permanent
  // cache key. This also lets the compositor take the overlay hand-off without
  // waiting for WebKit to fetch the PNG it just uploaded.
  payloadCache.set(`${resultRef}@0`, compact.result)
  payloadCache.set(`${maskRef}@0`, compact.mask)

  if (!existing) {
    stack.addOp({
      id: opId,
      class: 'container',
      enabled: true,
      label: 'Retouch',
      exec: { kind: 'retouch-regions', version: 1 },
      defaults: { ...DEFAULT_RETOUCH_REGION_SETTINGS },
      regions: [region],
      sampled_input_hash: sampledInputHash,
    } as any)
  } else {
    stack.setRegions(opId, [...regions, region])
  }

  retouchOpId.value = opId
  selectedOpId.value = opId
  selectedRetouchRegionId.value = regionId
  selectedRetouchFeedbackVisible.value = false
  await render()
  await refreshRetouchInput()
  await refreshRetouchFeedback()
  if (retouchOpId.value === opId) retouchRef.value?.clearDisplay(revision)
}

function onRetouchStroke(
  result: HTMLCanvasElement,
  _readsPixels: boolean,
  revision: number,
  metadata: RetouchGestureMetadata,
) {
  const opId = retouchOpId.value || newOpId()
  retouchOpId.value = opId
  retouchCommitQueue = retouchCommitQueue
    .then(() => commitRetouchRegion(result, revision, opId, metadata))
    .catch(err => {
      console.error('[imageStack] retouch region commit failed', err)
      error.value = apiErrorMessage(err, 'Could not apply the heal region.')
    })
}

async function refreshRetouchInput() {
  const doc = stack.doc.value
  const opId = retouchOpId.value
  if (!doc || !opId) {
    retouchInput.value = composite.value
    return
  }
  const index = doc.edits.findIndex(op => op.id === opId)
  retouchInput.value = index >= 0
    ? await compositor.renderUpTo(doc, index + 1)
    : composite.value
}

function retouchRegionLocation(regionId: string | null) {
  const doc = stack.doc.value
  if (!doc || !regionId) return null
  for (let index = 0; index < doc.edits.length; index++) {
    const op = doc.edits[index] as any
    if (op.exec?.kind !== 'retouch-regions') continue
    const region = (op.regions ?? []).find((candidate: RetouchRegion) => candidate.id === regionId)
    if (region) return { op, index, region }
  }
  return null
}

const selectedRetouchRegion = computed<RetouchRegion | null>(
  () => retouchRegionLocation(selectedRetouchRegionId.value)?.region ?? null,
)

/**
 * The selected region's gradient, mapped into the CURRENT composite frame so
 * its handles land on the pixels they describe. Geometry is authored in the
 * region's own frame, exactly like a payload, so a crop underneath moves the
 * handles with the image instead of leaving them behind.
 */
const selectedGradient = computed<GradientMask | null>(() => {
  const location = retouchRegionLocation(selectedRetouchRegionId.value)
  const mask = location?.region.mask
  if (!location || !isGradientMask(mask)) return null
  const doc = stack.doc.value
  if (!doc) return mask
  const now = geometryBelow(doc, location.index)
  const canonical = location.region.payload_to_document as Affine | undefined
  const created = location.region.payload_frame
  const carry = canonical
    ? multiply(now.matrix, canonical)
    : created
      ? coTransform(created.matrix as Affine, now.matrix as Affine)
      : null
  return carry ? transformGradientMask(mask, carry) : mask
})

/**
 * A gradient region keeps GEOMETRY, not pixels: nothing is uploaded, and the
 * compositor rasterises the ramp on every render. That is what keeps the
 * handles live for the life of the document.
 *
 * Called once per gesture, on release. The canvas owns the in-flight drag and
 * draws it locally, because a document write per pointer move re-renders the
 * composite at full resolution per mouse event — which buries the guides under
 * a second of pixel work and makes the tool feel broken.
 */
function onGradientChange(mask: GradientMask) {
  // The ramp lands as a workspace selection like every other gesture; what is
  // remembered here is its parametric identity, so an Adjust click can scope
  // with live geometry instead of the frozen raster. The canvas emits the
  // geometry first and publishes the raster second, both synchronously —
  // `gradientGestureLanding` is armed here and consumed by the change handler.
  rememberGradientDefaults(mask)
  gradientGestureLanding = true
  // Combined onto an existing selection, the published raster is a composite
  // and the ramp alone no longer describes it — raster scoping is the honest
  // fallback there.
  workspaceGradient =
    !selection.value || selectCombine.value === 'new' ? mask : null
}

/** A handle drag re-aims the region the handles belong to, and only that one. */
function onGradientEdit(mask: GradientMask) {
  const into = selectedGradientRegionId()
  if (!into) return
  persistGradientRegion(mask, { into })
}

/** The selected region, but only when it is a gradient we can edit in place. */
function selectedGradientRegionId(): string | null {
  const region = selectedRetouchRegion.value
  return region && isGradientMask(region.mask) ? region.id : null
}

function rememberGradientDefaults(mask: GradientMask) {
  if (mask.kind === 'linear') selectGradientSoftness.value = mask.softness
  else selectGradientFeather.value = mask.feather
}

/**
 * The inspector edits the region's own stored geometry, so its values are
 * already in the authored frame. The canvas hands back composite-space handles.
 * Saying which avoids transforming twice — invisible until a crop exists, and
 * then badly wrong.
 */
function onInspectorGradient(mask: GradientMask) {
  const into = selectedGradientRegionId()
  if (!into) return
  persistGradientRegion(mask, {
    into,
    space: 'authored',
    render: false,
    coalesceKey: `retouch-gradient:${into}`,
  })
  scheduleRetouchSettingsPreview()
}

function commitInspectorGradient() {
  void commitRetouchSettingsRender()
}

/**
 * Re-aim an EXISTING gradient region. Creation goes through Adjust
 * (`addScopedLevelEdit`); this only rewrites geometry the region already has.
 */
function persistGradientRegion(
  mask: GradientMask,
  options: {
    into: string
    space?: 'composite' | 'authored'
    render?: boolean
    coalesceKey?: string
  },
) {
  rememberGradientDefaults(mask)
  const location = retouchRegionLocation(options.into)
  if (!location) return
  const existing = location.region
  // An edit maps back into the frame THAT REGION was authored in, which is not
  // necessarily the frame a new region would get: regions outlive crops.
  const frame = existing.payload_frame
  const canonical = existing.payload_to_document as Affine | undefined

  // Handles are dragged in composite space; the region stores them in its own
  // authored frame, so the inverse of the carry goes back the way it came.
  const authored = options.space === 'authored'
    ? mask
    : authoredGradient(mask, frame, canonical, location.index)
  if (!authored) return

  stack.setRegions(location.op.id, location.op.regions.map((region: RetouchRegion) =>
    region.id === options.into ? { ...region, mask: authored } : region
  ), options.coalesceKey)

  if (options.render !== false) {
    armedSelectTool.value = null
    void render().then(refreshRetouchInput)
  }
}

/** Composite-space geometry back into the region's authored frame. */
function authoredGradient(
  mask: GradientMask,
  frame: { matrix: number[]; width: number; height: number } | undefined,
  canonical: Affine | undefined,
  opIndex: number,
): GradientMask | null {
  const doc = stack.doc.value
  if (!doc) return mask
  const now = geometryBelow(doc, opIndex >= 0 ? opIndex : doc.edits.length)
  const carry = canonical
    ? multiply(now.matrix, canonical)
    : frame
      ? coTransform(frame.matrix as Affine, now.matrix as Affine)
      : null
  if (!carry) return mask
  const back = invertMatrix(carry)
  return back ? transformGradientMask(mask, back) : mask
}

/** Expand a compact retained mask and carry it into the region's current frame. */
async function retouchFeedbackMask(regionId: string | null): Promise<HTMLCanvasElement | null> {
  const location = retouchRegionLocation(regionId)
  if (!location) return null
  const { index, region } = location
  const doc = stack.doc.value!
  const now = geometryBelow(doc, index)
  const created = region.payload_frame
  const canonical = region.payload_to_document as Affine | undefined
  const authored = document.createElement('canvas')
  authored.width = created?.width ?? now.width
  authored.height = created?.height ?? now.height
  // A gradient region owns no payload; its coverage comes from the same
  // rasteriser the compositor uses, so feedback and render agree by construction.
  if (isGradientMask(region.mask)) {
    authored.getContext('2d')!.drawImage(
      gradientMaskCanvas(region.mask, authored.width, authored.height), 0, 0,
    )
  } else {
    if (!region.mask_ref) return null
    const key = `${region.mask_ref}@0`
    let payload = payloadCache.get(key)
    if (!payload) {
      try {
        payload = await loadImage(stack.payloadUrl(region.mask_ref, 0))
      } catch {
        return null
      }
    }
    if (canonical) {
      const matrix = multiply(now.matrix, canonical)
      return rewritePayload(payload, matrix, now.width, now.height)
    }
    const [x, y] = region.payload_origin ?? [0, 0]
    authored.getContext('2d')!.drawImage(payload, x, y)
  }
  if (canonical) {
    const matrix = multiply(now.matrix, canonical)
    return matrix && !isIdentity(matrix)
      ? rewritePayload(authored, matrix, now.width, now.height)
      : authored
  }
  if (!created) return authored
  const matrix = coTransform(created.matrix as Affine, now.matrix)
  return matrix && !isIdentity(matrix)
    ? rewritePayload(authored, matrix, now.width, now.height)
    : authored
}

/** Carry a model patch's full-frame mask into its current stack geometry. */
async function modelFeedbackMask(opId: string): Promise<HTMLCanvasElement | null> {
  const doc = stack.doc.value
  if (!doc) return null
  const index = doc.edits.findIndex(op => op.id === opId)
  if (index < 0) return null
  const op = doc.edits[index] as any
  if (op.class !== 'patch' || !op.mask_ref) return null

  const now = geometryBelow(doc, index)
  const created = op.payload_frame
  const canonical = op.payload_to_document as Affine | undefined
  const authored = document.createElement('canvas')
  authored.width = created?.width ?? now.width
  authored.height = created?.height ?? now.height
  try {
    const payload = await loadImage(stack.payloadUrl(op.mask_ref, 0))
    const context = authored.getContext('2d', { willReadFrequently: true })!
    context.drawImage(payload, 0, 0, authored.width, authored.height)
    // Generative masks are opaque white-on-black because the STP tool needs
    // luminance. Canvas feedback consumes alpha, so translate the stored shape
    // instead of outlining the entire opaque frame.
    const pixels = context.getImageData(0, 0, authored.width, authored.height)
    for (let i = 0; i < pixels.data.length; i += 4) {
      const alpha = pixels.data[i]
      pixels.data[i] = 255
      pixels.data[i + 1] = 255
      pixels.data[i + 2] = 255
      pixels.data[i + 3] = alpha
    }
    context.putImageData(pixels, 0, 0)
  } catch {
    return null
  }
  if (canonical) {
    const matrix = multiply(now.matrix, canonical)
    return !isIdentity(matrix)
      ? rewritePayload(authored, matrix, now.width, now.height)
      : authored
  }
  if (!created) return authored
  const matrix = coTransform(created.matrix as Affine, now.matrix)
  return matrix && !isIdentity(matrix)
    ? rewritePayload(authored, matrix, now.width, now.height)
    : authored
}

function retouchFeedbackPoint(
  location: ReturnType<typeof retouchRegionLocation>,
  point: { x: number; y: number } | undefined,
) {
  if (!location || !point) return null
  if (location.region.points_in_document) {
    const now = geometryBelow(stack.doc.value!, location.index)
    const [x, y] = applyToPoint(now.matrix, point.x, point.y)
    return { x, y }
  }
  const created = location.region.payload_frame
  if (!created) return point
  const now = geometryBelow(stack.doc.value!, location.index)
  const matrix = coTransform(created.matrix as any, now.matrix)
  if (!matrix) return point
  const [x, y] = applyToPoint(matrix, point.x, point.y)
  return { x, y }
}

let retouchFeedbackRevision = 0
async function refreshRetouchFeedback() {
  const revision = ++retouchFeedbackRevision
  // Identity is the authority. Clear stale canvases synchronously so a
  // deleted/unhovered child cannot remain visible during async payload work.
  if (!selectedRetouchRegionId.value) {
    selectedRetouchMask.value = null
    selectedRetouchSource.value = null
    selectedRetouchTarget.value = null
    selectedRetouchIsPatch.value = false
  }
  if (!hoveredRetouchRegionId.value) {
    hoveredRetouchMask.value = null
    hoveredRetouchSource.value = null
    hoveredRetouchTarget.value = null
    hoveredRetouchIsPatch.value = false
  }
  const [selected, hovered] = await Promise.all([
    retouchFeedbackMask(selectedRetouchRegionId.value),
    retouchFeedbackMask(hoveredRetouchRegionId.value),
  ])
  if (revision !== retouchFeedbackRevision) return
  selectedRetouchMask.value = selected
  hoveredRetouchMask.value = hovered
  const location = retouchRegionLocation(selectedRetouchRegionId.value)
  selectedRetouchSource.value = retouchFeedbackPoint(location, location?.region.source)
  selectedRetouchTarget.value = retouchFeedbackPoint(location, location?.region.target)
  selectedRetouchIsPatch.value = location?.region.kind === 'patch'
  // Hover owns the canvas while it is present, even when it is the currently
  // selected child. Do not suppress its source geometry in that case.
  const hoveredLocation = retouchRegionLocation(hoveredRetouchRegionId.value)
  hoveredRetouchSource.value = retouchFeedbackPoint(
    hoveredLocation,
    hoveredLocation?.region.source,
  )
  hoveredRetouchTarget.value = retouchFeedbackPoint(
    hoveredLocation,
    hoveredLocation?.region.target,
  )
  hoveredRetouchIsPatch.value = hoveredLocation?.region.kind === 'patch'
}

function selectRetouchRegion(opId: string, regionId: string) {
  // Picking a region by hand ends any other step's mask-editing session.
  if (maskedAdjustRegionId && maskedAdjustRegionId !== regionId) {
    disarmMaskedAdjustmentEditing()
  }
  selectedOpId.value = opId
  selectedShapeId.value = null
  const alreadySelected = selectedRetouchRegionId.value === regionId
  const deselecting = alreadySelected
  selectedRetouchRegionId.value = deselecting ? null : regionId
  selectedRetouchFeedbackVisible.value = !deselecting
  void refreshRetouchFeedback()
}

function hoverRetouchRegion(regionId: string | null) {
  hoveredRetouchRegionId.value = regionId
  void refreshRetouchFeedback()
}

let allRetouchFeedbackRevision = 0
async function hoverRetouchOp(opId: string, hovering: boolean) {
  if (!hovering) {
    if (hoveredRetouchOpId.value === opId) hoveredRetouchOpId.value = null
    allRetouchFeedback.value = []
    allRetouchFeedbackRevision++
    return
  }

  hoveredRetouchOpId.value = opId
  const revision = ++allRetouchFeedbackRevision
  const op = stack.opById(opId) as any
  if (op?.class === 'patch') {
    const mask = await modelFeedbackMask(opId)
    if (revision !== allRetouchFeedbackRevision || hoveredRetouchOpId.value !== opId) return
    allRetouchFeedback.value = mask ? [{ mask, isPatch: false }] : []
    return
  }
  if (op?.exec?.kind !== 'retouch-regions') {
    allRetouchFeedback.value = []
    return
  }
  const feedback = await Promise.all(
    (op.regions ?? []).map(async (region: RetouchRegion) => {
      const mask = await retouchFeedbackMask(region.id)
      if (!mask) return null
      const location = retouchRegionLocation(region.id)
      return {
        mask,
        source: retouchFeedbackPoint(location, region.source),
        target: retouchFeedbackPoint(location, region.target),
        isPatch: region.kind === 'patch',
      }
    }),
  )
  if (revision !== allRetouchFeedbackRevision || hoveredRetouchOpId.value !== opId) return
  allRetouchFeedback.value = feedback.filter(
    (item): item is NonNullable<typeof item> => item !== null,
  )
}

async function enterRetouchOp(opId: string) {
  const op = stack.opById(opId) as any
  if (op?.exec?.kind !== 'retouch-regions') return
  family.value = 'retouch'
  sub.value = 'heal'
  retouchOpId.value = opId
  selectedOpId.value = opId
  retouchRef.value?.reset()
  await refreshRetouchInput()
}

function resetRetouchSession() {
  retouchOpId.value = null
  retouchInput.value = null
  maskedAdjustRegionId = null
  retouchRef.value?.reset()
}

/**
 * Blend and mask drags render the document at fitted display resolution.
 * Masked photographic adjustments use the GPU delta preview above instead;
 * expensive source pixels are touched only once on pointer-up.
 */
let retouchPreviewFrame: number | null = null
let retouchPreviewInFlight = false
let retouchPreviewQueued = false
let retouchPreviewRevision = 0
let retouchPreviewSizeKey = ''

function scaledRetouchPreviewDocument(): any | null {
  const doc = displayDoc.value
  const source = composite.value
  if (!doc || !source || !displayBox.value.width || !displayBox.value.height) return null
  // Clarity/Blur/Sharpen are several full pixel passes. Half a
  // megapixel is enough for a faithful fitted preview and keeps those passes
  // interactive on the main thread.
  const pixelBudgetScale = Math.sqrt(500_000 / Math.max(1, source.width * source.height))
  const scale = Math.min(
    1,
    pixelBudgetScale,
    displayBox.value.width / Math.max(1, source.width),
    displayBox.value.height / Math.max(1, source.height),
  )
  const preview = JSON.parse(JSON.stringify(doc))
  preview.canvas = {
    width: Math.max(1, Math.round(doc.canvas.width * scale)),
    height: Math.max(1, Math.round(doc.canvas.height * scale)),
  }
  preview._preview_scale = scale
  for (const op of preview.edits ?? []) {
    if (op.class === 'patch' && op.blend?.feather_px) {
      op.blend.feather_px *= scale
    }
    if (op.exec?.kind !== 'retouch-regions') continue
    for (const region of op.regions ?? []) {
      if (!region.settings) continue
      region.settings.feather_px = (region.settings.feather_px ?? 0) * scale
      if (region.settings.blur) region.settings.blur *= scale
      if (region.settings.sharpenRadius) {
        region.settings.sharpenRadius = Math.max(
          0.5,
          region.settings.sharpenRadius * scale,
        )
      }
      if (region.settings.grainSize) {
        region.settings.grainSize = Math.max(
          0,
          (1 + region.settings.grainSize / 12) * scale * 12 - 12,
        )
      }
    }
  }
  return preview
}

function scheduleRetouchSettingsPreview() {
  retouchPreviewQueued = true
  retouchPreviewRevision++
  if (retouchPreviewInFlight || retouchPreviewFrame !== null) return
  retouchPreviewFrame = requestAnimationFrame(() => {
    retouchPreviewFrame = null
    void flushRetouchSettingsPreview()
  })
}

async function flushRetouchSettingsPreview() {
  if (retouchPreviewInFlight || !retouchPreviewQueued) return
  retouchPreviewQueued = false
  retouchPreviewInFlight = true
  const revision = retouchPreviewRevision
  try {
    const previewDoc = scaledRetouchPreviewDocument()
    if (!previewDoc) return
    const sizeKey = `${previewDoc.canvas.width}x${previewDoc.canvas.height}`
    if (sizeKey !== retouchPreviewSizeKey) {
      retouchPreviewSizeKey = sizeKey
      retouchPreviewCompositor.clear()
    }
    const preview = await retouchPreviewCompositor.render(previewDoc)
    if (revision !== retouchPreviewRevision) return
    const target = displayCanvas.value
    if (!target) return
    target.width = preview.width
    target.height = preview.height
    const ctx = target.getContext('2d')!
    ctx.clearRect(0, 0, target.width, target.height)
    ctx.drawImage(preview, 0, 0)
  } finally {
    retouchPreviewInFlight = false
    if (retouchPreviewQueued) scheduleRetouchSettingsPreview()
  }
}

async function commitRetouchSettingsRender() {
  cancelLiveAdjustPreview()
  retouchPreviewRevision++
  retouchPreviewQueued = false
  if (retouchPreviewFrame !== null) {
    cancelAnimationFrame(retouchPreviewFrame)
    retouchPreviewFrame = null
  }
  await render()
  await refreshRetouchInput()
}

function setRetouchRegionSettings(
  patch: Partial<RetouchRegionSettings>,
  coalesceKey: string,
) {
  const location = retouchRegionLocation(selectedRetouchRegionId.value)
  if (!location) return
  // The first substantive property gesture commits the child. It may still
  // be visually neutral if the slider lands back on its default, just like a
  // top-level Adjust step: the person's interaction, not value comparison,
  // is the durable boundary.
  fragileRetouchRegions.commit(location.region.id)
  // The same boundary ends the step's mask-editing session. While the step
  // is fresh, selection gestures refine ITS mask (rough-select, then tighten);
  // once a slider has moved, the adjustment is committed and the next
  // selection is a new selection — not a silent re-aim of this step.
  // "Edit mask" in Properties re-arms deliberately.
  if (maskedAdjustRegionId === location.region.id) disarmMaskedAdjustmentEditing()
  const before = { ...location.region.settings }
  // Once a property moves, the person is judging the photograph rather than
  // constructing the region. Keep the mask intact but get its wash and ants
  // off the pixels immediately.
  dismissCanvasFeedback()
  stack.setRegions(
    location.op.id,
    location.op.regions.map((region: RetouchRegion) =>
      region.id === location.region.id
        ? { ...region, settings: { ...region.settings, ...patch } }
        : region
    ),
    coalesceKey,
  )
  const updated = retouchRegionLocation(location.region.id)?.region.settings
  const changesMaskBlend = 'opacity' in patch || 'feather_px' in patch
  if (updated && isMaskedAdjustmentKind(location.region.kind) && !changesMaskBlend) {
    void previewAdjustment(
      `retouch:${location.region.id}`,
      before,
      updated,
      {
        mask: selectedRetouchMask.value ?? retouchFeedbackMask(location.region.id),
        maskStrength: updated.opacity ?? 1,
      },
    )
  } else {
    scheduleRetouchSettingsPreview()
  }
}

function setRetouchRegionEnabled(opId: string, regionId: string, enabled: boolean) {
  const op = stack.opById(opId) as any
  if (op?.exec?.kind !== 'retouch-regions') return
  fragileRetouchRegions.commit(regionId)
  stack.setRegions(opId, op.regions.map((region: RetouchRegion) =>
    region.id === regionId ? { ...region, enabled } : region
  ))
  void refreshRetouchFeedback()
  void render().then(refreshRetouchInput)
}

function removeRetouchRegion(opId: string, regionId: string) {
  const op = stack.opById(opId) as any
  if (op?.exec?.kind !== 'retouch-regions') return
  fragileRetouchRegions.forget(regionId)
  // Removing a row can remove the DOM under the pointer, so mouseleave is not
  // guaranteed. End every hover path before mutating the stack.
  hoveredRetouchRegionId.value = null
  hoveredRetouchMask.value = null
  hoveredRetouchOpId.value = null
  allRetouchFeedback.value = []
  allRetouchFeedbackRevision++
  const regions = op.regions.filter((region: RetouchRegion) => region.id !== regionId)
  if (regions.length) stack.setRegions(opId, regions)
  else {
    stack.removeOp(opId)
    if (retouchOpId.value === opId) resetRetouchSession()
    if (selectedOpId.value === opId) selectedOpId.value = null
  }
  if (selectedRetouchRegionId.value === regionId) {
    selectedRetouchRegionId.value = null
    selectedRetouchFeedbackVisible.value = false
  }
  if (maskedAdjustRegionId === regionId) maskedAdjustRegionId = null
  void refreshRetouchFeedback()
  // Region rows disappear immediately; coalesce a rapid trash run into one
  // full-resolution replay of the surviving regions.
  void render({ settleMs: RENDER_BURST_SETTLE_MS }).then(refreshRetouchInput)
}

/**
 * Selection is referential: if undo, row removal, or another edit path drops
 * its region, feedback and refinement must disappear in the same tick.
 */
watch(
  () => (stack.doc.value?.edits ?? []).flatMap((op: any) =>
    op.exec?.kind === 'retouch-regions'
      ? (op.regions ?? []).map((region: RetouchRegion) => region.id)
      : []
  ),
  liveIds => {
    const live = new Set(liveIds)
    let changed = false
    if (selectedRetouchRegionId.value && !live.has(selectedRetouchRegionId.value)) {
      selectedRetouchRegionId.value = null
      selectedRetouchFeedbackVisible.value = false
      changed = true
    }
    if (hoveredRetouchRegionId.value && !live.has(hoveredRetouchRegionId.value)) {
      hoveredRetouchRegionId.value = null
      changed = true
    }
    if (maskedAdjustRegionId && !live.has(maskedAdjustRegionId)) {
      disarmMaskedAdjustmentEditing()
    }
    if (changed) void refreshRetouchFeedback()
  },
)

// -- annotate --------------------------------------------------------------------

/**
 * Annotations accumulate into one Annotate step per session. The shapes are the
 * params, so the step stays vector and re-entering it is lossless.
 */
/**
 * Dragging and on-canvas text entry stay local to the vector overlay. It
 * reports the finished shape list here once at mouseup / text-session end, so
 * the persistent stack, journal and autosave see one edit. One gesture, one
 * undo.
 */
const annotateGesture = ref(0)
const annotateGestureKey = computed(() => `annotate:${annotateGesture.value}`)

/**
 * Reconcile the canvas's shape list against one step per shape.
 *
 * The canvas owns the list and reports the whole of it; this turns that into
 * creations, updates and removals. New shapes become steps at the top, changed
 * ones update in place under the gesture's coalesce key, and a shape that has
 * gone takes its step with it.
 */
function onAnnotationsChange(shapes: Shape[]) {
  const doc = stack.doc.value
  if (!doc) return
  const head = geometryBelow(doc, doc.edits.length)
  const documentFromHead = invertMatrix(head.matrix)
  if (!documentFromHead) return
  const inDocument = (shape: Shape): Shape => transformShapes(
    [shape],
    documentFromHead,
    head.width,
    head.height,
    doc.canvas.width,
    doc.canvas.height,
  )[0] as Shape

  const seen = new Set(shapes.map(shape => shape.id))
  const shapeToOp = new Map<string, string>()
  for (const op of annotateOps.value) {
    for (const shape of ((op as any).params?.shapes ?? []) as Shape[]) {
      shapeToOp.set(shape.id, op.id)
    }
  }

  const nextById = new Map(doc.edits.map(op => [op.id, op]))
  const additions: any[] = []
  let newestOpId: string | null = null

  for (const shape of shapes) {
    const documentShape = inDocument(shape)
    const opId = shapeToOp.get(shape.id)
    const existing = opId ? nextById.get(opId) as any : null
    if (opId && existing) {
      nextById.set(opId, {
        ...existing,
        label: shapeLabel(shape),
        shapes_in_document: true,
        params: { ...(existing.params || {}), shapes: [documentShape] },
      })
      continue
    }

    newestOpId = newOpId()
    additions.push({
      id: newestOpId,
      class: 'container',
      enabled: true,
      label: shapeLabel(shape),
      exec: { kind: 'annotate' },
      shapes_in_document: true,
      params: { shapes: [documentShape] },
    })
  }

  // Only the enabled ops the canvas was given can be reconciled against what
  // it returned. Hidden annotation rows remain untouched.
  const removed = new Set(
    visibleAnnotateOps.value
      .filter(op => {
        const held = ((op as any).params?.shapes ?? []) as Shape[]
        return !held.every(shape => seen.has(shape.id))
      })
      .map(op => op.id)
  )
  const nextEdits = [
    ...doc.edits.flatMap(op => removed.has(op.id) ? [] : (nextById.get(op.id) ?? [])),
    ...additions,
  ]

  stack.replaceEdits(nextEdits, annotateGestureKey.value)
  if (newestOpId) selectedOpId.value = newestOpId
  // The live vector overlay already owns these pixels. Rebuilding the stage
  // here would only replay the stack, resample the palette and repaint the
  // source beneath an overlay that has not changed. When no overlay is active
  // (for example, an inspector edit while another family is open), the
  // composite does need the updated annotation.
  if (!annotationOverlayActive.value) void render()
}

/**
 * The stack takes the keyboard.
 *
 * A list of things you can select is a list you expect to walk with the arrow
 * keys and clear with Delete — and deleting should land you on the next row,
 * not nowhere, so a run of deletions is one gesture repeated rather than a
 * click between each.
 */
function focusRow(opId: string | null) {
  if (!opId) return
  selectedOpId.value = opId
  void nextTick(() => {
    const element = sidebarEl.value?.querySelector<HTMLElement>(`[data-op-id="${opId}"]`)
    element?.focus()
  })
}

async function onStackKeydown(event: KeyboardEvent) {
  const doc = stack.doc.value
  const current = selectedOpId.value
  if (!doc || !current) return
  const index = doc.edits.findIndex(op => op.id === current)
  if (index < 0) return

  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    // The list is drawn top-down with the newest first, so Down walks toward
    // the base — the direction the rows actually run on screen.
    const next = doc.edits[event.key === 'ArrowDown' ? index - 1 : index + 1]
    if (next) focusRow(next.id)
    return
  }

  if (event.key === 'Delete' || event.key === 'Backspace') {
    event.preventDefault()
    // Whatever sits where this row was, once it is gone.
    const after = doc.edits[index - 1] ?? doc.edits[index + 1] ?? null
    const nextId = after?.id ?? null
    await removeOpWithGeometry(current)
    if (nextId) focusRow(nextId)
    else selectedOpId.value = null
  }
}

/**
 * Selecting a row selects what the row IS.
 *
 * For an annotation that means the shape, so the canvas puts handles on it and
 * the inspector shows its properties — a row that named a thing but selected
 * nothing was a dead end.
 */
function onRowSelect(op: any) {
  if (maskedAdjustOpId && maskedAdjustOpId !== op.id) disarmMaskedAdjustmentEditing()
  selectedOpId.value = op.id
  // A parent-row click selects the parent, not whichever child happened to be
  // selected before it. Child clicks stop propagation and take their own path.
  if (selectedRetouchRegionId.value || hoveredRetouchRegionId.value) {
    selectedRetouchRegionId.value = null
    hoveredRetouchRegionId.value = null
    selectedRetouchFeedbackVisible.value = false
    void refreshRetouchFeedback()
  }
  // A scoped Adjust step is one region wearing a row: clicking it should open
  // its controls, not an empty parent surface.
  if (
    op.exec?.kind === 'retouch-regions'
    && (op.regions ?? []).length === 1
    && isMaskedAdjustmentKind(op.regions[0].kind)
  ) {
    selectedRetouchRegionId.value = op.regions[0].id
    selectedRetouchFeedbackVisible.value = true
    void refreshRetouchFeedback()
  }
  selectedShapeId.value = op.exec?.kind === 'annotate'
    ? (op.params?.shapes ?? [])[0]?.id ?? null
    : null
  // Selecting a shape puts handles on the canvas; an armed selection tool
  // would sit on top of them with the pointer.
  if (selectedShapeId.value) disarmSelect()
}

/**
 * The canvas follows the host's shape selection too — a row click or a family
 * switch must put handles up, and the canvas keeps its own selection state for
 * gesture-time reasons, so it is pushed rather than passed.
 */
watch([selectedShapeId, annotateRef], ([id]) => {
  annotateRef.value?.setSelected(id)
})

/** Selecting an annotation selects its step, so the stack follows the canvas. */
function onShapeSelected(shapeId: string | null) {
  selectedShapeId.value = shapeId
  const opId = shapeId ? opIdForShape(shapeId) : null
  if (opId) {
    selectedOpId.value = opId
  } else {
    const selectedOp = selectedOpId.value ? stack.opById(selectedOpId.value) as any : null
    if (selectedOp?.exec?.kind === 'annotate') selectedOpId.value = null
  }
}

/**
 * The gesture ended: the next one starts its own undo step, and a tool that
 * just CREATED something hands back to Select.
 *
 * One-shot creation is what removes the create-versus-move ambiguity rather
 * than arbitrating it: with no armed creation tool, a drag on top of a shape
 * can only mean move. Drawing another takes one keystroke, and you almost
 * always want to adjust the thing you just made first.
 */
function onAnnotationCommit(action: string) {
  annotateGesture.value += 1
  if (family.value === 'annotate' && action.startsWith('Draw')) sub.value = null
}

// -- selection handoff ------------------------------------------------------------

/**
 * Arm a selection tool: the overlay takes the pointer, the open family is
 * SUSPENDED — its session, step and controls all survive underneath. Clicking
 * the armed tool again hands the pointer back.
 */
function armSelectTool(id: SelectToolId, force = false) {
  // Crop replaces the display box with its own viewport, so there is nothing
  // to select over; arming from inside it leaves it first.
  if (family.value === 'crop') leaveMode()
  if (!force && armedSelectTool.value === id) {
    disarmSelect()
    return
  }
  armedSelectTool.value = id
  lastSelectTool.value = id
  writeToolPrefs({ selectTool: id })
  // Arming Object is the earliest honest signal a segmentation is coming;
  // encode now so the click only pays the decoder.
  if (id === 'object') warmAiSelect()
}

/**
 * Hand the pointer back to whatever family is open. Reaching for any control
 * that implies a canvas gesture — a paint engine, an annotate sub-tool, a
 * family — calls this: a selection tool that stays armed past the user's
 * attention is a broken pointer.
 */
function disarmSelect() {
  armedSelectTool.value = null
}

/** Island-only settings: tuning the armed tool must never disarm it. */
function onSelectionSet(patch: Record<string, any>) {
  if ('combine' in patch) selectCombine.value = patch.combine
  if ('featherPx' in patch) selectFeather.value = patch.featherPx
  if ('tolerance' in patch) selectTolerance.value = patch.tolerance
  if ('spread' in patch) selectSpread.value = patch.spread
  if ('growPx' in patch) selectGrow.value = patch.growPx
  if ('antialias' in patch) selectAntialias.value = patch.antialias
  if ('selectBrushSize' in patch) selectBrushSize.value = patch.selectBrushSize
  // The gradient sliders edit the ramp on the canvas when there is one, and the
  // default for the next ramp when there is not. Same control, and the mask
  // thumbnail plus the guides make which one is happening obvious.
  if ('gradientSoftness' in patch) {
    selectGradientSoftness.value = patch.gradientSoftness
    retuneSelectedGradient(patch.gradientSoftness, 'linear')
  }
  if ('gradientFeather' in patch) {
    selectGradientFeather.value = patch.gradientFeather
    retuneSelectedGradient(patch.gradientFeather, 'radial')
  }
}

function retuneSelectedGradient(value: number, kind: 'linear' | 'radial') {
  const current = selectedGradient.value
  if (!current || current.kind !== kind) return
  onGradientEdit(withGradientSlider(current, value), true)
}

function clearSelection() {
  // Through the overlay when it exists (it also cancels an in-flight gesture);
  // straight at the model when crop has the display box (overlay unmounted) —
  // otherwise the ants would come back the moment crop closes.
  if (selectRef.value) selectRef.value.clear()
  else selModel.clearSelection()
  selection.value = null
  selectionMaster = null
  selectionToDocument = null
  selectionAppliedKey = null
  // Combine modes describe how a gesture meets an existing selection. Once
  // there is no existing selection, the next gesture starts a new one.
  selectCombine.value = combineAfterSelectionChange(selectCombine.value, false)
}

function invertSelection() {
  selectRef.value?.invert()
}

// -- AI select (prompt-to-mask) ---------------------------------------------

const aiSelectBusy = ref(false)
const aiSelectError = ref<string | null>(null)

/** Longest side sent to segmentation. SAM3 works at ~1k; sending more is transfer cost, not quality. */
const AI_SELECT_MAX_SIDE = 1536

/**
 * The last Object click's granularity stack. The tracker returns the clicked
 * object at every granularity (object → part → subpart, area-descending);
 * clicking the SAME spot again steps to the next one, locally, against the
 * selection as it was before the first application — no second request.
 */
let objectPickState: {
  src: HTMLCanvasElement
  x: number
  y: number
  masks: HTMLImageElement[]
  index: number
  mode: SelectionMode
  before: HTMLCanvasElement | null
} | null = null
/** True while an applyMask below is publishing, so onSelectionChange can tell
 *  our own change events from a gesture that invalidates the cycle stack. */
let applyingAiMask = false

/**
 * The composite as segmentation sees it. Warm and select MUST both come
 * through here: the backend's embedding cache is keyed on the sent bytes, so
 * a warm encoded any other way buys nothing.
 */
function aiSelectCanvas(src: HTMLCanvasElement): HTMLCanvasElement {
  const scale = Math.min(1, AI_SELECT_MAX_SIDE / Math.max(src.width, src.height))
  if (scale >= 1) return src
  const sent = document.createElement('canvas')
  sent.width = Math.round(src.width * scale)
  sent.height = Math.round(src.height * scale)
  sent.getContext('2d')!.drawImage(src, 0, 0, sent.width, sent.height)
  return sent
}

/**
 * Fire-and-forget encoder warm-up, sent when the Object tool arms: model load
 * plus the encoder pass happen while the user aims, so the click itself pays
 * only the decoder. Arming is the earliest signal of intent worth this much
 * compute — composite edits do NOT re-warm.
 */
function warmAiSelect() {
  const src = composite.value
  if (!src) return
  const image_data_url = aiSelectCanvas(src).toDataURL('image/png')
  void axios.post('/api/mask/select/warm', { image_data_url }).catch(() => {})
}

function loadMaskImage(dataUrl: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('mask decode failed'))
    img.src = dataUrl
  })
}

function applyAiMask(mask: CanvasImageSource, mode: SelectionMode) {
  applyingAiMask = true
  try {
    selectRef.value?.applyMask(mask, mode)
  } finally {
    applyingAiMask = false
  }
}

/**
 * AI select: segment the CURRENT composite (the pixels the selection will sit
 * over) and land the result exactly as a drawn gesture would, through the
 * combine mode. Two request shapes, one product rule: a PROMPT names a concept
 * and selects every instance of it ("sky", "people"); a POINT (normalized 0-1)
 * is the Object tool's click and selects the one object under it.
 */
async function runAiSelect(
  request: { prompt?: string; point?: { x: number; y: number } },
  mode: SelectionMode = selectCombine.value,
) {
  if (aiSelectBusy.value) return
  // Crop replaces the display box, so there is no overlay to land a mask on.
  if (family.value === 'crop') leaveMode()
  const src = composite.value
  if (!src || !selectRef.value) return
  aiSelectBusy.value = true
  aiSelectError.value = null
  try {
    const sent = aiSelectCanvas(src)
    const { data } = await axios.post('/api/mask/select', {
      image_data_url: sent.toDataURL('image/png'),
      ...request,
    })
    if (!data.success || !data.detections?.length) {
      aiSelectError.value = data.error
        || (request.prompt ? `No match for “${request.prompt}”` : 'No object at that point')
      return
    }
    const masks = await Promise.all(
      data.detections.map((d: any) => loadMaskImage(d.mask_data_url))
    )
    if (request.point) {
      // One object, several granularities: apply the object-level mask and
      // keep the rest for same-spot cycling.
      objectPickState = {
        src,
        x: request.point.x * src.width,
        y: request.point.y * src.height,
        masks,
        index: 0,
        mode,
        before: selModel.toSnapshot(),
      }
      applyAiMask(masks[0], mode)
      return
    }
    // A named concept: every instance, as one selection.
    const union = document.createElement('canvas')
    union.width = sent.width
    union.height = sent.height
    const unionCtx = union.getContext('2d')!
    for (const mask of masks) unionCtx.drawImage(mask, 0, 0, union.width, union.height)
    applyAiMask(union, mode)
  } catch (e: any) {
    aiSelectError.value = e?.message || 'Selection failed'
  } finally {
    aiSelectBusy.value = false
  }
}

/** A same-spot re-click means "not that granularity": within this radius (in
 *  source pixels, scaled for large sources) the click cycles instead of
 *  re-segmenting. */
function objectCycleRadius(src: HTMLCanvasElement): number {
  return Math.max(8, Math.max(src.width, src.height) * 0.01)
}

/** The Object tool's click uses the same explicit combine control as every
 *  other selection tool. Shift remains the geometry constraint for rectangle
 *  and ellipse rather than meaning something different only for Object. */
function onObjectPick(pick: { x: number; y: number }) {
  const src = composite.value
  if (!src) return
  const cycle = objectPickState
  if (
    cycle && cycle.src === src && cycle.masks.length > 1
    && Math.hypot(pick.x - cycle.x, pick.y - cycle.y) <= objectCycleRadius(src)
  ) {
    cycle.index = (cycle.index + 1) % cycle.masks.length
    if (cycle.before) selModel.loadFromSnapshot(cycle.before)
    else selModel.clearSelection()
    applyAiMask(cycle.masks[cycle.index], cycle.mode)
    return
  }
  void runAiSelect(
    { point: { x: pick.x / src.width, y: pick.y / src.height } },
    selectCombine.value,
  )
}

/**
 * The affine from the crop geometry's frame to the actual composite frame —
 * the part `geometryBelow` cannot see, because Expand grows the frame with
 * pixels rather than with geometry: it pads around unmoved content, so the
 * mapping is a centred translate. A frame change that is not that has no honest
 * mapping, and returns null.
 *
 * There used to be a uniform-scale case here for an upscale checkpoint. The
 * output stage runs at save, on the flattened composite, so no step ever
 * rescales the frame under a live selection any more.
 */
function frameAdjust(
  geomW: number, geomH: number, frameW: number, frameH: number
): number[] | null {
  if (geomW === frameW && geomH === frameH) return [1, 0, 0, 1, 0, 0]
  if (frameW >= geomW && frameH >= geomH) {
    return [1, 0, 0, 1, Math.round((frameW - geomW) / 2), Math.round((frameH - geomH) / 2)]
  }
  return null
}

/** Every gesture end republishes: the mask consumers copy, and the master the
 *  geometry sync re-derives from. */
function onSelectionChange(mask: HTMLCanvasElement | null) {
  // Any change the Object tool didn't publish itself (a drawn gesture, clear,
  // invert) makes its granularity stack stale — cycling would resurrect the
  // pre-click selection over the user's newer edits.
  if (!applyingAiMask) objectPickState = null
  selection.value = mask
  // The patch flow is select-then-DRAG: the moment the selection lands, the
  // pointer hands back to the paint canvas so the very next gesture drags it.
  if (
    mask && armedSelectTool.value
    && (
      (family.value === 'paint' && paintEngineId.value === 'patch')
      || (family.value === 'retouch' && sub.value === 'patch')
    )
  ) {
    armedSelectTool.value = null
  }
  if (!mask) {
    selectionMaster = null
    selectionToDocument = null
    selectionAppliedKey = null
    workspaceGradient = null
    workspaceGradientKey = null
    selectCombine.value = combineAfterSelectionChange(selectCombine.value, false)
    return
  }
  selectCombine.value = combineAfterSelectionChange(selectCombine.value, true)
  selectionMaster = selModel.toSnapshot()
  const head = payloadFrame()
  const adjust = head && composite.value
    ? frameAdjust(head.width, head.height, composite.value.width, composite.value.height)
    : null
  // The current composite is `adjust × head.matrix × document`. Invert it
  // once at authoring time; every later projection starts from this canonical
  // local-selection → document relationship.
  const compositeFromDocument = head && adjust
    ? multiply(adjust as Affine, head.matrix as Affine)
    : null
  selectionToDocument = compositeFromDocument
    ? invertMatrix(compositeFromDocument)
    : null
  selectionAppliedKey = null
  if (composite.value) {
    selectionAppliedKey = appliedKeyFor(head, composite.value.width, composite.value.height)
  }
  // A gradient gesture keeps its parametric identity for Adjust to scope
  // with; any other gesture makes the selection drawn pixels. The key pins
  // the frame the ramp was drawn in — geometry changes underneath invalidate
  // it, and the raster (which sync DOES carry) becomes the honest scope.
  const landedAsGradient = gradientGestureLanding
  gradientGestureLanding = false
  if (landedAsGradient) {
    workspaceGradientKey = selectionAppliedKey
  } else {
    workspaceGradient = null
    workspaceGradientKey = null
  }
  if (!suppressMaskedAdjustmentSync && !landedAsGradient && maskedAdjustRegionId) {
    // A scoped Adjust step is armed for mask edits: every completed gesture
    // republishes its whole mask. The combine control is explicit — a later
    // gesture replaces, adds, subtracts or intersects exactly as the island
    // currently says.
    queueMaskedAdjustmentMask(mask)
    // Hand the pointer back after the gesture, but keep the ants visible. This
    // is especially important for asynchronous AI selection: hiding feedback
    // here made the successful mask appear only after another selection tool
    // was armed.
    armedSelectTool.value = null
  }
}

function appliedKeyFor(
  head: { matrix: any } | undefined | null, width: number, height: number
): string {
  return JSON.stringify({ m: head?.matrix ?? null, width, height })
}

/**
 * A live selection pre-fills the next mask. Consumed by COPY at the moment it
 * is used, never live-linked — the op ends up referencing only its own payload.
 * Flattened onto black: white-where-selected on opaque black is the shape every
 * mask consumer expects (the model’s own canvas is white on transparent).
 */
function selectionAsMask(): HTMLCanvasElement | null {
  if (!selection.value) return null
  const copy = document.createElement('canvas')
  copy.width = selection.value.width
  copy.height = selection.value.height
  const ctx = copy.getContext('2d')!
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, copy.width, copy.height)
  ctx.drawImage(selection.value, 0, 0)
  return copy
}

/**
 * Keep the selection registered to the pixels it was drawn over.
 *
 * The selection lives at the head of the stack, so any change to the geometry
 * below the head moves the image under it: crop edits, toggles, reorders, and
 * Expand, which pads the frame around the pixels already there.
 * Re-derives from the as-created master each time — never from the previous
 * derivative — and runs after every render, which is the one funnel all of
 * those changes already pass through.
 */
function syncSelectionGeometry() {
  if (!selectionMaster || !selectionToDocument || !stack.doc.value || !composite.value) return

  const head = payloadFrame()
  if (!head) return
  const frameW = composite.value.width
  const frameH = composite.value.height

  const key = appliedKeyFor(head, frameW, frameH)
  if (key === selectionAppliedKey) return

  const adjustNow = frameAdjust(head.width, head.height, frameW, frameH)
  if (!adjustNow) {
    // A frame change with no honest mapping: a wrong selection is worse than
    // none, so it clears — visibly, since the ants vanish with it.
    clearSelection()
    return
  }
  // local selection → permanent document → current geometry → current frame.
  const documentToComposite = multiply(adjustNow as Affine, head.matrix as Affine)
  const matrix = multiply(documentToComposite, selectionToDocument)

  const rewritten = rewritePayload(selectionMaster, matrix, frameW, frameH)
  selModel.initSelection({ width: frameW, height: frameH })
  selModel.loadFromSnapshot(rewritten)
  selection.value = selModel.hasSelection() ? selModel.getSelectionMask() : null
  if (!selection.value) { clearSelection(); return }
  selectionAppliedKey = key
  selectRef.value?.redraw()
}

// -- compare -------------------------------------------------------------------

/**
 * Compare against the base. Toggling into compare swaps the canvas for a
 * before/after wipe (ImageCompareSlider) — the original on the left, the edited
 * composite on the right. Both are encoded at the composite's frame so the
 * divider reveals the same pixel location on either side even after geometry
 * ops (a crop) change the frame.
 */
const comparing = ref(false)
const baseImage = ref<HTMLImageElement | null>(null)
const compareOriginalUrl = ref<string | null>(null)
const compareEditedUrl = ref<string | null>(null)

async function toggleCompare() {
  if (comparing.value) {
    comparing.value = false
    return
  }
  const src = composite.value
  if (!src) return
  const baseMediaId = stack.doc.value?.base.media_id
  if (!baseImage.value && baseMediaId) {
    baseImage.value = await loadImage(getMediaFileUrl(Number(baseMediaId)))
  }
  compareEditedUrl.value = src.toDataURL()
  if (baseImage.value) {
    // Draw the base into the composite's frame, so a cropped edit lines up with
    // its original instead of the two images sitting at different sizes.
    const frame = document.createElement('canvas')
    frame.width = src.width
    frame.height = src.height
    frame.getContext('2d')!.drawImage(baseImage.value, 0, 0, frame.width, frame.height)
    compareOriginalUrl.value = frame.toDataURL()
  } else {
    compareOriginalUrl.value = compareEditedUrl.value
  }
  comparing.value = true
}

// -- output stage ----------------------------------------------------------

/**
 * The upscaler used when the document has not named one. Kept out of the
 * document until the stage is actually turned on: writing a default into
 * document.json on open would mark a freshly-opened image as edited.
 */
const defaultUpscaleToolId = ref<string | null>(null)
const outputPickerOpen = ref(false)

/** Which sidebar panel is showing. The Edits list is the stack and only the
 *  stack; the output stage is a place beside it, not an entry in it. */
const sidebarTab = ref<'edits' | 'output'>('edits')

const outputStage = computed(() => {
  const stored = outputOf(stack.doc.value?.output)
  return { ...stored, tool_id: stored.tool_id ?? defaultUpscaleToolId.value }
})

/** What a save starts from — the composite's real size, not the base's. */
const outputInput = computed(() => ({
  width: composite.value?.width ?? stack.doc.value?.canvas.width ?? 0,
  height: composite.value?.height ?? stack.doc.value?.canvas.height ?? 0,
}))

function updateOutput(patch: Partial<OutputStage>) {
  // The tool is written down the moment the stage starts mattering, so the
  // saved document says what it will actually run rather than depending on
  // whatever the catalog happens to offer first next time.
  const withTool =
    patch.enabled && !stack.doc.value?.output?.tool_id && defaultUpscaleToolId.value
      ? { ...patch, tool_id: defaultUpscaleToolId.value }
      : patch
  stack.setOutput(withTool)
}

/** Merge into the tool's params; the panel never owns the whole blob. */
function setOutputParams(patch: Record<string, any>) {
  stack.setOutput({ params: { ...outputStage.value.params, ...patch } })
}

// -- version chain and the commit bar ---------------------------------------

/**
 * The journal cursor as of the last commit — what Revert walks back to.
 *
 * Set at open and after every in-place save. Undo already knows how to move the
 * document backwards, so reverting is walking that cursor rather than a second
 * mechanism that could disagree with it.
 */
const savedCursor = ref(0)
const confirmingRevert = ref(false)

const canRevert = computed(() => stack.cursor.value > savedCursor.value)

const revertCount = computed(() => stack.cursor.value - savedCursor.value)

async function revertToSaved() {
  confirmingRevert.value = false
  while (stack.cursor.value > savedCursor.value && stack.canUndo.value) stack.undo()
  // Back at the committed state by definition.
  stack.markCommitted()
  await afterGeometryChange(stack.doc.value)
  void render()
}

/** Transient confirmation, so a commit is not a button that just stops spinning. */
const savedNote = ref<string | null>(null)
let savedNoteTimer: ReturnType<typeof setTimeout> | null = null

function noteSaved(message: string) {
  savedNote.value = message
  if (savedNoteTimer) clearTimeout(savedNoteTimer)
  savedNoteTimer = setTimeout(() => { savedNote.value = null }, 2600)
}

/** The split button's menu: Save is the button, the rare fork is behind it. */
const saveMenuOpen = ref(false)
const saveMenuRef = ref<HTMLElement | null>(null)

function onSaveMenuClickOutside(ev: MouseEvent) {
  if (saveMenuRef.value && !saveMenuRef.value.contains(ev.target as Node)) {
    saveMenuOpen.value = false
  }
}

// Soft-dismiss on any click outside the split control. Deferred so the click
// that opened the menu does not immediately close it.
watch(saveMenuOpen, (open) => {
  if (open) {
    setTimeout(() => document.addEventListener('mousedown', onSaveMenuClickOutside), 0)
  } else {
    document.removeEventListener('mousedown', onSaveMenuClickOutside)
  }
})

onBeforeUnmount(() => document.removeEventListener('mousedown', onSaveMenuClickOutside))

// -- save ------------------------------------------------------------------

const saving = ref(false)
const savedRevisionId = ref<number | null>(null)

/**
 * What the save is doing right now, as the label of the button that is doing
 * it — a save with the output stage on runs a model and takes as long as one
 * takes, and a button that only spins reads as stuck. A separate status line
 * put the answer somewhere other than the thing the user is watching.
 */
const savingNote = ref<string | null>(null)

async function save(asNew = false) {
  if (!composite.value || !stack.doc.value) return
  saving.value = true
  error.value = null
  savingNote.value = null
  try {
    await stack.flush()
    // Always flatten the REAL document, never the stage. Saving from inside
    // the annotate family would otherwise write the composite the overlay is
    // drawing over — the one without its annotations.
    const flattened = await applyOutputStage(await compositor.render(stack.doc.value))
    const blob = await canvasToBlob(flattened)
    const form = new FormData()
    form.append('file', blob, 'edited.png')
    form.append('source_media_id', String(stack.doc.value.base.media_id))
    form.append('asset_id', String(stack.doc.value.base.asset_id))
    form.append('base_revision_id', String(stack.doc.value.base.revision_id))
    form.append('working_document_id', String(stack.documentId.value))
    form.append('stack_summary', JSON.stringify(stack.executedStackSummary()))
    if (asNew) form.append('save_as_new', 'true')

    const { data } = await axios.post('/api/media/save-edit', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    savedRevisionId.value = data.revision_id
    stack.markCommitted(data.asset_id, data.revision_id)
    savedCursor.value = stack.cursor.value
    // The version commit already succeeded. Persist its working-state boundary
    // separately so a reload cannot turn that state back into "unsaved."
    void stack.flush().catch((persistError) => {
      console.error('[imageStack] could not persist commit boundary', persistError)
    })
    if (asNew) {
      // The editor stays on the original Asset, but the current state is now
      // committed durably to the new one, so it is no longer "unsaved."
      noteSaved('Saved as a new asset')
    } else {
      noteSaved('Saved')
    }
  } catch (err: any) {
    error.value = apiErrorMessage(err, 'Could not save.')
  } finally {
    saving.value = false
    savingNote.value = null
  }
}

/**
 * The output stage: scale the flattened composite, then re-render the vector
 * steps on top at the final resolution.
 *
 * Vectors AFTER the scale is the whole reason this lives at save rather than in
 * the stack — text an upscaler enlarged is text at 2× the pixels and none of
 * the sharpness, while text rendered into the scaled frame is simply text at
 * the final size. Raster steps ride the scale, which is what you want from them.
 *
 * Throws rather than degrading: a save that quietly skipped the upscale would
 * write the wrong file into the version chain, and the row said 2×.
 */
async function applyOutputStage(flattened: HTMLCanvasElement): Promise<HTMLCanvasElement> {
  const doc = stack.doc.value!
  const output = outputStage.value
  if (!output.enabled) return flattened

  // The vector steps come off before the scale and go back on after it, so the
  // upscaler never sees them and never has to reproduce them.
  const vectorOps = doc.edits.filter(
    op => op.enabled && op.class === 'container' && (op as any).exec?.kind === 'annotate'
  )
  const withoutVectors = vectorOps.length
    ? await compositor.render({
        ...doc,
        edits: doc.edits.filter(op => !vectorOps.some(v => v.id === op.id)),
      })
    : flattened

  const target = outputDimensions(output, withoutVectors.width, withoutVectors.height)

  let scaled: HTMLCanvasElement
  const tool = tools.value.find(t => t.full_tool_id === output.tool_id)
  if (output.method === 'resample' || !tool) {
    if (output.method === 'photo' && !tool) {
      throw new Error('The upscale tool is no longer in the catalog.')
    }
    savingNote.value = 'Resizing…'
    scaled = resampleLanczos(withoutVectors, target.width, target.height)
  } else {
    savingNote.value = 'Upscaling…'
    // The tool's OWN parameters, by schema property name, straight through the
    // shared payload builder — the same path ToolView takes. Nothing here
    // knows what this particular upscaler calls its factor.
    const result = await candidates.runToolOnce({
      tool,
      inputCanvas: withoutVectors,
      params: output.params,
      finalResolution: finalResolutionFor(
        output, withoutVectors.width, withoutVectors.height
      ),
    })
    // Providers snap to their own grids, so the returned size is the size —
    // the vectors are drawn into whatever actually came back rather than into
    // what was asked for.
    scaled = document.createElement('canvas')
    scaled.width = result.naturalWidth
    scaled.height = result.naturalHeight
    scaled.getContext('2d')!.drawImage(result, 0, 0)
  }

  if (!vectorOps.length) return scaled

  savingNote.value = 'Rendering…'
  const shapes: any[] = []
  const sx = scaled.width / withoutVectors.width
  const sy = scaled.height / withoutVectors.height
  for (const op of vectorOps) {
    shapes.push(...transformShapes((op as any).params?.shapes || [], [sx, 0, 0, sy, 0, 0]))
  }
  return applyAnnotations(scaled, scaled.width, scaled.height, shapes, scaled)
}

const migrationNote = ref<string | null>(null)

/**
 * Resolve a document that still contains whole-image steps.
 *
 * Runs before the first render, because those steps have no executor any more —
 * rendering first would show the image without them and then replace it.
 */
async function flattenIfNeeded() {
  const doc = stack.doc.value
  if (!hasWholeOps(doc)) return

  const result = await flattenWholeOps(doc!, {
    loadPayload: (ref: string, revision = 0) =>
      loadImage(stack.payloadUrl(ref, revision)),
    loadBase: loadStackBase,
    uploadPayload: stack.uploadPayload,
    canvasToBlob,
  })
  if (!result) return

  stack.replaceDocument(result.document, {
    action: 'flatten_whole_ops',
    forward: { flattened: result.flattenedCount },
    inverse: { document: doc },
  })
  await stack.flush()
  compositor.clear()

  const count = result.flattenedCount
  migrationNote.value =
    `Combined ${count} ${count === 1 ? 'step' : 'steps'} into the image. `
    + 'Whole-image edits are now saved as a version instead of a step.'
}

// -- lifecycle -------------------------------------------------------------

function onKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement
  // Canvas text editing has no focusable element to hide behind, so the
  // single-key tool shortcuts would eat the typing: 'e' and 'l' switched to
  // Effects and Adjust mid-word and unmounted the editor being typed into.
  if (annotateRef.value?.isEditingText()) return
  if (event.key === 'Escape') {
    event.preventDefault()
    // First Esc releases whichever canvas tool or Retouch diagnostic owns the
    // interaction. A live pixel selection stays visible; at idle, Esc
    // explicitly deselects it.
    if (hasDismissibleCanvasFeedback.value) {
      dismissCanvasFeedback()
    } else if (family.value || mode.value) {
      leaveMode()
    } else if (selectedShapeId.value) {
      selectedShapeId.value = null
      selectedOpId.value = null
    } else if (selection.value) {
      clearSelection()
    }
    return
  }
  if (target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA') return
  if (event.code === 'Space' && !event.metaKey && !event.ctrlKey && !event.altKey) {
    spacePanHeld.value = true
    event.preventDefault()
    return
  }
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'z') {
    event.preventDefault()
    if (event.shiftKey) stack.redo()
    else stack.undo()
    void render()
  }
  // A selected annotation answers the Delete key wherever focus is (inputs
  // and canvas text editing already returned above); the sidebar's own
  // handler covers rows, so this only fires for canvas-selected shapes.
  if (
    (event.key === 'Delete' || event.key === 'Backspace') &&
    selectedShapeId.value && !sidebarEl.value?.contains(event.target as Node)
  ) {
    event.preventDefault()
    // The canvas owns object selection, including marquee groups. It reports
    // the resulting list through the same reconciliation path as every other
    // annotation gesture, so one keypress removes the whole selection.
    if (annotateRef.value) {
      annotateRef.value.deleteSelected()
    } else {
      const opId = opIdForShape(selectedShapeId.value)
      selectedShapeId.value = null
      if (opId) void removeOpWithGeometry(opId)
    }
    return
  }
  // Toggle the before/after comparison against the base.
  if (event.key === '\\' && !event.repeat) void toggleCompare()
  if (!event.metaKey && !event.ctrlKey) {
    if (event.key === '0') {
      event.preventDefault()
      resetView()
      return
    }
    if (event.key === '=' || event.key === '+') {
      event.preventDefault()
      zoomViewBy(1)
      return
    }
    if (event.key === '-') {
      event.preventDefault()
      zoomViewBy(-1)
      return
    }
    // 's' arms the last-used selection tool; the families keep their keys.
    if (event.key.toLowerCase() === 's') armSelectTool(lastSelectTool.value)
    const shortcut = TOOL_FAMILIES.find(f => f.key === event.key.toLowerCase())
    if (shortcut) selectFamily(shortcut.id)
  }
}

function onKeyup(event: KeyboardEvent) {
  if (event.code === 'Space') spacePanHeld.value = false
}

function clearViewportGestureState() {
  spacePanHeld.value = false
  viewPanning.value = false
}

/**
 * Leaving a mode ends its session: the next entry starts a new step.
 * The selection is NOT a session — it survives, visibly, ants marching.
 */
function leaveMode() {
  // Leaving is a pick too: Esc'ing out means the next visit should open on the
  // canvas, not back inside the family that was deliberately closed.
  if (family.value) writeToolPrefs({ family: null })
  // Ending the mode ends a scoped step's mask-editing session. The step
  // itself survives like any pristine whole-image step would — the next
  // Adjust doorway click is what replaces an untouched one.
  disarmMaskedAdjustmentEditing()
  family.value = null
  sub.value = null
  mode.value = null
  // Ending a mode session ends its STEP: the next entry starts a new one.
  cropOpId.value = null
  resetPaintSession()
  resetRetouchSession()
}

let resizeObserver: ResizeObserver | null = null

/** Re-read the runnable catalog after a provider is enabled, disabled or drops. */
async function refreshToolCatalog() {
  try {
    tools.value = (await listAllTools()).filter(isRunnableTool)
  } catch (toolError) {
    console.warn('[imageStack] could not refresh tool catalog', toolError)
  }
}

async function hydrateEditorExtras() {
  void stack.hydrateHistory()
    .then(() => { savedCursor.value = stack.openedCursor.value })
    .catch(() => {
      // The current recipe is already open. History failure disables Undo but
      // must not take the image back down.
    })

  try {
    // Only tools that can actually run. The catalog reports the ones behind a
    // disconnected or disabled provider so screens that EXPLAIN a tool can
    // still name it; a picker is not one of those screens — every row in it is
    // an offer, and offering a tool that cannot run is a dead end the person
    // only discovers by pressing Run.
    const all = (await listAllTools()).filter(isRunnableTool)
    tools.value = all
    // Last session's pick wins, but only while that tool is still installed
    // and still supports the operation the restored family will ask it for.
    const prefs = readToolPrefs()
    const eligibleRepaint = all.filter(t => (t.task_types || []).includes('inpaint-image'))
    const eligibleRemove = removeCapableTools(all)
    const validRepaint = (id: string) =>
      eligibleRepaint.some(t => t.full_tool_id === id)
    const validRemove = (id: string) =>
      eligibleRemove.some(t => t.full_tool_id === id)

    // The former Generate/Inpaint pick is a safe migration fallback for both
    // Expand and Repaint; each gets its own preference from this point on.
    expandToolId.value =
      rememberedIfValid(prefs.expandToolId, validRepaint)
      ?? rememberedIfValid(prefs.inpaintToolId, validRepaint)
      ?? eligibleRepaint[0]?.full_tool_id
      ?? null
    repaintToolId.value =
      rememberedIfValid(prefs.repaintToolId, validRepaint)
      ?? rememberedIfValid(prefs.inpaintToolId, validRepaint)
      ?? eligibleRepaint[0]?.full_tool_id
      ?? null
    removeToolId.value =
      rememberedIfValid(prefs.removeToolId, validRemove)
      ?? rememberedIfValid(prefs.eraseToolId, validRemove)
      ?? eligibleRemove[0]?.full_tool_id
      ?? null
    const eligibleCutout = all.filter(t =>
      (t.task_types || []).includes('remove-background'))
    cutoutToolId.value =
      rememberedIfValid(
        prefs.cutoutToolId,
        id => eligibleCutout.some(t => t.full_tool_id === id),
      )
      ?? eligibleCutout[0]?.full_tool_id
      ?? null
    for (const id of [
      expandToolId.value, repaintToolId.value, removeToolId.value, cutoutToolId.value,
    ]) {
      ensureModelToolParams(all.find(tool => tool.full_tool_id === id))
    }
    defaultUpscaleToolId.value =
      all.find(t => (t.task_types || []).includes('upscale-image'))?.full_tool_id ?? null
  } catch (toolError) {
    console.warn('[imageStack] could not load tool catalog', toolError)
  }

  // The catalog changes under a long-lived editor: a provider gets disabled or
  // goes offline in Settings while this tab stays open, and a menu fetched once
  // at open keeps offering its tools. Re-read it on the same signal the rest of
  // the app listens for. Picks are left alone — a person's chosen tool going
  // quiet is reported when they press Run, not by silently swapping models.
  window.addEventListener('tools-changed', refreshToolCatalog)

  // Restore workspace preference only after the first usable frame. Some
  // families prepare previews of their own; none may delay showing the image.
  const rememberedFamily = rememberedIfValid(
    readToolPrefs().family ?? undefined,
    id => TOOL_FAMILIES.some(spec => spec.id === id),
  )
  if (rememberedFamily) selectFamily(rememberedFamily as FamilyId)
}

onMounted(async () => {
  try {
    const opened = await stack.open(Number(props.assetId), props.revisionId ? Number(props.revisionId) : undefined)
    // A saved Asset head and a working document base are different things.
    // The recipe owns the latter and is authoritative whenever it exists.
    baseInfo.value = stack.doc.value?.base
      ? { ...stack.doc.value.base }
      : opened.base
    candidates.start()

    // Before the first render: whole-image steps have no executor any more, so
    // rendering first would show the image without them.
    await flattenIfNeeded()

    // A hash-addressed materialized head makes the common cold open a decode,
    // not a replay. A first open or evicted cache falls back to the recipe.
    if (!await restoreCachedHead()) await render()

    // Let Vue create and paint the viewport before starting history, tool
    // discovery, version status, or family-specific preview work.
    loading.value = false
    await nextTick()
    requestAnimationFrame(() => setTimeout(() => { void hydrateEditorExtras() }, 0))
  } catch (err: any) {
    error.value = apiErrorMessage(err, 'Could not open this image.')
  } finally {
    loading.value = false
  }

})

// The screen is KeepAlive'd per asset, so it stays mounted after you navigate
// away: window-level keys must follow activation, not mount, or the editor's
// shortcuts would keep firing on whatever screen you moved to.
onActivated(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('keyup', onKeyup)
  window.addEventListener('blur', clearViewportGestureState)
})

onDeactivated(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('keyup', onKeyup)
  window.removeEventListener('blur', clearViewportGestureState)
  clearViewportGestureState()
  // Leaving is not saving — but the document (the recipe) is persisted so the
  // stack is intact when you come back, and after an eviction or a reload.
  void stack.flush().catch(() => {})
})

// The sidebar entry's unsaved-edits indicator.
watch(() => stack.dirtySinceSave.value, dirty => setEditorDirty(props.assetId, dirty), { immediate: true })

// The viewport only exists once loading finishes, so the observer attaches when
// the element appears rather than at mount — otherwise the canvas is sized
// against a viewport of 0x0 and never paints.
watch(viewport, element => {
  resizeObserver?.disconnect()
  if (!element) return
  resizeObserver = new ResizeObserver(entries => {
    const box = entries[0].contentRect
    viewportSize.value = { width: box.width, height: box.height }
    nextTick(clampViewPan)
  })
  resizeObserver.observe(element)
}, { flush: 'post' })

onBeforeUnmount(() => {
  if (savedNoteTimer) clearTimeout(savedNoteTimer)
  if (headCacheTimer) clearTimeout(headCacheTimer)
  abandonScheduledRender()
  if (paintPrefsTimer) persistPaintSettings()
  if (retouchPreviewFrame !== null) cancelAnimationFrame(retouchPreviewFrame)
  cancelLiveAdjustPreview()
  liveAdjustPreview.dispose()
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('keyup', onKeyup)
  window.removeEventListener('blur', clearViewportGestureState)
  window.removeEventListener('tools-changed', refreshToolCatalog)
  setEditorDirty(props.assetId, false)
  resizeObserver?.disconnect()
  candidates.stop()
  void stack.flush().catch(() => {})
})

// Mounting or unmounting the annotation overlay hands its pixels between the
// overlay and the composite, so the stage is rebuilt in both directions.
// Keyed on the boolean, not on displayDoc: the filtered document is a fresh
// object on every evaluation, and watching it would re-render on every shape
// edit for a composite that cannot have changed.
watch(annotationOverlayActive, () => { void render() })
// The composite is usually ready BEFORE the canvas exists (rendering happens
// while `loading` still hides it), so repaint on either changing rather than
// only on the composite.
// renderSnapshot paints composite changes itself. This watcher only covers the
// canvas appearing after initial loading and geometry-driven display sizing.
watch([displayCanvas, displayBox], () => nextTick(paint), { flush: 'post' })
watch([displayBox, () => family.value], () => nextTick(clampViewPan), { flush: 'post' })

// -- clipping overlays -------------------------------------------------------

/**
 * Clipping indicators: workspace state toggled from the curve plot's corners,
 * never part of the document. The overlay canvas sits over the composite and
 * marks blown highlights red and crushed shadows blue.
 */
const clipShadows = ref(false)
const clipHighlights = ref(false)
const clipCanvas = ref<HTMLCanvasElement | null>(null)
const showClipOverlay = computed(() => clipShadows.value || clipHighlights.value)

function setClipIndicators(state: { shadows: boolean; highlights: boolean }) {
  clipShadows.value = state.shadows
  clipHighlights.value = state.highlights
}

/** The warning needs display resolution, not the full-resolution frame. */
const CLIP_SCAN_MAX_PIXELS = 1_500_000

function paintClipOverlay() {
  const target = clipCanvas.value
  const source = composite.value
  if (!target || !source || !showClipOverlay.value) return
  const scale = Math.min(
    1,
    Math.sqrt(CLIP_SCAN_MAX_PIXELS / Math.max(1, source.width * source.height)),
  )
  const width = Math.max(1, Math.round(source.width * scale))
  const height = Math.max(1, Math.round(source.height * scale))
  const staging = document.createElement('canvas')
  staging.width = width
  staging.height = height
  const stagingContext = staging.getContext('2d', { willReadFrequently: true })!
  stagingContext.drawImage(source, 0, 0, width, height)
  const frame = stagingContext.getImageData(0, 0, width, height)
  const overlay = stagingContext.createImageData(width, height)
  const pixels = frame.data
  const marks = overlay.data
  for (let index = 0; index < pixels.length; index += 4) {
    if (pixels[index + 3] === 0) continue
    const maxChannel = Math.max(pixels[index], pixels[index + 1], pixels[index + 2])
    const minChannel = Math.min(pixels[index], pixels[index + 1], pixels[index + 2])
    if (clipHighlights.value && maxChannel >= 254) {
      marks[index] = 239
      marks[index + 1] = 68
      marks[index + 2] = 68
      marks[index + 3] = 230
    } else if (clipShadows.value && minChannel <= 1) {
      marks[index] = 96
      marks[index + 1] = 165
      marks[index + 2] = 250
      marks[index + 3] = 230
    }
  }
  target.width = width
  target.height = height
  target.getContext('2d')!.putImageData(overlay, 0, 0)
}

watch(
  [clipShadows, clipHighlights, composite, clipCanvas],
  () => nextTick(paintClipOverlay),
  { flush: 'post' },
)

// -- point-color eyedropper ----------------------------------------------------

/** Which inspector the armed eyedropper writes its pick into. */
const pointPickTarget = ref<'adjust' | 'retouch' | null>(null)
const pointPicking = computed(() => pointPickTarget.value !== null)

/** The chip toggles: armed is a mode you can also leave by pressing it. */
function armPointColorPick() {
  if (pointPicking.value) {
    pointPickTarget.value = null
    return
  }
  if (inspectorKind.value === 'retouch' && selectedRetouchRegion.value) {
    pointPickTarget.value = 'retouch'
  } else if (selectedAdjustOp.value) {
    pointPickTarget.value = 'adjust'
  }
}

/**
 * Landing on Point color with nothing sampled arms the dropper for you.
 *
 * The tool has exactly one thing it can do first, and making the person say so
 * with an extra click taught nothing. Only the empty case auto-arms — coming
 * back to a step that already has its color must not hijack the next canvas
 * click.
 */
function pointStepNeedsPick(): boolean {
  const values = inspectorKind.value === 'retouch'
    ? (selectedRetouchRegion.value?.kind === 'point'
        ? selectedRetouchRegion.value.settings as Record<string, any>
        : null)
    : (adjustInspectorParams.value.section === 'point'
        ? adjustInspectorParams.value
        : null)
  if (!values) return false
  return !values.pointHue && !values.pointSat && !values.pointLum
}

function onPointColorPick(event: PointerEvent) {
  const target = pointPickTarget.value
  const canvas = displayCanvas.value
  if (!target || !canvas?.width || !canvas.height) {
    pointPickTarget.value = null
    return
  }
  const rect = canvas.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  const x = Math.max(0, Math.min(
    canvas.width - 1,
    Math.floor((event.clientX - rect.left) / rect.width * canvas.width),
  ))
  const y = Math.max(0, Math.min(
    canvas.height - 1,
    Math.floor((event.clientY - rect.top) / rect.height * canvas.height),
  ))
  const sample = canvas.getContext('2d')?.getImageData(x, y, 1, 1).data
  if (!sample) return
  const picked = rgbToHslColor(sample[0], sample[1], sample[2])
  const patch = {
    pointHue: Math.round(picked.hue),
    pointSat: Math.round(picked.sat),
    pointLum: Math.round(picked.lum),
  }
  if (target === 'retouch') {
    setRetouchRegionSettings(patch, 'point-pick')
    void commitRetouchSettingsRender()
  } else {
    onAdjustInspectorChange(patch, 'adjust:point-pick')
    void commitAdjustInspectorChange()
  }
  // The dropper STAYS armed: sampling is a hunt, and the second click is
  // usually a correction of the first. Esc, the chip, or leaving the step
  // puts it away.
}

function pointPickKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  pointPickTarget.value = null
  event.stopPropagation()
  event.preventDefault()
}

watch(pointPicking, active => {
  if (active) window.addEventListener('keydown', pointPickKeydown, true)
  else window.removeEventListener('keydown', pointPickKeydown, true)
})

// Switching steps or panels disarms the dropper — a pick belongs to the
// inspector that asked for it — and landing on a Point color step with no
// color yet arms it, because that is the only move the step has.
watch(
  [inspectorKind, selectedOpId, selectedRetouchRegionId],
  () => {
    pointPickTarget.value = null
    nextTick(() => {
      if (pointPicking.value || !pointStepNeedsPick()) return
      armPointColorPick()
    })
  },
)
</script>

<template>
  <!--
    Layout, top level:

      ┌──────────────────────────────┬────────────┐
      │  toolbars (stacked, shrink)  │            │
      │──────────────────────────────│   Edits    │
      │                              │  sidebar   │
      │   canvas — flex-1, matte     │ (full      │
      │                              │  height)   │
      │──────────────────────────────│            │
      │  document bar (undo/save)    │            │
      └──────────────────────────────┴────────────┘

    The sidebar sits OUTSIDE the toolbars and spans top to bottom, so nothing a
    mode does can disturb it. The toolbars are shrink-0 above a flex-1 canvas,
    so opening one takes matte space from the canvas and closing one gives it
    back — the image itself never gets pushed around.
  -->
  <div class="h-full flex flex-col bg-base">
    <div class="flex-1 flex min-h-0">
      <div class="flex-1 flex flex-col min-w-0 min-h-0">
      <!-- Toolbar 1: the families. -->
      <div class="flex items-center gap-3 px-3 h-11 shrink-0 border-b border-edge-subtle">
        <h1 class="text-sm font-medium text-content shrink-0">Darkroom</h1>
        <StatusDot
          v-if="stack.dirtySinceSave.value"
          bucket="warning"
          class="shrink-0"
          title="Unsaved edits"
          aria-label="Unsaved edits"
        />
        <EditorToolbar :active="family" class="ml-2" @select="selectFamily" />
      </div>

      <!-- The canvas region. relative so the sub-toolbar can FLOAT over the
           top of the matte: the viewport keeps its full height whether or not
           a family is open, so the image holds steady and opening a mode
           consumes matte instead of reflowing the picture. -->
      <div class="relative flex-1 min-h-0 flex flex-col">
      <!-- Toolbar 2: the active family's controls, overlaid on the matte. -->
      <div class="absolute top-0 left-0 right-0 z-20">
        <EditorSubbar
          v-if="family"
          :family="family"
          :sub="sub"
          :state="subbarState"
          :tool-label="activeToolLabel"
          :busy="busy"
          :can-run="canRun"
          :hint="subbarHint"
          @sub="selectSub"
          @set="onSubbarSet"
          @commit="onSubbarCommit"
          @run="run"
          @open-tool-picker="onOpenToolPicker"
        />

        <!-- Under the sub-bar and left-aligned to the button that opened it. -->
        <div v-if="toolPickerOpen" class="relative z-menu">
          <div class="absolute top-0" :style="{ left: toolPickerLeft + 'px' }">
            <ToolPicker
              :tools="tools"
              :task-type="activeTaskType"
              :compatible-task-types="activeCompatibleTaskTypes"
              :selected-id="activeToolId"
              @select="chooseTool"
              @close="toolPickerOpen = false"
            />
          </div>
        </div>
      </div>

      <div v-if="loading" class="flex-1 grid place-items-center">
        <Spinner size="md" />
      </div>

      <!-- Canvas. Centred in whatever matte is left. The selection island
           floats over the matte at the bottom: selection is workspace state
           (WHERE) and the top bar is the families (WHAT), and floating chrome
           can never push either one around. -->
      <div
        v-else
        ref="viewport"
        class="relative flex-1 min-h-0 grid place-items-center overflow-hidden bg-matte p-6"
        :class="viewPanning ? 'cursor-grabbing' : (spacePanHeld ? 'cursor-grab' : '')"
        @wheel.prevent="onViewportWheel"
        @pointerdown.capture="startViewPan"
        @pointermove.capture="moveViewPan"
        @pointerup.capture="endViewPan"
        @pointercancel.capture="endViewPan"
        @mousedown.self="onViewportMatteMouseDown"
        @click.self="onViewportMatteClick"
      >
        <!-- Crop works on the step's INPUT, not on the composite: the region
             outside the crop is dimmed rather than absent, so it takes the
             whole viewport instead of the cropped display box. -->
        <div
          v-if="family === 'crop'"
          class="absolute left-1/2 top-1/2"
          :style="[
            {
              width: viewportSize.width * viewZoom + 'px',
              height: viewportSize.height * viewZoom + 'px',
            },
            viewTransformStyle,
          ]"
        >
          <StackCropCanvas
            :source="cropInput"
            :crop="cropRect"
            :flip-x="!!cropParamsOf().flipX"
            :flip-y="!!cropParamsOf().flipY"
            :rotation="cropParamsOf().rotation ?? 0"
            :rotation90="cropParamsOf().rotation90 ?? 0"
            :view-width="viewportSize.width * viewZoom"
            :view-height="viewportSize.height * viewZoom"
            @change="onCropRectChange"
            @commit="onCropCommit"
          />
        </div>
        <div
          v-else
          class="absolute left-1/2 top-1/2"
          :style="[
            { width: zoomedDisplayBox.width + 'px', height: zoomedDisplayBox.height + 'px' },
            viewTransformStyle,
          ]"
        >
          <canvas
            ref="displayCanvas"
            class="rounded-media w-full h-full"
            :class="compositeHasCutout ? 'bg-checker' : ''"
            :style="{ width: zoomedDisplayBox.width + 'px', height: zoomedDisplayBox.height + 'px' }"
          />
          <!-- Clipping overlay: marks blown highlights and crushed shadows
               over the composite. Pointer-transparent — it is a read-out. -->
          <canvas
            v-if="showClipOverlay"
            ref="clipCanvas"
            class="absolute inset-0 w-full h-full pointer-events-none rounded-media"
          />
          <!-- Armed point-color eyedropper: one click samples the composite
               under the cursor into the selected step, Esc disarms. -->
          <div
            v-if="pointPicking"
            class="absolute inset-0 z-20 cursor-crosshair"
            @pointerdown.stop.prevent="onPointColorPick"
          />
          <StackPaintCanvas
            v-if="family === 'retouch' && !isModelRetouchSub(sub)"
            ref="retouchRef"
            :source="retouchInput || composite"
            :selection-mask="selection"
            :display-width="zoomedDisplayBox.width"
            :display-height="zoomedDisplayBox.height"
            :engine-id="sub || 'heal'"
            :brush="retouchBrush"
            :accumulate="false"
            @stroke="onRetouchStroke"
            @patch-applied="clearSelection"
          />
          <StackPaintCanvas
            v-else-if="family === 'paint'"
            ref="paintRef"
            :source="composite"
            :initial-layer="paintInitialLayer"
            :selection-mask="selection"
            :display-width="zoomedDisplayBox.width"
            :display-height="zoomedDisplayBox.height"
            :engine-id="paintEngineId"
            :brush="paintBrush"
            :color="paintColorRgb"
            :exposure="paintExposure"
            :range="paintRange"
            :strength="paintStrength"
            :saturate="paintSaturate"
            @stroke="onPaintStroke"
            @patch-applied="clearSelection"
          />
          <!-- Also mounted in the IDLE state (no family, nothing armed), in
               object-select mode: annotations are the grabbable things, and
               clicking one should just select it. -->
          <StackAnnotateCanvas
            v-else-if="family === 'annotate' || objectSelectActive"
            ref="annotateRef"
            :source="composite"
            :shapes="annotateShapes"
            :display-width="zoomedDisplayBox.width"
            :display-height="zoomedDisplayBox.height"
            :tool="annotateTool"
            :stroke-color="annotatePaint"
            :fill-color="annotateFillColor"
            :stroke-width="annotateStrokeWidth"
            :shape-effect="annotateShapeEffect"
            :opacity="annotateOpacity"
            :text-style="textStyle"
            @change="onAnnotationsChange"
            @commit="onAnnotationCommit"
            @select="onShapeSelected"
          />
          <StackRetouchFeedback
            v-if="(
              (selectedRetouchFeedbackVisible && selectedRetouchMask)
              || (hoveredRetouchRegionId && hoveredRetouchMask)
              || (hoveredRetouchOpId && allRetouchFeedback.length)
            )"
            :all-regions="hoveredRetouchRegionId ? [] : allRetouchFeedback"
            :selected-mask="
              !hoveredRetouchRegionId && !hoveredRetouchOpId && selectedRetouchFeedbackVisible
                ? selectedRetouchMask
                : null
            "
            :hovered-mask="hoveredRetouchMask"
            :source-point="selectedRetouchSource"
            :target-point="selectedRetouchTarget"
            :hovered-source-point="hoveredRetouchSource"
            :hovered-target-point="hoveredRetouchTarget"
            :selected-is-patch="selectedRetouchIsPatch"
            :hovered-is-patch="hoveredRetouchIsPatch"
            :display-width="zoomedDisplayBox.width"
            :display-height="zoomedDisplayBox.height"
          />
          <!-- The selection overlay: always mounted, ants above whatever mode
               is open, pointer-transparent until a rail tool is armed. The
               model itself lives in the host, so nothing here owns the state. -->
          <StackSelectCanvas
            ref="selectRef"
            :source="composite"
            :model="selModel"
            :armed="armedSelectTool"
            :busy="aiSelectBusy"
            :display-width="zoomedDisplayBox.width"
            :display-height="zoomedDisplayBox.height"
            :combine="selectCombine"
            :feather-px="selectFeather"
            :tolerance="selectTolerance"
            :wand-spread="selectSpread"
            :wand-grow-px="selectGrow"
            :wand-antialias="selectAntialias"
            :brush-size="selectBrushSize"
            :gradient="selectedGradient"
            :gradient-softness="selectGradientSoftness"
            :gradient-feather="selectGradientFeather"
            @change="onSelectionChange"
            @object-pick="onObjectPick"
            @gradient="onGradientChange"
            @gradient-edit="onGradientEdit"
          />
          <!-- The selected annotation's own verbs, over the shape they act
               on. Inside the display box so it shares the shapes' coordinate
               space, and last so it sits above every overlay. Always mounted:
               it owns its own fade, and a v-if here would unmount it before
               the leave could play. -->
          <AnnotationIsland
            :visible="annotationIslandVisible"
            :shapes="selectedAnnotationShapes"
            :image-size="frameSize"
            :display-width="zoomedDisplayBox.width"
            :display-height="zoomedDisplayBox.height"
            :can-bring-to-front="canBringAnnotationToFront"
            :can-send-to-back="canSendAnnotationToBack"
            class="z-chrome"
            @edit-text="editSelectedText"
            @reset-rotation="onShapeChange({ rotation: 0 })"
            @bring-to-front="moveAnnotation('front')"
            @send-to-back="moveAnnotation('back')"
            @duplicate="duplicateAnnotation"
            @remove="deleteSelectedAnnotation"
          />
          <!-- Before/after wipe against the base. Covers the canvas and its
               overlays while active; Esc or the footer toggle leaves. -->
          <ImageCompareSlider
            v-if="comparing && compareOriginalUrl && compareEditedUrl"
            :left-src="compareOriginalUrl"
            :right-src="compareEditedUrl"
            left-label="Original"
            right-label="Edited"
            class="z-overlay"
            @close="comparing = false"
          />
        </div>

        <SelectIsland
          :armed="armedSelectTool"
          :pointer-active="objectSelectActive"
          :has-selection="!!selection"
          :combine="selectCombine"
          :feather-px="selectFeather"
          :tolerance="selectTolerance"
          :spread="selectSpread"
          :grow-px="selectGrow"
          :antialias="selectAntialias"
          :brush-size="selectBrushSize"
          :gradient-softness="selectedGradient?.kind === 'linear'
            ? selectedGradient.softness : selectGradientSoftness"
          :gradient-feather="selectedGradient?.kind === 'radial'
            ? selectedGradient.feather : selectGradientFeather"
          :ai-busy="aiSelectBusy"
          :ai-error="aiSelectError"
          class="absolute bottom-4 left-1/2 -translate-x-1/2 z-chrome"
          @arm="armSelectTool"
          @pointer="activatePointer"
          @set="onSelectionSet"
          @invert="invertSelection"
          @clear="clearSelection"
          @ai-select="(prompt: string) => runAiSelect({ prompt })"
        />
      </div>
      </div>
    </div>

      <!-- Edits: outside everything a mode can touch. -->
      <!-- Drag to widen the stack. The panels in here carry real controls, and
           how much room they deserve is the user's call, not a constant. -->
      <div
        class="w-1 shrink-0 cursor-col-resize bg-edge-subtle/40 hover:bg-accent/40 transition-colors"
        @pointerdown="startSidebarResize"
      />
      <aside
        ref="sidebarEl"
        @keydown="onStackKeydown"
        class="shrink-0 border-l border-edge-subtle flex flex-col min-h-0"
        :style="{ width: sidebarWidth + 'px' }"
      >
        <!-- Two panels, not two lists. Edits is the stack and only the stack;
             Output is the terminal stage, which is a tool with a picker and a
             schema and therefore needs a place rather than a row. -->
        <div
          class="px-3 h-11 flex items-center gap-1 shrink-0 bg-surface-raised/60
                 border-b border-edge-strong"
        >
          <button
            v-for="tab in [
              { id: 'edits', label: 'Edits' },
              { id: 'output', label: 'Output' },
            ]"
            :key="tab.id"
            type="button"
            class="px-2 py-1 text-xs font-medium uppercase tracking-wide rounded-md
                   transition-colors focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
            :class="sidebarTab === tab.id
              ? 'text-content bg-selection/15'
              : 'text-content-tertiary hover:text-content-secondary'"
            @click="sidebarTab = tab.id as 'edits' | 'output'"
          >
            {{ tab.label }}
            <span
              v-if="tab.id === 'output' && outputLabel(outputStage)"
              class="ml-1 text-accent normal-case tracking-normal tabular-nums"
            >{{ outputLabel(outputStage) }}</span>
          </button>
          <div class="flex-1" />
          <Spinner v-if="rendering" size="sm" />
        </div>

        <OutputPanel
          v-if="sidebarTab === 'output' && stack.doc.value"
          :output="outputStage"
          :tools="tools"
          :input-width="outputInput.width"
          :input-height="outputInput.height"
          :picker-open="outputPickerOpen"
          @update="updateOutput"
          @set-params="setOutputParams"
          @toggle-picker="outputPickerOpen = !outputPickerOpen"
          @close-picker="outputPickerOpen = false"
        />

        <!-- One dragover on the list, resolved with closest(): per-row
             handlers miss the gaps (the list's padding) and leave a stale line
             behind, and dragenter is unreliable in WKWebView. -->
        <div
          v-else
          class="flex-1 overflow-y-auto custom-scrollbar p-1.5"
          @dragover.prevent="onListDragOver"
          @drop.prevent="onDrop"
          @dragleave="onListDragLeave"
        >
          <!-- Top of the stack reads first, the way the image is built up. -->
          <template v-for="row in visibleRows" :key="row.op.id">
            <!-- Where the dragged row would land. The gap above a row is the
                 doc index one higher, because the list is drawn top-first. -->
            <div v-if="dropGap === row.index + 1" :class="DROP_LINE" />
            <EditRow
              :op="row.op"
              :selected="selectedOpId === row.op.id"
              :staleness="row.staleness"
              :candidate-thumbs="candidateThumbs[row.op.id]"
              :pending-count="pendingByOp[row.op.id]"
              :preview-staleness="previewStalenessOf(row.op.id)"
              :out-of-frame="outOfFrame[row.op.id]"
              :resampling="runningOpIds.has(row.op.id)"
              :draggable="true"
              :dragging="dragOpId === row.op.id"
              :preview="stepPreviews[row.op.id]"
              :selected-region-id="selectedRetouchRegionId"
              @select="onRowSelect(row.op)"
              @toggle="setEnabledWithGeometry(row.op.id, $event)"
              @pick="stack.pickCandidate(row.op.id, $event); render()"
              @remove="removeOpWithGeometry(row.op.id)"
              @resample="resample(row.op.id)"
              @toggle-region="(regionId, enabled) => setRetouchRegionEnabled(row.op.id, regionId, enabled)"
              @remove-region="removeRetouchRegion(row.op.id, $event)"
              @select-region="selectRetouchRegion(row.op.id, $event)"
              @hover-region="hoverRetouchRegion($event)"
              @hover-retouch="hoverRetouchOp(row.op.id, $event)"
              @intent-hover="intentOpId = $event ? row.op.id : null"
              @drag-start="onDragStart(row.op.id, $event)"
              @drag-end="onDragEnd"
              @reenter="enterContainerOp(row.op)"
            />
            <div
              v-if="dropGap !== null && dropGap === row.index && row.index === lastVisibleIndex"
              :class="DROP_LINE"
            />
          </template>

          <!-- The image every edit above applies to. Last, because the stack
               composites bottom to top. -->
          <BaseRow
            v-if="baseInfo"
            :media-id="Number(baseInfo.media_id)"
            :width="baseInfo.width"
            :height="baseInfo.height"
          />
        </div>

        <!-- Inspector: the selected row's full control surface, under the
             stack. The row keeps only the eye as an immediate affordance. -->
        <!-- Properties is half the sidebar: these panels carry a dozen
             controls each, and a 288px window turned every one of them into a
             scrolling peephole. -->
        <div
          v-if="inspectorKind !== null"
          class="h-1 shrink-0 cursor-row-resize bg-edge-subtle/40 hover:bg-accent/40 transition-colors"
          @pointerdown="startPropertiesResize"
        />
        <div
          v-if="inspectorKind === 'annotation' && selectedShape"
          class="shrink-0 border-t border-edge-subtle flex flex-col"
          :style="{ height: propertiesHeight + 'px' }"
        >
          <div
            class="px-3 h-11 flex items-center shrink-0 bg-surface-raised/60
                   border-b border-edge-strong"
          >
            <h2 class="text-xs font-medium uppercase tracking-wide text-content-secondary">
              Properties
            </h2>
          </div>
          <div class="flex-1 min-h-0 overflow-y-auto custom-scrollbar">
            <AnnotationInspector
              :shape="selectedShape"
              :shapes="selectedAnnotationShapes"
              :palette="imagePalette"
              @change="onSelectedShapesChange"
              @commit="commitSelectedShapesChange"
              @remove="annotateRef?.deleteSelected()"
            />
          </div>
        </div>

        <div
          v-else-if="inspectorKind === 'retouch' && selectedRetouchRegion"
          class="shrink-0 border-t border-edge-subtle flex flex-col"
          :style="{ height: propertiesHeight + 'px' }"
        >
          <div
            class="px-3 h-11 flex items-center shrink-0 bg-surface-raised/60
                   border-b border-edge-strong"
          >
            <h2 class="text-xs font-medium uppercase tracking-wide text-content-secondary">
              Properties
            </h2>
          </div>
          <div class="flex-1 min-h-0 overflow-y-auto custom-scrollbar">
            <RetouchInspector
              :region="selectedRetouchRegion"
              :histogram="toneCurveHistogram"
              :picking="pointPicking"
              :clip-shadows="clipShadows"
              :clip-highlights="clipHighlights"
              @settings="setRetouchRegionSettings"
              @settings-commit="commitRetouchSettingsRender"
              @pick="armPointColorPick"
              @clip="setClipIndicators"
              @gradient="onInspectorGradient"
              @gradient-commit="commitInspectorGradient"
              @edit-mask="armScopedMaskEditing"
              @unscope="unscopeSelectedRegion"
            />
          </div>
        </div>

        <div
          v-else-if="inspectorKind === 'model' && selectedModelOp"
          class="shrink-0 border-t border-edge-subtle flex flex-col"
          :style="{ height: propertiesHeight + 'px' }"
        >
          <div
            class="px-3 h-11 flex items-center shrink-0 bg-surface-raised/60
                   border-b border-edge-strong"
          >
            <h2 class="text-xs font-medium uppercase tracking-wide text-content-secondary">
              Properties
            </h2>
          </div>
          <div class="flex-1 min-h-0 overflow-y-auto custom-scrollbar">
            <ModelEditInspector
              :op="selectedModelOp"
              :tool="selectedModelTool"
              :running="runningOpIds.has(selectedModelOp.id)"
              @params="setSelectedModelParams"
              @references="setSelectedModelReferences"
              @blend="setSelectedModelBlend"
              @blend-commit="commitSelectedModelBlend"
              @run="resample(selectedModelOp.id)"
            />
          </div>
        </div>

        <!-- Properties names the panel, so it is a level above the groups
             inside it: fixed, outside the scroll region, styled like the
             Edits header rather than like a section within. -->
        <div
          v-else-if="showsAdjustInspector"
          class="shrink-0 border-t border-edge-subtle flex flex-col"
          :style="{ height: propertiesHeight + 'px' }"
        >
          <div
            class="px-3 h-11 flex items-center shrink-0 bg-surface-raised/60
                   border-b border-edge-strong"
          >
            <h2 class="text-xs font-medium uppercase tracking-wide text-content-secondary">
              Properties
            </h2>
          </div>
          <div class="flex-1 min-h-0 overflow-y-auto custom-scrollbar">
          <AdjustInspector
            :params="adjustInspectorParams"
            :histogram="toneCurveHistogram"
            :picking="pointPicking"
            :clip-shadows="clipShadows"
            :clip-highlights="clipHighlights"
            :scope-eligible="!!selectedAdjustScopeGroup"
            :has-selection="!!selection"
            @change="onAdjustInspectorChange"
            @commit="commitAdjustInspectorChange"
            @pick="armPointColorPick"
            @clip="setClipIndicators"
            @limit="limitSelectedAdjustToSelection"
          />
          </div>
        </div>

        <p v-if="migrationNote" class="px-3 py-2 text-xs text-content-tertiary border-t border-edge-subtle">
          {{ migrationNote }}
        </p>
        <p v-if="error" class="px-3 py-2 text-xs text-red-400 border-t border-edge-subtle">
          {{ error }}
        </p>
        <p v-else-if="candidates.lastError.value" class="px-3 py-2 text-xs text-red-400 border-t border-edge-subtle">
          {{ candidates.lastError.value }}
        </p>
      </aside>
    </div>

      <!-- The commit bar. Left is session history, middle is what this document
           IS (which version, whether it has uncommitted work), right is what
           you can do to it. One meaning per control: the chip reports, Revert
           discards, Save commits. -->
    <footer class="flex items-center gap-2 px-3 h-11 shrink-0 border-t border-edge-subtle">
      <Tooltip text="Undo">
        <IconButton :disabled="!stack.canUndo.value" @click="stack.undo(); render()">
          <ArrowUturnLeftIcon class="w-4 h-4" />
        </IconButton>
      </Tooltip>
      <Tooltip text="Redo">
        <IconButton :disabled="!stack.canRedo.value" @click="stack.redo(); render()">
          <ArrowUturnRightIcon class="w-4 h-4" />
        </IconButton>
      </Tooltip>

      <span class="h-5 w-px bg-edge-subtle mx-1" />

      <div class="flex items-center gap-1" aria-label="Canvas zoom controls">
        <Tooltip text="Zoom out (−)">
          <IconButton
            aria-label="Zoom out"
            :disabled="viewZoom <= MIN_VIEW_ZOOM"
            @click="zoomViewBy(-1)"
          >
            <MinusIcon class="w-3.5 h-3.5" />
          </IconButton>
        </Tooltip>
        <span
          class="w-11 text-center font-mono text-[11px] tabular-nums text-content-secondary"
          aria-live="polite"
        >
          {{ viewZoomLabel }}
        </span>
        <Tooltip text="Zoom in (+)">
          <IconButton
            aria-label="Zoom in"
            :disabled="viewZoom >= MAX_VIEW_ZOOM"
            @click="zoomViewBy(1)"
          >
            <PlusIcon class="w-3.5 h-3.5" />
          </IconButton>
        </Tooltip>
        <Tooltip text="Fit and recenter (0)">
          <IconButton aria-label="Fit and recenter" @click="resetView">
            <ArrowsPointingInIcon class="w-3.5 h-3.5" />
          </IconButton>
        </Tooltip>
      </div>

      <Transition
        enter-active-class="transition-opacity duration-150"
        leave-active-class="transition-opacity duration-500"
        enter-from-class="opacity-0"
        leave-to-class="opacity-0"
      >
        <p v-if="savedNote" class="text-xs text-accent">{{ savedNote }}</p>
      </Transition>

      <div class="flex-1" />

      <!-- A mode toggle, not an action: lit with the selected-state indigo so
           its on-state reads like the app's other toggles. -->
      <button
        type="button"
        :disabled="!composite"
        :aria-pressed="comparing"
        class="inline-flex items-center justify-center rounded-md px-2.5 py-1.5 text-xs font-medium
               transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2
               ring-accent/60 ring-offset-1 ring-offset-surface disabled:opacity-50 disabled:cursor-not-allowed"
        :class="comparing
          ? 'bg-selection/15 text-selection'
          : 'bg-surface-raised hover:bg-surface-hover text-content'"
        @click="toggleCompare()"
      >
        Compare
      </button>

      <!-- Revert is about THIS session's uncommitted work, which is why it is
           disabled the moment there is none. Restoring an older version of the
           asset is a different verb and does not live here. -->
      <Tooltip :text="canRevert ? 'Discard edits made since the last save' : 'Nothing to revert'">
        <Button
          variant="secondary" size="sm"
          :disabled="!canRevert || saving"
          @click="confirmingRevert = true"
        >
          Revert
        </Button>
      </Tooltip>

      <!-- Split: saving to this asset is the act; forking to a new one is rare
           enough that giving it equal weight made the pair read as a choice
           every time. -->
      <div ref="saveMenuRef" class="relative flex items-stretch">
        <Button
          size="sm"
          class="rounded-r-none"
          :loading="saving"
          :disabled="saving || !composite"
          @click="save(false)"
        >
          <i v-if="savingNote">{{ savingNote }}</i>
          <template v-else>Save</template>
        </Button>
        <button
          type="button"
          class="px-1.5 rounded-r-md bg-accent hover:bg-accent/90 text-white
                 border-l border-white/20 transition-colors disabled:opacity-50
                 focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
          :disabled="saving || !composite"
          aria-label="More save options"
          @click="saveMenuOpen = !saveMenuOpen"
        >
          <ChevronUpIcon class="w-3.5 h-3.5" />
        </button>

        <!-- Opens upward: the bar is the last row of the window. -->
        <div
          v-if="saveMenuOpen"
          class="absolute bottom-full right-0 mb-1 w-56 py-1 z-menu
                 rounded-lg border border-edge-subtle bg-surface-overlay shadow-xl"
        >
          <button
            type="button"
            class="w-full flex items-center gap-3 px-3 py-2 text-left text-[13px] text-content hover:bg-overlay-light transition-colors"
            @click="saveMenuOpen = false; save(false)"
          >
            <span class="flex-1">Save a new version</span>
            <span class="text-[11px] text-content-tertiary">Default</span>
          </button>
          <button
            type="button"
            class="w-full px-3 py-2 text-left text-[13px] text-content hover:bg-overlay-light transition-colors"
            @click="saveMenuOpen = false; save(true)"
          >
            Save as new asset
          </button>
        </div>
      </div>
    </footer>

    <ConfirmDialog
      :show="confirmingRevert"
      title="Revert to the last saved version?"
      :message="`${revertCount} ${revertCount === 1 ? 'edit' : 'edits'} made since the last save will be undone. The saved version is not affected.`"
      confirm-label="Revert"
      danger
      @confirm="revertToSaved"
      @cancel="confirmingRevert = false"
    />
  </div>
</template>
