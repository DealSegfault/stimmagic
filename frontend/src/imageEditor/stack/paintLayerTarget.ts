import type { LegacyPaintLayerOp, Op, PaintLayerOp } from './types'

export type RasterPaintLayerOp = PaintLayerOp | LegacyPaintLayerOp

/** Raster Paint layers, including the two executor names written by old builds. */
export function isRasterPaintLayer(op: Op | undefined): op is RasterPaintLayerOp {
  return op?.class === 'container'
    && ['paint', 'retouch', 'sketch'].includes(op.exec?.kind)
}

/**
 * Resolve the layer a newly entered Paint workspace implicitly owns.
 *
 * An explicitly selected Paint row wins wherever it sits. Without one, only
 * the top edit is eligible: reusing an older buried layer would unexpectedly
 * put new pixels below later edits, so that case deliberately starts a layer.
 */
export function implicitPaintLayer(
  edits: readonly Op[],
  selectedOpId: string | null,
): RasterPaintLayerOp | null {
  const selected = selectedOpId
    ? edits.find(op => op.id === selectedOpId)
    : undefined
  if (isRasterPaintLayer(selected)) return selected

  const top = edits.at(-1)
  return isRasterPaintLayer(top) ? top : null
}
