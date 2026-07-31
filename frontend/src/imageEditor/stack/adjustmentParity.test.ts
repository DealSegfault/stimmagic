import assert from 'node:assert/strict'
import test from 'node:test'

import {
  PHOTO_ADJUSTMENT_CONTROLS,
  maskedRetouchAdjustmentParams,
  wholeImageAdjustmentParams,
} from './adjustSections.ts'
import { buildLiveAdjustUniforms } from './liveAdjustPreview.ts'

function changedValue(control: (typeof PHOTO_ADJUSTMENT_CONTROLS)[number]) {
  if (control.kind === 'curve') {
    return {
      rgb: [[0, 0], [0.25, 0.18], [0.56, 0.62], [1, 1]],
      red: [[0, 0], [1, 1]],
      green: [[0, 0], [1, 1]],
      blue: [[0, 0], [1, 1]],
    }
  }
  const candidate = control.default + control.step
  return candidate <= control.max ? candidate : control.default - control.step
}

function dependencyFor(key: string): Record<string, any> {
  if (key === 'colorizeHue') return { colorizeAmount: 40 }
  if (key.startsWith('sharpen') && key !== 'sharpen') return { sharpen: 50 }
  if (
    key === 'noiseReductionDetail'
    || key === 'noiseReductionContrast'
  ) return { noiseReduction: 50 }
  if (
    key === 'colorNoiseReductionDetail'
    || key === 'colorNoiseReductionSmoothness'
  ) return { colorNoiseReduction: 50 }
  if (key === 'grainSize' || key === 'grainRoughness') return { noise: 40 }
  return {}
}

test('every shared control reaches whole-image, masked and GPU render parameters', () => {
  for (const control of PHOTO_ADJUSTMENT_CONTROLS) {
    const dependency = dependencyFor(control.key)
    const baseline = { ...dependency }
    const changed = { ...dependency, [control.key]: changedValue(control) }
    const whole = wholeImageAdjustmentParams(changed)
    const masked = maskedRetouchAdjustmentParams(changed)

    assert.deepEqual(
      masked,
      whole,
      `${control.key} diverged between whole-image and masked projection`,
    )
    assert.deepEqual(
      masked[control.key],
      changed[control.key],
      `${control.key} did not reach authoritative masked rendering`,
    )
    assert.notDeepEqual(
      buildLiveAdjustUniforms(changed, baseline),
      buildLiveAdjustUniforms(baseline, baseline),
      `${control.key} did not reach GPU drag preview`,
    )
  }
})

test('documents saved before advanced detail controls retain compatibility defaults', () => {
  const sharpen = wholeImageAdjustmentParams({ sharpen: 40 })
  assert.equal(sharpen.sharpenRadius, 1)
  assert.equal(sharpen.sharpenDetail, 0)
  assert.equal(sharpen.sharpenMasking, 0)

  const reduction = wholeImageAdjustmentParams({ noiseReduction: 40 })
  assert.equal(reduction.noiseReductionDetail, 0)
  assert.equal(reduction.noiseReductionContrast, 0)
  assert.equal(reduction.colorNoiseReduction, 0)

  const grain = wholeImageAdjustmentParams({ noise: 40 })
  assert.equal(grain.grainSize, 0)
  assert.equal(grain.grainRoughness, 50)
  assert.deepEqual(
    wholeImageAdjustmentParams({}),
    maskedRetouchAdjustmentParams({}),
  )
  assert.deepEqual(
    wholeImageAdjustmentParams({ curve: { rgb: [[0, Number.NaN]] } }).curve,
    wholeImageAdjustmentParams({}).curve,
  )
})
