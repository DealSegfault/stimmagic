import assert from 'node:assert/strict'
import test from 'node:test'

import {
  directEditRowId,
  editRowKeyboardCommand,
  rowCandidateIndex,
} from './editListKeyboard.ts'

test('vertical arrows move rows and horizontal arrows move candidates', () => {
  assert.deepEqual(editRowKeyboardCommand('ArrowDown'), { type: 'move-row', indexDelta: -1 })
  assert.deepEqual(editRowKeyboardCommand('ArrowUp'), { type: 'move-row', indexDelta: 1 })
  assert.deepEqual(editRowKeyboardCommand('ArrowRight'), {
    type: 'move-candidate', candidateDelta: 1,
  })
  assert.deepEqual(editRowKeyboardCommand('ArrowLeft'), {
    type: 'move-candidate', candidateDelta: -1,
  })
})

test('a focused row can enter and walk its candidate strip from either direction', () => {
  assert.equal(rowCandidateIndex(4, -1, 1), 0)
  assert.equal(rowCandidateIndex(4, -1, -1), 3)
  assert.equal(rowCandidateIndex(4, 1, 1), 2)
  assert.equal(rowCandidateIndex(4, 2, -1), 1)
  assert.equal(rowCandidateIndex(4, 3, 1), 3)
  assert.equal(rowCandidateIndex(0, -1, 1), -1)
})

test('edit rows support visibility and removal keys', () => {
  assert.deepEqual(editRowKeyboardCommand(' '), { type: 'toggle' })
  assert.deepEqual(editRowKeyboardCommand('Spacebar'), { type: 'toggle' })
  assert.deepEqual(editRowKeyboardCommand('Delete'), { type: 'remove' })
  assert.deepEqual(editRowKeyboardCommand('Backspace'), { type: 'remove' })
  assert.equal(editRowKeyboardCommand('Enter'), null)
})

test('only a directly focused edit row owns stack shortcuts', () => {
  const row = {
    dataset: { opId: 'regenerate' },
    matches: (selector: string) => selector === '[data-op-id]',
  }
  const textarea = {
    // Even if an editable descendant can find a row ancestor, it is not the
    // row that owns focus and must keep Backspace for text editing.
    closest: () => row,
    matches: () => false,
  }
  const rowButton = { closest: () => row, matches: () => false }

  assert.equal(directEditRowId(row as unknown as EventTarget), 'regenerate')
  assert.equal(directEditRowId(textarea as unknown as EventTarget), null)
  assert.equal(directEditRowId(rowButton as unknown as EventTarget), null)
  assert.equal(directEditRowId(null), null)
})
