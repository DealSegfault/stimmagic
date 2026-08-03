/**
 * Every model-backed run the editor makes: staged candidates for the steps in
 * the stack, and the one-shot run the output stage makes at save time.
 *
 * Candidates are job outputs, not versions and not library tiles. They run with
 * `output_disposition: 'context'` rooted at the editor's working document, so
 * they are durable and reachable without ever becoming Assets. Picking one
 * commits nothing to the version chain — it only updates document.json.
 *
 * Every candidate is a PATCH. There is no whole-image class any more: a run
 * whose result replaces the composite outright is a new base, and the only
 * operation allowed to make one is the output stage, which produces a saved
 * version rather than a row (`runToolOnce`).
 *
 * Invocations are built exactly the way ToolView builds them, through the same
 * schema-driven payload builder, so prompt pipeline, entitlements, reservations,
 * seeds and telemetry are all inherited rather than reimplemented. The editor
 * adds no parallel execution path.
 */

import { ref, shallowRef } from 'vue'
import axios from 'axios'
import { useWebSocket } from '../../composables/useWebSocket'
import {
  buildBasePayload,
  buildCapturedState,
  getPreUploadTasks,
  type PayloadBuilderConfig,
  type PayloadBuilderState,
} from '../../composables/useJobPayloadBuilder'
import {
  canvasToBlob,
  extractPatch,
  maskBounds,
} from './useStackCompositor'
import { multiply } from './geometryTransform'
import type { Affine } from './geometryTransform'
import { convertMaskPixels } from '../../utils/maskFormat'
import type { MaskFormat } from '../../composables/useToolSchemaFeatures'
import type { Candidate, ModelReferenceImage } from './types'

const API_BASE = '/api'

/** Feather needs pixels to blend into, so the patch keeps a margin. */
const PATCH_MARGIN_PX = 24

/**
 * The editor brushes masks white-on-black, but what a tool expects is declared
 * per-tool by `x-mask-format`. Sending the wrong one is silent: a tool that
 * reads alpha sees a fully opaque image, finds nothing to inpaint, and returns
 * its input unchanged.
 */
const EDITOR_MASK_FORMAT: MaskFormat = 'white-black'

function maskFormatFor(tool: PayloadBuilderConfig['tool']): MaskFormat {
  const format = (tool.parameter_schema?.properties as any)?.mask?.['x-mask-format']
  return format === 'white-black' || format === 'black-white' ? format : 'alpha'
}

/** Re-encode the brushed mask into the format this tool declares. */
function maskDataUrlFor(canvas: HTMLCanvasElement, target: MaskFormat): string {
  if (target === EDITOR_MASK_FORMAT) return canvas.toDataURL('image/png')
  const context = canvas.getContext('2d', { willReadFrequently: true })!
  const source = context.getImageData(0, 0, canvas.width, canvas.height)
  const converted = convertMaskPixels(source.data, EDITOR_MASK_FORMAT, target)

  const out = document.createElement('canvas')
  out.width = canvas.width
  out.height = canvas.height
  const outContext = out.getContext('2d')!
  outContext.putImageData(new ImageData(converted, canvas.width, canvas.height), 0, 0)
  return out.toDataURL('image/png')
}

export interface PendingSubmission {
  opId: string
  batchId: string
  jobId: number
  status: 'queued' | 'processing' | 'failed'
  error?: string
}

export interface SubmitRequest {
  opId: string
  tool: PayloadBuilderConfig['tool']
  /** The editor verb's canonical task when a tool advertises several. */
  taskType?: string
  /** The op's input composite, already rendered. */
  inputCanvas: HTMLCanvasElement
  /** White-on-black mask. Required: every candidate is a patch. */
  maskCanvas: HTMLCanvasElement
  prompt: string
  count: number
  params?: Record<string, any>
  /** Ordered images appended after the edited target in input_images. */
  referenceImages?: ModelReferenceImage[]
  /** Content hash of the input composite, stamped onto every candidate. */
  sampledInputHash: string
  /** Complete affine from the submitted input frame into document space. */
  payloadToDocument?: number[]
  /**
   * Defaults true: a patch only composites on the pixel grid it was sampled
   * from. Expand submits false — the outpaint tool computes its own (larger)
   * output size from the percent params, and the mask's dimensions carry the
   * expected size for the ingest check instead.
   */
  lockResolution?: boolean
}

/** A single run whose whole output is the result — the output stage's upscale. */
export interface OneShotRequest {
  tool: PayloadBuilderConfig['tool']
  inputCanvas: HTMLCanvasElement
  /** The tool's parameters, by schema property name. */
  params?: Record<string, any>
  /**
   * Short edge to ask for, computed the way ToolView computes it. The payload
   * builder treats `scale_factor` as UI state and always sends `resolution`,
   * so an upscale run that omitted this would fall back to a default the user
   * never chose.
   */
  finalResolution?: number
}

export function useStackCandidates(deps: {
  documentId: () => number | null
  uploadPayload: (name: string, blob: Blob, subdir?: string) => Promise<string>
  attachCandidates: (opId: string, candidates: Candidate[]) => void
  /** Media URL resolver — <img> cannot send the profile header. */
  mediaFileUrl: (mediaId: number) => string
  /** Called for the first candidate of a staged op so a pick can auto-apply. */
  onFirstCandidate?: (opId: string, candidate: Candidate) => void
}) {
  const { on: onWebSocketEvent } = useWebSocket()
  const pending = shallowRef<PendingSubmission[]>([])
  const lastError = ref<string | null>(null)
  let placeholderSequence = -1
  let candidateBatchSequence = 0

  /** Jobs this editor instance owns, and what to do with their outputs. */
  const jobIntents = new Map<number, {
    opId: string
    batchId: string
    maskCanvas: HTMLCanvasElement
    sampledInputHash: string
    payloadToDocument?: number[]
  }>()

  /** One-shot runs (the output stage), keyed by job id. */
  const oneShotIntents = new Map<number, {
    resolve: (image: HTMLImageElement) => void
    reject: (error: Error) => void
  }>()
  /** A WebSocket event and a status poll may discover the same result. */
  const ingestingJobIds = new Set<number>()

  let unsubscribe: Array<() => void> = []
  let reconciliationTimer: ReturnType<typeof setInterval> | null = null

  function generatorInstanceId(): string {
    return `image-stack-${deps.documentId() ?? 'none'}`
  }

  function newCandidateBatchId(): string {
    candidateBatchSequence += 1
    return `candidate-batch-${Date.now().toString(36)}-${candidateBatchSequence.toString(36)}`
  }

  // -- submission ----------------------------------------------------------

  async function uploadCanvasAsInput(canvas: HTMLCanvasElement): Promise<string> {
    const blob = await canvasToBlob(canvas)
    const form = new FormData()
    form.append('file', blob, 'composite.png')
    // The editor's flattened input is internal job context, not a library
    // Asset. Candidate outputs are owned by the working document separately.
    form.append('materialize_asset', 'false')
    const { data } = await axios.post(`${API_BASE}/generate/upload-reference`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data.path
  }

  /**
   * Copy a canvas. The caller owns the live brush surface and clears it as soon
   * as the step is created, so anything that has to outlive the gesture — the
   * mask a candidate will be cropped against, minutes later — must be a
   * snapshot, not a reference to it.
   */
  function snapshot(canvas: HTMLCanvasElement): HTMLCanvasElement {
    const copy = document.createElement('canvas')
    copy.width = canvas.width
    copy.height = canvas.height
    copy.getContext('2d')!.drawImage(canvas, 0, 0)
    return copy
  }

  /**
   * The wire body for one run, built through ToolView's own payload builder.
   * Shared by the candidate path and the output stage's one-shot so there is
   * exactly one place that knows how an invocation is shaped.
   */
  async function buildBody(options: {
    tool: PayloadBuilderConfig['tool']
    taskType?: string
    inputCanvas: HTMLCanvasElement
    prompt: string
    params?: Record<string, any>
    referenceImages?: ModelReferenceImage[]
    maskCanvas?: HTMLCanvasElement | null
    lockResolution: boolean
    finalResolution?: number
  }) {
    const documentId = deps.documentId()
    if (!documentId) throw new Error('No stack document')

    // The input composite is what the model sees. It is synthetic, so it has no
    // library media id of its own — lineage back to the base asset travels
    // through the save path instead.
    const inputPath = await uploadCanvasAsInput(options.inputCanvas)

    const maskDataUrl = options.maskCanvas
      ? maskDataUrlFor(options.maskCanvas, maskFormatFor(options.tool))
      : null

    const config: PayloadBuilderConfig = {
      tool: options.tool,
      generatorInstanceId: generatorInstanceId(),
      // Candidates live as long as their step, so they never auto-delete.
      // (The builder's type says number; the wire field is the duration
      // string the queue parses.)
      autoDeleteDuration: 'never' as unknown as number,
    }
    const state: PayloadBuilderState = {
      globalPrefs: {
        prompt: options.prompt,
        negative_prompt: '',
        folder_path: '',
        inputImages: [{ path: inputPath }],
        inpaintRefImages: (options.referenceImages ?? []).map(reference => ({
          // Digit-only media ids are resolved to managed paths by the backend.
          path: String(reference.media_id),
          mediaId: reference.media_id,
        })),
        inputVideos: [],
        inputAudios: [],
      },
      modelParams: {
        // A patch only composites when the output lands on the same pixel grid
        // it was sampled from, so its resolution is locked to the input. An
        // upscaler told to return the input's dimensions would return the
        // input, so the output stage does not lock.
        ...(options.lockResolution
          ? { width: options.inputCanvas.width, height: options.inputCanvas.height }
          : {}),
        ...(options.params || {}),
      },
      videoImages: { startImage: null, endImage: null },
      maskDataUrl,
      enabledLoras: [],
      inputImageWidth: options.inputCanvas.width,
      inputImageHeight: options.inputCanvas.height,
      finalResolution: options.finalResolution,
    }

    const uploads: Record<string, any> = {}
    for (const task of getPreUploadTasks(config, state)) {
      Object.assign(uploads, await task())
    }
    const captured = buildCapturedState(config, state, uploads)
    const base = buildBasePayload(config, state)

    return {
      ...base,
      // ToolView can infer image-to-image from its inputs. Masked editor verbs
      // cannot: one provider may advertise image-to-image, inpaint-image and
      // erase-image together, while the selected toolbar verb is unambiguous.
      ...(options.taskType ? { task_type: options.taskType } : {}),
      parameters: {
        ...captured.parameters,
        // Editor-hosted schema values are already keyed by exact STP property
        // name. Overlay them last so even fields with ToolView-specific
        // extractors (negative_prompt, loras, future dedicated controls) pass
        // through instead of being replaced by an empty host UI state.
        ...(options.params || {}),
      },
      prompt_options: captured.promptOptions,
      output_disposition: 'context',
      output_context_kind: 'working_document',
      output_context_id: String(documentId),
    }
  }

  async function submit(request: SubmitRequest): Promise<number[]> {
    lastError.value = null
    const maskSnapshot = snapshot(request.maskCanvas)
    const count = Math.max(1, Math.min(8, Math.floor(request.count) || 1))
    const batchId = newCandidateBatchId()
    // The strip describes the requested work, not the speed of several HTTP
    // round trips. Reserve every slot before the first job is submitted.
    const placeholderIds = Array.from({ length: count }, () => placeholderSequence--)
    pending.value = [
      ...pending.value,
      ...placeholderIds.map(jobId => ({
        opId: request.opId,
        batchId,
        jobId,
        status: 'queued' as const,
      })),
    ]

    const jobIds: number[] = []
    try {
      const body = await buildBody({
        tool: request.tool,
        taskType: request.taskType,
        inputCanvas: request.inputCanvas,
        prompt: request.prompt,
        params: request.params,
        referenceImages: request.referenceImages,
        maskCanvas: request.maskCanvas,
        lockResolution: request.lockResolution ?? true,
      })

      for (let i = 0; i < count; i++) {
        const { data } = await axios.post(`${API_BASE}/generate/submit`, {
          ...body,
          parameters: {
            ...body.parameters,
            // Distinct seeds, or every candidate is the same image.
            ...(request.params?.seed === undefined
              ? { seed: Math.floor(Math.random() * 2 ** 31) }
              : {}),
          },
        })
        const jobId = Number(data.job_id)
        jobIds.push(jobId)
        jobIntents.set(jobId, {
          opId: request.opId,
          batchId,
          maskCanvas: maskSnapshot,
          sampledInputHash: request.sampledInputHash,
          payloadToDocument: request.payloadToDocument
            ? [...request.payloadToDocument]
            : undefined,
        })
        pending.value = pending.value.map(item =>
          item.jobId === placeholderIds[i] ? { ...item, jobId } : item
        )
      }
      // Completion events are an optimization, not the source of truth. A
      // reconnect or a very fast provider can make an event unobservable.
      void reconcilePendingJobs()
      return jobIds
    } catch (error) {
      const unused = new Set(placeholderIds.slice(jobIds.length))
      pending.value = pending.value.filter(item => !unused.has(item.jobId))
      throw error
    }
  }

  /**
   * Run one tool over one canvas and resolve with its output pixels.
   *
   * The output stage's path: no op, no candidate, no pick — the result is not a
   * step in the document, it is the image being saved. Rejects rather than
   * degrading, because a save that silently skipped the upscale would write the
   * wrong file to the version chain.
   */
  function runToolOnce(request: OneShotRequest): Promise<HTMLImageElement> {
    return new Promise<HTMLImageElement>((resolve, reject) => {
      buildBody({
        tool: request.tool,
        inputCanvas: request.inputCanvas,
        prompt: '',
        params: request.params,
        maskCanvas: null,
        // An upscaler told to return the input's dimensions would return the
        // input; its size comes from its own resolution parameter.
        lockResolution: false,
        finalResolution: request.finalResolution,
      })
        .then(body => axios.post(`${API_BASE}/generate/submit`, body))
        .then(({ data }) => {
          oneShotIntents.set(Number(data.job_id), { resolve, reject })
        })
        .catch(reject)
    })
  }

  // -- completion ----------------------------------------------------------

  function loadImage(url: string): Promise<HTMLImageElement> {
    return new Promise((resolve, reject) => {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.onload = () => resolve(img)
      img.onerror = () => reject(new Error(`failed to load ${url}`))
      img.src = url
    })
  }

  async function ingestOutput(jobId: number, mediaId: number) {
    const intent = jobIntents.get(jobId)
    if (!intent || ingestingJobIds.has(jobId)) return
    ingestingJobIds.add(jobId)

    try {
      // Trust the media record, not the job: the job says an output exists, the
      // media record says what it actually is.
      const { data: media } = await axios.get(`${API_BASE}/media/${mediaId}`)
      const output = await loadImage(deps.mediaFileUrl(mediaId))

      const candidateId = `cand-${jobId}`
      const width = intent.maskCanvas.width
      const height = intent.maskCanvas.height
      if (output.naturalWidth !== width || output.naturalHeight !== height) {
        // A tool that does not return the input's dimensions cannot be
        // patch-composited: the crop would land somewhere other than where it
        // was sampled from. Say so rather than silently resampling.
        failJob(
          jobId,
          `This tool returned ${output.naturalWidth}×${output.naturalHeight} for a ` +
          `${width}×${height} input. Its results cannot be applied as a patch.`,
        )
        return
      }

      const bounds = maskBounds(intent.maskCanvas, width, height, PATCH_MARGIN_PX)
      if (!bounds) {
        failJob(jobId, 'The mask is empty.')
        return
      }
      const patchCanvas = extractPatch(output, bounds)
      const ref = await deps.uploadPayload(
        `${candidateId}-patch.png`,
        await canvasToBlob(patchCanvas)
      )
      const candidate: Candidate = {
        id: candidateId,
        batch_id: intent.batchId,
        patch_ref: ref,
        // The compact origin is part of the canonical transform. Keeping the
        // compatibility field as well lets older readers place the patch.
        payload_to_document: intent.payloadToDocument
          ? multiply(
              intent.payloadToDocument as Affine,
              [1, 0, 0, 1, bounds.x, bounds.y],
            )
          : undefined,
        patch_origin: [bounds.x, bounds.y],
        media_id: mediaId,
        file_hash: media.file_hash,
        job_id: String(jobId),
        sampled_input_hash: intent.sampledInputHash,
      }

      deps.attachCandidates(intent.opId, [candidate])
      deps.onFirstCandidate?.(intent.opId, candidate)
      pending.value = pending.value.filter(p => p.jobId !== jobId)
      jobIntents.delete(jobId)
    } finally {
      ingestingJobIds.delete(jobId)
    }
  }

  function failJob(jobId: number, message: string) {
    lastError.value = message
    pending.value = pending.value.filter(item => item.jobId !== jobId)
    jobIntents.delete(jobId)
  }

  async function reconcilePendingJobs() {
    const jobIds = [...jobIntents.keys()].filter(id => !ingestingJobIds.has(id))
    if (!jobIds.length) return
    try {
      const { data } = await axios.get(`${API_BASE}/generate/jobs/status`, {
        params: { ids: jobIds.join(',') },
      })
      for (const job of Array.isArray(data) ? data : []) {
        const jobId = Number(job.id)
        if (!jobIntents.has(jobId)) continue
        if (job.status === 'completed') {
          if (job.result_media_id) {
            void ingestOutput(jobId, Number(job.result_media_id)).catch((error: any) => {
              failJob(jobId, error?.message || 'Failed to read the result.')
            })
          } else {
            failJob(jobId, 'The run completed without an image.')
          }
        } else if (['failed', 'cancelled'].includes(job.status)) {
          failJob(jobId, job.error || 'Generation failed.')
        } else if (job.status === 'processing') {
          pending.value = pending.value.map(item =>
            item.jobId === jobId ? { ...item, status: 'processing' as const } : item
          )
        }
      }
    } catch {
      // The WebSocket can still deliver while this best-effort safety net is
      // temporarily unavailable. Keep the placeholders and try again.
    }
  }

  function start() {
    pause()
    unsubscribe = [
      onWebSocketEvent('generation_job_started', (data: any) => {
        const jobId = Number(data.job?.id)
        if (!jobIntents.has(jobId)) return
        pending.value = pending.value.map(p =>
          p.jobId === jobId ? { ...p, status: 'processing' as const } : p
        )
      }),
      onWebSocketEvent('generation_job_completed', async (data: any) => {
        const jobId = Number(data.job?.id)
        const oneShot = oneShotIntents.get(jobId)
        if (oneShot) {
          oneShotIntents.delete(jobId)
          if (!data.job.result_media_id) {
            oneShot.reject(new Error('The run produced no output.'))
            return
          }
          try {
            oneShot.resolve(await loadImage(deps.mediaFileUrl(data.job.result_media_id)))
          } catch (err: any) {
            oneShot.reject(new Error(err?.message || 'Failed to read the result.'))
          }
          return
        }
        if (!jobIntents.has(jobId)) return
        if (!data.job.result_media_id) {
          failJob(jobId, 'The run completed without an image.')
          return
        }
        try {
          await ingestOutput(jobId, Number(data.job.result_media_id))
        } catch (err: any) {
          failJob(jobId, err?.message || 'Failed to read the result.')
        }
      }),
      onWebSocketEvent('generation_job_failed', (data: any) => {
        const jobId = Number(data.job?.id)
        const oneShot = oneShotIntents.get(jobId)
        if (oneShot) {
          oneShotIntents.delete(jobId)
          oneShot.reject(new Error(data.job?.error || 'The run failed.'))
          return
        }
        if (!jobIntents.has(jobId)) return
        failJob(jobId, data.job.error || 'Generation failed.')
      }),
    ]
    reconciliationTimer = setInterval(() => {
      void reconcilePendingJobs()
    }, 1500)
  }

  /** Suspend background reconciliation while a KeepAlive editor is hidden. */
  function pause() {
    unsubscribe.forEach(fn => fn())
    unsubscribe = []
    if (reconciliationTimer) clearInterval(reconciliationTimer)
    reconciliationTimer = null
  }

  function stop() {
    pause()
    // Nothing will ever resolve these once the socket handlers are gone, and a
    // save awaiting one would hang with a spinner instead of reporting.
    for (const intent of oneShotIntents.values()) {
      intent.reject(new Error('The editor closed before the run finished.'))
    }
    oneShotIntents.clear()
  }

  function clearPending(opId?: string) {
    pending.value = opId ? pending.value.filter(p => p.opId !== opId) : []
  }

  return { pending, lastError, submit, runToolOnce, start, pause, stop, clearPending }
}
