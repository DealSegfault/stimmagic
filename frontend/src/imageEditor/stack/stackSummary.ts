/**
 * Reading a saved stack summary back as a short account of what was done.
 *
 * A save records the steps that were actually enabled (`executedStackSummary`),
 * and that record is the only description of an editor-made image anywhere
 * outside the editor. Lineage shows it, so this turns it into one line per
 * step: what the step was, and at most one fact a reader cannot guess from
 * the name — the verb behind a named patch, how many repairs a Retouch row
 * holds, the factor an upscale ran at.
 *
 * It is a summary, not the document: candidates, masks, payload transforms and
 * every slider value stay in the working document, which is one click away in
 * the editor. Anything that needs the full state should open it there.
 */

import { photoAdjustmentGroup } from './adjustSections.ts'
import { outputLabel } from './outputStage.ts'

/** One step as recorded in `generation_metadata.parameters.stack`. */
export interface RecordedStep {
  class?: string
  label?: string
  exec?: { kind?: string; tool_id?: string; task_type?: string } | null
  /** The editor verb. Absent on saves made before it was recorded. */
  operation?: string
  params?: Record<string, any> | null
  reference_images?: unknown[] | null
  job_id?: string | null
}

export interface StackSummaryStep {
  key: string
  /** What the step was called in the Edits list. */
  name: string
  /** The one supporting fact, or '' when the name already says everything. */
  detail: string
  /** A second line under the name: the prompt, or what a container holds. */
  note: string
}

export interface StackSummary {
  /** Newest first, the order the Edits list uses. */
  steps: StackSummaryStep[]
  total: number
}

/** Resolves a tool id to its display name; see `utils/toolDisplay`. */
export type ToolNameResolver = (toolId: string | null | undefined) => string

const OPERATION_LABELS: Record<string, string> = {
  remove: 'Remove',
  repaint: 'Repaint',
  expand: 'Expand',
  erase: 'Erase',
  cutout: 'Remove background',
}

/** Fallback verb for saves written before the editor verb was recorded. */
const TASK_TYPE_VERBS: Record<string, string> = {
  'inpaint-image': 'Repaint',
  'erase-image': 'Erase',
  'outpaint-image': 'Expand',
  'remove-background': 'Remove background',
  'image-to-image': 'Repaint',
  'upscale-image': 'Upscale',
}

const EXEC_KIND_NAMES: Record<string, string> = {
  crop: 'Crop',
  adjust: 'Adjust',
  paint: 'Paint',
  retouch: 'Paint',
  sketch: 'Paint',
  annotate: 'Annotate',
  'retouch-regions': 'Retouch',
  'backend-filter': 'Filter',
}

function joinDetail(parts: Array<string | null | undefined>): string {
  return parts.map(part => (part || '').trim()).filter(Boolean).join(' · ')
}

/** A single region wearing a row (a scoped adjustment) holds nothing to count. */
function isLoneAdjustmentRegion(regions: any[]): boolean {
  if (regions.length !== 1) return false
  const kind = String(regions[0]?.kind || '')
  return kind === 'adjust' || kind === 'look' || !!photoAdjustmentGroup(kind)
}

/**
 * The container's contents as a count, not a list of its children.
 *
 * Retouch is the stack's one hierarchy level, and it stays collapsed here: how
 * many repairs it holds is the fact worth carrying out of the editor, and the
 * repairs themselves are only meaningful next to the picture they sit on.
 */
function regionsNote(regions: any[]): string {
  if (!regions.length || isLoneAdjustmentRegion(regions)) return ''
  return `${regions.length} ${regions.length === 1 ? 'region' : 'regions'}`
}

function cropDetail(params: Record<string, any>): string {
  const parts: string[] = []
  const quarters = Number(params.rotation90 || 0) % 4
  const fine = Number(params.cropRotation || params.rotation || 0)
  if (quarters) parts.push(`${((quarters + 4) % 4) * 90}°`)
  if (Math.abs(fine) >= 0.05) parts.push(`${fine.toFixed(1)}°`)
  if (params.flipX || params.flipY) parts.push('Flipped')
  return parts.join(' · ')
}

function outputStep(step: RecordedStep, toolName: ToolNameResolver): StackSummaryStep {
  const params = step.params || {}
  const method = params.method === 'resample' ? 'resample' : 'photo'
  const factor = outputLabel({
    enabled: true,
    method,
    tool_id: step.exec?.tool_id ?? null,
    params,
  })
  const tool = method === 'photo' ? step.exec?.tool_id : null
  return {
    key: 'output',
    name: method === 'photo' ? 'Upscale' : 'Resample',
    // The upscaler is named because it is the whole substance of the step;
    // a patch step's model is not, since its name already says what it did.
    detail: joinDetail([factor, tool ? toolName(tool) : '']),
    note: '',
  }
}

function summarizeStep(
  step: RecordedStep,
  index: number,
  toolName: ToolNameResolver,
): StackSummaryStep {
  if (step.class === 'output') return outputStep(step, toolName)

  const exec = step.exec || {}
  const params = step.params || {}
  const kind = String(exec.kind || '')
  const name = step.label || EXEC_KIND_NAMES[kind] || 'Edit'
  const base = { key: `step-${index}`, name, note: '' }

  if (kind === 'tool') {
    const verb = OPERATION_LABELS[String(step.operation || '')]
      || TASK_TYPE_VERBS[String(exec.task_type || '')]
      || ''
    const references = step.reference_images?.length || 0
    return {
      ...base,
      detail: joinDetail([
        verb === name ? '' : verb,
        references ? `${references} ${references === 1 ? 'reference' : 'references'}` : '',
      ]),
      note: typeof params.prompt === 'string' ? params.prompt.trim() : '',
    }
  }

  if (kind === 'retouch-regions') {
    const regions = Array.isArray(params.regions) ? params.regions : []
    return { ...base, detail: '', note: regionsNote(regions) }
  }
  if (kind === 'crop') return { ...base, detail: cropDetail(params) }
  if (kind === 'annotate') {
    const shapes = Array.isArray(params.shapes) ? params.shapes.length : 0
    return { ...base, detail: shapes ? `${shapes} ${shapes === 1 ? 'shape' : 'shapes'}` : '' }
  }
  if (kind === 'backend-filter') return { ...base, detail: toolName(exec.tool_id) }

  return { ...base, detail: '' }
}

/**
 * The recorded stack as display rows, newest first — the order the Edits list
 * puts them in, so the account reads the same way in both places.
 */
export function summarizeStack(
  recorded: unknown,
  toolName: ToolNameResolver = id => String(id || ''),
): StackSummary {
  const steps = Array.isArray(recorded) ? (recorded as RecordedStep[]) : []
  const summarized = steps
    .map((step, index) => summarizeStep(step || {}, index, toolName))
    .reverse()
  return { steps: summarized, total: summarized.length }
}
