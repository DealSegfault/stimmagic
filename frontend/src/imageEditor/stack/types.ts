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

/**
 * There is no whole-image class, and adding one back would be a mistake.
 *
 * An op that replaces the composite occludes everything below it, and a layer
 * that fully occludes the stack beneath it is not a layer — it is a new base.
 * Those live in the version chain, where they are visible and forkable, rather
 * than as a frozen row that the rest of the list's physics contradict.
 */
export type OpClass = 'parametric' | 'patch' | 'container'

export interface OpBlend {
  feather_px: number
  opacity: number
}

export interface Candidate {
  id: string
  /** Bbox-cropped patch PNG — the only region the composite ever keeps. */
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
}

export interface BaseOp {
  id: string
  class: OpClass
  enabled: boolean
  label: string
  /**
   * The geometry below this op when its spatial payloads were created — the
   * anchor that makes those pixels addressable in the ORIGINAL image's
   * coordinates.
   *
   * Everything spatial an op owns (its mask, its raster layer, the candidates
   * generated against its mask) lives in this frame. The compositor
   * carries them into whatever the geometry is now with `M_now ∘ M_created⁻¹`.
   * Absent on documents written before this existed, which render as they
   * always did: unanchored, correct only while the geometry below them has not
   * changed.
   */
  payload_frame?: { matrix: number[]; width: number; height: number }
}

export interface ParametricOp extends BaseOp {
  class: 'parametric'
  exec: { kind: 'crop' } | { kind: 'adjust' } | { kind: 'backend-filter'; tool_id: string }
  params: Record<string, any>
}

export interface GenerativeOp extends BaseOp {
  class: 'patch'
  exec: { kind: 'tool'; tool_id: string; task_type: string }
  /** STP parameters as submitted, minus the inputs. */
  params: Record<string, any>
  /** The mask this patch was sampled through. */
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
  /**
   * A payload in the document's own directory that supplies the base pixels
   * instead of the revision's media.
   *
   * Written only by the flatten migration, which bakes a document that still
   * had whole-image steps down to the pixels those steps produced. The
   * asset/revision ids stay as they were: the save path still commits against
   * the same revision, and the flattened pixels are what the stack now sits on.
   */
  payload_ref?: string
}

/**
 * The terminal stage, and deliberately NOT a row.
 *
 * Upscale is the one operation allowed to change the base, and it does that at
 * the save boundary — the only place a base change is legitimate. Keeping it
 * out of `edits` is what stops it becoming a fence: nothing in the stack reads
 * a composite it then replaces.
 *
 * `params` holds the TOOL's own parameters, by schema property name, exactly as
 * ToolView holds them. The editor knows nothing about any particular upscaler:
 * the `upscale-image` task defines the interface (`x-control: upscale_resolution`
 * → `scale_factor` or `resolution`, plus whatever else a tool declares), the
 * catalog defines the tool list, and the shared payload builder turns this into
 * an invocation. A hardcoded factor name here would work for one provider and
 * silently do nothing for the next.
 */
export interface OutputStage {
  /** Off by default: a save writes the working size unless asked otherwise. */
  enabled: boolean
  /** `photo` runs a catalog upscale-image tool; `resample` is client-side Lanczos. */
  method: 'photo' | 'resample'
  /** Recorded when method is `photo`; same picker semantics as any generative op. */
  tool_id: string | null
  /**
   * Tool parameters by schema property name, plus the upscale picker's own
   * state (`resolutionMode` / `scaleFactor` / `targetResolution`) under the
   * same names ToolView uses, so the payload builder resolves them identically.
   */
  params: Record<string, any>
}

export const DEFAULT_OUTPUT: OutputStage = {
  enabled: false,
  method: 'photo',
  tool_id: null,
  params: {},
}

export interface StackDocument {
  format: 'stimma-image-stack'
  version: 1
  base: DocumentBase
  canvas: { width: number; height: number }
  /** Bottom to top: index 0 composites first. */
  edits: Op[]
  /** Absent on documents written before the output stage existed: 1×. */
  output?: OutputStage
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
  return op.class === 'patch'
}

/** The candidate currently supplying this op's pixels, if any. */
export function pickedCandidate(op: Op): Candidate | null {
  if (!isGenerative(op) || !op.picked) return null
  return op.candidates.find(c => c.id === op.picked) || null
}
