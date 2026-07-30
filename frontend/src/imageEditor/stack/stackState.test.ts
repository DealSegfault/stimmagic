import assert from 'node:assert/strict'
import test from 'node:test'

import {
  blastRadius,
  deriveStackState,
  moveTargetForGap,
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

function adjust(id: string, params: any = { brightness: 5 }, enabled = true) {
  return { id, class: 'parametric', enabled, label: id, exec: { kind: 'adjust' }, params }
}

/** The hash an op at `index` will be compared against. */
function inputHashAt(document: StackDocument, index: number) {
  return stackHashes(document).inputs[index]
}

test('an op sampled against its current input is clean', () => {
  const d = doc([patch('a', 'base')])
  assert.equal(deriveStackState(d).ops[0].staleness, 'clean')
})

test('a patch whose input moved is advisory', () => {
  const d = doc([adjust('d'), patch('a', 'base')])
  // The patch was sampled against the bare base, but now sits above an adjust.
  const state = deriveStackState(d)
  assert.equal(state.ops[1].staleness, 'advisory')
})

test('advisory is the only severity there is', () => {
  // Everything that can be stale is stale here, and none of it escalates:
  // nothing in the stack can stop being derivable from its input.
  const d = doc([adjust('d'), patch('a', 'base'), adjust('e'), patch('p', 'anything')])
  const state = deriveStackState(d)
  assert.deepEqual(
    state.ops.map(o => o.staleness),
    ['clean', 'advisory', 'clean', 'advisory']
  )
})

test('a disabled op is never stale — it contributes nothing to compare', () => {
  const d = doc([adjust('d'), patch('a', 'base', false)])
  assert.equal(deriveStackState(d).ops[1].staleness, 'clean')
})

test('a staged op with no pick has nothing to be stale against', () => {
  const d = doc([adjust('d'), patch('a', null)])
  assert.equal(deriveStackState(d).ops[1].staleness, 'clean')
})

test('a parametric op is never stale — it is deterministic in its params', () => {
  const d = doc([patch('a', 'base'), adjust('d')])
  assert.equal(deriveStackState(d).ops[1].staleness, 'clean')
})

test('a container that reads pixels carries an advisory hash like a patch', () => {
  const d = doc([
    adjust('d'),
    { id: 'r', class: 'container', enabled: true, label: 'Paint', exec: { kind: 'paint' },
      raster_ref: 'payloads/r.png', sampled_input_hash: 'base' },
  ])
  assert.equal(deriveStackState(d).ops[1].staleness, 'advisory')
})

test('a pure paint layer has no sampled hash and never goes advisory', () => {
  const d = doc([
    adjust('d'),
    { id: 'p', class: 'container', enabled: true, label: 'Paint', exec: { kind: 'paint' },
      raster_ref: 'payloads/p.png' },
  ])
  assert.equal(deriveStackState(d).ops[1].staleness, 'clean')
})

test('retouch region children participate in their container pixel identity', () => {
  const base = {
    id: 'repair',
    class: 'container',
    enabled: true,
    label: 'Retouch',
    exec: { kind: 'retouch-regions', version: 1 },
    defaults: {},
    regions: [{ id: 'spot', kind: 'heal', enabled: true, mask_ref: 'payloads/mask.png', settings: {} }],
  }
  const before = stackHashes(doc([base as any])).head
  const after = stackHashes(doc([{
    ...base,
    regions: [{ ...base.regions[0], settings: { exposure: 10 } }],
  } as any])).head

  assert.notEqual(before, after)
})

test('a masked adjustment is parametric and never carries sampling staleness', () => {
  const d = doc([
    adjust('under'),
    {
      id: 'local',
      class: 'container',
      enabled: true,
      label: 'Retouch',
      exec: { kind: 'retouch-regions', version: 1 },
      defaults: {},
      regions: [{
        id: 'mask',
        kind: 'adjust',
        enabled: true,
        mask_ref: 'payloads/mask.png',
        settings: { exposure: 20, opacity: 1, feather_px: 4 },
      }],
    } as any,
  ])

  assert.equal(deriveStackState(d).ops[1].staleness, 'clean')
})

test('an op sampled against the hash it actually has stays clean', () => {
  const base = doc([adjust('d'), patch('a', 'placeholder')])
  const correct = inputHashAt(base, 1)
  const d = doc([adjust('d'), patch('a', correct)])
  assert.equal(deriveStackState(d).ops[1].staleness, 'clean')
})

test('blast radius is every generative row above the gesture', () => {
  const d = doc([adjust('a'), patch('p', 'base'), adjust('b'), patch('q', 'base')])
  const radius = blastRadius(d, 'a')
  assert.deepEqual([...radius.advisory].sort(), ['p', 'q'])
})

test('the top row disturbs nothing', () => {
  const d = doc([adjust('a'), patch('p', 'base')])
  assert.equal(blastRadius(d, 'p').advisory.size, 0)
})

// -- drop gaps --------------------------------------------------------------
//
// A gap `g` is the boundary before edits[g]. The list draws top-of-stack
// first, so the gap ABOVE visible row i is g = i + 1.

test('dropping into a gap above the row lands it there', () => {
  // [a, b, c] draws as c, b, a. Dragging a to the gap above b (g = 2) puts it
  // between b and c.
  const d = doc([adjust('a'), adjust('b'), adjust('c')])
  const to = moveTargetForGap(d, 'a', 2)
  assert.equal(to, 1)
  const [op] = d.edits.splice(0, 1)
  d.edits.splice(to as number, 0, op)
  assert.deepEqual(d.edits.map(o => o.id), ['b', 'a', 'c'])
})

test('dropping into a gap below the row lands it there', () => {
  // Dragging c (index 2) to the bottom of the list (g = 0).
  const d = doc([adjust('a'), adjust('b'), adjust('c')])
  const to = moveTargetForGap(d, 'c', 0)
  assert.equal(to, 0)
  const [op] = d.edits.splice(2, 1)
  d.edits.splice(to as number, 0, op)
  assert.deepEqual(d.edits.map(o => o.id), ['c', 'a', 'b'])
})

test('dropping to the top of the stack lands on top', () => {
  const d = doc([adjust('a'), adjust('b'), adjust('c')])
  const to = moveTargetForGap(d, 'a', 3)
  assert.equal(to, 2)
  const [op] = d.edits.splice(0, 1)
  d.edits.splice(to as number, 0, op)
  assert.deepEqual(d.edits.map(o => o.id), ['b', 'c', 'a'])
})

test('the two gaps touching a row are no-ops, not moves', () => {
  const d = doc([adjust('a'), adjust('b'), adjust('c')])
  assert.equal(moveTargetForGap(d, 'b', 1), null)
  assert.equal(moveTargetForGap(d, 'b', 2), null)
})

test('every other gap is legal — no row pins order any more', () => {
  // The generative row used to be a fence its neighbours could not cross.
  const d = doc([adjust('a'), patch('p', 'base'), adjust('b')])
  assert.equal(moveTargetForGap(d, 'b', 0), 0, 'b may pass under the patch')
  assert.equal(moveTargetForGap(d, 'a', 3), 2, 'a may pass over it')
  assert.equal(moveTargetForGap(d, 'p', 0), 0, 'the patch itself moves too')
})

test('a gap outside the list is not a landing place', () => {
  const d = doc([adjust('a'), adjust('b')])
  assert.equal(moveTargetForGap(d, 'a', -1), null)
  assert.equal(moveTargetForGap(d, 'a', 5), null)
})
