import assert from 'node:assert/strict'
import test from 'node:test'

import {
  CHIP_GAP_PX,
  CHIP_PX,
  orderByRecency,
  orderForDisplay,
  rankShelfEntries,
  shelfColumns,
  splitShelf,
  type ShelfEntry,
} from './editorShelf.ts'

let seq = 0
function entry(tabId: string, over: Partial<ShelfEntry> = {}): ShelfEntry {
  return {
    tabId,
    assetId: tabId,
    displayName: 'Edit',
    pinned: false,
    unsaved: false,
    touchedAt: 0,
    createdOrder: seq++,
    ...over,
  }
}

test('columns come from measured width, never below one', () => {
  assert.equal(shelfColumns(CHIP_PX), 1)
  assert.equal(shelfColumns(CHIP_PX * 2 + CHIP_GAP_PX), 2)
  assert.equal(shelfColumns(CHIP_PX * 4 + CHIP_GAP_PX * 3), 4)
  // A hair short of the next chip does not gain a column.
  assert.equal(shelfColumns(CHIP_PX * 5 + CHIP_GAP_PX * 4 - 1), 4)
  // Pre-measurement and degenerate widths still render one chip per row.
  assert.equal(shelfColumns(0), 1)
  assert.equal(shelfColumns(Number.NaN), 1)
})

test('pinned lead, then unsaved, then most recently touched', () => {
  const ranked = rankShelfEntries([
    entry('cold', { touchedAt: 10 }),
    entry('hot', { touchedAt: 90 }),
    entry('half-done', { unsaved: true, touchedAt: 20 }),
    entry('kept', { pinned: true, touchedAt: 1 }),
  ])
  assert.deepEqual(ranked.map(e => e.tabId), ['kept', 'half-done', 'hot', 'cold'])
})

test('an unsaved edit is not pushed behind +N by newer opens', () => {
  const entries = [entry('half-done', { unsaved: true, touchedAt: 0 })]
  for (let i = 1; i <= 12; i++) entries.push(entry(`open-${i}`, { touchedAt: i * 100 }))
  const { visible, overflow } = splitShelf(rankShelfEntries(entries), 8)
  assert.equal(visible[0].tabId, 'half-done')
  assert.ok(!overflow.some(e => e.unsaved))
})

test('overflow starts only above capacity, and the door costs a slot', () => {
  const eight = Array.from({ length: 8 }, (_, i) => entry(`t${i}`))
  const exact = splitShelf(eight, 8)
  assert.equal(exact.visible.length, 8)
  assert.equal(exact.overflow.length, 0)

  const nine = splitShelf([...eight, entry('t8')], 8)
  assert.equal(nine.visible.length, 7)
  assert.equal(nine.overflow.length, 2)
})

test('pinned chips never fall behind the +N chip', () => {
  const entries = [
    ...Array.from({ length: 9 }, (_, i) => entry(`pin${i}`, { pinned: true, touchedAt: i })),
    ...Array.from({ length: 5 }, (_, i) => entry(`auto${i}`, { touchedAt: 100 + i })),
  ]
  const { visible, overflow } = splitShelf(rankShelfEntries(entries), 8)
  assert.equal(visible.filter(e => e.pinned).length, 9)
  assert.ok(overflow.every(e => !e.pinned))
})

test('display order ignores activation, so clicking a chip never moves it', () => {
  const entries = [
    entry('first', { createdOrder: 1, touchedAt: 10 }),
    entry('second', { createdOrder: 2, touchedAt: 20 }),
    entry('third', { createdOrder: 3, touchedAt: 30 }),
  ]
  const before = orderForDisplay(entries).map(e => e.tabId)
  assert.deepEqual(before, ['third', 'second', 'first'])

  // Activate the oldest chip: its rank jumps to the top...
  entries[0].touchedAt = 99
  assert.equal(rankShelfEntries(entries)[0].tabId, 'first')
  // ...and its position does not move.
  assert.deepEqual(orderForDisplay(entries).map(e => e.tabId), before)

  // Nor does going dirty move it, though it now outranks the others.
  entries[2].unsaved = true
  assert.deepEqual(orderForDisplay(entries).map(e => e.tabId), before)
})

test('pinning is the one interaction that moves a chip', () => {
  const entries = [
    entry('a', { createdOrder: 1 }),
    entry('b', { createdOrder: 2 }),
    entry('c', { createdOrder: 3, pinned: true }),
  ]
  assert.deepEqual(orderForDisplay(entries).map(e => e.tabId), ['c', 'b', 'a'])
})

test('a newly opened editor enters at the front of the unpinned shelf', () => {
  const entries = [
    entry('oldest', { createdOrder: 1 }),
    entry('middle', { createdOrder: 2 }),
  ]

  assert.deepEqual(orderForDisplay(entries).map(e => e.tabId), ['middle', 'oldest'])

  entries.push(entry('newest', { createdOrder: 3 }))
  assert.deepEqual(
    orderForDisplay(entries).map(e => e.tabId),
    ['newest', 'middle', 'oldest'],
  )
})

test('the flyout is plain recency order, newest first', () => {
  const ordered = orderByRecency([
    entry('stale', { touchedAt: 10 }),
    entry('newest', { touchedAt: 900 }),
    entry('middle', { touchedAt: 400 }),
  ])
  assert.deepEqual(ordered.map(e => e.tabId), ['newest', 'middle', 'stale'])
})

test('flyout order ignores pinned and unsaved — only time', () => {
  const ordered = orderByRecency([
    entry('pinned-old', { pinned: true, touchedAt: 1 }),
    entry('dirty-old', { unsaved: true, touchedAt: 2 }),
    entry('clean-new', { touchedAt: 3 }),
  ])
  assert.deepEqual(ordered.map(e => e.tabId), ['clean-new', 'dirty-old', 'pinned-old'])
})
