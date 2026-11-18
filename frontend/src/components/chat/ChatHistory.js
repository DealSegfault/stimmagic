import { defineComponent } from 'vue'

// A stable slot gives the transcript its own render effect. Typing in the
// composer must not reparse every historical message; transcript dependencies
// (including streamed text and expanded controls) still update normally.
export default defineComponent({
  name: 'ChatHistory',
  setup(_, { slots }) {
    return () => slots.default?.()
  },
})
