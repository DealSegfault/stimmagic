import assert from 'node:assert/strict'
import test from 'node:test'
import {
  editableModelParamNames,
  modelToolDefaults,
  sanitizeModelToolParams,
} from './modelToolParams.ts'

const tool = {
  parameter_schema: {
    properties: {
      prompt: { type: 'string' },
      input_images: { type: 'array' },
      mask: { type: 'string' },
      width: { type: 'integer', default: 1024 },
      height: { type: 'integer', default: 1024 },
      strength: { type: 'number', default: 0.75 },
      mode: { type: 'string', default: 'balanced' },
      adapters: { type: 'array', default: [] },
      internal: { type: 'string', default: 'secret', 'x-hidden': true },
    },
  },
}

test('model params expose every declared tool field except host-managed inputs', () => {
  assert.deepEqual(
    editableModelParamNames(tool),
    ['strength', 'mode', 'adapters'],
  )
})

test('model defaults preserve exact STP property names and structured values', () => {
  assert.deepEqual(modelToolDefaults(tool), {
    strength: 0.75,
    mode: 'balanced',
    adapters: [],
  })
})

test('parameter sanitization cannot override host-managed or undeclared fields', () => {
  assert.deepEqual(
    sanitizeModelToolParams(tool, {
      prompt: 'not allowed here',
      width: 1,
      strength: 0.5,
      adapters: ['one'],
      surprise: true,
    }),
    { strength: 0.5, adapters: ['one'] },
  )
})
