import type { LoraOption } from '../composables/useLoraPool'

export interface LoraUploadConfig {
  extensions: string[]
  max_size: number
}

export function toolSupportsLoras(tool: any): boolean {
  return !!tool?.parameter_schema?.properties?.loras
}

/** Read the provider-owned, positionally paired LoRA path/name enums. */
export function loraOptionsForTool(tool: any): LoraOption[] {
  const schema = tool?.parameter_schema?.properties?.loras
  const paths = schema?.items?.properties?.path?.enum
  const names = schema?.items?.properties?.name?.enum
  if (!Array.isArray(paths)) return []

  return paths
    .map((path: unknown, index: number) => {
      const value = String(path ?? '')
      const fallback = value.split('/').pop()?.replace(/\.[^.]+$/i, '').replace(/_/g, ' ') || value
      return { path: value, name: String(names?.[index] || fallback) }
    })
    .filter(option => option.path)
    .sort((a, b) => a.path.localeCompare(b.path))
}

export function loraUploadConfigForTool(tool: any): LoraUploadConfig | null {
  const schema = tool?.parameter_schema?.properties?.loras
  const config = schema?.['x-accept-upload']
    ?? schema?.items?.properties?.path?.['x-accept-upload']
  if (!config) return null
  return {
    extensions: Array.isArray(config.extensions) ? config.extensions : [],
    max_size: Number(config.max_size) || 0,
  }
}
