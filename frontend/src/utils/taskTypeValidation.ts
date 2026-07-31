/**
 * Task-type level submit validation.
 *
 * A task type is an interface: `outpaint-image` means "grows a canvas by these
 * four percentages", and that is knowable at the application level without
 * asking any particular tool. So rules that follow from the task rather than
 * from one tool's schema belong here, keyed by task type, next to the
 * per-field checks ToolView already runs against `parameter_schema.required`.
 *
 * The contract these mirror lives in backend/tasks/schemas.py — see
 * TASK_SCHEMA_REQUIREMENTS and OUTPAINT_EXPAND_FIELDS.
 */

/** The outpaint-image canvas-growth fields, in reading order. */
export const OUTPAINT_EXPAND_FIELDS = [
  'expand_top_pct',
  'expand_bottom_pct',
  'expand_left_pct',
  'expand_right_pct',
] as const

export interface TaskTypeValidation {
  /** Whether the parameters satisfy the task type's own rules. */
  ok: boolean
  /** Why not, phrased for a disabled-button tooltip. Present only when !ok. */
  reason?: string
}

const OK: TaskTypeValidation = { ok: true }

/**
 * Rules a task type imposes on its parameter VALUES, beyond which fields the
 * tool declares. Absent entry means the task type adds no rule of its own.
 */
const TASK_TYPE_RULES: Record<string, (params: Record<string, unknown>) => TaskTypeValidation> = {
  // An outpaint with nothing to expand is a no-op that still costs a
  // generation, so it is blocked rather than sent. Every edge defaults to 0,
  // which makes this the state the tool opens in — the message has to say what
  // to do, not just that something is wrong.
  'outpaint-image': (params) => {
    const total = OUTPAINT_EXPAND_FIELDS.reduce((sum, field) => {
      const value = Number(params[field])
      return sum + (Number.isFinite(value) ? Math.max(0, value) : 0)
    }, 0)
    return total > 0 ? OK : { ok: false, reason: 'Expand at least one edge to outpaint' }
  },
}

/**
 * Validate parameters against the rules of the effective task type.
 */
export function validateTaskType(
  taskType: string | null | undefined,
  params: Record<string, unknown>
): TaskTypeValidation {
  if (!taskType) return OK
  const rule = TASK_TYPE_RULES[taskType]
  return rule ? rule(params) : OK
}
