/**
 * Stable op identity.
 *
 * Ops are addressed by id everywhere — UI, undo, the journal, and any future
 * agent tooling — and never by index, because a step must keep its name across
 * reordering. Monotonic and sortable (a ULID in shape), which also makes a
 * document's edit list readable in creation order when that is useful for
 * debugging, without the document ever depending on it.
 *
 * Dependency-free on purpose: the migrator mints ids and must stay testable
 * without dragging in the whole document composable.
 */

const B32 = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'

export function newOpId(): string {
  let time = Date.now()
  let out = ''
  for (let i = 0; i < 10; i++) {
    out = B32[time % 32] + out
    time = Math.floor(time / 32)
  }
  for (let i = 0; i < 16; i++) {
    out += B32[Math.floor(Math.random() * 32)]
  }
  return out
}
