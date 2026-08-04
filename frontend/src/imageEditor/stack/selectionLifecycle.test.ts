import assert from 'node:assert/strict'
import test from 'node:test'
import {
  combineAfterSelectionChange,
  combineFromModifiers,
  editorEscapeAction,
  emptySelectionCombine,
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

test('the selection brush implicitly uses union mode', () => {
  assert.equal(emptySelectionCombine('brush'), 'add')
  assert.equal(combineAfterSelectionChange('subtract', false, 'brush'), 'add')
  assert.equal(emptySelectionCombine('rect'), 'new')
})

test('Escape clears a pixel selection before changing any editor mode', () => {
  assert.equal(editorEscapeAction({
    hasSelection: true,
    hasRetouchFeedback: true,
    hasArmedSelectionTool: true,
    hasFamily: true,
    hasSelectedShape: true,
  }), 'clear-selection')
})

test('Escape actions cannot disarm the selected region tool or its palette', () => {
  assert.equal(editorEscapeAction({
    hasSelection: false,
    hasRetouchFeedback: false,
    hasArmedSelectionTool: true,
    hasFamily: true,
    hasSelectedShape: true,
  }), 'none')
})

test('Escape still dismisses canvas feedback and modes in visual priority order', () => {
  assert.equal(editorEscapeAction({
    hasSelection: false,
    hasRetouchFeedback: true,
    hasArmedSelectionTool: false,
    hasFamily: true,
    hasSelectedShape: true,
  }), 'dismiss-retouch-feedback')
  assert.equal(editorEscapeAction({
    hasSelection: false,
    hasRetouchFeedback: false,
    hasArmedSelectionTool: false,
    hasFamily: true,
    hasSelectedShape: true,
  }), 'leave-family')
  assert.equal(editorEscapeAction({
    hasSelection: false,
    hasRetouchFeedback: false,
    hasArmedSelectionTool: false,
    hasFamily: false,
    hasSelectedShape: true,
  }), 'clear-shape')
})

test('an empty-matte click clears a selection before changing tools', () => {
  assert.equal(selectionMatteAction(true, true), 'clear-selection')
  assert.equal(selectionMatteAction(true, false), 'clear-selection')
})

test('a subsequent empty-matte click can release the armed tool', () => {
  assert.equal(selectionMatteAction(false, true), 'disarm-tool')
  assert.equal(selectionMatteAction(false, false), 'none')
})

test('held modifiers speak the standard combine grammar', () => {
  assert.equal(combineFromModifiers(false, false), null)
  assert.equal(combineFromModifiers(true, false), 'add')
  assert.equal(combineFromModifiers(false, true), 'subtract')
  assert.equal(combineFromModifiers(true, true), 'intersect')
})
