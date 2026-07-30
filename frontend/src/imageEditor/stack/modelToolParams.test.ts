import assert from 'node:assert/strict'
import test from 'node:test'
import {
  copyModelReferenceImages,
  editableModelParamNames,
  modelReferenceLimits,
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

test('reference limits reserve the first input image for the edited target', () => {
  assert.deepEqual(modelReferenceLimits({
    parameter_schema: {
      properties: {
        input_images: { type: 'array', minItems: 2, maxItems: 4 },
      },
    },
  }), {
    totalMin: 2,
    totalMax: 4,
    min: 1,
    max: 3,
  })
})

test('reference limits support legacy x-* constraints', () => {
  assert.deepEqual(modelReferenceLimits({
    parameter_schema: {
      properties: {
        input_images: { type: 'array', 'x-min-items': 1, 'x-max-items': 8 },
      },
    },
  }), {
    totalMin: 1,
    totalMax: 8,
    min: 0,
    max: 7,
  })
})

test('tools without explicit multi-image capacity expose no reference slots', () => {
  assert.deepEqual(modelReferenceLimits({
    parameter_schema: {
      properties: {
        input_images: { type: 'array' },
      },
    },
  }), {
    totalMin: 1,
    totalMax: 1,
    min: 0,
    max: 0,
  })
  assert.equal(modelReferenceLimits(null).max, 0)
})

test('reactive-style reference proxies become plain ordered document data', () => {
  const reactiveStyle = new Proxy([
    new Proxy({ media_id: 42, file_hash: 'first', filename: 'first.png' }, {}),
    new Proxy({ media_id: 84, file_hash: 'second' }, {}),
  ], {})

  assert.deepEqual(copyModelReferenceImages(reactiveStyle), [
    { media_id: 42, file_hash: 'first', filename: 'first.png' },
    { media_id: 84, file_hash: 'second' },
  ])
  assert.deepEqual(copyModelReferenceImages(new Proxy([], {})), [])
})
