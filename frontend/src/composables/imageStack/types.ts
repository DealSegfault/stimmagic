/**
 * The op-stack image editor's document model.
 *
 * The stack is a RECIPE, not a log. Chronology appears nowhere: undo (session)
 * and the version chain (materialized saves) are the only histories. Ops are
 * addressed by stable id, never by index — the UI, undo, and any future agent
 * tooling all need a name for a step that survives reordering.
 *
 * Ops only ever reference the composite below them (dumb references). That is
 * what makes "drag a row" mean exactly one thing everywhere: change what this
 * step applies on top of.
 */

export type OpClass = 'parametric' | 'patch' | 'whole' | 'container'

export interface OpRegion {
  /** Payload ref, relative to the document directory. */
  mask_ref: string
  feather_px: number
  invert: boolean
}

export interface OpBlend {
  feather_px: number
  opacity: number
}

export interface Candidate {
  id: string
  /** Bbox-cropped patch PNG (patch ops only); whole-image ops use media_id. */
  patch_ref?: string
  /** Top-left of the patch in its input space. */
  patch_origin?: [number, number]
  /** Raw model output — context-owned Media, never a library Asset. */
  media_id: number
  file_hash: string
  job_id?: string
  /**
   * Content hash of the input composite this candidate was sampled against.
   * Compared at render time against the op's current input to derive staleness;
   * nothing about staleness is stored.
   */
  sampled_input_hash: string
  /** Whole-image ops record output dimensions; they may differ from the input. */
  dims?: [number, number]
}

export interface BaseOp {
  id: string
  class: OpClass
  enabled: boolean
  label: string
  region?: OpRegion | null
}

export interface ParametricOp extends BaseOp {
  class: 'parametric'
  exec: { kind: 'crop' } | { kind: 'develop' } | { kind: 'backend-filter'; tool_id: string }
  params: Record<string, any>
}

export interface GenerativeOp extends BaseOp {
  class: 'patch' | 'whole'
  exec: { kind: 'tool'; tool_id: string; task_type: string }
  /** STP parameters as submitted, minus the inputs. */
  params: Record<string, any>
  /** Patch ops carry the mask they were sampled through. */
  mask_ref?: string
  blend?: OpBlend
  /** null while candidates are staged and none has been picked yet. */
  picked: string | null
  candidates: Candidate[]
}

export interface ContainerOp extends BaseOp {
  class: 'container'
  exec: { kind: 'sketch' | 'retouch' | 'paint' | 'annotate' }
  state_ref?: string
  raster_ref?: string
  sampled_input_hash?: string | null
  blend?: OpBlend
  params?: Record<string, any>
}

export type Op = ParametricOp | GenerativeOp | ContainerOp

export interface DocumentBase {
  asset_id: number
  revision_id: number
  media_id: number
  /** The durable pixel reference; media ids are recyclable rowids. */
  file_hash: string
  width: number
  height: number
}

export interface StackDocument {
  format: 'stimma-image-stack'
  version: 1
  base: DocumentBase
  canvas: { width: number; height: number }
  /** Bottom to top: index 0 composites first. */
  edits: Op[]
}

/**
 * One document edit, as recorded in journal.jsonl. `inverse` carries whatever
 * undo needs to put the document back — for a removal, the whole op.
 */
export interface JournalEntry {
  seq: number
  ts?: string
  action: string
  op_id?: string
  /** Applied to move forward. */
  forward?: any
  /** Applied to move back. */
  inverse?: any
  /** Checkpoint entries carry a full document snapshot. */
  document?: StackDocument
}

export const DOCUMENT_FORMAT = 'stimma-image-stack'
export const DOCUMENT_VERSION = 1

export function isGenerative(op: Op): op is GenerativeOp {
  return op.class === 'patch' || op.class === 'whole'
}

/** The candidate currently supplying this op's pixels, if any. */
export function pickedCandidate(op: Op): Candidate | null {
  if (!isGenerative(op) || !op.picked) return null
  return op.candidates.find(c => c.id === op.picked) || null
}
