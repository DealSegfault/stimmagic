import test from 'node:test'
import assert from 'node:assert/strict'
import { FragileEntryTracker } from './fragileEntries.ts'

test('an untouched entry is cancelled when a sibling replaces it', () => {
  const tracker = new FragileEntryTracker()
  tracker.mark('light')

  assert.equal(tracker.cancel('light'), true)
  assert.equal(tracker.isCancelled('light'), true)
})

test('touching a substantive property makes an entry durable', () => {
  const tracker = new FragileEntryTracker()
  tracker.mark('detail')
  tracker.commit('detail')

  assert.equal(tracker.cancel('detail'), false)
  assert.equal(tracker.isCancelled('detail'), false)
})

test('forget clears cancellation before an id is reused', () => {
  const tracker = new FragileEntryTracker()
  tracker.mark('grade')
  tracker.cancel('grade')
  tracker.forget('grade')
  tracker.mark('grade')

  assert.equal(tracker.isCancelled('grade'), false)
})
