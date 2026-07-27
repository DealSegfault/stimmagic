import assert from 'node:assert/strict'
import test from 'node:test'

import {
  blastRadius,
  canMoveWithinSegment,
  checkpointStatus,
  deriveStackState,
  foldedCount,
  segmentBounds,
} from './stackState.ts'
import { stackHashes } from './stackHashes.ts'
import type { StackDocument } from './types.ts'

function doc(edits: any[]): StackDocument {
  return {
    format: 'stimma-image-stack',
    version: 1,
    base: { asset_id: 1, revision_id: 1, media_id: 1, file_hash: 'base', width: 100, height: 100 },
    canvas: { width: 100, height: 100 },
    edits,
  } as StackDocument
}

function patch(id: string, sampled: string | null, enabled = true) {
  return {
    id, class: 'patch', enabled, label: id,
    exec: { kind: 'tool', tool_id: 't', task_type: 'inpaint-image' },
    params: {}, mask_ref: `payloads/${id}.png`,
    picked: sampled === null ? null : 'c1',
    candidates: sampled === null ? [] : [{ id: 'c1', patch_ref: 'p', media_id: 1, file_hash: 'h', sampled_input_hash: sampled }],
  }
}

function whole(id: string, sampled: string | null, enabled = true) {
  return {
    ...patch(id, sampled, enabled),
    class: 'whole',
    exec: { kind: 'tool', tool_id: 't', task_type: 'image-to-image' },
  }
}

function develop(id: string, params: any = { brightness: 5 }, enabled = true) {
  return { id, class: 'parametric', enabled, label: id, exec: { kind: 'develop' }, params }
}

/** The hash an op at `index` will be compared against. */
function inputHashAt(document: StackDocument, index: number) {
  return stackHashes(document).inputs[index]
}

test('an op sampled against its current input is clean', () => {
  const d = doc([patch('a', 'base')])
  assert.equal(deriveStackState(d).ops[0].staleness, 'clean')
})

test('a patch whose input moved is advisory, never hard', () => {
  const d = doc([develop('d'), patch('a', 'base')])
  // The patch was sampled against the bare base, but now sits above a develop.
  const state = deriveStackState(d)
  assert.equal(state.ops[1].staleness, 'advisory')
})

test('a checkpoint whose input moved is hard-stale', () => {
  const d = doc([develop('d'), whole('w', 'base')])
  assert.equal(deriveStackState(d).ops[1].staleness, 'hard')
})

test('everything above a hard-stale checkpoint is hard-stale too', () => {
  const d = doc([develop('d'), whole('w', 'base'), develop('e'), patch('p', 'anything')])
  const state = deriveStackState(d)
  assert.deepEqual(state.ops.map(o => o.staleness), ['clean', 'hard', 'hard', 'hard'])
})

test('a disabled op is never stale — it contributes nothing to compare', () => {
  const d = doc([develop('d'), patch('a', 'base', false)])
  assert.equal(deriveStackState(d).ops[1].staleness, 'clean')
})

test('a staged op with no pick has nothing to be stale against', () => {
  const d = doc([develop('d'), patch('a', null)])
  assert.equal(deriveStackState(d).ops[1].staleness, 'clean')
})

test('a parametric op is never stale — it is deterministic in its params', () => {
  const d = doc([whole('w', 'base'), develop('d')])
  const state = deriveStackState(d)
  // The develop above a clean checkpoint stays clean.
  assert.equal(state.ops[1].staleness, 'clean')
})

test('a container that reads pixels carries an advisory hash like a patch', () => {
  const d = doc([
    develop('d'),
    { id: 'r', class: 'container', enabled: true, label: 'Retouch', exec: { kind: 'retouch' },
      raster_ref: 'payloads/r.png', sampled_input_hash: 'base' },
  ])
  assert.equal(deriveStackState(d).ops[1].staleness, 'advisory')
})

test('a pure paint layer has no sampled hash and never goes advisory', () => {
  const d = doc([
    develop('d'),
    { id: 'p', class: 'container', enabled: true, label: 'Paint', exec: { kind: 'paint' },
      raster_ref: 'payloads/p.png' },
  ])
  assert.equal(deriveStackState(d).ops[1].staleness, 'clean')
})

test('an op sampled against the hash it actually has stays clean under a checkpoint', () => {
  const base = doc([develop('d'), patch('a', 'placeholder')])
  const correct = inputHashAt(base, 1)
  const d = doc([develop('d'), patch('a', correct)])
  assert.equal(deriveStackState(d).ops[1].staleness, 'clean')
})

test('segments are bounded by checkpoints', () => {
  const d = doc([develop('a'), develop('b'), whole('w', null), develop('c')])
  assert.deepEqual(segmentBounds(d, 0), { start: 0, end: 2 })
  assert.deepEqual(segmentBounds(d, 1), { start: 0, end: 2 })
  assert.deepEqual(segmentBounds(d, 3), { start: 3, end: 4 })
})

test('a row may reorder within its segment but not across a checkpoint', () => {
  const d = doc([develop('a'), develop('b'), whole('w', null), develop('c')])
  assert.equal(canMoveWithinSegment(d, 'a', 1), true)
  assert.equal(canMoveWithinSegment(d, 'a', 3), false, 'cannot cross the checkpoint')
  assert.equal(canMoveWithinSegment(d, 'c', 0), false)
})

test('a checkpoint itself never moves', () => {
  const d = doc([develop('a'), whole('w', null)])
  assert.equal(canMoveWithinSegment(d, 'w', 0), false)
})

test('blast radius separates what would go advisory from what would go hard', () => {
  const d = doc([develop('a'), patch('p', 'base'), whole('w', 'base'), patch('q', 'base')])
  const radius = blastRadius(d, 'a')
  assert.deepEqual([...radius.advisory], ['p'])
  assert.deepEqual([...radius.hard].sort(), ['q', 'w'])
})

test('the top row disturbs nothing', () => {
  const d = doc([develop('a'), patch('p', 'base')])
  const radius = blastRadius(d, 'p')
  assert.equal(radius.advisory.size + radius.hard.size, 0)
})

test('a stale checkpoint states the count as a fact', () => {
  const d = doc([develop('d'), whole('w', 'base')])
  const state = deriveStackState(d)
  assert.equal(checkpointStatus(state, 1), 'Showing previous result — 1 edit stale')
})

test('a clean checkpoint has no status line', () => {
  const d = doc([whole('w', 'base')])
  assert.equal(checkpointStatus(deriveStackState(d), 0), null)
})

test('a checkpoint reports how many steps it folds', () => {
  const d = doc([develop('a'), develop('b'), whole('w', null)])
  assert.equal(foldedCount(d, 2), 2)
})

test('rows are attributed to the checkpoint that folds them', () => {
  const d = doc([develop('a'), whole('w', null), develop('b')])
  const state = deriveStackState(d)
  assert.equal(state.ops[0].checkpointIndex, 1)
  assert.equal(state.ops[2].checkpointIndex, null, 'nothing above folds the top row')
})
