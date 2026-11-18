import assert from 'node:assert/strict'
import test from 'node:test'
import { formatH3References, parseH3References, parseH3ExampleHref, splitChatMarkdown } from '../src/utils/h3Examples.ts'

test('style selections round-trip separately from scene text and physical media inputs', () => {
  const refs = [{ id: '000128', label: 'Noir 35 mm · Mafia' }, { id: '000123', label: 'Club enfumé' }]
  const header = formatH3References(refs)
  assert.deepEqual(parseH3References(`${header}\n\nGarde nos personnages.`), { refs, text: 'Garde nos personnages.' })
  assert.equal(parseH3References(header).text, '')
  assert.match(header, /not media inputs/)
  assert.doesNotMatch(header, /<Picture|input_images|media_id/)
  assert.deepEqual(parseH3References('Une scène ordinaire.'), { refs: [], text: 'Une scène ordinaire.' })
  assert.equal(parseH3ExampleHref('stimma-h3:000128'), '000128')
  assert.equal(parseH3ExampleHref('stimma-h3:000128?script=bad'), null)
  assert.equal(parseH3ExampleHref('stimma-h3:../../data'), null)
})

test('inline examples and library media retain their order with escaped labels', () => {
  const label = 'Noir & blanc <35mm>'
  const marker = `<button type="button" data-stimma-h3="000128" data-h3-label="${encodeURIComponent(label)}">Noir &amp; blanc &lt;35mm&gt;</button>`
  assert.deepEqual(splitChatMarkdown(`<p>Essaie ${marker} ici.</p><!--STIMMA_MEDIA:42--><p>Fin</p>`), [
    { type: 'html', content: '<p>Essaie ' }, { type: 'h3-example', id: '000128', label },
    { type: 'html', content: ' ici.</p>' }, { type: 'media', mediaId: 42 }, { type: 'html', content: '<p>Fin</p>' },
  ])
  assert.deepEqual(splitChatMarkdown(''), [{ type: 'html', content: '' }])
  assert.deepEqual(splitChatMarkdown('<button data-stimma-h3="000128" data-h3-label="%bad">Noir</button>'), [
    { type: 'h3-example', id: '000128', label: '%bad' },
  ])
  const incomplete = '> **Style inspiration (H3 examples):**\n> - [Noir](stimma-h3:000128)\nMy own text'
  assert.equal(parseH3References(incomplete).text, incomplete)
})
