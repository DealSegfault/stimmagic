/**
 * The old model put ONE gradient on the shape and let the renderer decide which
 * slot it landed in. These pin that decision down, because it is the only thing
 * standing between an old document and a shape that silently loses its color.
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { migrateShapePaint, migrateShapePaints, needsPaintMigration } from './migrateShapePaints.ts'
import { isGradient } from './paints.ts'

const RED = { r: 255, g: 0, b: 0, a: 1 }
const BLUE = { r: 0, g: 0, b: 255, a: 1 }

function legacyRect(extra: Record<string, any> = {}) {
  return {
    id: 'r1', type: 'rectangle', x: 0, y: 0, rotation: 0, opacity: 1,
    width: 0.5, height: 0.5,
    strokeColor: RED, strokeWidth: 8,
    style: { effect: 'gradient', gradientColors: [RED, BLUE], gradientDirection: 'vertical' },
    ...extra,
  } as any
}

test('a filled shape kept its gradient on the fill', () => {
  const shape = migrateShapePaint(legacyRect({ backgroundColor: BLUE }))
  assert.ok(isGradient(shape.backgroundColor))
  assert.equal((shape.backgroundColor as any).direction, 'vertical')
  assert.deepEqual(shape.strokeColor, RED, 'the stroke stays the flat color it was')
})

test('an unfilled shape kept its gradient on the stroke', () => {
  const shape = migrateShapePaint(legacyRect())
  assert.ok(isGradient(shape.strokeColor))
  assert.deepEqual((shape.strokeColor as any).colors, [RED, BLUE])
})

test('the effect is spent — a migrated shape is no longer "in gradient mode"', () => {
  const shape: any = migrateShapePaint(legacyRect())
  assert.notEqual(shape.style?.effect, 'gradient')
  assert.equal(shape.gradientColors, undefined)
  assert.equal(shape.gradientDirection, undefined)
})

test('neon survives alongside, because it was always a different thing', () => {
  const shape: any = migrateShapePaint(legacyRect({
    style: { effect: 'neon', glowIntensity: 80 },
  }))
  assert.equal(shape.style.effect, 'neon')
  assert.equal(shape.style.glowIntensity, 80)
  assert.deepEqual(shape.strokeColor, RED)
})

test('text gradients were CSS strings and become the text color', () => {
  const shape: any = migrateShapePaint({
    id: 't1', type: 'text', x: 0, y: 0, rotation: 0, opacity: 1,
    text: 'hi', width: 0.2, height: 0.1, baseWidth: 0.2, baseHeight: 0.1,
    fontFamily: 'Inter', fontWeight: 'normal', fontStyle: 'normal', textAlign: 'center',
    textColor: { r: 255, g: 255, b: 255, a: 1 },
    textEffect: 'gradient',
    gradientColors: ['#ff0000', '#0000ff'],
    gradientDirection: 'diagonal',
  } as any)

  assert.ok(isGradient(shape.textColor))
  assert.deepEqual((shape.textColor as any).colors, [RED, BLUE])
  assert.equal((shape.textColor as any).direction, 'diagonal')
  assert.notEqual(shape.textEffect, 'gradient')
})

test('running it twice changes nothing the second time', () => {
  const once = migrateShapePaints([legacyRect()])
  const twice = migrateShapePaints(once)
  assert.deepEqual(twice, once)
})

test('a shape already speaking paints is left alone', () => {
  const modern = {
    id: 'r2', type: 'rectangle', x: 0, y: 0, rotation: 0, opacity: 1,
    width: 0.5, height: 0.5, strokeWidth: 8,
    strokeColor: { type: 'gradient', colors: [RED, BLUE], direction: 'horizontal' },
  } as any
  assert.equal(needsPaintMigration(modern), false)
  assert.deepEqual(migrateShapePaint(modern), modern)
})

test('a gradient with one usable stop falls back to the color that was there', () => {
  const shape = migrateShapePaint(legacyRect({
    style: { effect: 'gradient', gradientColors: [RED] },
  }))
  assert.deepEqual(shape.strokeColor, RED)
})
