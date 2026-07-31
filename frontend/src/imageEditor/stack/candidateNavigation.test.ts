import assert from 'node:assert/strict'
import test from 'node:test'

import {
  adjacentCandidateIndex,
  candidateNavigationDelta,
} from './candidateNavigation.ts'

test('candidate keyboard movement advances in either direction', () => {
  assert.equal(adjacentCandidateIndex(4, 1, 1), 2)
  assert.equal(adjacentCandidateIndex(4, 2, -1), 1)
})

test('candidate keyboard movement stops at the strip edges', () => {
  assert.equal(adjacentCandidateIndex(4, 0, -1), 0)
  assert.equal(adjacentCandidateIndex(4, 3, 1), 3)
})

test('candidate keyboard movement accepts arrows and A/D regardless of case', () => {
  assert.equal(candidateNavigationDelta('ArrowLeft'), -1)
  assert.equal(candidateNavigationDelta('ArrowRight'), 1)
  assert.equal(candidateNavigationDelta('a'), -1)
  assert.equal(candidateNavigationDelta('D'), 1)
  assert.equal(candidateNavigationDelta('Enter'), null)
})
