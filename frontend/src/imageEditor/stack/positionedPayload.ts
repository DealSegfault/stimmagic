import { isIdentity, type Affine } from './geometryTransform.ts'

/**
 * An identity transform says where a payload starts, not how large its frame is.
 *
 * Compact payloads at origin [0, 0] also have an identity transform. Returning
 * one of those directly makes downstream full-frame mask draws stretch the
 * compact rectangle over the whole image. Reuse is safe only when the source
 * already has the stage's dimensions; otherwise it must be rebuilt on a
 * stage-sized canvas even though no geometric transform is required.
 */
export function canReusePositionedPayload(
  source: CanvasImageSource,
  matrix: Affine,
  width: number,
  height: number,
): boolean {
  if (!isIdentity(matrix)) return false
  const candidate = source as any
  const sourceWidth = [
    candidate.naturalWidth,
    candidate.videoWidth,
    candidate.displayWidth,
    candidate.width,
  ].find(value => typeof value === 'number' && value > 0)
  const sourceHeight = [
    candidate.naturalHeight,
    candidate.videoHeight,
    candidate.displayHeight,
    candidate.height,
  ].find(value => typeof value === 'number' && value > 0)
  return sourceWidth === width && sourceHeight === height
}
