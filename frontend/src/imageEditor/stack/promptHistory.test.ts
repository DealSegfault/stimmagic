import assert from 'node:assert/strict'
import test from 'node:test'

import { addRecentPrompt } from './promptHistory.ts'

test('recent prompts are newest-first, trimmed, and deduplicated', () => {
  assert.deepEqual(
    addRecentPrompt(['Keep this', 'Remove the hat'], '  remove the hat  '),
    ['remove the hat', 'Keep this'],
  )
})

test('blank drafts do not enter recent prompts', () => {
  assert.deepEqual(addRecentPrompt(['Keep this'], '   '), ['Keep this'])
})

test('recent prompts stay bounded', () => {
  assert.deepEqual(
    addRecentPrompt(['two', 'three'], 'one', 2),
    ['one', 'two'],
  )
})
