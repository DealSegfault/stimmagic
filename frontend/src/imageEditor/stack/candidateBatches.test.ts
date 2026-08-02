import assert from 'node:assert/strict'
import test from 'node:test'

import { groupCandidateBatches } from './candidateBatches.ts'

test('each generation invocation becomes its own candidate row', () => {
  const rows = groupCandidateBatches([
    { id: 'a', batchId: 'run-1' },
    { id: 'b', batchId: 'run-1' },
    { id: 'c', batchId: 'run-2' },
    { id: 'd', batchId: 'run-2' },
  ])

  assert.deepEqual(rows.map(row => row.candidates.map(candidate => candidate.id)), [
    ['a', 'b'],
    ['c', 'd'],
  ])
})

test('pending slots stay with completed candidates from the same invocation', () => {
  const rows = groupCandidateBatches(
    [{ id: 'a', batchId: 'run-1' }],
    [{ batchId: 'run-1', count: 3 }],
  )

  assert.equal(rows.length, 1)
  assert.equal(rows[0].pendingCount, 3)
})

test('legacy candidates remain together and new runs start new rows', () => {
  const rows = groupCandidateBatches([
    { id: 'old-a' },
    { id: 'old-b' },
    { id: 'new-a', batchId: 'run-2' },
  ])

  assert.deepEqual(rows.map(row => row.candidates.map(candidate => candidate.id)), [
    ['old-a', 'old-b'],
    ['new-a'],
  ])
})
