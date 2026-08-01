/**
 * Name a generative step after what it did to the picture.
 *
 * A column of rows all reading "Repaint" is a column that says nothing: the
 * verb is the one thing the person already knows, because they pressed it. What
 * they cannot recover from the row is WHICH repaint it was. So the region as it
 * looked before the step, plus the prompt they typed, go to the quick-task
 * model and come back as "Remove house" or "Dog → fox".
 *
 * Advisory, always. It runs after the job is submitted, off the run path, and
 * every failure — no model configured, a refusal, a shape we cannot use — is
 * silent and leaves the verb label in place. A name is worth nothing if getting
 * it wrong can cost the edit.
 */
import axios from 'axios'
import { maskBounds, extractPatch } from './useStackCompositor'

/** Enough of the surroundings to tell a roof from a shed, and no more. */
const CONTEXT_FRACTION = 0.25
const MIN_CONTEXT_PX = 24
/** The model reads a thumbnail; a 4K crop is bytes spent on nothing. */
const MAX_EDGE_PX = 512

export type NameableOperation = 'remove' | 'repaint'

/**
 * The region crop the model is asked to name, as a JPEG data URL's payload.
 * Null when the mask has no area — nothing was selected, so nothing to name.
 */
export function regionCropBase64(
  input: HTMLCanvasElement,
  mask: HTMLCanvasElement,
): string | null {
  const { width, height } = input
  const tight = maskBounds(mask, width, height)
  if (!tight) return null

  const margin = Math.max(
    MIN_CONTEXT_PX,
    Math.round(Math.max(tight.width, tight.height) * CONTEXT_FRACTION),
  )
  const bounds = maskBounds(mask, width, height, margin)
  if (!bounds) return null

  const patch = extractPatch(input, bounds)
  const scale = Math.min(1, MAX_EDGE_PX / Math.max(patch.width, patch.height))
  const target = scale < 1
    ? (() => {
        const scaled = document.createElement('canvas')
        scaled.width = Math.max(1, Math.round(patch.width * scale))
        scaled.height = Math.max(1, Math.round(patch.height * scale))
        const ctx = scaled.getContext('2d')!
        ctx.imageSmoothingQuality = 'high'
        ctx.drawImage(patch, 0, 0, scaled.width, scaled.height)
        return scaled
      })()
    : patch

  const url = target.toDataURL('image/jpeg', 0.85)
  const comma = url.indexOf(',')
  return comma < 0 ? null : url.slice(comma + 1)
}

/**
 * A short label for this step, or null to keep the verb.
 *
 * Takes the crop rather than the canvases: the caller cuts it synchronously,
 * while the mask and the input it was sampled against are still the ones the
 * step ran on. The workspace selection can be edited or reused immediately,
 * so reading those live canvases one await later could read different pixels.
 */
export async function nameStepFromCrop(
  operation: NameableOperation,
  imageB64: string,
  prompt?: string,
): Promise<string | null> {
  try {
    const { data } = await axios.post('/api/image-stack/name-edit', {
      operation,
      image_b64: imageB64,
      prompt: prompt || null,
    })
    const label = typeof data?.label === 'string' ? data.label.trim() : ''
    return label || null
  } catch {
    return null
  }
}
