import assert from 'node:assert/strict'
import test from 'node:test'

import {
  LEVEL_EDITS,
  PHOTO_ADJUSTMENT_GROUPS,
  photoAdjustmentGroup,
} from './adjustSections.ts'

test('Adjust and masked Retouch share one Light Color Detail schema', () => {
  assert.deepEqual(
    PHOTO_ADJUSTMENT_GROUPS.map(group => group.label),
    ['Light', 'Color', 'Detail'],
  )
  assert.deepEqual(
    LEVEL_EDITS.map(edit => edit.label),
    ['Light', 'Color', 'Detail'],
  )
  for (const group of PHOTO_ADJUSTMENT_GROUPS) {
    const level = LEVEL_EDITS.find(edit => edit.id === group.section)
    assert.ok(level)
    assert.strictEqual(level.controls, group.controls)
    assert.equal(level.icon, group.icon)
  }
})

test('the shared schema includes the photographic parity controls', () => {
  assert.deepEqual(
    photoAdjustmentGroup('light')?.controls.map(control => control.key),
    [
      'exposure', 'contrast', 'highlights', 'shadows', 'whites', 'blacks',
      'brightness', 'gamma', 'curve',
    ],
  )
  assert.deepEqual(
    photoAdjustmentGroup('color')?.controls.map(control => control.key),
    [
      'temperature', 'tint', 'hue', 'saturation', 'vibrance',
      'colorizeHue', 'colorizeAmount', 'defringe',
    ],
  )
  assert.deepEqual(
    photoAdjustmentGroup('detail')?.controls.map(control => control.key),
    [
      'texture', 'clarity', 'dehaze', 'moire',
      'sharpen', 'sharpenRadius', 'sharpenDetail', 'sharpenMasking',
      'noiseReduction', 'noiseReductionDetail', 'noiseReductionContrast',
      'colorNoiseReduction', 'colorNoiseReductionDetail',
      'colorNoiseReductionSmoothness',
      'noise', 'grainSize', 'grainRoughness', 'blur',
    ],
  )
})
