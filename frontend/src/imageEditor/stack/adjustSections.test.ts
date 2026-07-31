import assert from 'node:assert/strict'
import test from 'node:test'

import {
  LEVEL_EDITS,
  MIXER_BANDS,
  MIXER_MODES,
  PHOTO_ADJUSTMENT_CONTROLS,
  PHOTO_ADJUSTMENT_GROUPS,
  effectLookStepOf,
  mixerKey,
  photoAdjustmentGroup,
  stripEntryById,
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
      'curve',
    ],
  )
  assert.deepEqual(
    photoAdjustmentGroup('color')?.controls.map(control => control.key),
    ['temperature', 'tint', 'vibrance', 'saturation'],
  )
  assert.deepEqual(
    photoAdjustmentGroup('detail')?.controls.map(control => control.key),
    [
      'texture', 'clarity', 'dehaze', 'moire', 'defringe',
      'sharpen', 'sharpenRadius', 'sharpenDetail', 'sharpenMasking',
      'noiseReduction', 'noiseReductionDetail', 'noiseReductionContrast',
      'colorNoiseReduction', 'colorNoiseReductionDetail',
      'colorNoiseReductionSmoothness',
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

test('strip-look dials stay in the render schema without being group sliders', () => {
  const offered = new Set(
    PHOTO_ADJUSTMENT_GROUPS.flatMap(group => group.controls.map(control => control.key))
  )
  const schema = new Set(PHOTO_ADJUSTMENT_CONTROLS.map(control => control.key))
  for (const key of [
    'colorizeHue', 'colorizeAmount', 'noise', 'grainSize', 'grainRoughness', 'blur',
  ]) {
    assert.ok(!offered.has(key), `${key} offered by a group`)
    assert.ok(schema.has(key), `${key} fell out of the render schema`)
  }
})

test('strip looks match their own steps, supporting dials included', () => {
  const colorize = stripEntryById('colorize')!
  assert.equal(
    effectLookStepOf({ colorizeAmount: 50, colorizeHue: 30 })?.id, 'colorize'
  )
  assert.deepEqual(colorize.seed, { colorizeHue: 30 })
  assert.equal(effectLookStepOf({ noise: 40, grainSize: 25 })?.id, 'grain')
  assert.equal(effectLookStepOf({ blur: 10 })?.id, 'blur')
  // A migrated blob carrying extra params is never a strip step.
  assert.equal(effectLookStepOf({ noise: 40, vignette: 20 }), undefined)
  assert.equal(effectLookStepOf({}), undefined)
})
