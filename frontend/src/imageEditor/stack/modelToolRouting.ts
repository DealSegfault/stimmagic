/**
 * Provider routing for the editor's semantic model operations.
 *
 * "Remove" is a user intent, not necessarily an STP task type. A dedicated
 * `erase-image` tool is the best match, but an inpaint tool can perform the same job
 * when given a removal prompt.
 */

export const REMOVE_COMPATIBLE_TASK_TYPES = [
  'erase-image',
  'inpaint-image',
] as const

export const INPAINT_REMOVE_PROMPT =
  'Remove the main object in the selected area. Fill the area with a natural continuation of the surrounding background.'

function taskTypesOf(tool: any): string[] {
  return tool?.task_types?.length
    ? tool.task_types
    : tool?.task_type
      ? [tool.task_type]
      : []
}

export function removeRouteForTool(
  tool: any,
): { taskType: 'erase-image' | 'inpaint-image'; prompt: string } | null {
  const taskTypes = taskTypesOf(tool)
  if (taskTypes.includes('erase-image')) {
    return { taskType: 'erase-image', prompt: '' }
  }
  if (taskTypes.includes('inpaint-image')) {
    return { taskType: 'inpaint-image', prompt: INPAINT_REMOVE_PROMPT }
  }
  return null
}

/** Native `erase-image` first, then inpaint fallbacks, preserving catalog order. */
export function removeCapableTools(tools: any[]): any[] {
  return [
    ...tools.filter(tool => taskTypesOf(tool).includes('erase-image')),
    ...tools.filter(tool => {
      const taskTypes = taskTypesOf(tool)
      return !taskTypes.includes('erase-image') && taskTypes.includes('inpaint-image')
    }),
  ]
}
