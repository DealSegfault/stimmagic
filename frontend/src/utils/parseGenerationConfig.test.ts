import assert from 'node:assert/strict'
import test from 'node:test'
import { parseGenerationConfig } from './parseGenerationConfig.ts'

const baseOptions = {
  hasPrompt: true,
  hasFrameCount: false,
  hasDuration: true,
  hasResolution: false,
  hasVideoFrames: false,
}

test('restores duration for tools that expose a duration parameter', () => {
  const update = parseGenerationConfig({ duration: 8 }, baseOptions)

  assert.equal(update?.modelParams.duration, 8)
})

test('does not transfer duration to tools without a duration parameter', () => {
  const update = parseGenerationConfig(
    { duration: 8 },
    { ...baseOptions, hasDuration: false },
  )

  assert.equal(update?.modelParams.duration, undefined)
})
