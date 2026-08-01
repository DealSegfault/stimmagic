/**
 * Parameter ownership for model-backed image-editor operations.
 *
 * The host owns the pixels, mask, prompt, and exact output grid. Everything
 * else declared by the selected STP tool belongs to the tool and must pass
 * through unchanged, by its schema property name.
 */

import type { ModelReferenceImage } from './types'

export const HOST_MANAGED_MODEL_PARAMS = new Set([
  'prompt',
  'input_images',
  'mask',
  'width',
  'height',
])

export interface ModelReferenceLimits {
  /** Total image capacity declared by the tool, including the edited target. */
  totalMin: number
  totalMax: number
  /** Additional reference-image requirements after reserving the target slot. */
  min: number
  max: number
}

/**
 * Materialize Vue-backed draft references as plain document data.
 *
 * `structuredClone()` rejects reactive proxies, including an empty reactive
 * array. Copying the declared scalar fields also prevents UI-only state from
 * leaking into persisted operations or generation payloads.
 */
export function copyModelReferenceImages(
  images: readonly ModelReferenceImage[],
): ModelReferenceImage[] {
  return images.map(image => ({
    media_id: image.media_id,
    file_hash: image.file_hash,
    ...(image.filename ? { filename: image.filename } : {}),
  }))
}

/**
 * Return the reference-image capacity for an editor model tool.
 *
 * STP schemas in the wild use both standard JSON Schema keys and legacy x-*
 * hints. The edited composite always occupies input_images[0], so the editor
 * exposes only the remaining slots as references.
 */
export function modelReferenceLimits(tool: any): ModelReferenceLimits {
  const schema = tool?.parameter_schema?.properties?.input_images
  if (!schema || schema.type !== 'array') {
    return { totalMin: 1, totalMax: 1, min: 0, max: 0 }
  }

  const rawMin = schema.minItems ?? schema['x-min-items'] ?? 1
  const rawMax = schema.maxItems ?? schema['x-max-items'] ?? 1
  const totalMin = Number.isFinite(Number(rawMin))
    ? Math.max(1, Math.trunc(Number(rawMin)))
    : 1
  const totalMax = Number.isFinite(Number(rawMax))
    ? Math.max(totalMin, Math.trunc(Number(rawMax)))
    : 1

  return {
    totalMin,
    totalMax,
    min: Math.max(0, totalMin - 1),
    max: Math.max(0, totalMax - 1),
  }
}

export function editableModelParamNames(tool: any): string[] {
  const properties = tool?.parameter_schema?.properties ?? {}
  return Object.entries(properties)
    .filter(([name, schema]: [string, any]) =>
      !HOST_MANAGED_MODEL_PARAMS.has(name) && schema?.['x-hidden'] !== true
    )
    .map(([name]) => name)
}

/** Defaults with exact STP/schema keys—no frontend camel-case translation. */
export function modelToolDefaults(tool: any): Record<string, any> {
  const properties = tool?.parameter_schema?.properties ?? {}
  const result: Record<string, any> = {}
  for (const name of editableModelParamNames(tool)) {
    const value = properties[name]?.default
    // JSON round-trip, not structuredClone: the catalog lives in a deep
    // reactive ref, so an object/array default arrives as a Vue proxy, which
    // structuredClone rejects (DataCloneError). Schema defaults are JSON by
    // definition, so nothing is lost.
    if (value !== undefined) {
      result[name] = typeof value === 'object' && value !== null
        ? JSON.parse(JSON.stringify(value))
        : value
    }
  }
  return result
}

/**
 * Keep only declared, user-editable fields.
 */
export function sanitizeModelToolParams(
  tool: any,
  values: Record<string, any> | null | undefined,
): Record<string, any> {
  const allowed = new Set(editableModelParamNames(tool))
  return Object.fromEntries(
    Object.entries(values ?? {}).filter(([name]) => allowed.has(name))
  )
}
