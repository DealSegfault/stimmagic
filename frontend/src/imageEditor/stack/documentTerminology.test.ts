import assert from 'node:assert/strict'
import test from 'node:test'

import {
  normalizeDocumentTerminology,
  normalizeJournalTerminology,
} from './documentTerminology.ts'

test('legacy raster Retouch rows become Paint without rewriting executor identity', () => {
  const document = {
    edits: [
      {
        id: 'legacy-read',
        class: 'container',
        label: 'Retouch',
        exec: { kind: 'retouch' },
        raster_ref: 'payloads/read.png',
      },
      {
        id: 'legacy-color',
        class: 'container',
        label: 'Retouch',
        exec: { kind: 'paint' },
        raster_ref: 'payloads/color.png',
      },
    ],
  }

  normalizeDocumentTerminology(document)

  assert.deepEqual(
    document.edits.map(op => [op.label, op.exec.kind]),
    [['Paint', 'retouch'], ['Paint', 'paint']],
  )
})

test('custom labels and region-based Retouch containers are untouched', () => {
  const document = {
    edits: [
      {
        id: 'custom',
        class: 'container',
        label: 'Skin cleanup',
        exec: { kind: 'retouch' },
        raster_ref: 'payloads/custom.png',
      },
      {
        id: 'regions',
        class: 'container',
        label: 'Retouch',
        exec: { kind: 'retouch-regions' },
        regions: [],
      },
    ],
  }

  normalizeDocumentTerminology(document)

  assert.equal(document.edits[0].label, 'Skin cleanup')
  assert.equal(document.edits[1].label, 'Retouch')
})

test('journal op copies normalize so undo cannot restore the retired label', () => {
  const entries = [{
    seq: 1,
    action: 'remove_op',
    inverse: {
      op: {
        id: 'legacy',
        class: 'container',
        label: 'Retouch',
        exec: { kind: 'paint' },
        raster_ref: 'payloads/legacy.png',
      },
    },
  }]

  normalizeJournalTerminology(entries)

  assert.equal(entries[0].inverse.op.label, 'Paint')
})

test('legacy Erase patches become Remove without rewriting the STP task', () => {
  const document = {
    edits: [{
      id: 'legacy-remove',
      class: 'patch',
      label: 'Erase',
      operation: 'erase',
      exec: { kind: 'tool', task_type: 'erase-image' },
    }],
  }

  normalizeDocumentTerminology(document)

  assert.equal(document.edits[0].label, 'Remove')
  assert.equal(document.edits[0].operation, 'remove')
  assert.equal(document.edits[0].exec.task_type, 'erase-image')
})
