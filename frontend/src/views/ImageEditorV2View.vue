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
import EditRow from '../components/imageStack/EditRow.vue'
import CheckpointBand from '../components/imageStack/CheckpointBand.vue'
import StackMaskCanvas from '../components/imageStack/StackMaskCanvas.vue'
import { useStackDocument, newOpId } from '../composables/imageStack/useStackDocument'
import { useStackCandidates } from '../composables/imageStack/useStackCandidates'
import { StackCompositor, stackHashes, canvasToBlob } from '../composables/imageStack/useStackCompositor'
import { useProvidersApi } from '../composables/useProvidersApi'
import { useMediaApi } from '../composables/useMediaApi'
import { apiErrorMessage } from '../composables/imageStack/errors'
import { migrateLegacyProject } from '../composables/imageStack/migrateLegacyProject'
import {
  blastRadius, canMoveWithinSegment, checkpointStatus, deriveStackState, foldedCount,
} from '../composables/imageStack/stackState'
import {
  geometryBelow, coTransform, isIdentity, intersectsFrame, rewritePayload,
} from '../composables/imageStack/geometryTransform'
import type { GenerativeOp } from '../composables/imageStack/types'

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
type Mode = null | 'inpaint' | 'whole' | 'expand' | 'upscale'
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
  } catch (err: any) {
    error.value = err?.message || 'Could not render the composite.'
  } finally {
    rendering.value = false
  }
}

/** Fit the composite into the viewport; the mask overlay uses the same box. */
const displayBox = computed(() => {
  const doc = stack.doc.value
  const vp = viewportSize.value
  if (!doc || !vp.width || !vp.height) return { width: 0, height: 0 }
  const scale = Math.min(vp.width / doc.canvas.width, vp.height / doc.canvas.height, 1)
  return {
    width: Math.round(doc.canvas.width * scale),
    height: Math.round(doc.canvas.height * scale),
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
  ctx.drawImage(source, 0, 0)
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
    if (!refs.length) continue

    const previousIndex = before.edits.findIndex((candidate: any) => candidate.id === op.id)
    if (previousIndex < 0) continue

    const oldGeometry = geometryBelow(before, previousIndex)
    const newGeometry = geometryBelow(doc, index)
    const matrix = coTransform(oldGeometry.matrix, newGeometry.matrix)
    if (!matrix || isIdentity(matrix)) continue

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

/** Payload refs always name the master; derivatives are cache entries beside it. */
function masterRef(ref: string): string {
  return ref.startsWith('cache/') ? `payloads/${ref.slice('cache/'.length)}` : ref
}
function derivedName(ref: string): string {
  return ref.split('/').pop()!
}

// -- running a generative step ---------------------------------------------

const canRun = computed(() => {
  if (!composite.value || busy.value) return false
  if (regionTargetOpId.value) return !!maskCanvas.value
  if (mode.value === 'inpaint') return !!maskCanvas.value && !!inpaintToolId.value
  if (mode.value === 'whole') return !!prompt.value.trim() && !!wholeToolId.value
  // Expand auto-masks the border it adds, and Upscale takes no prompt, so
  // neither has anything to wait for beyond a tool.
  if (mode.value === 'expand') return !!inpaintToolId.value
  if (mode.value === 'upscale') return !!upscaleToolId.value
  return false
})

const busy = ref(false)

const generateSubTools = [
  { id: 'inpaint', label: 'Inpaint' },
  { id: 'whole', label: 'Whole image' },
  { id: 'expand', label: 'Expand' },
  { id: 'upscale', label: 'Upscale' },
] as const

const promptPlaceholder = computed(() => {
  if (regionTargetOpId.value) return 'Optional label for this region'
  if (mode.value === 'inpaint') return 'Describe what belongs here'
  if (mode.value === 'expand') return 'Describe what surrounds it'
  return 'Describe the change'
})

async function run() {
  if (!canRun.value || !stack.doc.value || !composite.value) return

  // A brushed region scopes an existing step rather than creating one.
  if (regionTargetOpId.value && maskCanvas.value) {
    const targetId = regionTargetOpId.value
    const ref = await stack.uploadPayload(
      `${targetId}-region.png`, await canvasToBlob(maskCanvas.value)
    )
    stack.setRegion(targetId, { mask_ref: ref, feather_px: 8, invert: false })
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
    let submitMask = isPatch ? maskCanvas.value : null
    if (mode.value === 'expand') {
      const grown = growCanvas(composite.value, expandFactor.value)
      submitInput = grown.image
      submitMask = grown.borderMask
      maskCanvas.value = grown.borderMask
    }

    let maskPayloadRef: string | undefined
    if (isPatch && maskCanvas.value) {
      maskPayloadRef = await stack.uploadPayload(
        `${opId}-mask.png`,
        await canvasToBlob(maskCanvas.value)
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
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'z') {
    event.preventDefault()
    if (event.shiftKey) stack.redo()
    else stack.undo()
    void render()
  }
  if (event.key === 'Escape' && mode.value) {
    // Esc leaves a mode with nothing to undo — empty steps cannot exist.
    mode.value = null
    maskCanvas.value = null
    maskRef.value?.clear()
  }
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
  <div class="h-full flex flex-col bg-base">
    <!-- Header -->
    <header class="flex items-center gap-3 px-4 h-12 border-b border-edge-subtle shrink-0">
      <h1 class="text-sm font-medium text-content">Edit image</h1>
      <span v-if="stack.dirtySinceSave.value" class="text-xs text-content-tertiary">
        Unsaved edits
      </span>
      <div class="flex-1" />
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
      <Button variant="secondary" size="sm" :disabled="saving" @click="save(true)">
        Save as new
      </Button>
      <Button size="sm" :loading="saving" :disabled="!composite" @click="save(false)">
        Save
      </Button>
    </header>

    <div v-if="loading" class="flex-1 grid place-items-center">
      <Spinner size="md" />
    </div>

    <div v-else class="flex-1 flex min-h-0">
      <!-- Canvas -->
      <div class="flex-1 flex flex-col min-w-0">
        <div ref="viewport" class="flex-1 min-h-0 grid place-items-center bg-matte p-6">
          <div class="relative" :style="{ width: displayBox.width + 'px', height: displayBox.height + 'px' }">
            <canvas
              ref="displayCanvas"
              class="rounded-media w-full h-full"
              :style="{ width: displayBox.width + 'px', height: displayBox.height + 'px' }"
            />
            <StackMaskCanvas
              v-if="mode === 'inpaint'"
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

        <!-- Generate family sub-toolbar. Entering a mode never edits the
             stack; the step is created by Run. -->
        <div class="border-t border-edge-subtle px-4 py-3 shrink-0 space-y-3">
          <div class="flex items-center gap-2">
            <span class="text-xs text-content-tertiary mr-1">Generate</span>
            <button
              v-for="option in generateSubTools"
              :key="option.id"
              type="button"
              class="px-2.5 py-1.5 text-xs rounded-md transition-colors"
              :class="mode === option.id
                ? 'bg-selection/15 text-content'
                : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'"
              @click="mode = mode === option.id ? null : option.id"
            >
              {{ option.label }}
            </button>

            <template v-if="mode === 'expand'">
              <div class="w-px h-5 bg-edge-subtle mx-1" />
              <label class="flex items-center gap-2 text-xs text-content-tertiary">
                Grow
                <input v-model.number="expandFactor" type="range" min="1.05" max="2" step="0.05" class="w-24" />
                <span class="tabular-nums">{{ Math.round(expandFactor * 100) }}%</span>
              </label>
            </template>

            <template v-if="mode === 'inpaint'">
              <div class="w-px h-5 bg-edge-subtle mx-1" />
              <button
                v-for="brush in (['paint', 'erase'] as const)"
                :key="brush"
                type="button"
                class="px-2.5 py-1.5 text-xs rounded-md capitalize transition-colors"
                :class="brushMode === brush
                  ? 'bg-selection/15 text-content'
                  : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'"
                @click="brushMode = brush"
              >
                {{ brush }}
              </button>
              <label class="flex items-center gap-2 text-xs text-content-tertiary ml-1">
                Size
                <input v-model.number="brushSize" type="range" min="8" max="300" class="w-24" />
              </label>
            </template>
          </div>

          <div v-if="mode" class="flex items-center gap-2">
            <input
              v-if="mode !== 'upscale'"
              v-model="prompt"
              type="text"
              :placeholder="promptPlaceholder"
              class="flex-1 px-3 py-2 text-sm bg-surface-raised rounded-md text-content placeholder:text-content-tertiary focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
              @keydown.enter="run"
            />
            <label class="flex items-center gap-2 text-xs text-content-tertiary">
              Count
              <input v-model.number="candidateCount" type="number" min="1" max="8"
                class="w-14 px-2 py-1.5 bg-surface-raised rounded-md text-content" />
            </label>
            <Button size="sm" :disabled="!canRun" :loading="busy" @click="run">Run</Button>
          </div>

          <p v-if="regionTargetOpId" class="text-xs text-content-tertiary">
            Brush the area to limit that edit to, then Run.
          </p>
          <p v-else-if="mode === 'inpaint' && !maskCanvas" class="text-xs text-content-tertiary">
            Brush over the area to change.
          </p>
        </div>
      </div>

      <!-- Edits -->
      <aside class="w-80 shrink-0 border-l border-edge-subtle flex flex-col min-h-0">
        <div class="px-3 h-10 flex items-center border-b border-edge-subtle">
          <h2 class="text-xs font-medium text-content-secondary">Edits</h2>
          <div class="flex-1" />
          <Spinner v-if="rendering" size="sm" />
        </div>

        <div class="flex-1 overflow-y-auto custom-scrollbar p-1.5">
          <!-- The base is a chip, not a row: it is what the stack applies to,
               not a step in it. -->
          <div class="px-2 py-2 text-xs text-content-tertiary">
            Source · v{{ baseInfo?.revision_id ?? '—' }}
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
              @toggle-enabled="stack.setEnabled(row.op.id, $event); render()"
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
              :resampling="resamplingOpId === row.op.id"
              :draggable="true"
              @select="selectedOpId = row.op.id"
              @toggle="stack.setEnabled(row.op.id, $event); render()"
              @pick="stack.pickCandidate(row.op.id, $event); render()"
              @remove="stack.removeOp(row.op.id); render()"
              @resample="resample(row.op.id)"
              @verb="runVerb(row.op.id, $event)"
              @intent-hover="intentOpId = $event ? row.op.id : null"
              @drag-start="onDragStart(row.op.id, $event)"
              @drop="onDrop(row.op.id)"
            />
          </template>

          <p v-if="!stack.ops.value.length" class="px-2 py-3 text-xs text-content-tertiary">
            No edits yet.
          </p>
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
  </div>
</template>
