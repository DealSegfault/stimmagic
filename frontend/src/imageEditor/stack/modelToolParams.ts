/**
 * Parameter ownership for model-backed image-editor operations.
 *
 * The host owns the pixels, mask, prompt, and exact output grid. Everything
 * else declared by the selected STP tool belongs to the tool and must pass
 * through unchanged, by its schema property name.
 */

export const HOST_MANAGED_MODEL_PARAMS = new Set([
  'prompt',
  'input_images',
  'mask',
  'width',
  'height',
])

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
    if (value !== undefined) result[name] = structuredClone(value)
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
