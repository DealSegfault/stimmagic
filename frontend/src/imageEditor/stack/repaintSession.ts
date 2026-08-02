import type { GenerativeOp, StackDocument } from './types.ts'

export interface RepaintSession {
  opId: string
  selectionRevision: number
}

/**
 * Resolve the Regenerate step that another Run may append candidates to.
 *
 * Selection identity is deliberately a session revision rather than a mask
 * comparison. Clearing and redrawing the same pixels is still a new editing
 * decision, while a selection carried through ordinary renders is still the
 * same one. The step must remain the head: otherwise reusing it would move the
 * new request underneath later edits and sample a different visual history.
 */
export function reusableRepaintOp(
  doc: StackDocument,
  session: RepaintSession | null,
  selectionRevision: number,
  toolId: string,
  taskType: string,
): GenerativeOp | null {
  if (!session || session.selectionRevision !== selectionRevision) return null

  const head = doc.edits[doc.edits.length - 1]
  if (
    !head
    || head.id !== session.opId
    || head.class !== 'patch'
    || !head.enabled
    || head.operation !== 'repaint'
    || head.exec.kind !== 'tool'
    || head.exec.tool_id !== toolId
    || head.exec.task_type !== taskType
  ) return null

  return head
}
