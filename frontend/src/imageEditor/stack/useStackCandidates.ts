/**
 * Staged candidates: submitting generative steps and turning their outputs
 * into patches the compositor can use.
 *
 * Candidates are job outputs, not versions and not library tiles. They run with
 * `output_disposition: 'context'` rooted at the editor's working document, so
 * they are durable and reachable without ever becoming Assets. Picking one
 * commits nothing to the version chain — it only updates document.json.
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
import { convertMaskPixels } from '../../utils/maskFormat'
import type { MaskFormat } from '../../composables/useToolSchemaFeatures'
import type { Candidate } from './types'

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
  jobId: number
  status: 'queued' | 'processing' | 'failed'
  error?: string
}

export interface SubmitRequest {
  opId: string
  tool: PayloadBuilderConfig['tool']
  /** The op's input composite, already rendered. */
  inputCanvas: HTMLCanvasElement
  /** White-on-black mask; absent for whole-image ops. */
  maskCanvas?: HTMLCanvasElement | null
  prompt: string
  count: number
  params?: Record<string, any>
  /** Content hash of the input composite, stamped onto every candidate. */
  sampledInputHash: string
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

  /** Jobs this editor instance owns, and what to do with their outputs. */
  const jobIntents = new Map<number, {
    opId: string
    isPatch: boolean
    maskCanvas: HTMLCanvasElement | null
    sampledInputHash: string
  }>()

  let unsubscribe: Array<() => void> = []

  function generatorInstanceId(): string {
    return `image-stack-${deps.documentId() ?? 'none'}`
  }

  // -- submission ----------------------------------------------------------

  async function uploadCanvasAsInput(canvas: HTMLCanvasElement): Promise<string> {
    const blob = await canvasToBlob(canvas)
    const form = new FormData()
    form.append('file', blob, 'composite.png')
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

  async function submit(request: SubmitRequest): Promise<number[]> {
    lastError.value = null
    const documentId = deps.documentId()
    if (!documentId) throw new Error('No stack document')

    const maskSnapshot = request.maskCanvas ? snapshot(request.maskCanvas) : null

    // The op's input composite is what the model sees. It is synthetic, so it
    // has no library media id of its own — lineage back to the base asset
    // travels through the save path instead.
    const inputPath = await uploadCanvasAsInput(request.inputCanvas)

    const maskDataUrl = request.maskCanvas
      ? maskDataUrlFor(request.maskCanvas, maskFormatFor(request.tool))
      : null

    const config: PayloadBuilderConfig = {
      tool: request.tool,
      generatorInstanceId: generatorInstanceId(),
      // Candidates live as long as their step, so they never auto-delete.
      // (The builder's type says number; the wire field is the duration
      // string the queue parses.)
      autoDeleteDuration: 'never' as unknown as number,
    }
    const state: PayloadBuilderState = {
      globalPrefs: {
        prompt: request.prompt,
        negative_prompt: '',
        folder_path: '',
        inputImages: [{ path: inputPath }],
        inputVideos: [],
        inputAudios: [],
      },
      // Resolution is locked to the input: a patch only composites when the
      // output lands on the same pixel grid it was sampled from.
      modelParams: {
        width: request.inputCanvas.width,
        height: request.inputCanvas.height,
        ...(request.params || {}),
      },
      videoImages: { startImage: null, endImage: null },
      maskDataUrl,
      enabledLoras: [],
      inputImageWidth: request.inputCanvas.width,
      inputImageHeight: request.inputCanvas.height,
    }

    const uploads: Record<string, any> = {}
    for (const task of getPreUploadTasks(config, state)) {
      Object.assign(uploads, await task())
    }
    const captured = buildCapturedState(config, state, uploads)
    const base = buildBasePayload(config, state)

    const jobIds: number[] = []
    for (let i = 0; i < request.count; i++) {
      const body = {
        ...base,
        parameters: {
          ...captured.parameters,
          // Distinct seeds, or every candidate is the same image.
          ...(request.params?.seed === undefined
            ? { seed: Math.floor(Math.random() * 2 ** 31) }
            : {}),
        },
        prompt_options: captured.promptOptions,
        output_disposition: 'context',
        output_context_kind: 'working_document',
        output_context_id: String(documentId),
      }
      const { data } = await axios.post(`${API_BASE}/generate/submit`, body)
      const jobId = Number(data.job_id)
      jobIds.push(jobId)
      jobIntents.set(jobId, {
        opId: request.opId,
        isPatch: !!maskSnapshot,
        maskCanvas: maskSnapshot,
        sampledInputHash: request.sampledInputHash,
      })
      pending.value = [...pending.value, { opId: request.opId, jobId, status: 'queued' }]
    }
    return jobIds
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
    if (!intent) return

    // Trust the media record, not the job: the job says an output exists, the
    // media record says what it actually is.
    const { data: media } = await axios.get(`${API_BASE}/media/${mediaId}`)
    const output = await loadImage(deps.mediaFileUrl(mediaId))

    const candidateId = `cand-${jobId}`
    let candidate: Candidate

    if (intent.isPatch && intent.maskCanvas) {
      const width = intent.maskCanvas.width
      const height = intent.maskCanvas.height
      if (output.naturalWidth !== width || output.naturalHeight !== height) {
        // A tool that does not return the input's dimensions cannot be
        // patch-composited: the crop would land somewhere other than where it
        // was sampled from. Say so rather than silently resampling.
        lastError.value =
          `This tool returned ${output.naturalWidth}×${output.naturalHeight} for a ` +
          `${width}×${height} input. Its results cannot be applied as a patch.`
        pending.value = pending.value.map(p =>
          p.jobId === jobId ? { ...p, status: 'failed' as const, error: lastError.value! } : p
        )
        return
      }

      const bounds = maskBounds(intent.maskCanvas, width, height, PATCH_MARGIN_PX)
      if (!bounds) {
        lastError.value = 'The mask is empty.'
        return
      }
      const patchCanvas = extractPatch(output, bounds)
      const ref = await deps.uploadPayload(
        `${candidateId}-patch.png`,
        await canvasToBlob(patchCanvas)
      )
      candidate = {
        id: candidateId,
        patch_ref: ref,
        patch_origin: [bounds.x, bounds.y],
        media_id: mediaId,
        file_hash: media.file_hash,
        job_id: String(jobId),
        sampled_input_hash: intent.sampledInputHash,
      }
    } else {
      // Whole-image results replace the composite outright, so the payload is
      // the frame as returned.
      const canvas = document.createElement('canvas')
      canvas.width = output.naturalWidth
      canvas.height = output.naturalHeight
      canvas.getContext('2d')!.drawImage(output, 0, 0)
      const ref = await deps.uploadPayload(
        `${candidateId}-whole.png`,
        await canvasToBlob(canvas)
      )
      candidate = {
        id: candidateId,
        patch_ref: ref,
        media_id: mediaId,
        file_hash: media.file_hash,
        job_id: String(jobId),
        sampled_input_hash: intent.sampledInputHash,
        dims: [output.naturalWidth, output.naturalHeight],
      }
    }

    deps.attachCandidates(intent.opId, [candidate])
    deps.onFirstCandidate?.(intent.opId, candidate)
    pending.value = pending.value.filter(p => p.jobId !== jobId)
    jobIntents.delete(jobId)
  }

  function start() {
    stop()
    unsubscribe = [
      onWebSocketEvent('generation_job_started', (data: any) => {
        if (!jobIntents.has(data.job?.id)) return
        pending.value = pending.value.map(p =>
          p.jobId === data.job.id ? { ...p, status: 'processing' as const } : p
        )
      }),
      onWebSocketEvent('generation_job_completed', async (data: any) => {
        const jobId = data.job?.id
        if (!jobIntents.has(jobId)) return
        if (!data.job.result_media_id) {
          pending.value = pending.value.filter(p => p.jobId !== jobId)
          jobIntents.delete(jobId)
          return
        }
        try {
          await ingestOutput(jobId, data.job.result_media_id)
        } catch (err: any) {
          lastError.value = err?.message || 'Failed to read the result.'
          pending.value = pending.value.map(p =>
            p.jobId === jobId ? { ...p, status: 'failed' as const, error: lastError.value! } : p
          )
        }
      }),
      onWebSocketEvent('generation_job_failed', (data: any) => {
        const jobId = data.job?.id
        if (!jobIntents.has(jobId)) return
        pending.value = pending.value.map(p =>
          p.jobId === jobId
            ? { ...p, status: 'failed' as const, error: data.job.error || 'Generation failed.' }
            : p
        )
        jobIntents.delete(jobId)
      }),
    ]
  }

  function stop() {
    unsubscribe.forEach(fn => fn())
    unsubscribe = []
  }

  function clearPending(opId?: string) {
    pending.value = opId ? pending.value.filter(p => p.opId !== opId) : []
  }

  return { pending, lastError, submit, start, stop, clearPending }
}
