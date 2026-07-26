/**
 * Insert a newline at the caret of a text field, replacing any selection.
 * Returns the field's new value so callers can push it back through v-model.
 * Used by chat composers where plain Enter submits and Shift+Enter breaks the
 * line, so the default newline has to be produced explicitly.
 */
export function insertNewlineAtCaret(el: HTMLTextAreaElement): string {
  const start = el.selectionStart ?? el.value.length
  const end = el.selectionEnd ?? start
  el.setRangeText('\n', start, end, 'end')
  return el.value
}
