import assert from 'node:assert/strict'
import test from 'node:test'
import { validateTaskType, OUTPAINT_EXPAND_FIELDS } from './taskTypeValidation.ts'

test('outpaint with every edge at zero cannot be submitted', () => {
  const result = validateTaskType('outpaint-image', {
    expand_top_pct: 0,
    expand_bottom_pct: 0,
    expand_left_pct: 0,
    expand_right_pct: 0,
  })
  assert.equal(result.ok, false)
  assert.match(result.reason ?? '', /expand at least one edge/i)
})

test('outpaint with no expand params at all is the same as all zero', () => {
  // The state the tool opens in, before any slider is touched.
  assert.equal(validateTaskType('outpaint-image', {}).ok, false)
})

test('any single expanded edge is enough', () => {
  for (const field of OUTPAINT_EXPAND_FIELDS) {
    assert.equal(
      validateTaskType('outpaint-image', { [field]: 5 }).ok,
      true,
      `${field} alone should permit submission`
    )
  }
})

test('negative and non-numeric values do not count as expansion', () => {
  assert.equal(validateTaskType('outpaint-image', { expand_top_pct: -20 }).ok, false)
  assert.equal(validateTaskType('outpaint-image', { expand_top_pct: 'lots' }).ok, false)
  // A string the host round-tripped through a form field still counts.
  assert.equal(validateTaskType('outpaint-image', { expand_top_pct: '20' }).ok, true)
})

test('task types with no rule of their own always pass', () => {
  assert.equal(validateTaskType('text-to-image', {}).ok, true)
  assert.equal(validateTaskType('inpaint-image', {}).ok, true)
  assert.equal(validateTaskType(null, {}).ok, true)
  assert.equal(validateTaskType(undefined, {}).ok, true)
})
