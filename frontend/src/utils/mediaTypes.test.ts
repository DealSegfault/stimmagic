import assert from 'node:assert/strict'
import test from 'node:test'
import { getMediaType, isImage, isLayout, isStructured } from './mediaTypes.ts'

test('HTML documents use layout previews rather than image inputs', () => {
  for (const file_format of ['html', 'htm', 'HTML', 'stimmalayout']) {
    const item = { file_format }
    assert.equal(getMediaType(item), 'layout')
    assert.equal(isLayout(item), true)
    assert.equal(isStructured(item), true)
    assert.equal(isImage(item), false)
  }
  assert.equal(getMediaType({ file_format: 'png' }), 'image')
  assert.equal(getMediaType({ file_format: 'md' }), 'text')
})
