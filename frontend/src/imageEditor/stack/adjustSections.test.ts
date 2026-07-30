import assert from 'node:assert/strict'
import test from 'node:test'

import {
  LEVEL_EDITS,
  MIXER_BANDS,
  MIXER_MODES,
  PHOTO_ADJUSTMENT_GROUPS,
  mixerKey,
  photoAdjustmentGroup,
} from './adjustSections.ts'

test('Adjust and masked Retouch share one adjustment group schema', () => {
  const labels = ['Light', 'Color', 'Detail', 'Mixer', 'Point color', 'Grading']
  assert.deepEqual(PHOTO_ADJUSTMENT_GROUPS.map(group => group.label), labels)
  assert.deepEqual(LEVEL_EDITS.map(edit => edit.label), labels)
  for (const group of PHOTO_ADJUSTMENT_GROUPS) {
    const level = LEVEL_EDITS.find(edit => edit.id === group.section)
    assert.ok(level)
    assert.strictEqual(level.controls, group.controls)
    assert.equal(level.icon, group.icon)
    assert.equal(level.presentation, group.presentation)
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
  assert.deepEqual(
    photoAdjustmentGroup('mixer')?.controls.map(control => control.key),
    MIXER_MODES.flatMap(mode => MIXER_BANDS.map(band => mixerKey(mode.id, band.id))),
  )
  assert.deepEqual(
    photoAdjustmentGroup('point')?.controls.map(control => control.key),
    [
      'pointHue', 'pointSat', 'pointLum',
      'pointHueShift', 'pointSatShift', 'pointLumShift', 'pointRange',
    ],
  )
  assert.deepEqual(
    photoAdjustmentGroup('grade')?.controls.map(control => control.key),
    [
      'gradeShadowHue', 'gradeShadowSat', 'gradeShadowLum',
      'gradeMidHue', 'gradeMidSat', 'gradeMidLum',
      'gradeHighlightHue', 'gradeHighlightSat', 'gradeHighlightLum',
      'gradeBlend', 'gradeBalance',
    ],
  )
})
