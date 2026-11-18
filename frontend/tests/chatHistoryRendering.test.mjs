import assert from 'node:assert/strict'
import test from 'node:test'
import { compile, createRenderer, defineComponent, nextTick, ref } from 'vue'
import ChatHistory from '../src/components/chat/ChatHistory.js'

// An in-memory Vue host measures render work without a browser or timing noise.
function node(text = '') { return { text, children: [], parent: null } }
const { createApp } = createRenderer({
  createElement: () => node(),
  createText: node,
  createComment: node,
  setText: (el, text) => { el.text = text },
  setElementText: (el, text) => { el.text = text },
  patchProp: () => {},
  insert(el, parent, anchor = null) {
    if (el.parent) el.parent.children.splice(el.parent.children.indexOf(el), 1)
    const index = anchor ? parent.children.indexOf(anchor) : -1
    parent.children.splice(index < 0 ? parent.children.length : index, 0, el)
    el.parent = parent
  },
  remove(el) {
    el.parent.children.splice(el.parent.children.indexOf(el), 1)
    el.parent = null
  },
  parentNode: el => el.parent,
  nextSibling: el => el.parent?.children[el.parent.children.indexOf(el) + 1] || null,
})

test('typing skips history rendering while streaming, expansion and chat changes stay reactive', async () => {
  const draft = ref('')
  const messages = ref(Array.from({ length: 269 }, (_, id) => ({ id, text: `Message ${id}` })))
  const expanded = ref(false)
  let rendered = []
  const app = createApp(defineComponent({
    components: { ChatHistory },
    setup: () => ({ draft, messages, expanded, renderText: text => { rendered.push(text); return text } }),
    // Compile real stable slots, as Vue's SFC compiler does in ChatView.
    render: compile('<main><ChatHistory><section><p v-for="m in messages" :key="m.id">{{ renderText(m.text) }}</p><p v-if="expanded">{{ renderText("details") }}</p></section></ChatHistory><textarea :value="draft" /></main>'),
  }))
  app.mount(node())
  assert.equal(rendered.length, 269)
  rendered = []
  for (const letter of 'Test de saisie sans envoi.') {
    draft.value += letter
    await nextTick()
  }
  assert.deepEqual(rendered, [], 'typing must not rerender existing messages')

  messages.value[0].text = 'Streamed update'
  await nextTick()
  assert.ok(rendered.includes('Streamed update'))
  rendered = []
  expanded.value = true
  await nextTick()
  assert.ok(rendered.includes('details'))
  rendered = []
  messages.value = [{ id: 1000, text: 'Other chat' }]
  await nextTick()
  assert.deepEqual(rendered, ['Other chat', 'details'])
  app.unmount()
})
