import assert from 'node:assert/strict'
import test from 'node:test'

import { paintEngineSettings } from './paintEngineSettings.ts'

test('retouch engines start with subtle, soft defaults', () => {
  assert.equal(paintEngineSettings('dodge').exposure, 10)
  assert.equal(paintEngineSettings('burn').exposure, 10)
  assert.equal(paintEngineSettings('sponge').strength, 20)
  assert.equal(paintEngineSettings('blur').strength, 20)
  assert.equal(paintEngineSettings('sharpen').strength, 15)

  for (const engine of ['dodge', 'burn', 'sponge', 'blur', 'sharpen']) {
    assert.equal(paintEngineSettings(engine).brush.hardness, 20)
  }
})

test('each engine restores its own brush and gesture controls', () => {
  const dodge = paintEngineSettings('dodge', {
    brush: { size: 73, hardness: 8, opacity: 42, flow: 17, spacing: 31 },
    exposure: 6,
    range: 'highlights',
  })
  const sponge = paintEngineSettings('sponge', {
    brush: { size: 18, hardness: 70, opacity: 85, flow: 32, spacing: 44 },
    strength: 9,
    saturate: false,
  })

  assert.deepEqual(dodge.brush, {
    size: 73, hardness: 8, opacity: 42, flow: 17, spacing: 31,
  })
  assert.equal(dodge.exposure, 6)
  assert.equal(dodge.range, 'highlights')
  assert.deepEqual(sponge.brush, {
    size: 18, hardness: 70, opacity: 85, flow: 32, spacing: 44,
  })
  assert.equal(sponge.strength, 9)
  assert.equal(sponge.saturate, false)
})

test('persisted engine settings are clamped and corrupt fields fall back', () => {
  const restored = paintEngineSettings('burn', {
    brush: {
      size: 500,
      hardness: -20,
      opacity: Number.NaN,
      flow: 30,
      spacing: 0,
    },
    exposure: 300,
    range: 'invalid' as any,
    strength: -5,
  })

  assert.deepEqual(restored.brush, {
    size: 100,
    hardness: 0,
    opacity: 100,
    flow: 30,
    spacing: 1,
  })
  assert.equal(restored.exposure, 100)
  assert.equal(restored.range, 'midtones')
  assert.equal(restored.strength, 1)
})

