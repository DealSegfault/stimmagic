/**
 * The Edits list's layout law, in one place so every row obeys the same one.
 *
 * The square preview is each row's anchor. Its size is fixed and its position
 * is the first thing after the grip column, so the list reads as a single
 * column of images down the panel — that column IS the structure of the list.
 *
 * Everything beside the square centers ON the square, by giving each column
 * the square's height as a floor and centering within it:
 *   - one line of text  → centered against the square
 *   - a title + subtitle (20px + 16px = the square's 36px) → the pair spans
 *     the square exactly, top to bottom
 *   - anything taller (a candidate strip) → the floor stops mattering and the
 *     content grows downward from the top, square still at the row's top
 * One rule, no per-row special cases — which is why a first-line offset was
 * wrong: it centered the title and let a subtitle hang below, so a two-line
 * row read as sitting low against its square.
 */

/** The anchor. Change this and ROW_COLUMN's min-height must change with it. */
export const ROW_SQUARE = 'w-9 h-9 shrink-0 rounded-media overflow-hidden bg-matte'

/** Any column beside the square: text block, control cluster, grip. */
export const ROW_COLUMN = 'min-h-9 flex flex-col justify-center'

/** Same rule for columns laid out in a row (controls, grip). */
export const ROW_COLUMN_INLINE = 'min-h-9 flex items-center'

/**
 * Where a dragged row would land: an accent hairline sitting IN the gap.
 *
 * Negative margins let it overlay the 2px of breathing room between rows
 * instead of adding height — the list must not reflow as the line moves from
 * gap to gap, or the row under the cursor shifts out from under it.
 */
export const DROP_LINE =
  'h-0.5 -my-px mx-1 rounded-full bg-accent shadow-[0_0_6px] shadow-accent/50 pointer-events-none'
