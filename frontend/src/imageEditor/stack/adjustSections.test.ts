import assert from 'node:assert/strict'
import test from 'node:test'

import { FILTER_MATRICES, FILTER_PRESET_LABELS } from '../ported/filterMatrices.ts'
import {
  LEGACY_FILTER_LABELS,
  LEVEL_EDITS,
  LOOKS,
  LOOK_CATEGORIES,
  MIXER_BANDS,
  MIXER_MODES,
  PHOTO_ADJUSTMENT_CONTROLS,
  PHOTO_ADJUSTMENT_GROUPS,
  effectLookStepOf,
  lookById,
  mixerKey,
  photoAdjustmentGroup,
  touchedGroups,
} from './adjustSections.ts'

test('Adjust and masked Retouch share one adjustment group schema', () => {
  const labels = [
    'Light', 'Color', 'Detail', 'Mixer', 'Point color', 'Grading',
    'Effects', 'Stylize',
  ]
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
    ['temperature', 'tint', 'vibrance', 'saturation', 'colorizeAmount', 'colorizeHue'],
  )
  assert.deepEqual(
    photoAdjustmentGroup('effects')?.controls.map(control => control.key),
    ['vignette', 'glow', 'blur', 'noise', 'grainSize', 'grainRoughness'],
  )
  assert.deepEqual(
    photoAdjustmentGroup('stylize')?.controls.map(control => control.key),
    [
      'halftone', 'halftoneAngle', 'vhs', 'glitch', 'glitchBlockSize',
      'chromaticAberration',
    ],
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

/**
 * The old Filters strip carried these as tiles, which is exactly why they were
 * unreachable from a selection. Every one is a group slider now, so a click
 * with a selection live scopes it like any other Adjust edit.
 */
test('the former strip effects are group sliders, not loose schema keys', () => {
  const offered = new Set(
    PHOTO_ADJUSTMENT_GROUPS.flatMap(group => group.controls.map(control => control.key))
  )
  const schema = new Set(PHOTO_ADJUSTMENT_CONTROLS.map(control => control.key))
  for (const key of [
    'colorizeHue', 'colorizeAmount', 'noise', 'grainSize', 'grainRoughness',
    'blur', 'vignette', 'glow', 'vhs', 'glitch', 'halftone',
    'chromaticAberration',
  ]) {
    assert.ok(offered.has(key), `${key} is not offered by any group`)
    assert.ok(schema.has(key), `${key} fell out of the render schema`)
  }
})

/**
 * A look is a bundle of ordinary adjustment params. Anything it sets must be a
 * key the render schema knows, or the look would silently do less than its
 * thumbnail promised.
 */
test('every look is written in the shared adjustment schema', () => {
  const schema = new Map(
    PHOTO_ADJUSTMENT_CONTROLS.map(control => [control.key, control]),
  )
  assert.ok(LOOKS.length)
  for (const look of LOOKS) {
    assert.ok(Object.keys(look.params).length, `${look.id} sets nothing`)
    for (const [key, value] of Object.entries(look.params)) {
      const control = schema.get(key)
      assert.ok(control, `${look.id} sets '${key}', which is not in the schema`)
      assert.notEqual(
        value, control.default,
        `${look.id} sets '${key}' to its default, which does nothing`,
      )
      if (control.kind !== 'curve') {
        assert.ok(
          value >= control.min && value <= control.max,
          `${look.id} sets '${key}' to ${value}, outside ${control.min}..${control.max}`,
        )
      }
    }
  }
})

test('look ids are unique and resolvable', () => {
  const ids = LOOKS.map(look => look.id)
  assert.equal(new Set(ids).size, ids.length)
  assert.deepEqual(LOOK_CATEGORIES.flatMap(category => category.looks), LOOKS)
  assert.equal(lookById('kodachrome')?.label, 'Kodachrome')
  assert.equal(lookById('nope'), undefined)
})

test('a look step reports exactly the groups its inspector should show', () => {
  const groups = touchedGroups(lookById('tri-x-400')!.params)
  assert.deepEqual(groups.map(group => group.id), ['light', 'color', 'effects'])
  assert.deepEqual(touchedGroups({}), [])
  assert.deepEqual(touchedGroups(null), [])
  // A value sitting at its default is not a touched group.
  assert.deepEqual(touchedGroups({ vignette: 0 }), [])
})

/**
 * The `filter` presets are a live contract for the post-processing chain (and
 * its Python mirror), not just editor read-compatibility, so the label list
 * must name every matrix and nothing else.
 */
test('the legacy filter preset labels cover exactly the matrices', () => {
  const matrices = new Set(Object.keys(FILTER_MATRICES))
  matrices.delete('none')
  assert.deepEqual(
    new Set(FILTER_PRESET_LABELS.map(preset => preset.id)),
    matrices,
  )
  assert.equal(LEGACY_FILTER_LABELS.get('tri-x-400'), 'Tri-X 400')
})

test('legacy single-effect steps keep their own inspector', () => {
  assert.equal(
    effectLookStepOf({ colorizeAmount: 50, colorizeHue: 30 })?.id, 'colorize'
  )
  assert.equal(effectLookStepOf({ noise: 40, grainSize: 25 })?.id, 'grain')
  assert.equal(effectLookStepOf({ blur: 10 })?.id, 'blur')
  // A migrated blob carrying extra params is never a single-effect step.
  assert.equal(effectLookStepOf({ noise: 40, vignette: 20 }), undefined)
  assert.equal(effectLookStepOf({}), undefined)
})
