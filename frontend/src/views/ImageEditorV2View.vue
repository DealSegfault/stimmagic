<script setup lang="ts">
/**
 * The op-stack image editor.
 *
 * The document is an ordered stack of ops over a base AssetRevision. Generative
 * steps submit through the existing job pipeline as context-owned candidates;
 * picking one composites client-side, taking only the pixels inside its mask.
 * Save materializes the composite as a new Revision — until then, nothing
 * outside this screen sees the stack (the rasterized-head invariant).
 *
 * Phase 1 scope: the Generate family (Inpaint, Whole image), staged candidates,
 * patch compositing, Save, and a read-only Edits list with eye toggles. Rows do
 * not reorder yet, which is why no staleness machinery is needed: with an
 * append-only stack nothing below an op can change.
 */
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { ArrowUturnLeftIcon, ArrowUturnRightIcon } from '@heroicons/vue/24/outline'
import Button from '../components/ui/Button.vue'
import IconButton from '../components/ui/IconButton.vue'
import Tooltip from '../components/ui/Tooltip.vue'
import Spinner from '../components/ui/Spinner.vue'
import EditRow from '../imageEditor/components/EditRow.vue'
import EditorToolbar from '../imageEditor/components/EditorToolbar.vue'
import EditorSubbar from '../imageEditor/components/EditorSubbar.vue'
import StackPaintCanvas from '../imageEditor/components/StackPaintCanvas.vue'
import StackSelectCanvas from '../imageEditor/components/StackSelectCanvas.vue'
import StackAnnotateCanvas from '../imageEditor/components/StackAnnotateCanvas.vue'
import CheckpointBand from '../imageEditor/components/CheckpointBand.vue'
import AdjustInspector from '../imageEditor/components/AdjustInspector.vue'
import AnnotationInspector from '../imageEditor/components/AnnotationInspector.vue'
import StackMaskCanvas from '../imageEditor/components/StackMaskCanvas.vue'
import StackCropCanvas from '../imageEditor/components/StackCropCanvas.vue'
import { useStackDocument, newOpId } from '../imageEditor/stack/useStackDocument'
import { useStackCandidates } from '../imageEditor/stack/useStackCandidates'
import { StackCompositor, stackHashes, canvasToBlob } from '../imageEditor/stack/useStackCompositor'
import { useProvidersApi } from '../composables/useProvidersApi'
import { useMediaApi } from '../composables/useMediaApi'
import { apiErrorMessage } from '../imageEditor/stack/errors'
import { migrateLegacyProject } from '../imageEditor/stack/migrateLegacyProject'
import {
  blastRadius, canMoveWithinSegment, checkpointStatus, deriveStackState, foldedCount,
} from '../imageEditor/stack/stackState'
import {
  geometryBelow, coTransform, isIdentity, intersectsFrame, rewritePayload,
  transformShapes,
} from '../imageEditor/stack/geometryTransform'
import {
  CROP_ASPECTS, cropRectForAspect, adjustLabel,
} from '../imageEditor/stack/adjustSections'
import { familyById, TOOL_FAMILIES } from '../imageEditor/stack/toolFamilies'
import type { FamilyId, SelectionMode } from '../imageEditor/stack/toolFamilies'
import type { GenerativeOp } from '../imageEditor/stack/types'
import type { AnnotateTool, Shape } from '../imageEditor/ported/shapeTypes'
import type { CropRect } from '../imageEditor/ported/useCropInteraction'
import { autoLevels, autoContrast, autoBalance } from '../imageEditor/ported/autoLevels'
import type { AdjustFamily } from '../imageEditor/stack/adjustSections'
import type { BrushSettings } from '../imageEditor/ported/geometry'

const props = defineProps<{ assetId: string; revisionId?: string }>()
const router = useRouter()

const stack = useStackDocument()
const { listAllTools } = useProvidersApi()
// <img> cannot send the X-Profile-ID header the profile middleware requires,
// which is why media URLs carry their database in the path.
const { getMediaFileUrl } = useMediaApi()

const loading = ref(true)
const error = ref<string | null>(null)
const baseInfo = ref<any>(null)

/** Generate sub-tool modes. Clicking a tool enters a mode; it never edits the
 *  stack. The step is created on the first real gesture — an explicit Run. */
type Mode = null | 'inpaint' | 'whole' | 'expand' | 'upscale' | 'adjust' | 'crop'
const mode = ref<Mode>(null)
const prompt = ref('')
const candidateCount = ref(4)
const brushSize = ref(80)
const brushMode = ref<'paint' | 'erase'>('paint')

const selectedOpId = ref<string | null>(null)
const maskCanvas = ref<HTMLCanvasElement | null>(null)
const maskRef = ref<InstanceType<typeof StackMaskCanvas> | null>(null)

const tools = ref<any[]>([])
const inpaintToolId = ref<string | null>(null)
const wholeToolId = ref<string | null>(null)
const upscaleToolId = ref<string | null>(null)
/** Expand grows the canvas and auto-masks the new border. */
const expandFactor = ref(1.25)
const upscaleFactor = ref(2)
/** Catalog tool picker for the active Generate sub-tool. */
const toolPickerOpen = ref(false)

// Select
const selectRef = ref<InstanceType<typeof StackSelectCanvas> | null>(null)
const selection = ref<HTMLCanvasElement | null>(null)
const selectCombine = ref<SelectionMode>('new')
const selectFeather = ref(0)
/** Magic wand colour tolerance, 0-255. */
const selectTolerance = ref(32)

// Paint
const paintRef = ref<InstanceType<typeof StackPaintCanvas> | null>(null)
const paintOpId = ref<string | null>(null)
const paintEngineId = ref('paint')
// The ported picker owns the whole brush, so there is one value here rather
// than a knob per parameter — size, hardness, opacity, flow and spacing all
// move together when a preset is chosen.
const paintBrush = ref<BrushSettings>({
  size: 26, hardness: 60, opacity: 100, flow: 100, spacing: 10,
})
const paintColorRgb = ref({ r: 201, g: 162, b: 118, a: 1 })
// Engine-specific gesture properties. Like the brush they are consumed at the
// moment of the stroke and belong to no step, so they live in the toolbar.
const paintExposure = ref(50)
const paintRange = ref<'shadows' | 'midtones' | 'highlights'>('midtones')
const paintFlow = ref(50)
const paintSaturate = ref(true)

// Annotate
const annotateRef = ref<InstanceType<typeof StackAnnotateCanvas> | null>(null)
const textStyle = ref<'pill' | 'plain' | 'outline' | 'neon'>('pill')
const shapeKind = ref<'rectangle' | 'ellipse' | 'line'>('rectangle')
const annotateColor = ref('#ffffff')
const selectedShapeId = ref<string | null>(null)

/**
 * The sub-bar names a family of tools; the ported gesture code wants the
 * specific one. Shape and Text carry a second choice, so the mapping is not
 * one-to-one.
 */
const annotateTool = computed<AnnotateTool>(() => {
  if (sub.value === 'redact') return 'redact'
  if (sub.value === 'text') return 'text'
  if (sub.value === 'select') return 'select'
  if (sub.value === 'draw') return 'sharpie'
  if (sub.value === 'arrow') return 'arrow'
  if (sub.value === 'shape') return shapeKind.value as AnnotateTool
  return 'arrow'
})

const annotateColorRgb = computed(() => {
  const hex = annotateColor.value.replace('#', '')
  return {
    r: parseInt(hex.slice(0, 2), 16),
    g: parseInt(hex.slice(2, 4), 16),
    b: parseInt(hex.slice(4, 6), 16),
    a: 1,
  }
})

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

/** Every annotation, in stack order — what the canvas draws and hit-tests. */
const annotateShapes = computed<Shape[]>(() =>
  annotateOps.value.flatMap(op => ((op as any).params?.shapes ?? []) as Shape[])
)

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
const rendering = ref(false)
const viewportSize = ref({ width: 0, height: 0 })
const viewport = ref<HTMLElement | null>(null)

const payloadCache = new Map<string, HTMLImageElement>()

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(`failed to load ${url}`))
    img.src = url
  })
}

const compositor = new StackCompositor({
  loadPayload: async (ref: string) => {
    const cached = payloadCache.get(ref)
    if (cached) return cached
    const img = await loadImage(stack.payloadUrl(ref))
    payloadCache.set(ref, img)
    return img
  },
  loadBase: async () => loadImage(getMediaFileUrl(Number(baseInfo.value.media_id))),
})

async function render() {
  // The ops watcher fires the moment open() populates the document, which is
  // before the base is assigned — without this the first render asks for the
  // base revision's media id and finds nothing.
  if (!stack.doc.value || !baseInfo.value) return
  rendering.value = true
  try {
    composite.value = await compositor.render(stack.doc.value)
    paint()
    samplePalette()
  } catch (err: any) {
    error.value = err?.message || 'Could not render the composite.'
  } finally {
    rendering.value = false
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

function paint() {
  const target = displayCanvas.value
  const source = composite.value
  if (!target || !source) return
  target.width = source.width
  target.height = source.height
  const ctx = target.getContext('2d')!
  ctx.clearRect(0, 0, target.width, target.height)
  // Comparing draws the base into the composite's frame, so geometry ops do
  // not make the two jump around while the key is held.
  const shown = comparing.value && baseImage.value ? baseImage.value : source
  ctx.drawImage(shown, 0, 0, target.width, target.height)
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
    const op = stack.opById(opId) as GenerativeOp | undefined
    if (op && !op.picked) stack.pickCandidate(opId, candidate.id)
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

/** Staleness, segments and folding are DERIVED, never stored. */
const stackState = computed(() => deriveStackState(stack.doc.value))

function stalenessOf(opId: string) {
  return stackState.value.ops.find(o => o.op.id === opId)?.staleness ?? 'clean'
}

/** Which rows the currently hovered gesture would disturb. */
const intentOpId = ref<string | null>(null)
const preview = computed(() =>
  intentOpId.value ? blastRadius(stack.doc.value, intentOpId.value) : null
)
function previewStalenessOf(opId: string) {
  if (!preview.value) return null
  if (preview.value.hard.has(opId)) return 'hard' as const
  if (preview.value.advisory.has(opId)) return 'advisory' as const
  return null
}

/** Checkpoint bands fold their inputs; a stale one always shows them. */
const expandedCheckpoints = ref<Set<string>>(new Set())
function toggleCheckpoint(opId: string) {
  const next = new Set(expandedCheckpoints.value)
  next.has(opId) ? next.delete(opId) : next.add(opId)
  expandedCheckpoints.value = next
}

/**
 * Rows the list actually shows, top-first. A clean checkpoint hides the steps
 * it folds, which is what keeps the resting state short.
 */
const visibleRows = computed(() => {
  const state = stackState.value
  const hidden = new Set<string>()
  for (const index of state.checkpoints) {
    const checkpoint = state.ops[index]
    if (!checkpoint) continue
    const stale = checkpoint.staleness === 'hard'
    if (stale || expandedCheckpoints.value.has(checkpoint.op.id)) continue
    for (const row of state.ops) {
      if (row.checkpointIndex === index) hidden.add(row.op.id)
    }
  }
  return [...state.ops].reverse().filter(row => !hidden.has(row.op.id))
})

/** A payload whose geometry has moved it entirely off the frame. */
const outOfFrame = computed(() => {
  const doc = stack.doc.value
  const result: Record<string, boolean> = {}
  if (!doc) return result
  for (let index = 0; index < doc.edits.length; index++) {
    const op = doc.edits[index] as any
    if (!op.mask_ref && !op.raster_ref) continue
    const geometry = geometryBelow(doc, index)
    result[op.id] = !intersectsFrame(
      geometry.matrix, doc.canvas.width, doc.canvas.height,
      geometry.width, geometry.height
    )
  }
  return result
})

// -- row verbs --------------------------------------------------------------

/**
 * The common ordering intents, as verbs that perform the move mechanically.
 * Expressing intent is the user's job; where the row ends up is ours.
 */
function verbsFor(opId: string) {
  const doc = stack.doc.value
  if (!doc) return []
  const index = doc.edits.findIndex(op => op.id === opId)
  const op = doc.edits[index]
  const lowestPatch = doc.edits.findIndex(o => o.class === 'patch')
  const isParametric = op?.class === 'parametric' || op?.class === 'container'

  return [
    {
      id: 'under-patches',
      label: 'Apply under the patches',
      disabled: lowestPatch < 0 || index < lowestPatch || !canMoveWithinSegment(doc, opId, lowestPatch),
    },
    {
      id: 'on-top',
      label: 'Apply on top',
      disabled: index === doc.edits.length - 1 || !canMoveWithinSegment(doc, opId, doc.edits.length),
    },
    { id: 'limit-to-region', label: op?.region ? 'Clear the region' : 'Limit to a region…' },
    { id: 'duplicate', label: 'Duplicate', disabled: !isParametric },
  ]
}

async function runVerb(opId: string, verb: string) {
  const doc = stack.doc.value
  if (!doc) return
  const before = JSON.parse(JSON.stringify(doc))

  if (verb === 'under-patches') {
    const target = doc.edits.findIndex(o => o.class === 'patch')
    if (target >= 0) stack.moveOp(opId, target)
  } else if (verb === 'on-top') {
    stack.moveOp(opId, doc.edits.length - 1)
  } else if (verb === 'limit-to-region') {
    const op = stack.opById(opId)
    if (op?.region) {
      stack.setRegion(opId, null)
    } else {
      // A region is a mask like any other, so scoping an adjustment reuses the
      // same brush the inpaint flow uses.
      regionTargetOpId.value = opId
      mode.value = 'inpaint'
      return
    }
  } else if (verb === 'duplicate') {
    const op = stack.opById(opId)
    if (op) {
      const copy = JSON.parse(JSON.stringify(op))
      copy.id = newOpId()
      copy.label = `${op.label} copy`
      stack.addOp(copy, doc.edits.findIndex(o => o.id === opId) + 1)
    }
  }

  await afterGeometryChange(before)
  void render()
}

/** The op a brushed region will be attached to, when scoping rather than inpainting. */
const regionTargetOpId = ref<string | null>(null)

// -- reorder ----------------------------------------------------------------

const dragOpId = ref<string | null>(null)

function onDragStart(opId: string, event: DragEvent) {
  dragOpId.value = opId
  intentOpId.value = opId
  event.dataTransfer?.setData('text/plain', opId)
}

async function onDrop(targetOpId: string) {
  const doc = stack.doc.value
  const source = dragOpId.value
  dragOpId.value = null
  intentOpId.value = null
  if (!doc || !source || source === targetOpId) return

  const target = doc.edits.findIndex(op => op.id === targetOpId)
  if (target < 0 || !canMoveWithinSegment(doc, source, target)) return

  const before = JSON.parse(JSON.stringify(doc))
  stack.moveOp(source, target)
  await afterGeometryChange(before)
  void render()
}

// -- geometry co-transform ---------------------------------------------------

/**
 * Rewrite spatial payloads whose geometry below them has changed.
 *
 * Derived from the AS-CREATED master each time rather than from the previous
 * derivative, so cropping and then un-cropping restores a mask exactly instead
 * of compounding resampling loss.
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
    const refs: Array<[string, string]> = []
    if (op.mask_ref) refs.push(['mask_ref', op.mask_ref])
    if (op.raster_ref) refs.push(['raster_ref', op.raster_ref])
    if (op.region?.mask_ref) refs.push(['region', op.region.mask_ref])
    const shapes = op.exec?.kind === 'annotate' ? op.params?.shapes : null
    if (!refs.length && !shapes?.length) continue

    const previousIndex = before.edits.findIndex((candidate: any) => candidate.id === op.id)
    if (previousIndex < 0) continue

    const oldGeometry = geometryBelow(before, previousIndex)
    const newGeometry = geometryBelow(doc, index)
    const matrix = coTransform(oldGeometry.matrix, newGeometry.matrix)
    if (!matrix || isIdentity(matrix)) continue

    // Annotations are vectors, so they are rewritten in place rather than
    // resampled — a crop and an un-crop restore them exactly.
    if (shapes?.length) {
      stack.setParams(op.id, {
        shapes: transformShapes(
          shapes, matrix,
          oldGeometry.width, oldGeometry.height,
          newGeometry.width, newGeometry.height
        ),
      })
    }

    for (const [, ref] of refs) {
      try {
        const master = await loadImage(stack.payloadUrl(masterRef(ref)))
        const rewritten = rewritePayload(master, matrix, newGeometry.width, newGeometry.height)
        // Derivatives live in cache/: they are reconstructible from the master,
        // so they must never displace it.
        await stack.uploadPayload(derivedName(ref), await canvasToBlob(rewritten), 'cache')
      } catch {
        // A payload that cannot be rewritten keeps its master; the row will
        // report Out of frame if it no longer lands anywhere.
      }
    }
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

/** Payload refs always name the master; derivatives are cache entries beside it. */
function masterRef(ref: string): string {
  return ref.startsWith('cache/') ? `payloads/${ref.slice('cache/'.length)}` : ref
}
function derivedName(ref: string): string {
  return ref.split('/').pop()!
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
  const before = JSON.parse(JSON.stringify(stack.doc.value))
  stack.removeOp(opId)
  if (opId === cropOpId.value) cropOpId.value = null
  await afterGeometryChange(before)
  void render()
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
  if (regionTargetOpId.value) return !!effectiveMask.value
  if (mode.value === 'inpaint') return !!effectiveMask.value && !!inpaintToolId.value
  if (mode.value === 'whole') return !!prompt.value.trim() && !!wholeToolId.value
  // Expand auto-masks the border it adds, and Upscale takes no prompt, so
  // neither has anything to wait for beyond a tool.
  if (mode.value === 'expand') return !!inpaintToolId.value
  if (mode.value === 'upscale') return !!upscaleToolId.value
  return false
})

const busy = ref(false)

/**
 * Tool families. Clicking one enters a MODE and opens its sub-toolbar; the step
 * is created on the first real gesture — a slider move, an aspect choice, an
 * explicit Run. Empty steps cannot exist, and Esc leaves a mode with nothing to
 * undo.
 */
/** The open family, or null when no mode is active. */
const family = ref<FamilyId | null>(null)
/** The active sub-tool within that family. */
const sub = ref<string | null>(null)

function selectFamily(id: FamilyId) {
  // Clicking the active family leaves it — entering and leaving are the same
  // gesture, and leaving with nothing drawn leaves nothing to undo.
  if (family.value === id) { leaveMode(); return }
  leaveMode()
  family.value = id
  sub.value = familyById(id).defaultSub
  if (id === 'generate') mode.value = (sub.value as Mode) ?? null
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
  sub.value = id
  if (family.value === 'generate') mode.value = id as Mode
}

/** Sub-toolbar state, flattened so the sub-bar stays a dumb renderer. */
const subbarState = computed(() => ({
  prompt: prompt.value,
  brushSize: brushSize.value,
  candidateCount: candidateCount.value,
  expandFactor: expandFactor.value,
  upscaleFactor: upscaleFactor.value,
  cropAspect: cropAspect.value,
  rotation: cropParamsOf().cropRotation ?? 0,
  flipX: !!cropParamsOf().flipX,
  flipY: !!cropParamsOf().flipY,
  combine: selectCombine.value,
  featherPx: selectFeather.value,
  tolerance: selectTolerance.value,
  hasSelection: !!selection.value,
  engineId: paintEngineId.value,
  paintBrush: paintBrush.value,
  paintColor: paintColorRgb.value,
  paintExposure: paintExposure.value,
  paintRange: paintRange.value,
  paintFlow: paintFlow.value,
  paintSaturate: paintSaturate.value,
  textStyle: textStyle.value,
  shapeKind: shapeKind.value,
  annotateColor: annotateColor.value,
  annotateColorRgb: annotateColorRgb.value,
  selectedShapeId: selectedShapeId.value,
  imagePalette: imagePalette.value,
}))

function onSubbarSet(patch: Record<string, any>) {
  if ('prompt' in patch) prompt.value = patch.prompt
  if ('brushSize' in patch) brushSize.value = patch.brushSize
  if ('candidateCount' in patch) candidateCount.value = patch.candidateCount
  if ('expandFactor' in patch) expandFactor.value = patch.expandFactor
  if ('upscaleFactor' in patch) upscaleFactor.value = patch.upscaleFactor
  if ('combine' in patch) selectCombine.value = patch.combine
  if ('featherPx' in patch) selectFeather.value = patch.featherPx
  if ('tolerance' in patch) selectTolerance.value = patch.tolerance
  if ('invertSelection' in patch) selectRef.value?.invert()
  if ('engineId' in patch) paintEngineId.value = patch.engineId
  if ('paintBrush' in patch) paintBrush.value = patch.paintBrush
  if ('paintColor' in patch) paintColorRgb.value = patch.paintColor
  if ('paintExposure' in patch) paintExposure.value = patch.paintExposure
  if ('paintRange' in patch) paintRange.value = patch.paintRange
  if ('paintFlow' in patch) paintFlow.value = patch.paintFlow
  if ('paintSaturate' in patch) paintSaturate.value = patch.paintSaturate
  if ('textStyle' in patch) textStyle.value = patch.textStyle
  if ('shapeKind' in patch) shapeKind.value = patch.shapeKind
  if ('annotateColor' in patch) annotateColor.value = patch.annotateColor
  if ('annotateColorRgb' in patch) {
    const { r, g, b } = patch.annotateColorRgb
    annotateColor.value =
      '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('')
  }
  if ('deleteShape' in patch) annotateRef.value?.deleteSelected()
  if ('auto' in patch) runAuto(patch.auto)
  if ('cropAspect' in patch) chooseAspect(patch.cropAspect)
  // Straighten and the lollipop are the same control: the crop window's tilt.
  if ('rotation' in patch) void applyCropChange({ cropRotation: patch.rotation })
  if ('rotateQuarter' in patch) rotateQuarter()
  if ('flipX' in patch) void applyCropChange({ flipX: patch.flipX })
  if ('flipY' in patch) void applyCropChange({ flipY: patch.flipY })
  if ('clearSelection' in patch) { selectRef.value?.clear(); selection.value = null }
  if ('newLayer' in patch) startNewPaintLayer()
}

/** One line of fact per mode: what to do, and what it will cost. */
/**
 * Only where the toolbar cannot speak for itself.
 *
 * A hint that narrates what the controls already show is noise — the tools are
 * the explanation. What survives is the one case where the app is WAITING for
 * something the user cannot see: a region brush, and the Generate sub-tools
 * whose cost and effect are not visible until they run.
 */
const subbarHint = computed(() => {
  if (regionTargetOpId.value) return 'Brush the area to limit that edit to'
  if (family.value === 'generate') {
    if (sub.value === 'inpaint') return 'Paint the area, then Run · Esc leaves'
    if (sub.value === 'whole') return 'Creates a checkpoint · everything below feeds it'
    if (sub.value === 'expand') return 'Grows the canvas · the new border is auto-masked'
    if (sub.value === 'upscale') return 'Creates a checkpoint · output continues at the new size'
  }
  return null
})

/** A step names the tool that made it the way the catalog does, not by slug. */
function toolNameFor(op: any): string {
  const id = op?.exec?.tool_id
  if (!id) return ''
  const tool = tools.value.find(t => t.full_tool_id === id)
  return tool?.name || tool?.display_name || ''
}

/** The catalog tool that will run the active Generate sub-tool. */
const activeToolId = computed(() => {
  if (sub.value === 'upscale') return upscaleToolId.value
  if (sub.value === 'whole') return wholeToolId.value
  return inpaintToolId.value
})
const activeToolLabel = computed(() => {
  const tool = tools.value.find(t => t.full_tool_id === activeToolId.value)
  return tool ? tool.name : null
})

async function run() {
  if (!canRun.value || !stack.doc.value || !composite.value) return

  // A brushed region scopes an existing step rather than creating one.
  if (regionTargetOpId.value && effectiveMask.value) {
    const targetId = regionTargetOpId.value
    const ref = await stack.uploadPayload(
      `${targetId}-region.png`, await canvasToBlob(effectiveMask.value)
    )
    const targetIndex = stack.doc.value?.edits.findIndex(o => o.id === targetId) ?? 0
    stack.setParams(targetId, {})
    ;(stack.opById(targetId) as any).payload_frame = payloadFrame(targetIndex)
    stack.setRegion(targetId, { mask_ref: ref, feather_px: selectFeather.value, invert: false })
    regionTargetOpId.value = null
    mode.value = null
    maskCanvas.value = null
    maskRef.value?.clear()
    void render()
    return
  }

  busy.value = true
  error.value = null
  try {
    const isPatch = mode.value === 'inpaint' || mode.value === 'expand'
    const toolId = mode.value === 'upscale'
      ? upscaleToolId.value!
      : isPatch ? inpaintToolId.value! : wholeToolId.value!
    const tool = tools.value.find(t => t.full_tool_id === toolId)
    if (!tool) throw new Error('That tool is no longer in the catalog.')

    // The op's input is the current head composite: Phase 1 appends on top,
    // so its input hash is the head hash.
    const { head } = stackHashes(stack.doc.value)

    const opId = newOpId()

    // Expand grows the frame and auto-masks the border it added — the same
    // extend-pad invariant the prep flow uses — then fills it like any patch.
    let submitInput = composite.value
    let submitMask = isPatch ? (maskCanvas.value || selectionAsMask()) : null
    if (mode.value === 'expand') {
      const grown = growCanvas(composite.value, expandFactor.value)
      submitInput = grown.image
      submitMask = grown.borderMask
    }

    let maskPayloadRef: string | undefined
    if (isPatch && submitMask) {
      maskPayloadRef = await stack.uploadPayload(
        `${opId}-mask.png`, await canvasToBlob(submitMask)
      )
    }

    const label =
      mode.value === 'upscale' ? 'Upscale'
      : mode.value === 'expand' ? 'Expand'
      : isPatch ? `Inpaint${prompt.value.trim() ? ` — ${prompt.value.trim()}` : ''}`
      : `Edit — ${prompt.value.trim()}`

    const op: GenerativeOp = {
      id: opId,
      class: isPatch ? 'patch' : 'whole',
      enabled: true,
      label,
      exec: { kind: 'tool', tool_id: toolId, task_type: tool.task_type },
      params: { prompt: prompt.value },
      ...(maskPayloadRef ? { mask_ref: maskPayloadRef } : {}),
      // The mask, and the candidates generated for it, are anchored to the
      // frame they were made in.
      payload_frame: payloadFrame(),
      blend: { feather_px: 6, opacity: 1 },
      picked: null,
      candidates: [],
    }
    stack.addOp(op)
    selectedOpId.value = opId

    await candidates.submit({
      opId,
      tool,
      inputCanvas: submitInput,
      maskCanvas: submitMask,
      prompt: prompt.value,
      count: candidateCount.value,
      sampledInputHash: head,
    })

    // Leaving the mode clears the brush: the step now owns that mask.
    mode.value = null
    maskCanvas.value = null
    maskRef.value?.clear()
    prompt.value = ''
  } catch (err: any) {
    error.value = apiErrorMessage(err, 'Could not start the edit.')
  } finally {
    busy.value = false
  }
}

/**
 * Re-run a generative step against its CURRENT input.
 *
 * Patch rows resample, checkpoints regenerate — the same mechanism, named for
 * what each costs the user's mental model. Old candidates are kept and marked
 * as sampled from a previous state: switching back to one is free and restores
 * the prior look, which is what makes a regeneration safe to try.
 */
const resamplingOpId = ref<string | null>(null)

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

  resamplingOpId.value = opId
  error.value = null
  try {
    // The op's input composite, not the head: a step re-samples against what it
    // actually sits on.
    const inputCanvas = await compositor.renderUpTo(doc, index)
    let mask: HTMLCanvasElement | null = null
    if (op.class === 'patch' && (op as any).mask_ref) {
      const image = await loadImage(stack.payloadUrl((op as any).mask_ref))
      mask = document.createElement('canvas')
      mask.width = inputCanvas.width
      mask.height = inputCanvas.height
      mask.getContext('2d')!.drawImage(image, 0, 0, mask.width, mask.height)
    }
    await candidates.submit({
      opId,
      tool,
      inputCanvas,
      maskCanvas: mask,
      prompt: (op.params as any)?.prompt || '',
      count: candidateCount.value,
      sampledInputHash: inputHash,
    })
  } catch (err: any) {
    error.value = apiErrorMessage(err, 'Could not resample.')
  } finally {
    resamplingOpId.value = null
  }
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
 * The Adjust step this session is editing. One step per mode session: entering
 * Adjust and moving a slider creates it, and every further move edits that
 * same step rather than stacking one per slider.
 */
const adjustOpId = ref<string | null>(null)

const adjustParams = computed<Record<string, any>>(() => {
  const op = adjustOpId.value ? stack.opById(adjustOpId.value) : null
  return (op as any)?.params || {}
})

function onAdjustChange(patch: Record<string, any>, coalesceKey: string) {
  if (!stack.doc.value) return
  if (!adjustOpId.value) {
    const opId = newOpId()
    stack.addOp({
      id: opId, class: 'parametric', enabled: true,
      label: adjustLabel(patch), exec: { kind: 'adjust' }, params: patch,
    } as any)
    adjustOpId.value = opId
    selectedOpId.value = opId
  } else {
    stack.setParams(adjustOpId.value, patch, coalesceKey)
    const op = stack.opById(adjustOpId.value)
    if (op) stack.setLabel(adjustOpId.value, adjustLabel((op as any).params || {}))
  }
  void render()
}

/**
 * Selecting a Adjust row makes the inspector edit THAT row, which is how an
 * earlier session's step is re-entered rather than a new one being stacked.
 */
const selectedAdjustOp = computed(() => {
  const op = selectedOpId.value ? stack.opById(selectedOpId.value) : null
  return op && op.class === 'parametric' && (op as any).exec?.kind === 'adjust' ? op : null
})

/**
 * The inspector shows for a selected Adjust row, and also whenever the Adjust
 * family is open with nothing selected — otherwise the FIRST Adjust step could
 * never be created, since there would be no row to select to get its controls.
 */
const ADJUST_FAMILIES: FamilyId[] = ['levels', 'filters', 'effects']
const adjustFamily = computed<AdjustFamily | null>(() =>
  ADJUST_FAMILIES.includes(family.value as FamilyId) ? (family.value as AdjustFamily) : null
)

const showsAdjustInspector = computed(
  () => !!selectedAdjustOp.value || !!adjustFamily.value
)

/**
 * The three Auto buttons from the old Levels panel. They read the histogram of
 * the image BELOW the step and propose slider values — nothing is baked, so an
 * auto result is a normal adjustable step.
 */
function runAuto(kind: 'levels' | 'contrast' | 'balance') {
  const source = composite.value
  const patch = kind === 'levels' ? autoLevels(source)
    : kind === 'contrast' ? autoContrast(source)
    : autoBalance(source)
  if (!patch) return
  if (selectedAdjustOp.value) adjustOpId.value = selectedAdjustOp.value.id
  onAdjustChange(patch, `adjust:auto:${kind}`)
}

const adjustInspectorParams = computed<Record<string, any>>(
  () => (selectedAdjustOp.value as any)?.params || adjustParams.value
)

function onAdjustInspectorChange(patch: Record<string, any>, coalesceKey: string) {
  // Selecting a row re-enters THAT step; with nothing selected the session's
  // own step is created on the first move and edited thereafter.
  if (selectedAdjustOp.value) adjustOpId.value = selectedAdjustOp.value.id
  onAdjustChange(patch, coalesceKey)
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
  if (live) { void render(); return }
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
const selectedShape = computed<Shape | null>(() => {
  if (family.value !== 'annotate' || !selectedShapeId.value) return null
  return annotateShapes.value.find(s => s.id === selectedShapeId.value) ?? null
})

function onShapeChange(patch: Record<string, any>) {
  const id = selectedShapeId.value
  if (!id) return
  onAnnotationsChange(
    annotateShapes.value.map(s => (s.id === id ? { ...s, ...patch } as Shape : s))
  )
  annotateGesture.value += 1
}

/**
 * Colours sampled off the composite, so the pickers can offer the image's own
 * palette rather than only a fixed row of swatches.
 */
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
  // actual colours without pretending to be a clustering algorithm.
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
async function onPaintStroke(layer: HTMLCanvasElement, readsPixels: boolean) {
  if (!stack.doc.value) return
  const opId = paintOpId.value || newOpId()
  const blob = await canvasToBlob(layer)
  const ref = await stack.uploadPayload(`${opId}-layer.png`, blob)

  if (!paintOpId.value) {
    const { head } = stackHashes(stack.doc.value)
    stack.addOp({
      id: opId,
      class: 'container',
      enabled: true,
      label: readsPixels ? 'Retouch' : 'Paint',
      exec: { kind: readsPixels ? 'retouch' : 'paint' },
      raster_ref: ref,
      payload_frame: payloadFrame(),
      blend: { feather_px: 0, opacity: 1 },
      // A pixel-reading engine baked what was underneath, so its layer carries
      // an advisory hash exactly like a generative patch.
      ...(readsPixels ? { sampled_input_hash: head } : {}),
    } as any)
    paintOpId.value = opId
    selectedOpId.value = opId
  } else {
    // The payload changed under the same ref; nudge the cache so the composite
    // picks it up.
    payloadCache.delete(ref)
    stack.touchOp(opId)
  }
  // The composite owns the stroke from here; the overlay handing off rather
  // than keeping a copy is what stops the halo and the paint that outlived
  // its own step being switched off.
  await render()
  paintRef.value?.clearDisplay()
}

/**
 * Double-clicking a row re-enters THAT step rather than starting another: a
 * Paint layer keeps painting into itself, an Annotate step keeps accumulating
 * shapes, and a Crop reopens on its own input — which is what makes a second
 * crop a deliberate act rather than the only thing you can do.
 */
function enterContainerOp(op: any) {
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
    sub.value = 'select'
    selectedShapeId.value = (op.params?.shapes ?? [])[0]?.id ?? null
    return
  }
  void enterPaintOp(op.id)
}

function startNewPaintLayer() {
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
  if (!op?.raster_ref) return
  family.value = 'paint'
  paintOpId.value = opId
  const image = await loadImage(stack.payloadUrl(op.raster_ref))
  const canvas = document.createElement('canvas')
  canvas.width = image.naturalWidth
  canvas.height = image.naturalHeight
  canvas.getContext('2d')!.drawImage(image, 0, 0)
  paintInitialLayer.value = canvas
}

// -- annotate --------------------------------------------------------------------

/**
 * Annotations accumulate into one Annotate step per session. The shapes are the
 * params, so the step stays vector and re-entering it is lossless.
 */
/**
 * Dragging a shape reports a new shape list on every mouse move. Every one of
 * those is written — nothing is held back, so a text edit that never announces
 * itself cannot be lost — but they all coalesce into a single journal entry,
 * which the gesture's own commit then closes. One gesture, one undo.
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
  if (!stack.doc.value) return

  const seen = new Set<string>()
  for (const shape of shapes) {
    seen.add(shape.id)
    const opId = opIdForShape(shape.id)
    if (opId) {
      const existing = ((stack.opById(opId) as any)?.params?.shapes ?? [])[0]
      if (JSON.stringify(existing) === JSON.stringify(shape)) continue
      stack.setParams(opId, { shapes: [shape] }, `${annotateGestureKey.value}:${shape.id}`)
      stack.setLabel(opId, shapeLabel(shape))
    } else {
      const newId = newOpId()
      stack.addOp({
        id: newId,
        class: 'container',
        enabled: true,
        label: shapeLabel(shape),
        exec: { kind: 'annotate' },
        params: { shapes: [shape] },
      } as any)
      selectedOpId.value = newId
    }
  }

  for (const op of annotateOps.value) {
    const held = ((op as any).params?.shapes ?? []) as Shape[]
    if (held.every(s => seen.has(s.id))) continue
    stack.removeOp(op.id)
  }
  void render()
}

/** Selecting an annotation selects its step, so the stack follows the canvas. */
function onShapeSelected(shapeId: string | null) {
  selectedShapeId.value = shapeId
  const opId = shapeId ? opIdForShape(shapeId) : null
  if (opId) selectedOpId.value = opId
}

/** The gesture ended: the next one starts its own undo step. */
function onAnnotationCommit(_action: string) {
  annotateGesture.value += 1
}

// -- selection handoff ------------------------------------------------------------

/**
 * A live selection pre-fills the next mask. Consumed by COPY at the moment it
 * is used, never live-linked — the op ends up referencing only its own payload.
 */
function selectionAsMask(): HTMLCanvasElement | null {
  if (!selection.value) return null
  const copy = document.createElement('canvas')
  copy.width = selection.value.width
  copy.height = selection.value.height
  copy.getContext('2d')!.drawImage(selection.value, 0, 0)
  return copy
}

/** The mask a Generate run will use: the brush if painted, else the selection. */
const effectiveMask = computed(() => maskCanvas.value || selection.value)

// -- compare -------------------------------------------------------------------

/**
 * Hold to see the base. Nearly free with an op stack — toggling the whole stack
 * off is what the cache already does — and the snapshot editor never had it.
 */
const comparing = ref(false)
const baseImage = ref<HTMLImageElement | null>(null)

async function setComparing(value: boolean) {
  comparing.value = value
  if (value && !baseImage.value && baseInfo.value) {
    baseImage.value = await loadImage(getMediaFileUrl(Number(baseInfo.value.media_id)))
  }
  paint()
}

// -- save ------------------------------------------------------------------

const saving = ref(false)
const savedRevisionId = ref<number | null>(null)

async function save(asNew = false) {
  if (!composite.value || !stack.doc.value) return
  saving.value = true
  error.value = null
  try {
    await stack.flush()
    const blob = await canvasToBlob(composite.value)
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
    stack.dirtySinceSave.value = false
    if (asNew) {
      router.push({ name: 'edit-image-v2', params: { assetId: String(data.asset_id) } })
    }
  } catch (err: any) {
    error.value = apiErrorMessage(err, 'Could not save.')
  } finally {
    saving.value = false
  }
}

// -- legacy migration ------------------------------------------------------

const migrationNote = ref<string | null>(null)

async function importLegacyProject(project: any) {
  const { ops, rasters, dropped } = migrateLegacyProject(project)
  if (!ops.length && !dropped.length) return

  // Payloads first: an op whose raster is missing would render as a no-op.
  for (const raster of rasters) {
    const blob = await (await fetch(raster.dataUrl)).blob()
    await stack.uploadPayload(raster.name, blob)
  }
  for (const op of ops) stack.addOp(op)
  await stack.flush()

  migrationNote.value = dropped.length
    ? `Imported ${ops.length} ${ops.length === 1 ? 'edit' : 'edits'}. ${dropped.join(' ')}`
    : `Imported ${ops.length} ${ops.length === 1 ? 'edit' : 'edits'} from the previous editor.`
}

// -- lifecycle -------------------------------------------------------------

function onKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement
  if (target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA') return
  // Canvas text editing has no focusable element to hide behind, so the
  // single-key tool shortcuts would eat the typing: 'e' and 'l' switched to
  // Effects and Levels mid-word and unmounted the editor being typed into.
  if (annotateRef.value?.isEditingText()) return
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'z') {
    event.preventDefault()
    if (event.shiftKey) stack.redo()
    else stack.undo()
    void render()
  }
  if (event.key === 'Escape' && (mode.value || regionTargetOpId.value)) {
    // Esc leaves a mode with nothing to undo — empty steps cannot exist.
    leaveMode()
  }
  // Hold to compare against the base.
  if (event.key === '\\' && !event.repeat) void setComparing(true)
  const shortcut = TOOL_FAMILIES.find(f => f.key === event.key.toLowerCase())
  if (shortcut && !event.metaKey && !event.ctrlKey) selectFamily(shortcut.id)
}

function onKeyup(event: KeyboardEvent) {
  if (event.key === '\\') void setComparing(false)
}

/** Leaving a mode ends its session: the next entry starts a new step. */
function leaveMode() {
  family.value = null
  sub.value = null
  mode.value = null
  regionTargetOpId.value = null
  maskCanvas.value = null
  maskRef.value?.clear()
  // Ending a mode session ends its STEP: the next entry starts a new one.
  adjustOpId.value = null
  cropOpId.value = null
  paintOpId.value = null
  paintInitialLayer.value = null
}

let resizeObserver: ResizeObserver | null = null

onMounted(async () => {
  try {
    const opened = await stack.open(Number(props.assetId), props.revisionId ? Number(props.revisionId) : undefined)
    baseInfo.value = opened.base
    candidates.start()

    // A project saved by the snapshot editor converts on first open. The
    // sidecar itself is left untouched, so the old editor keeps reading it.
    if (opened.legacyProject && !stack.ops.value.length) {
      await importLegacyProject(opened.legacyProject)
    }

    const all = await listAllTools()
    tools.value = all
    inpaintToolId.value = all.find(t => (t.task_types || []).includes('inpaint-image'))?.full_tool_id ?? null
    wholeToolId.value = all.find(t => (t.task_types || []).includes('image-to-image'))?.full_tool_id ?? null
    upscaleToolId.value = all.find(t => (t.task_types || []).includes('upscale-image'))?.full_tool_id ?? null

    await render()
  } catch (err: any) {
    error.value = apiErrorMessage(err, 'Could not open this image.')
  } finally {
    loading.value = false
  }

  window.addEventListener('keydown', onKeydown)
  window.addEventListener('keyup', onKeyup)
})

// The viewport only exists once loading finishes, so the observer attaches when
// the element appears rather than at mount — otherwise the canvas is sized
// against a viewport of 0x0 and never paints.
watch(viewport, element => {
  resizeObserver?.disconnect()
  if (!element) return
  resizeObserver = new ResizeObserver(entries => {
    const box = entries[0].contentRect
    viewportSize.value = { width: box.width, height: box.height }
  })
  resizeObserver.observe(element)
}, { flush: 'post' })

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('keyup', onKeyup)
  resizeObserver?.disconnect()
  candidates.stop()
  void stack.flush().catch(() => {})
})

watch(() => stack.ops.value.length, () => { void render() })
// The composite is usually ready BEFORE the canvas exists (rendering happens
// while `loading` still hides it), so repaint on either changing rather than
// only on the composite.
watch([composite, displayCanvas, displayBox], () => nextTick(paint), { flush: 'post' })
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
        <h1 class="text-sm font-medium text-content shrink-0">Edit image</h1>
        <span v-if="stack.dirtySinceSave.value" class="text-xs text-content-tertiary shrink-0">
          Unsaved edits
        </span>
        <EditorToolbar :active="family" class="ml-2" @select="selectFamily" />
      </div>

      <!-- Toolbar 2: the active family's controls. Present only when a family
           is open; the canvas below simply gets more or less matte. -->
      <EditorSubbar
        v-if="family"
        :family="family"
        :sub="sub"
        :state="subbarState"
        :tool-label="activeToolLabel"
        :busy="busy"
        :can-run="canRun"
        :hint="subbarHint"
        class="shrink-0"
        @sub="selectSub"
        @set="onSubbarSet"
        @run="run"
        @open-tool-picker="toolPickerOpen = true"
      />

      <div v-if="loading" class="flex-1 grid place-items-center">
        <Spinner size="md" />
      </div>

      <!-- Canvas. Centred in whatever matte is left. -->
      <div v-else ref="viewport" class="flex-1 min-h-0 grid place-items-center bg-matte p-6">
        <!-- Crop works on the step's INPUT, not on the composite: the region
             outside the crop is dimmed rather than absent, so it takes the
             whole viewport instead of the cropped display box. -->
        <div
          v-if="family === 'crop'"
          class="relative"
          :style="{ width: viewportSize.width + 'px', height: viewportSize.height + 'px' }"
        >
          <StackCropCanvas
            :source="cropInput"
            :crop="cropRect"
            :flip-x="!!cropParamsOf().flipX"
            :flip-y="!!cropParamsOf().flipY"
            :rotation="cropParamsOf().rotation ?? 0"
            :rotation90="cropParamsOf().rotation90 ?? 0"
            :view-width="viewportSize.width"
            :view-height="viewportSize.height"
            @change="onCropRectChange"
            @commit="onCropCommit"
          />
        </div>
        <div v-else class="relative" :style="{ width: displayBox.width + 'px', height: displayBox.height + 'px' }">
          <canvas
            ref="displayCanvas"
            class="rounded-media w-full h-full"
            :style="{ width: displayBox.width + 'px', height: displayBox.height + 'px' }"
          />
          <!-- Select draws over the composite; its output becomes the next
               mask or region rather than a step of its own. -->
          <StackSelectCanvas
            v-if="family === 'select'"
            ref="selectRef"
            :source="composite"
            :display-width="displayBox.width"
            :display-height="displayBox.height"
            :tool="(sub as any)"
            :combine="selectCombine"
            :feather-px="selectFeather"
            :tolerance="selectTolerance"
            @change="selection = $event"
          />
          <StackPaintCanvas
            v-else-if="family === 'paint'"
            ref="paintRef"
            :source="composite"
            :initial-layer="paintInitialLayer"
            :selection-mask="selection"
            :display-width="displayBox.width"
            :display-height="displayBox.height"
            :engine-id="paintEngineId"
            :brush="paintBrush"
            :color="paintColorRgb"
            :exposure="paintExposure"
            :range="paintRange"
            :flow="paintFlow"
            :saturate="paintSaturate"
            @stroke="onPaintStroke"
          />
          <StackAnnotateCanvas
            v-else-if="family === 'annotate'"
            ref="annotateRef"
            :source="composite"
            :shapes="annotateShapes"
            :display-width="displayBox.width"
            :display-height="displayBox.height"
            :tool="annotateTool"
            :stroke-color="annotateColorRgb"
            :text-style="textStyle"
            @change="onAnnotationsChange"
            @commit="onAnnotationCommit"
            @select="onShapeSelected"
          />
          <StackMaskCanvas
            v-else-if="mode === 'inpaint' || regionTargetOpId"
            ref="maskRef"
            :source="composite"
            :display-width="displayBox.width"
            :display-height="displayBox.height"
            :mode="brushMode"
            :brush-size="brushSize"
            @change="maskCanvas = $event"
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
        class="shrink-0 border-l border-edge-subtle flex flex-col min-h-0"
        :style="{ width: sidebarWidth + 'px' }"
      >
        <div class="px-3 h-11 flex items-center border-b border-edge-subtle">
          <h2 class="text-xs font-medium text-content-secondary">Edits</h2>
          <div class="flex-1" />
          <Spinner v-if="rendering" size="sm" />
        </div>

        <div class="flex-1 overflow-y-auto custom-scrollbar p-1.5">
          <!-- The base is a chip, not a row: it is what the stack applies to,
               not a step in it. -->
          <div class="px-2 py-2 text-xs text-content-tertiary">
            Original image
          </div>

          <!-- Top of the stack reads first, the way the image is built up. -->
          <template v-for="row in visibleRows" :key="row.op.id">
            <CheckpointBand
              v-if="row.op.class === 'whole'"
              :op="row.op"
              :selected="selectedOpId === row.op.id"
              :staleness="row.staleness"
              :folded-count="foldedCount(stack.doc.value, row.index)"
              :expanded="expandedCheckpoints.has(row.op.id)"
              :status-line="checkpointStatus(stackState, row.index)"
              :regenerating="resamplingOpId === row.op.id"
              @select="selectedOpId = row.op.id"
              @toggle-expanded="toggleCheckpoint(row.op.id)"
              @toggle-enabled="setEnabledWithGeometry(row.op.id, $event)"
              @regenerate="resample(row.op.id)"
            />
            <EditRow
              v-else
              :op="row.op"
              :selected="selectedOpId === row.op.id"
              :staleness="row.staleness"
              :candidate-thumbs="candidateThumbs[row.op.id]"
              :pending-count="pendingByOp[row.op.id]"
              :preview-staleness="previewStalenessOf(row.op.id)"
              :out-of-frame="outOfFrame[row.op.id]"
              :verbs="verbsFor(row.op.id)"
              :tool-name="toolNameFor(row.op)"
              :resampling="resamplingOpId === row.op.id"
              :draggable="true"
              @select="selectedOpId = row.op.id"
              @toggle="setEnabledWithGeometry(row.op.id, $event)"
              @pick="stack.pickCandidate(row.op.id, $event); render()"
              @remove="removeOpWithGeometry(row.op.id)"
              @resample="resample(row.op.id)"
              @verb="runVerb(row.op.id, $event)"
              @intent-hover="intentOpId = $event ? row.op.id : null"
              @drag-start="onDragStart(row.op.id, $event)"
              @drop="onDrop(row.op.id)"
              @reenter="enterContainerOp(row.op)"
            />
          </template>

          <p v-if="!stack.ops.value.length" class="px-2 py-3 text-xs text-content-tertiary">
            No edits yet.
          </p>
        </div>

        <!-- Inspector: the selected row's full control surface, under the
             stack. The row keeps only the eye as an immediate affordance. -->
        <!-- Properties is half the sidebar: these panels carry a dozen
             controls each, and a 288px window turned every one of them into a
             scrolling peephole. -->
        <div v-if="selectedShape" class="shrink-0 border-t border-edge-subtle flex flex-col max-h-[50%]">
          <div class="px-3 h-11 flex items-center border-b border-edge-subtle shrink-0">
            <h2 class="text-xs font-medium text-content-secondary">Properties</h2>
          </div>
          <div class="flex-1 min-h-0 overflow-y-auto custom-scrollbar">
            <AnnotationInspector
              :shape="selectedShape"
              :palette="imagePalette"
              @change="onShapeChange"
              @remove="annotateRef?.deleteSelected()"
            />
          </div>
        </div>

        <!-- Properties names the panel, so it is a level above the groups
             inside it: fixed, outside the scroll region, styled like the
             Edits header rather than like a section within. -->
        <div
          v-else-if="showsAdjustInspector"
          class="shrink-0 border-t border-edge-subtle flex flex-col max-h-[50%]"
        >
          <div class="px-3 h-11 flex items-center border-b border-edge-subtle shrink-0">
            <h2 class="text-xs font-medium text-content-secondary">Properties</h2>
          </div>
          <div class="flex-1 min-h-0 overflow-y-auto custom-scrollbar">
          <AdjustInspector
            :family="adjustFamily"
            :source="composite"
            :params="adjustInspectorParams"
            @change="onAdjustInspectorChange"
            @commit="stack.flush()"
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

      <!-- Document verbs live at the bottom: they act on the document, not on
         whatever tool happens to be open. -->
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
      <div class="flex-1" />
      <Button
        variant="secondary" size="sm"
        @pointerdown="setComparing(true)"
        @pointerup="setComparing(false)"
        @pointerleave="setComparing(false)"
      >
        Hold to compare
      </Button>
      <Button variant="secondary" size="sm" :disabled="saving" @click="save(true)">
        Save as new
      </Button>
      <Button size="sm" :loading="saving" :disabled="!composite" @click="save(false)">
        Save version
      </Button>
    </footer>
  </div>
</template>
