/**
 * The stack document: state, journal-cursor undo, and server persistence.
 *
 * Undo is a cursor into an append-only journal, not a stack of snapshots.
 * Every document edit (add, remove, reorder, toggle, param change, pick change)
 * is one journal entry carrying both directions. Undoing walks the cursor back
 * and applies inverses; it never truncates the log and never deletes a received
 * payload — undoing a pick just un-picks, and the candidates remain.
 *
 * Redo is linear: a new edit after undo starts a new run. The entries it
 * abandons stay in the journal (recorded as such) so any prior state is still
 * recoverable by replay, which is the whole point of the pack-rat rule.
 */

import { ref, computed, shallowRef } from 'vue'
import axios from 'axios'
import type { JournalEntry, Op, StackDocument } from './types'
import { DOCUMENT_FORMAT, DOCUMENT_VERSION } from './types'

const API_BASE = '/api'

/** Debounce for document.json writes. Slider drags must not thrash the disk. */
const PERSIST_DEBOUNCE_MS = 400

/**
 * Monotonic, sortable, collision-resistant enough for a single-writer document.
 * Crockford base32 of the timestamp plus randomness, i.e. a ULID in shape.
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

export interface StackEditOptions {
  /** Coalesce with the previous entry when it shares this key (slider drags). */
  coalesceKey?: string
}

export function useStackDocument() {
  const documentId = ref<number | null>(null)
  const doc = ref<StackDocument | null>(null)
  const journal = shallowRef<JournalEntry[]>([])
  /** Entries at index >= cursor are undone. */
  const cursor = ref(0)
  const saving = ref(false)
  const loadError = ref<string | null>(null)
  /** Set on every document edit, cleared by a successful Save. */
  const dirtySinceSave = ref(false)

  let nextSeq = 1
  let persistTimer: ReturnType<typeof setTimeout> | null = null
  let pendingJournal: JournalEntry[] = []

  const ops = computed<Op[]>(() => doc.value?.edits || [])
  const canUndo = computed(() => cursor.value > 0)
  const canRedo = computed(() => cursor.value < journal.value.length)

  function opById(id: string): Op | undefined {
    return doc.value?.edits.find(o => o.id === id)
  }

  // -- persistence ---------------------------------------------------------

  async function open(assetId: number, revisionId?: number) {
    loadError.value = null
    const { data } = await axios.post(`${API_BASE}/image-stack/open`, {
      asset_id: assetId,
      revision_id: revisionId ?? null,
    })
    documentId.value = data.document_id

    if (data.document) {
      doc.value = data.document
    } else {
      doc.value = {
        format: DOCUMENT_FORMAT,
        version: DOCUMENT_VERSION,
        base: {
          asset_id: data.base.asset_id,
          revision_id: data.base.revision_id,
          media_id: data.base.media_id,
          file_hash: data.base.file_hash,
          width: data.base.width,
          height: data.base.height,
        },
        canvas: { width: data.base.width, height: data.base.height },
        edits: [],
      }
    }

    // The journal's replayable suffix. The cursor starts at the end: the
    // document on disk already reflects every entry.
    const journalResponse = await axios.get(
      `${API_BASE}/image-stack/${data.document_id}/journal`
    )
    journal.value = journalResponse.data.entries || []
    cursor.value = journal.value.length
    nextSeq = journal.value.reduce((max, e) => Math.max(max, e.seq || 0), 0) + 1
    dirtySinceSave.value = false

    return {
      documentId: data.document_id,
      base: data.base,
      headRevisionId: data.head_revision_id,
      legacyProject: data.legacy_project,
    }
  }

  function schedulePersist() {
    if (persistTimer) clearTimeout(persistTimer)
    persistTimer = setTimeout(() => { void flush() }, PERSIST_DEBOUNCE_MS)
  }

  /** Write document.json and drain queued journal entries. */
  async function flush() {
    if (persistTimer) { clearTimeout(persistTimer); persistTimer = null }
    if (!documentId.value || !doc.value) return
    const id = documentId.value
    const entries = pendingJournal
    pendingJournal = []
    saving.value = true
    try {
      if (entries.length) {
        await axios.post(`${API_BASE}/image-stack/${id}/journal`, { entries })
      }
      await axios.put(`${API_BASE}/image-stack/${id}/document`, {
        document: JSON.parse(JSON.stringify(doc.value)),
      })
    } catch (err) {
      // Re-queue so the next flush retries rather than dropping history.
      pendingJournal = [...entries, ...pendingJournal]
      console.error('[imageStack] persist failed', err)
      throw err
    } finally {
      saving.value = false
    }
  }

  // -- edits ---------------------------------------------------------------

  /**
   * Record one document edit. `apply` mutates the document; `inverse` describes
   * how to undo it. Both are plain data so the journal stays replayable.
   */
  function record(
    action: string,
    forward: any,
    inverse: any,
    apply: () => void,
    options: StackEditOptions = {}
  ) {
    apply()

    // Anything undone is abandoned by this new edit. The entries are not
    // removed — the journal only ever appends — but they stop being reachable
    // by redo.
    if (cursor.value < journal.value.length) {
      journal.value = journal.value.slice(0, cursor.value)
    }

    const previous = journal.value[journal.value.length - 1]
    if (
      options.coalesceKey &&
      previous &&
      previous.action === action &&
      (previous as any)._coalesceKey === options.coalesceKey
    ) {
      // A slider drag is one undo step: keep the original inverse (the value
      // before the drag started) and move the forward value along.
      previous.forward = forward
      pendingJournal = pendingJournal.filter(e => e.seq !== previous.seq)
      pendingJournal.push(previous)
    } else {
      const entry: JournalEntry & { _coalesceKey?: string } = {
        seq: nextSeq++,
        action,
        forward,
        inverse,
      }
      if (options.coalesceKey) entry._coalesceKey = options.coalesceKey
      journal.value = [...journal.value, entry]
      pendingJournal.push(entry)
    }

    cursor.value = journal.value.length
    dirtySinceSave.value = true
    schedulePersist()
  }

  function addOp(op: Op, index?: number) {
    const at = index ?? (doc.value?.edits.length || 0)
    record(
      'add_op',
      { op, index: at },
      { op_id: op.id },
      () => { doc.value!.edits.splice(at, 0, op) }
    )
  }

  function removeOp(opId: string) {
    const index = doc.value!.edits.findIndex(o => o.id === opId)
    if (index < 0) return
    const op = doc.value!.edits[index]
    record(
      'remove_op',
      { op_id: opId },
      // The whole op rides in the inverse: its payload files stay on disk, so
      // restoring it is a document-only operation.
      { op, index },
      () => { doc.value!.edits.splice(index, 1) }
    )
  }

  function moveOp(opId: string, toIndex: number) {
    const from = doc.value!.edits.findIndex(o => o.id === opId)
    if (from < 0 || from === toIndex) return
    record(
      'move_op',
      { op_id: opId, from, to: toIndex },
      { op_id: opId, from: toIndex, to: from },
      () => {
        const [op] = doc.value!.edits.splice(from, 1)
        doc.value!.edits.splice(toIndex, 0, op)
      }
    )
  }

  function setEnabled(opId: string, enabled: boolean) {
    const op = opById(opId)
    if (!op || op.enabled === enabled) return
    const was = op.enabled
    record(
      'toggle_op',
      { op_id: opId, enabled },
      { op_id: opId, enabled: was },
      () => { op.enabled = enabled }
    )
  }

  function setParams(opId: string, params: Record<string, any>, coalesceKey?: string) {
    const op = opById(opId) as any
    if (!op) return
    const was = JSON.parse(JSON.stringify(op.params || {}))
    record(
      'set_params',
      { op_id: opId, params },
      { op_id: opId, params: was },
      () => { op.params = { ...(op.params || {}), ...params } },
      { coalesceKey }
    )
  }

  function setLabel(opId: string, label: string) {
    const op = opById(opId)
    if (!op || op.label === label) return
    const was = op.label
    record(
      'set_label',
      { op_id: opId, label },
      { op_id: opId, label: was },
      () => { op.label = label }
    )
  }

  function pickCandidate(opId: string, candidateId: string | null) {
    const op = opById(opId) as any
    if (!op || op.picked === candidateId) return
    const was = op.picked ?? null
    record(
      'pick_candidate',
      { op_id: opId, candidate_id: candidateId },
      { op_id: opId, candidate_id: was },
      () => { op.picked = candidateId }
    )
  }

  /**
   * Attach staged candidates as they arrive. Not an undoable document edit:
   * a job completing is not something the user did, and undoing it would
   * throw away work that was paid for.
   */
  function attachCandidates(opId: string, candidates: any[]) {
    const op = opById(opId) as any
    if (!op) return
    const known = new Set((op.candidates || []).map((c: any) => c.id))
    op.candidates = [...(op.candidates || []), ...candidates.filter(c => !known.has(c.id))]
    schedulePersist()
  }

  function setBlend(opId: string, blend: Partial<{ feather_px: number; opacity: number }>, coalesceKey?: string) {
    const op = opById(opId) as any
    if (!op) return
    const was = { ...(op.blend || { feather_px: 6, opacity: 1 }) }
    record(
      'set_blend',
      { op_id: opId, blend },
      { op_id: opId, blend: was },
      () => { op.blend = { ...was, ...blend } },
      { coalesceKey }
    )
  }

  // -- undo / redo ---------------------------------------------------------

  function applyInverse(entry: JournalEntry) {
    const d = doc.value!
    const inv = entry.inverse || {}
    switch (entry.action) {
      case 'add_op':
        d.edits = d.edits.filter(o => o.id !== inv.op_id)
        break
      case 'remove_op':
        d.edits.splice(Math.min(inv.index, d.edits.length), 0, inv.op)
        break
      case 'move_op': {
        const from = d.edits.findIndex(o => o.id === inv.op_id)
        if (from >= 0) {
          const [op] = d.edits.splice(from, 1)
          d.edits.splice(inv.to, 0, op)
        }
        break
      }
      case 'toggle_op': {
        const op = d.edits.find(o => o.id === inv.op_id)
        if (op) op.enabled = inv.enabled
        break
      }
      case 'set_params': {
        const op = d.edits.find(o => o.id === inv.op_id) as any
        if (op) op.params = inv.params
        break
      }
      case 'set_label': {
        const op = d.edits.find(o => o.id === inv.op_id)
        if (op) op.label = inv.label
        break
      }
      case 'pick_candidate': {
        const op = d.edits.find(o => o.id === inv.op_id) as any
        // Un-picking only; the candidates themselves are never touched.
        if (op) op.picked = inv.candidate_id
        break
      }
      case 'set_blend': {
        const op = d.edits.find(o => o.id === inv.op_id) as any
        if (op) op.blend = inv.blend
        break
      }
    }
  }

  function applyForward(entry: JournalEntry) {
    const d = doc.value!
    const fwd = entry.forward || {}
    switch (entry.action) {
      case 'add_op':
        d.edits.splice(Math.min(fwd.index, d.edits.length), 0, fwd.op)
        break
      case 'remove_op':
        d.edits = d.edits.filter(o => o.id !== fwd.op_id)
        break
      case 'move_op': {
        const from = d.edits.findIndex(o => o.id === fwd.op_id)
        if (from >= 0) {
          const [op] = d.edits.splice(from, 1)
          d.edits.splice(fwd.to, 0, op)
        }
        break
      }
      case 'toggle_op': {
        const op = d.edits.find(o => o.id === fwd.op_id)
        if (op) op.enabled = fwd.enabled
        break
      }
      case 'set_params': {
        const op = d.edits.find(o => o.id === fwd.op_id) as any
        if (op) op.params = { ...(op.params || {}), ...fwd.params }
        break
      }
      case 'set_label': {
        const op = d.edits.find(o => o.id === fwd.op_id)
        if (op) op.label = fwd.label
        break
      }
      case 'pick_candidate': {
        const op = d.edits.find(o => o.id === fwd.op_id) as any
        if (op) op.picked = fwd.candidate_id
        break
      }
      case 'set_blend': {
        const op = d.edits.find(o => o.id === fwd.op_id) as any
        if (op) op.blend = fwd.blend
        break
      }
    }
  }

  function undo() {
    if (!canUndo.value || !doc.value) return
    const entry = journal.value[cursor.value - 1]
    applyInverse(entry)
    cursor.value -= 1
    // The undo is itself journaled: the log is a record of what happened, and
    // a truncating undo would make prior states unrecoverable.
    pendingJournal.push({ seq: nextSeq++, action: 'undo', forward: { undid: entry.seq } })
    dirtySinceSave.value = true
    schedulePersist()
  }

  function redo() {
    if (!canRedo.value || !doc.value) return
    const entry = journal.value[cursor.value]
    applyForward(entry)
    cursor.value += 1
    pendingJournal.push({ seq: nextSeq++, action: 'redo', forward: { redid: entry.seq } })
    dirtySinceSave.value = true
    schedulePersist()
  }

  // -- payloads ------------------------------------------------------------

  function payloadUrl(ref: string): string {
    const [subdir, name] = ref.split('/')
    return `${API_BASE}/image-stack/${documentId.value}/payloads/${name}?subdir=${subdir}`
  }

  async function uploadPayload(name: string, blob: Blob, subdir = 'payloads'): Promise<string> {
    const form = new FormData()
    form.append('file', blob, name)
    form.append('name', name)
    form.append('subdir', subdir)
    const { data } = await axios.post(
      `${API_BASE}/image-stack/${documentId.value}/payloads`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    return data.ref
  }

  /**
   * The ops that were enabled at save time, stripped of volatile ids — the
   * chains "record only what ran" discipline, for the committed Media's
   * generation_metadata.
   */
  function executedStackSummary() {
    return ops.value.filter(op => op.enabled).map((op: any) => ({
      class: op.class,
      label: op.label,
      exec: op.exec,
      params: op.params ?? null,
      // Provenance of the pixels that actually landed, not every candidate.
      job_id: (op.candidates || []).find((c: any) => c.id === op.picked)?.job_id ?? null,
    }))
  }

  return {
    documentId,
    doc,
    ops,
    journal,
    cursor,
    saving,
    loadError,
    dirtySinceSave,
    canUndo,
    canRedo,
    open,
    flush,
    opById,
    addOp,
    removeOp,
    moveOp,
    setEnabled,
    setParams,
    setLabel,
    setBlend,
    pickCandidate,
    attachCandidates,
    undo,
    redo,
    payloadUrl,
    uploadPayload,
    executedStackSummary,
  }
}
