import assert from 'node:assert/strict'
import test from 'node:test'

import { implicitPaintLayer, isRasterPaintLayer } from './paintLayerTarget.ts'
import type { Op } from './types.ts'

function paint(id: string, kind: 'paint' | 'retouch' | 'sketch' = 'paint'): Op {
  return {
    id,
    class: 'container',
    enabled: true,
    label: 'Paint',
    exec: { kind },
    raster_ref: `payloads/${id}.png`,
  } as Op
}

function adjust(id: string): Op {
  return {
    id,
    class: 'parametric',
    enabled: true,
    label: 'Adjust',
    exec: { kind: 'adjust' },
    params: {},
  }
}

test('the selected Paint layer wins even when another Paint layer is on top', () => {
  const edits = [paint('lower'), adjust('middle'), paint('top')]
  assert.equal(implicitPaintLayer(edits, 'lower')?.id, 'lower')
})

test('the top Paint layer is reused when no Paint layer is selected', () => {
  const edits = [adjust('lower'), paint('top')]
  assert.equal(implicitPaintLayer(edits, null)?.id, 'top')
  assert.equal(implicitPaintLayer(edits, 'lower')?.id, 'top')
})

test('a buried unselected Paint layer is not reused', () => {
  const edits = [paint('buried'), adjust('top')]
  assert.equal(implicitPaintLayer(edits, null), null)
  assert.equal(implicitPaintLayer(edits, 'top'), null)
})

test('legacy raster Paint executor names remain selectable', () => {
  assert.equal(isRasterPaintLayer(paint('old-retouch', 'retouch')), true)
  assert.equal(isRasterPaintLayer(paint('old-sketch', 'sketch')), true)
})

test('region Retouch containers are not Paint layers', () => {
  const regions = {
    id: 'regions',
    class: 'container',
    enabled: true,
    label: 'Retouch',
    exec: { kind: 'retouch-regions', version: 1 },
    defaults: {},
    regions: [],
  } as Op
  assert.equal(isRasterPaintLayer(regions), false)
})
