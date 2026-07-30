import assert from 'node:assert/strict'
import test from 'node:test'
import { combineAfterSelectionChange } from './selectionLifecycle.ts'

test('publishing a selection does not silently turn New into Add', () => {
  assert.equal(combineAfterSelectionChange('new', true), 'new')
})

test('an explicitly chosen combine mode survives while a selection exists', () => {
  assert.equal(combineAfterSelectionChange('add', true), 'add')
  assert.equal(combineAfterSelectionChange('subtract', true), 'subtract')
  assert.equal(combineAfterSelectionChange('intersect', true), 'intersect')
})

test('an empty selection resets the next gesture to New', () => {
  assert.equal(combineAfterSelectionChange('add', false), 'new')
})
