import assert from 'node:assert/strict'
import test from 'node:test'

import {
  INPAINT_REMOVE_PROMPT,
  removeCapableTools,
  removeRouteForTool,
} from './modelToolRouting.ts'

test('Remove prefers a native erase task when a tool supports both routes', () => {
  assert.deepEqual(
    removeRouteForTool({ task_types: ['inpaint-image', 'erase-image'] }),
    { taskType: 'erase-image', prompt: '' },
  )
})

test('an inpaint-only tool performs Remove with the hidden removal prompt', () => {
  assert.deepEqual(
    removeRouteForTool({ task_types: ['inpaint-image'] }),
    { taskType: 'inpaint-image', prompt: INPAINT_REMOVE_PROMPT },
  )
})

test('unrelated tools cannot perform Remove', () => {
  assert.equal(removeRouteForTool({ task_types: ['image-to-image'] }), null)
})

test('Remove lists native tools before inpaint fallbacks', () => {
  const inpaint = { full_tool_id: 'local:inpaint', task_types: ['inpaint-image'] }
  const native = { full_tool_id: 'cloud:erase', task_types: ['erase-image'] }
  const both = {
    full_tool_id: 'local:both',
    task_types: ['inpaint-image', 'erase-image'],
  }

  assert.deepEqual(
    removeCapableTools([inpaint, native, both]).map(tool => tool.full_tool_id),
    ['cloud:erase', 'local:both', 'local:inpaint'],
  )
})
