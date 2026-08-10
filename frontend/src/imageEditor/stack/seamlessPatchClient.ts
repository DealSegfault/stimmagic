import { seamlessPatch } from './seamlessPatch.ts'

interface PatchWorkerResponse {
  id: number
  output: ArrayBuffer
}

interface PendingPatch {
  resolve: (output: Uint8ClampedArray) => void
  reject: (error: Error) => void
}

let patchWorker: Worker | null = null
let nextRequestId = 1
const pendingPatches = new Map<number, PendingPatch>()

function rejectPendingPatches(message: string): void {
  for (const pending of pendingPatches.values()) pending.reject(new Error(message))
  pendingPatches.clear()
}

function sharedPatchWorker(): Worker | null {
  if (patchWorker) return patchWorker
  try {
    patchWorker = new Worker(
      new URL('./seamlessPatch.worker.ts', import.meta.url),
      { type: 'module', name: 'stimma-seamless-patch' },
    )
  } catch {
    return null
  }
  patchWorker.onmessage = (event: MessageEvent<PatchWorkerResponse>) => {
    const pending = pendingPatches.get(event.data.id)
    if (!pending) return
    pendingPatches.delete(event.data.id)
    pending.resolve(new Uint8ClampedArray(event.data.output))
  }
  patchWorker.onerror = (event) => {
    const failedWorker = patchWorker
    patchWorker = null
    failedWorker?.terminate()
    rejectPendingPatches(event.message || 'Patch reconstruction worker failed')
  }
  return patchWorker
}

/**
 * Run the reconstruction off the UI thread. The synchronous path is retained
 * for non-browser renderers and tests that do not expose Web Workers.
 */
export function solveSeamlessPatch(
  source: Uint8ClampedArray,
  destination: Uint8ClampedArray,
  mask: Uint8ClampedArray,
  width: number,
  height: number,
): Promise<Uint8ClampedArray> {
  if (typeof Worker === 'undefined') {
    return Promise.resolve(seamlessPatch(source, destination, mask, width, height))
  }

  const worker = sharedPatchWorker()
  if (!worker) {
    return Promise.resolve(seamlessPatch(source, destination, mask, width, height))
  }

  return new Promise((resolve, reject) => {
    const id = nextRequestId++
    pendingPatches.set(id, { resolve, reject })
    worker.postMessage({
      id,
      source: source.buffer,
      destination: destination.buffer,
      mask: mask.buffer,
      width,
      height,
    }, [source.buffer, destination.buffer, mask.buffer])
  })
}
