import assert from 'node:assert/strict'
import test from 'node:test'
import {
  combineAfterSelectionChange,
  selectionMatteAction,
} from './selectionLifecycle.ts'

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

test('an empty-matte click clears a selection before changing tools', () => {
  assert.equal(selectionMatteAction(true, true), 'clear-selection')
  assert.equal(selectionMatteAction(true, false), 'clear-selection')
})

test('a subsequent empty-matte click can release the armed tool', () => {
  assert.equal(selectionMatteAction(false, true), 'disarm-tool')
  assert.equal(selectionMatteAction(false, false), 'none')
})
