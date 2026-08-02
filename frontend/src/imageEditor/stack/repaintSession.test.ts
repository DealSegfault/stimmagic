import assert from 'node:assert/strict'
import test from 'node:test'

import { reusableRepaintOp } from './repaintSession.ts'
import type { StackDocument } from './types.ts'

function repaint(id = 'repaint') {
  return {
    id,
    class: 'patch',
    enabled: true,
    label: 'Regenerate',
    exec: { kind: 'tool', tool_id: 'provider:inpaint', task_type: 'inpaint-image' },
    operation: 'repaint',
    params: { prompt: 'first prompt' },
    picked: 'candidate-1',
    candidates: [],
  }
}

function doc(edits: any[]): StackDocument {
  return {
    format: 'stimma-image-stack',
    version: 1,
    base: {
      asset_id: 1,
      revision_id: 1,
      media_id: 1,
      file_hash: 'base',
      width: 100,
      height: 100,
    },
    canvas: { width: 100, height: 100 },
    edits,
  } as StackDocument
}

test('an unchanged selection reuses the head Regenerate step', () => {
  const op = repaint()
  assert.equal(
    reusableRepaintOp(
      doc([op]),
      { opId: op.id, selectionRevision: 3 },
      3,
      'provider:inpaint',
      'inpaint-image',
    ),
    op,
  )
})

test('clearing or changing the selection breaks the Regenerate session', () => {
  const op = repaint()
  assert.equal(
    reusableRepaintOp(
      doc([op]),
      { opId: op.id, selectionRevision: 3 },
      4,
      'provider:inpaint',
      'inpaint-image',
    ),
    null,
  )
})

test('a later edit above Regenerate prevents reuse', () => {
  const op = repaint()
  const adjust = {
    id: 'adjust', class: 'parametric', enabled: true, label: 'Light',
    exec: { kind: 'adjust' }, params: { exposure: 1 },
  }
  assert.equal(
    reusableRepaintOp(
      doc([op, adjust]),
      { opId: op.id, selectionRevision: 3 },
      3,
      'provider:inpaint',
      'inpaint-image',
    ),
    null,
  )
})

test('a disabled Regenerate step is not a live session target', () => {
  const op = { ...repaint(), enabled: false }
  assert.equal(
    reusableRepaintOp(
      doc([op]),
      { opId: op.id, selectionRevision: 3 },
      3,
      'provider:inpaint',
      'inpaint-image',
    ),
    null,
  )
})

test('changing the model route starts a new Regenerate step', () => {
  const op = repaint()
  const session = { opId: op.id, selectionRevision: 3 }
  assert.equal(
    reusableRepaintOp(doc([op]), session, 3, 'provider:other', 'inpaint-image'),
    null,
  )
  assert.equal(
    reusableRepaintOp(doc([op]), session, 3, 'provider:inpaint', 'erase-image'),
    null,
  )
})
