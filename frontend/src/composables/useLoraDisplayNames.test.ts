import assert from 'node:assert/strict'
import test from 'node:test'

import { computeDisplayNames } from './useLoraDisplayNames.ts'

test('moves a zero-padded step suffix into a compact secondary chip', () => {
  const path = 'Studio Ghibli Dark FairytaleV2 step0000006000.safetensors'

  assert.deepEqual(computeDisplayNames([path])[path], {
    primary: 'Studio Ghibli Dark FairytaleV2',
    secondary: 'step-6k',
  })
})

test('keeps recognizing checkpoint markers in their own path segment', () => {
  const path = 'Studio Ghibli/checkpoint-000012000/model.safetensors'

  assert.equal(computeDisplayNames([path])[path].secondary, 'checkpoint-12k')
})
