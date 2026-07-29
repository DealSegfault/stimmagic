/**
 * One-time conversion of documents written while whole-image steps existed.
 *
 * A whole-image step replaced the composite outright, which is what made it a
 * fence — everything below it was an input it had already consumed, and
 * everything above it sat on pixels no other step could re-derive. The class is
 * gone, so a document that still contains one has to be resolved rather than
 * rendered: the steps at and below the topmost one become the base they already
 * were, and the steps above them carry on as an ordinary stack.
 *
 * Deterministic, and it never asks a model for anything: a whole step's pixels
 * are its picked candidate's payload, which is by definition the composite at
 * that point. A disabled one contributed nothing and is simply dropped.
 *
 * The pre-flatten document is not destroyed — the caller journals the
 * conversion, and payloads are never deleted — so the old state stays
 * recoverable under the pack-rat rule.
 */

import type { StackDocument } from './types'
import { StackCompositor } from './useStackCompositor'
import { geometryBelow } from './geometryTransform'

export interface FlattenDeps {
  loadPayload: (ref: string, revision?: number) => Promise<CanvasImageSource>
  loadBase: () => Promise<CanvasImageSource>
  uploadPayload: (name: string, blob: Blob) => Promise<string>
  canvasToBlob: (canvas: HTMLCanvasElement) => Promise<Blob>
}

function makeCanvas(source: CanvasImageSource, width: number, height: number) {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  canvas.getContext('2d')!.drawImage(source, 0, 0, width, height)
  return canvas
}

export function hasWholeOps(doc: StackDocument | null): boolean {
  return !!doc?.edits.some(op => (op as any).class === 'whole')
}

/**
 * Returns the flattened document, or null when there is nothing to convert.
 * Does not mutate the input.
 */
export async function flattenWholeOps(
  doc: StackDocument,
  deps: FlattenDeps
): Promise<{ document: StackDocument; flattenedCount: number } | null> {
  const wholeIndices = doc.edits
    .map((op, index) => ((op as any).class === 'whole' ? index : -1))
    .filter(index => index >= 0)
  if (!wholeIndices.length) return null

  const last = wholeIndices[wholeIndices.length - 1]

  let current = makeCanvas(await deps.loadBase(), doc.canvas.width, doc.canvas.height)
  let segmentStart = 0

  for (const index of wholeIndices) {
    // Everything between the previous whole step and this one composites
    // normally, over whatever the previous one left behind.
    if (index > segmentStart) {
      current = await renderSegment(doc, segmentStart, index, current, deps)
    }

    const op = doc.edits[index] as any
    // Read the pick directly: `pickedCandidate` only knows the classes that
    // still exist, and this one no longer does.
    const picked = (op.candidates || []).find((c: any) => c.id === op.picked)
    if (op.enabled && picked?.patch_ref) {
      // A whole step's payload IS the composite at that point — that is what
      // made it a fence, and it is what makes this conversion exact.
      const payload = await deps.loadPayload(picked.patch_ref)
      const width = (payload as any).naturalWidth || (payload as any).width
      const height = (payload as any).naturalHeight || (payload as any).height
      current = makeCanvas(payload, width, height)
    }
    segmentStart = index + 1
  }

  const ref = await deps.uploadPayload(
    `flattened-${last}.png`,
    await deps.canvasToBlob(current)
  )

  const surviving = doc.edits.slice(last + 1)
  const document_: StackDocument = {
    ...doc,
    base: {
      ...doc.base,
      payload_ref: ref,
      width: current.width,
      height: current.height,
    },
    canvas: { width: current.width, height: current.height },
    edits: surviving,
  }

  // Every surviving step's payloads were anchored to a geometry that included
  // crops below the fence. Those crops are baked into the new base, so the
  // anchor has to be re-taken against what is left, or the co-transform would
  // carry each payload through a crop that has already happened to it.
  for (let index = 0; index < document_.edits.length; index++) {
    const op = document_.edits[index] as any
    if (!op.payload_frame) continue
    const now = geometryBelow(document_, index)
    op.payload_frame = { matrix: now.matrix, width: now.width, height: now.height }
  }

  return { document: document_, flattenedCount: last + 1 }
}

/** Composite `[start, end)` over `input`, using the normal op executors. */
async function renderSegment(
  doc: StackDocument,
  start: number,
  end: number,
  input: HTMLCanvasElement,
  deps: FlattenDeps
): Promise<HTMLCanvasElement> {
  const compositor = new StackCompositor({
    loadPayload: deps.loadPayload,
    loadBase: async () => input,
  })
  return compositor.render({
    ...doc,
    base: { ...doc.base, width: input.width, height: input.height },
    canvas: { width: input.width, height: input.height },
    edits: doc.edits.slice(start, end),
  })
}
