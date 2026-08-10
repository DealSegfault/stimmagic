import { seamlessPatch } from './seamlessPatch.ts'
import initSeamlessPatchWasm, {
  seamless_patch as seamlessPatchWasm,
} from './seamlessPatchWasm/seamlessPatchWasm.js'

interface SeamlessPatchRequest {
  id: number
  source: ArrayBuffer
  destination: ArrayBuffer
  mask: ArrayBuffer
  width: number
  height: number
}

const wasmReady = initSeamlessPatchWasm()

self.onmessage = async (event: MessageEvent<SeamlessPatchRequest>) => {
  const { id, source, destination, mask, width, height } = event.data
  const sourcePixels = new Uint8ClampedArray(source)
  const destinationPixels = new Uint8ClampedArray(destination)
  const selectionMask = new Uint8ClampedArray(mask)
  let output: Uint8ClampedArray
  try {
    await wasmReady
    output = new Uint8ClampedArray(seamlessPatchWasm(
      sourcePixels,
      destinationPixels,
      selectionMask,
      width,
      height,
    ))
  } catch (error) {
    // Preserve the tool in browsers where WASM is unavailable. This reference
    // path is intentionally slower, but it produces the same reconstruction.
    console.warn('WASM patch solver unavailable; using TypeScript fallback', error)
    output = seamlessPatch(
      sourcePixels,
      destinationPixels,
      selectionMask,
      width,
      height,
    )
  }
  self.postMessage({ id, output: output.buffer }, { transfer: [output.buffer] })
}

export {}
