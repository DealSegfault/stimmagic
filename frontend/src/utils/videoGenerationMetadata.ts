import { getMediaType } from './mediaTypes'

type MetadataRecord = Record<string, any>

export interface VideoGenerationRow {
  label: string
  value: string | number
  mono?: boolean
  truncate?: boolean
}

export interface VideoGenerationFacts {
  workflowType: string | null
  workflowId: string | null
  quality: string | null
  resolution: string | null
  fps: string | number | null
}

function asRecord(value: unknown): MetadataRecord {
  return value && typeof value === 'object' ? value as MetadataRecord : {}
}

function firstValue(...values: unknown[]): unknown {
  return values.find(value => value !== undefined && value !== null && value !== '') ?? null
}

function normalizedText(value: unknown): string | null {
  if (value === undefined || value === null || value === '') return null
  return String(value)
}

function isVideoMetadata(meta: MetadataRecord, media?: MetadataRecord | null): boolean {
  if (media && getMediaType(media as any) === 'video') return true
  const taskType = String(meta.task_type || '').toLowerCase()
  const toolId = String(meta.tool_id || '').toLowerCase()
  const video = asRecord(meta.video)
  return taskType.includes('video')
    || toolId.includes('video')
    || Boolean(meta.workflow_type || meta.workflow_id || meta.quality || meta.resolution || Object.keys(video).length)
}

function inferWorkflowType(meta: MetadataRecord): string | null {
  const explicit = normalizedText(meta.workflow_type)
  if (explicit) return explicit.toUpperCase()

  const haystack = [meta.task_type, meta.tool_id, meta.generator]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()

  if (/(^|[^a-z])(r2v|ref2va|reference[-_ ]?to[-_ ]?video)([^a-z]|$)/.test(haystack)) return 'R2V'
  if (/(^|[^a-z])(i2v|fl2va|image[-_ ]?to[-_ ]?video)([^a-z]|$)/.test(haystack)) return 'I2V'
  if (/(^|[^a-z])(t2v|text[-_ ]?to[-_ ]?video)([^a-z]|$)/.test(haystack)) return 'T2V'
  if (/(^|[^a-z])(v2v|video[-_ ]?to[-_ ]?video)([^a-z]|$)/.test(haystack)) return 'V2V'
  if (/(extend|longer[-_ ]?video)/.test(haystack)) return 'EXTEND'
  if (/(stitch|concat|join)/.test(haystack)) return 'STITCH'
  if (/(upscale|super[-_ ]?resolution)/.test(haystack)) return 'UPSCALE'
  return null
}

function qualityFromDimensions(width: unknown, height: unknown): string | null {
  const w = Number(width)
  const h = Number(height)
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return null
  const longEdge = Math.max(w, h)
  const shortEdge = Math.min(w, h)
  if (longEdge >= 2000) return '2K'
  if (shortEdge <= 540) return '480p'
  if (shortEdge <= 900) return '720p'
  if (shortEdge <= 1440) return '1080p'
  return `${shortEdge}p`
}

function resolutionFromDimensions(width: unknown, height: unknown): string | null {
  const w = Number(width)
  const h = Number(height)
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return null
  return `${w} × ${h}`
}

export function getVideoGenerationFacts(
  metadata: unknown,
  media: Record<string, any> | null = null,
): VideoGenerationFacts | null {
  const meta = asRecord(metadata)
  if (!isVideoMetadata(meta, media)) return null

  const params = asRecord(meta.parameters)
  const video = asRecord(meta.video)
  const width = firstValue(video.width, meta.output_width, params.output_width, meta.width, params.width, media?.width)
  const height = firstValue(video.height, meta.output_height, params.output_height, meta.height, params.height, media?.height)

  const resolution = normalizedText(firstValue(
    meta.resolution,
    video.resolution,
    params.resolution,
    resolutionFromDimensions(width, height),
  ))
  const quality = normalizedText(firstValue(
    meta.quality,
    video.quality,
    params.output_quality,
    params.quality,
    qualityFromDimensions(width, height),
  ))
  const fps = firstValue(video.fps, meta.fps, params.fps)

  return {
    workflowType: inferWorkflowType(meta),
    workflowId: normalizedText(firstValue(meta.workflow_id, video.workflow_id, meta.tool_id)),
    quality,
    resolution,
    fps: fps === null ? null : (typeof fps === 'number' ? fps : String(fps)),
  }
}

export function getVideoGenerationRows(
  metadata: unknown,
  media: Record<string, any> | null = null,
): VideoGenerationRow[] {
  const facts = getVideoGenerationFacts(metadata, media)
  if (!facts) return []

  const rows: VideoGenerationRow[] = []
  if (facts.workflowType) rows.push({ label: 'Workflow', value: facts.workflowType, mono: false })
  if (facts.workflowId) rows.push({ label: 'Workflow ID', value: facts.workflowId, truncate: true })
  if (facts.quality) rows.push({ label: 'Quality', value: facts.quality })
  if (facts.resolution) rows.push({ label: 'Resolution', value: facts.resolution })
  if (facts.fps !== null) rows.push({ label: 'FPS', value: facts.fps })
  return rows
}
