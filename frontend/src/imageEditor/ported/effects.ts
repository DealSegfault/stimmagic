/**
 * Ported from the retired editor's effects implementation.
 *
 * Vignette, clarity, blur, sharpen, grain, glow, fringing, halftone, VHS and
 * glitch — the Effects family's pixel work, copied with the color pipeline it
 * runs after.
 *
 * ONE deliberate change from the original: grain, VHS and glitch drew from
 * Math.random(), which was harmless in an editor that baked its result once.
 * Here every step recomposites whenever anything above or below it moves, so
 * unseeded noise reshuffled the whole frame while you dragged an annotation
 * that had nothing to do with it. The noise is now seeded per step, which also
 * makes the content hash mean what it claims: the same parameters produce the
 * same pixels.
 */

/**
 * mulberry32 — small, fast, and good enough for film grain. Deterministic from
 * the seed the executor sets, so a re-render reproduces the previous frame.
 */
let randomState = 0x9e3779b9

export function setEffectsSeed(seed: number): void {
  randomState = (seed >>> 0) || 0x9e3779b9
}

function random(): number {
  randomState |= 0
  randomState = (randomState + 0x6d2b79f5) | 0
  let t = Math.imul(randomState ^ (randomState >>> 15), 1 | randomState)
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296
}
/**
 * Spatial effects utilities for image processing
 */

import { createCanvas, getContext } from './canvasTransform';

/**
 * Pure-pixel Gaussian blur.
 *
 * Replaces `ctx.filter = 'blur(Npx)'`, which the app's macOS WKWebView renders
 * as a no-op for canvas sources — so Blur, Sharpen and Clarity (the Adjust
 * "Detail" edits, the only effects that lean on canvas blur) had no visible
 * effect while every pure-pixel adjustment worked. This runs the same math on
 * the ImageData directly, so it behaves identically on every engine.
 *
 * Approximates a Gaussian of standard deviation `sigma` with three successive
 * box blurs (Kutskir's fast Gaussian), matching CSS `blur()` closely enough for
 * these controls. Edges are clamped.
 */
function boxSizesForGauss(sigma: number, passes: number): number[] {
  const wIdeal = Math.sqrt((12 * sigma * sigma) / passes + 1);
  let wl = Math.floor(wIdeal);
  if (wl % 2 === 0) wl--;
  const wu = wl + 2;
  const mIdeal =
    (12 * sigma * sigma - passes * wl * wl - 4 * passes * wl - 3 * passes) /
    (-4 * wl - 4);
  const m = Math.round(mIdeal);
  const sizes: number[] = [];
  for (let i = 0; i < passes; i++) sizes.push(i < m ? wl : wu);
  return sizes;
}

function boxBlurH(src: Float32Array, dst: Float32Array, w: number, h: number, r: number): void {
  if (r <= 0) { dst.set(src); return; }
  const norm = 1 / (r + r + 1);
  for (let y = 0; y < h; y++) {
    const row = y * w;
    let acc = 0;
    for (let k = -r; k <= r; k++) acc += src[row + Math.min(w - 1, Math.max(0, k))];
    for (let x = 0; x < w; x++) {
      dst[row + x] = acc * norm;
      acc += src[row + Math.min(w - 1, x + r + 1)] - src[row + Math.max(0, x - r)];
    }
  }
}

function boxBlurV(src: Float32Array, dst: Float32Array, w: number, h: number, r: number): void {
  if (r <= 0) { dst.set(src); return; }
  const norm = 1 / (r + r + 1);
  for (let x = 0; x < w; x++) {
    let acc = 0;
    for (let k = -r; k <= r; k++) acc += src[Math.min(h - 1, Math.max(0, k)) * w + x];
    for (let y = 0; y < h; y++) {
      dst[y * w + x] = acc * norm;
      acc += src[Math.min(h - 1, y + r + 1) * w + x] - src[Math.max(0, y - r) * w + x];
    }
  }
}

function gaussianBlurRGBA(data: Uint8ClampedArray, w: number, h: number, sigma: number): void {
  if (sigma <= 0 || w === 0 || h === 0) return;
  const boxes = boxSizesForGauss(sigma, 3);
  const n = w * h;
  const channel = new Float32Array(n);
  const scratch = new Float32Array(n);
  for (let c = 0; c < 4; c++) {
    for (let i = 0; i < n; i++) channel[i] = data[i * 4 + c];
    for (let b = 0; b < boxes.length; b++) {
      const r = (boxes[b] - 1) / 2;
      boxBlurH(channel, scratch, w, h, r);
      boxBlurV(scratch, channel, w, h, r);
    }
    for (let i = 0; i < n; i++) data[i * 4 + c] = channel[i];
  }
}

/** A blurred copy of `source` on a fresh canvas — the ctx.filter-free blur. */
function blurredCanvas(source: HTMLCanvasElement, radiusPx: number): HTMLCanvasElement {
  const width = source.width;
  const height = source.height;
  const out = createCanvas(width, height);
  const octx = getContext(out);
  const sctx = getContext(source);
  const imageData = sctx.getImageData(0, 0, width, height);
  gaussianBlurRGBA(imageData.data, width, height, radiusPx);
  octx.putImageData(imageData, 0, 0);
  return out;
}

export interface EffectsState {
  blur: number;
  sharpen: number;
  noise: number;
  glow: number;
  pixelate: number;
  chromaticAberration: number;
  motionBlur: number;
  motionBlurAngle: number;
  vignette: number;
  texture: number;
  clarity: number;
  noiseReduction: number;
  sharpenRadius: number;
  sharpenDetail: number;
  sharpenMasking: number;
  noiseReductionDetail: number;
  noiseReductionContrast: number;
  colorNoiseReduction: number;
  colorNoiseReductionDetail: number;
  colorNoiseReductionSmoothness: number;
  grainSize: number;
  grainRoughness: number;
  moire: number;
  defringe: number;
  // Creative effects
  halftone: number;
  halftoneAngle: number;
  vhs: number;
  glitch: number;
  glitchBlockSize: number;
  ditherEnabled: boolean;
  ditherPalette: 'bw' | '4bit' | '8bit' | 'gameboy' | 'cga';
}

/**
 * Check if any effects need to be applied
 */
export function hasEffects(state: Partial<EffectsState>): boolean {
  return (
    (state.blur ?? 0) > 0 ||
    (state.sharpen ?? 0) > 0 ||
    (state.noise ?? 0) > 0 ||
    (state.glow ?? 0) > 0 ||
    (state.pixelate ?? 0) > 0 ||
    (state.chromaticAberration ?? 0) > 0 ||
    (state.motionBlur ?? 0) > 0 ||
    (state.vignette ?? 0) > 0 ||
    (state.texture ?? 0) !== 0 ||
    (state.clarity ?? 0) !== 0 ||
    (state.noiseReduction ?? 0) > 0 ||
    (state.colorNoiseReduction ?? 0) > 0 ||
    (state.moire ?? 0) > 0 ||
    (state.defringe ?? 0) > 0 ||
    (state.halftone ?? 0) > 0 ||
    (state.vhs ?? 0) > 0 ||
    (state.glitch ?? 0) > 0 ||
    (state.ditherEnabled ?? false)
  );
}

/**
 * Apply all effects to a canvas
 */
export function applyEffects(
  canvas: HTMLCanvasElement,
  state: Partial<EffectsState>
): HTMLCanvasElement {
  let currentCanvas = canvas;

  // Apply effects in order that makes visual sense

  // 1. Pixelate (early - affects everything after)
  if ((state.pixelate ?? 0) > 0) {
    currentCanvas = applyPixelate(currentCanvas, state.pixelate!);
  }

  // 2. Clarity (local contrast - before blur effects)
  if ((state.clarity ?? 0) !== 0) {
    currentCanvas = applyClarity(currentCanvas, state.clarity!);
  }

  // 3. Texture works at a smaller radius than Clarity.
  if ((state.texture ?? 0) !== 0) {
    currentCanvas = applyTexture(currentCanvas, state.texture!);
  }

  // 4. Moiré/defringe and noise reduction precede sharpening so restored
  // edges remain crisp and chroma artifacts are not sharpened.
  if ((state.moire ?? 0) > 0) {
    currentCanvas = applyMoireReduction(currentCanvas, state.moire!);
  }

  if ((state.defringe ?? 0) > 0) {
    currentCanvas = applyDefringe(currentCanvas, state.defringe!);
  }

  if ((state.noiseReduction ?? 0) > 0) {
    currentCanvas = applyNoiseReduction(
      currentCanvas,
      state.noiseReduction!,
      state.noiseReductionDetail ?? 0,
      state.noiseReductionContrast ?? 0,
    );
  }

  if ((state.colorNoiseReduction ?? 0) > 0) {
    currentCanvas = applyColorNoiseReduction(
      currentCanvas,
      state.colorNoiseReduction!,
      state.colorNoiseReductionDetail ?? 0,
      state.colorNoiseReductionSmoothness ?? 0,
    );
  }

  // 5. Sharpen (before blur so they can be combined)
  if ((state.sharpen ?? 0) > 0) {
    currentCanvas = applySharpen(
      currentCanvas,
      state.sharpen!,
      state.sharpenRadius ?? 1,
      state.sharpenDetail ?? 0,
      state.sharpenMasking ?? 0,
    );
  }

  // 4. Blur effects
  if ((state.blur ?? 0) > 0) {
    currentCanvas = applyBlur(currentCanvas, state.blur!);
  }

  if ((state.motionBlur ?? 0) > 0) {
    currentCanvas = applyMotionBlur(currentCanvas, state.motionBlur!, state.motionBlurAngle ?? 0);
  }

  // 5. Glow (after main blur)
  if ((state.glow ?? 0) > 0) {
    currentCanvas = applyGlow(currentCanvas, state.glow!);
  }

  // 6. Chromatic aberration (color effect)
  if ((state.chromaticAberration ?? 0) > 0) {
    currentCanvas = applyChromaticAberration(currentCanvas, state.chromaticAberration!);
  }

  // 7. Noise (late - should be on top)
  if ((state.noise ?? 0) > 0) {
    currentCanvas = applyNoise(
      currentCanvas,
      state.noise!,
      state.grainSize ?? 0,
      state.grainRoughness ?? 50,
    );
  }

  // 8. Vignette (last - frames the image)
  if ((state.vignette ?? 0) > 0) {
    currentCanvas = applyVignette(currentCanvas, state.vignette!);
  }

  // 9. Halftone
  if ((state.halftone ?? 0) > 0) {
    currentCanvas = applyHalftone(currentCanvas, state.halftone!, state.halftoneAngle ?? 0);
  }

  // 10. VHS / Analog
  if ((state.vhs ?? 0) > 0) {
    currentCanvas = applyVHS(currentCanvas, state.vhs!);
  }

  // 11. Glitch
  if ((state.glitch ?? 0) > 0) {
    currentCanvas = applyGlitch(currentCanvas, state.glitch!, state.glitchBlockSize ?? 16);
  }

  // 12. Dither (last - affects final color palette)
  if (state.ditherEnabled) {
    currentCanvas = applyDither(currentCanvas, state.ditherPalette ?? '8bit');
  }

  return currentCanvas;
}

/**
 * Apply Gaussian blur using canvas filter
 */
export function applyBlur(canvas: HTMLCanvasElement, amount: number): HTMLCanvasElement {
  return blurredCanvas(canvas, amount);
}

/**
 * Apply sharpening using unsharp mask technique
 */
export function applySharpen(
  canvas: HTMLCanvasElement,
  amount: number,
  radius = 1,
  detail = 0,
  masking = 0,
): HTMLCanvasElement {
  const width = canvas.width;
  const height = canvas.height;
  const result = createCanvas(width, height);
  const ctx = getContext(result);

  // Draw original
  ctx.drawImage(canvas, 0, 0);

  // Create blurred version (pure-pixel blur; see blurredCanvas)
  const blurred = blurredCanvas(canvas, Math.max(0.5, radius));
  const blurCtx = getContext(blurred);
  const detailCanvas = detail > 0
    ? blurredCanvas(canvas, Math.max(0.5, radius * 0.4))
    : null;

  // Get image data
  const originalData = ctx.getImageData(0, 0, width, height);
  const blurredData = blurCtx.getImageData(0, 0, width, height);
  const detailData = detailCanvas
    ? getContext(detailCanvas).getImageData(0, 0, width, height)
    : null;
  const resultData = ctx.getImageData(0, 0, width, height);

  const strength = amount / 50; // Normalize to reasonable range
  const detailMix = Math.max(0, Math.min(1, detail / 100));
  const edgeThreshold = Math.max(0, masking / 100) * 48;

  for (let i = 0; i < originalData.data.length; i += 4) {
    const luminance =
      originalData.data[i] * 0.2126 +
      originalData.data[i + 1] * 0.7152 +
      originalData.data[i + 2] * 0.0722;
    const softLuminance =
      blurredData.data[i] * 0.2126 +
      blurredData.data[i + 1] * 0.7152 +
      blurredData.data[i + 2] * 0.0722;
    const edge = Math.abs(luminance - softLuminance);
    const edgeMask = edgeThreshold <= 0
      ? 1
      : Math.max(0, Math.min(1, (edge - edgeThreshold) / 24));
    // Unsharp mask: original + (original - blurred) * amount
    for (let c = 0; c < 3; c++) {
      const broad = originalData.data[i + c] - blurredData.data[i + c];
      const fine = detailData
        ? originalData.data[i + c] - detailData.data[i + c]
        : broad;
      const diff = broad * (1 - detailMix) + fine * detailMix;
      resultData.data[i + c] = Math.max(
        0,
        Math.min(255, originalData.data[i + c] + diff * strength * edgeMask),
      );
    }
  }

  ctx.putImageData(resultData, 0, 0);
  return result;
}

function applyLocalContrast(
  canvas: HTMLCanvasElement,
  amount: number,
  radius: number,
): HTMLCanvasElement {
  const width = canvas.width
  const height = canvas.height
  const result = createCanvas(width, height)
  const ctx = getContext(result)
  ctx.drawImage(canvas, 0, 0)
  const blurred = blurredCanvas(canvas, radius)
  const originalData = ctx.getImageData(0, 0, width, height)
  const blurredData = getContext(blurred).getImageData(0, 0, width, height)
  const strength = amount / 100
  for (let i = 0; i < originalData.data.length; i += 4) {
    for (let channel = 0; channel < 3; channel++) {
      const highPass = originalData.data[i + channel] - blurredData.data[i + channel]
      originalData.data[i + channel] = Math.max(
        0,
        Math.min(255, originalData.data[i + channel] + highPass * strength),
      )
    }
  }
  ctx.putImageData(originalData, 0, 0)
  return result
}

/** Fine-scale local contrast that leaves broader tonal transitions alone. */
export function applyTexture(canvas: HTMLCanvasElement, amount: number): HTMLCanvasElement {
  return applyLocalContrast(canvas, amount, 3)
}

/** Luminance-friendly smoothing; intentionally conservative at 100. */
export function applyNoiseReduction(
  canvas: HTMLCanvasElement,
  amount: number,
  detail = 0,
  contrast = 0,
): HTMLCanvasElement {
  const width = canvas.width
  const height = canvas.height
  const result = createCanvas(width, height)
  const ctx = getContext(result)
  ctx.drawImage(canvas, 0, 0)
  const blurred = blurredCanvas(canvas, 1 + (amount / 100) * 2)
  // Exact legacy path: documents saved before the supporting controls existed
  // retain their original output.
  if (detail === 0 && contrast === 0) {
    ctx.globalAlpha = Math.min(0.85, amount / 120)
    ctx.drawImage(blurred, 0, 0)
    ctx.globalAlpha = 1
    return result
  }

  const original = ctx.getImageData(0, 0, width, height)
  const soft = getContext(blurred).getImageData(0, 0, width, height)
  const mix = Math.min(0.85, amount / 120)
  const protection = Math.max(0, Math.min(1, detail / 100))
  const restore = Math.max(0, Math.min(1, contrast / 100))
  for (let i = 0; i < original.data.length; i += 4) {
    const originalLuma =
      original.data[i] * 0.2126 + original.data[i + 1] * 0.7152 + original.data[i + 2] * 0.0722
    const softLuma =
      soft.data[i] * 0.2126 + soft.data[i + 1] * 0.7152 + soft.data[i + 2] * 0.0722
    const edge = Math.min(1, Math.abs(originalLuma - softLuma) / 32)
    const localMix = mix * (1 - protection * edge)
    const targetLuma = originalLuma + (softLuma - originalLuma) * localMix
    const restoredLuma = targetLuma + (originalLuma - softLuma) * restore * 0.35
    const scale = originalLuma > 1e-3 ? restoredLuma / originalLuma : 1
    original.data[i] = Math.max(0, Math.min(255, original.data[i] * scale))
    original.data[i + 1] = Math.max(0, Math.min(255, original.data[i + 1] * scale))
    original.data[i + 2] = Math.max(0, Math.min(255, original.data[i + 2] * scale))
  }
  ctx.putImageData(original, 0, 0)
  return result
}

function applyChromaSmoothing(
  canvas: HTMLCanvasElement,
  amount: number,
  radius: number,
  edgeProtection: number,
): HTMLCanvasElement {
  const width = canvas.width
  const height = canvas.height
  const result = createCanvas(width, height)
  const ctx = getContext(result)
  ctx.drawImage(canvas, 0, 0)
  const original = ctx.getImageData(0, 0, width, height)
  const softCanvas = blurredCanvas(canvas, radius)
  const soft = getContext(softCanvas).getImageData(0, 0, width, height)
  const strength = Math.max(0, Math.min(1, amount / 100))
  for (let i = 0; i < original.data.length; i += 4) {
    const luma =
      original.data[i] * 0.2126 + original.data[i + 1] * 0.7152 + original.data[i + 2] * 0.0722
    const softLuma =
      soft.data[i] * 0.2126 + soft.data[i + 1] * 0.7152 + soft.data[i + 2] * 0.0722
    const edge = Math.min(1, Math.abs(luma - softLuma) / 28)
    const mix = strength * (1 - edge * edgeProtection)
    for (let channel = 0; channel < 3; channel++) {
      const chroma = original.data[i + channel] - luma
      const softChroma = soft.data[i + channel] - softLuma
      original.data[i + channel] = Math.max(
        0,
        Math.min(255, luma + chroma + (softChroma - chroma) * mix),
      )
    }
  }
  ctx.putImageData(original, 0, 0)
  return result
}

export function applyColorNoiseReduction(
  canvas: HTMLCanvasElement,
  amount: number,
  detail = 0,
  smoothness = 0,
): HTMLCanvasElement {
  const radius = 1 + Math.max(0, smoothness / 100) * 3
  return applyChromaSmoothing(
    canvas,
    amount,
    radius,
    Math.max(0, Math.min(1, detail / 100)),
  )
}

export function applyMoireReduction(
  canvas: HTMLCanvasElement,
  amount: number,
): HTMLCanvasElement {
  return applyChromaSmoothing(canvas, amount, 2.5, 0.85)
}

export function applyDefringe(
  canvas: HTMLCanvasElement,
  amount: number,
): HTMLCanvasElement {
  const width = canvas.width
  const height = canvas.height
  const result = createCanvas(width, height)
  const ctx = getContext(result)
  ctx.drawImage(canvas, 0, 0)
  const data = ctx.getImageData(0, 0, width, height)
  const strength = Math.max(0, Math.min(1, amount / 100))
  for (let i = 0; i < data.data.length; i += 4) {
    const r = data.data[i]
    const g = data.data[i + 1]
    const b = data.data[i + 2]
    const max = Math.max(r, g, b)
    const min = Math.min(r, g, b)
    const saturation = max <= 0 ? 0 : (max - min) / max
    const purple = Math.max(0, (r + b) * 0.5 - g) / 128
    const green = Math.max(0, g - (r + b) * 0.5) / 128
    const fringe = Math.max(0, Math.min(1, Math.max(purple, green) * saturation))
    if (fringe <= 0) continue
    const luma = r * 0.2126 + g * 0.7152 + b * 0.0722
    const mix = strength * fringe
    data.data[i] = r + (luma - r) * mix
    data.data[i + 1] = g + (luma - g) * mix
    data.data[i + 2] = b + (luma - b) * mix
  }
  ctx.putImageData(data, 0, 0)
  return result
}

/**
 * Apply film grain. `size = 0` is the legacy one-pixel grain path so saved
 * documents retain their exact seeded pattern.
 */
export function applyNoise(
  canvas: HTMLCanvasElement,
  amount: number,
  size = 0,
  roughness = 50,
): HTMLCanvasElement {
  const width = canvas.width;
  const height = canvas.height;
  const result = createCanvas(width, height);
  const ctx = getContext(result);

  ctx.drawImage(canvas, 0, 0);

  const imageData = ctx.getImageData(0, 0, width, height);
  const data = imageData.data;
  const intensity = amount * 2.55;

  if (size <= 0) {
    for (let i = 0; i < data.length; i += 4) {
      const noise = (random() - 0.5) * intensity;
      data[i] = Math.max(0, Math.min(255, data[i] + noise));
      data[i + 1] = Math.max(0, Math.min(255, data[i + 1] + noise));
      data[i + 2] = Math.max(0, Math.min(255, data[i + 2] + noise));
    }
  } else {
    const cell = 1 + Math.round(size / 12)
    const gridWidth = Math.ceil(width / cell)
    const gridHeight = Math.ceil(height / cell)
    const coarse = new Float32Array(gridWidth * gridHeight)
    for (let i = 0; i < coarse.length; i++) coarse[i] = random() - 0.5
    const fineMix = Math.max(0, Math.min(1, roughness / 100))
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const i = (y * width + x) * 4
        const coarseNoise = coarse[Math.floor(y / cell) * gridWidth + Math.floor(x / cell)]
        const noise = (coarseNoise * (1 - fineMix) + (random() - 0.5) * fineMix) * intensity
        data[i] = Math.max(0, Math.min(255, data[i] + noise))
        data[i + 1] = Math.max(0, Math.min(255, data[i + 1] + noise))
        data[i + 2] = Math.max(0, Math.min(255, data[i + 2] + noise))
      }
    }
  }

  ctx.putImageData(imageData, 0, 0);
  return result;
}

/**
 * Apply glow/bloom effect
 */
export function applyGlow(canvas: HTMLCanvasElement, amount: number): HTMLCanvasElement {
  const width = canvas.width;
  const height = canvas.height;
  const result = createCanvas(width, height);
  const ctx = getContext(result);

  // Draw original
  ctx.drawImage(canvas, 0, 0);

  // Bright pass + blur for glow (pure-pixel blur, then brightness(1.5)).
  const glowCanvas = blurredCanvas(canvas, amount * 2);
  const glowCtx = getContext(glowCanvas);
  {
    const bright = glowCtx.getImageData(0, 0, width, height);
    const bd = bright.data;
    for (let i = 0; i < bd.length; i += 4) {
      bd[i] = Math.min(255, bd[i] * 1.5);
      bd[i + 1] = Math.min(255, bd[i + 1] * 1.5);
      bd[i + 2] = Math.min(255, bd[i + 2] * 1.5);
    }
    glowCtx.putImageData(bright, 0, 0);
  }

  // Blend glow on top with screen/additive-like effect
  ctx.globalCompositeOperation = 'screen';
  ctx.globalAlpha = amount / 100;
  ctx.drawImage(glowCanvas, 0, 0);
  ctx.globalCompositeOperation = 'source-over';
  ctx.globalAlpha = 1;

  return result;
}

/**
 * Apply pixelate/mosaic effect
 */
export function applyPixelate(canvas: HTMLCanvasElement, amount: number): HTMLCanvasElement {
  const width = canvas.width;
  const height = canvas.height;

  // Pixel size based on amount (2-50 pixels)
  const pixelSize = Math.max(2, Math.floor(amount / 2));

  const smallWidth = Math.max(1, Math.floor(width / pixelSize));
  const smallHeight = Math.max(1, Math.floor(height / pixelSize));

  // Scale down
  const small = createCanvas(smallWidth, smallHeight);
  const smallCtx = getContext(small);
  smallCtx.imageSmoothingEnabled = false;
  smallCtx.drawImage(canvas, 0, 0, smallWidth, smallHeight);

  // Scale back up with no smoothing
  const result = createCanvas(width, height);
  const ctx = getContext(result);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(small, 0, 0, width, height);

  return result;
}

/**
 * Apply chromatic aberration (RGB channel offset)
 */
export function applyChromaticAberration(canvas: HTMLCanvasElement, amount: number): HTMLCanvasElement {
  const width = canvas.width;
  const height = canvas.height;
  const result = createCanvas(width, height);
  const ctx = getContext(result);

  const sourceCtx = canvas.getContext('2d')!;
  const sourceData = sourceCtx.getImageData(0, 0, width, height);
  const resultData = ctx.createImageData(width, height);

  const offset = Math.floor(amount / 5); // Offset in pixels

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;

      // Red channel - offset left
      const rxSrc = Math.max(0, Math.min(width - 1, x - offset));
      const ri = (y * width + rxSrc) * 4;
      resultData.data[i] = sourceData.data[ri];

      // Green channel - no offset
      resultData.data[i + 1] = sourceData.data[i + 1];

      // Blue channel - offset right
      const bxSrc = Math.max(0, Math.min(width - 1, x + offset));
      const bi = (y * width + bxSrc) * 4;
      resultData.data[i + 2] = sourceData.data[bi + 2];

      // Alpha - average or use original
      resultData.data[i + 3] = sourceData.data[i + 3];
    }
  }

  ctx.putImageData(resultData, 0, 0);
  return result;
}

/**
 * Apply directional motion blur
 */
export function applyMotionBlur(canvas: HTMLCanvasElement, amount: number, angle: number): HTMLCanvasElement {
  const width = canvas.width;
  const height = canvas.height;
  const result = createCanvas(width, height);
  const ctx = getContext(result);

  // Convert angle to radians (-180 to 180 -> -PI to PI)
  const radians = (angle * Math.PI) / 180;
  const dx = Math.cos(radians);
  const dy = Math.sin(radians);

  // Number of samples based on amount
  const samples = Math.max(3, Math.floor(amount / 3));
  const maxOffset = amount / 2;

  ctx.globalAlpha = 1 / samples;

  for (let i = 0; i < samples; i++) {
    const t = (i / (samples - 1)) - 0.5; // -0.5 to 0.5
    const offsetX = dx * t * maxOffset * 2;
    const offsetY = dy * t * maxOffset * 2;
    ctx.drawImage(canvas, offsetX, offsetY);
  }

  ctx.globalAlpha = 1;

  return result;
}

/**
 * Apply vignette effect (darken edges)
 */
export function applyVignette(canvas: HTMLCanvasElement, amount: number): HTMLCanvasElement {
  const width = canvas.width;
  const height = canvas.height;
  const result = createCanvas(width, height);
  const ctx = getContext(result);

  ctx.drawImage(canvas, 0, 0);

  // Create radial gradient for vignette
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.sqrt(centerX * centerX + centerY * centerY);

  const gradient = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius);

  // Inner area is transparent, outer is dark
  const strength = amount / 100;
  gradient.addColorStop(0, 'rgba(0,0,0,0)');
  gradient.addColorStop(0.5, 'rgba(0,0,0,0)');
  gradient.addColorStop(1, `rgba(0,0,0,${strength})`);

  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);

  return result;
}

/**
 * Apply clarity (local contrast enhancement)
 */
export function applyClarity(canvas: HTMLCanvasElement, amount: number): HTMLCanvasElement {
  const width = canvas.width;
  const height = canvas.height;
  const result = createCanvas(width, height);
  const ctx = getContext(result);

  // Draw original
  ctx.drawImage(canvas, 0, 0);

  // Create heavily blurred version (low frequency; pure-pixel blur)
  const blurred = blurredCanvas(canvas, 20);
  const blurCtx = getContext(blurred);

  // Get image data
  const originalData = ctx.getImageData(0, 0, width, height);
  const blurredData = blurCtx.getImageData(0, 0, width, height);

  const strength = amount / 100;

  for (let i = 0; i < originalData.data.length; i += 4) {
    for (let c = 0; c < 3; c++) {
      // High-pass: original - blurred (local details)
      // Add back to original weighted by strength
      const highPass = originalData.data[i + c] - blurredData.data[i + c];
      originalData.data[i + c] = Math.max(0, Math.min(255,
        originalData.data[i + c] + highPass * strength
      ));
    }
  }

  ctx.putImageData(originalData, 0, 0);
  return result;
}

/**
 * Apply halftone effect (CMYK-style dot pattern)
 */
export function applyHalftone(canvas: HTMLCanvasElement, amount: number, angle: number = 0): HTMLCanvasElement {
  const width = canvas.width;
  const height = canvas.height;
  const result = createCanvas(width, height);
  const ctx = getContext(result);

  const sourceCtx = canvas.getContext('2d')!;
  const sourceData = sourceCtx.getImageData(0, 0, width, height);

  // Dot size based on amount (2-20 pixels)
  const dotSize = Math.max(2, Math.floor(2 + (amount / 100) * 18));
  const halfDot = dotSize / 2;

  // Angle in radians
  const rad = (angle * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);

  // Fill with white background
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, width, height);

  // Process in grid cells
  for (let y = -dotSize; y < height + dotSize; y += dotSize) {
    for (let x = -dotSize; x < width + dotSize; x += dotSize) {
      // Apply rotation to get sample position
      const cx = x + halfDot;
      const cy = y + halfDot;

      // Rotate coordinates
      const rx = Math.floor(cos * (cx - width/2) - sin * (cy - height/2) + width/2);
      const ry = Math.floor(sin * (cx - width/2) + cos * (cy - height/2) + height/2);

      // Sample the source image
      if (rx >= 0 && rx < width && ry >= 0 && ry < height) {
        const i = (ry * width + rx) * 4;
        const r = sourceData.data[i];
        const g = sourceData.data[i + 1];
        const b = sourceData.data[i + 2];

        // Calculate luminance
        const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;

        // Dot radius based on darkness (darker = bigger dot)
        const radius = halfDot * (1 - lum) * 0.9;

        if (radius > 0.5) {
          ctx.beginPath();
          ctx.arc(cx, cy, radius, 0, Math.PI * 2);
          ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
          ctx.fill();
        }
      }
    }
  }

  return result;
}

/**
 * Apply VHS / Analog effect
 * Includes horizontal distortion, color bleed, and tracking lines
 */
export function applyVHS(canvas: HTMLCanvasElement, amount: number): HTMLCanvasElement {
  const width = canvas.width;
  const height = canvas.height;
  const result = createCanvas(width, height);
  const ctx = getContext(result);

  const sourceCtx = canvas.getContext('2d')!;
  const sourceData = sourceCtx.getImageData(0, 0, width, height);
  const resultData = ctx.createImageData(width, height);

  const intensity = amount / 100;

  // Pre-calculate random seeds for consistent noise
  const scanlineNoise: number[] = [];
  for (let y = 0; y < height; y++) {
    scanlineNoise[y] = (random() - 0.5) * 2;
  }

  for (let y = 0; y < height; y++) {
    // Horizontal distortion (wobble)
    const wobble = Math.sin(y * 0.1 + random() * 0.5) * intensity * 5;
    const jitter = scanlineNoise[y] * intensity * 3;

    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;

      // Apply horizontal offset with wobble
      const srcX = Math.floor(x + wobble + jitter);
      const clampedX = Math.max(0, Math.min(width - 1, srcX));

      // Color channel separation (chromatic aberration style)
      const redOffset = Math.floor(intensity * 4);
      const blueOffset = -Math.floor(intensity * 4);

      const srcR = Math.max(0, Math.min(width - 1, clampedX + redOffset));
      const srcB = Math.max(0, Math.min(width - 1, clampedX + blueOffset));

      const iR = (y * width + srcR) * 4;
      const iG = (y * width + clampedX) * 4;
      const iB = (y * width + srcB) * 4;

      resultData.data[i] = sourceData.data[iR];
      resultData.data[i + 1] = sourceData.data[iG + 1];
      resultData.data[i + 2] = sourceData.data[iB + 2];
      resultData.data[i + 3] = 255;
    }
  }

  ctx.putImageData(resultData, 0, 0);

  // Add scanlines
  ctx.globalAlpha = intensity * 0.3;
  for (let y = 0; y < height; y += 2) {
    ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
    ctx.fillRect(0, y, width, 1);
  }

  // Add random tracking glitches
  ctx.globalAlpha = intensity * 0.5;
  const numGlitches = Math.floor(intensity * 5);
  for (let i = 0; i < numGlitches; i++) {
    const glitchY = Math.floor(random() * height);
    const glitchHeight = Math.floor(random() * 10 + 2);
    ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
    ctx.fillRect(0, glitchY, width, glitchHeight);
  }

  ctx.globalAlpha = 1;

  // Add slight blur for tape degradation effect
  if (intensity > 0.3) {
    const blurred = blurredCanvas(result, intensity * 0.5);
    ctx.globalAlpha = intensity * 0.3;
    ctx.drawImage(blurred, 0, 0);
    ctx.globalAlpha = 1;
  }

  return result;
}

/**
 * Apply glitch effect
 * Random RGB channel displacement in blocks
 */
export function applyGlitch(canvas: HTMLCanvasElement, amount: number, blockSize: number = 16): HTMLCanvasElement {
  const width = canvas.width;
  const height = canvas.height;
  const result = createCanvas(width, height);
  const ctx = getContext(result);

  // Draw original first
  ctx.drawImage(canvas, 0, 0);

  const sourceCtx = canvas.getContext('2d')!;
  const sourceData = sourceCtx.getImageData(0, 0, width, height);
  const resultData = ctx.getImageData(0, 0, width, height);

  const intensity = amount / 100;
  const numBlocks = Math.floor(intensity * 20) + 1;

  // Create glitch blocks
  for (let b = 0; b < numBlocks; b++) {
    // Random block position and size
    const blockY = Math.floor(random() * height);
    const blockHeight = Math.floor(random() * blockSize * 2) + blockSize;
    const blockWidth = Math.floor(random() * (width * 0.8)) + width * 0.2;
    const blockX = Math.floor(random() * (width - blockWidth));

    // Random channel offsets
    const rOffset = Math.floor((random() - 0.5) * intensity * 30);
    const gOffset = Math.floor((random() - 0.5) * intensity * 30);
    const bOffset = Math.floor((random() - 0.5) * intensity * 30);

    // Apply to block
    for (let y = blockY; y < Math.min(blockY + blockHeight, height); y++) {
      for (let x = blockX; x < Math.min(blockX + blockWidth, width); x++) {
        const i = (y * width + x) * 4;

        // Get offset source positions
        const srcR = Math.max(0, Math.min(width - 1, x + rOffset));
        const srcG = Math.max(0, Math.min(width - 1, x + gOffset));
        const srcB = Math.max(0, Math.min(width - 1, x + bOffset));

        const iR = (y * width + srcR) * 4;
        const iG = (y * width + srcG) * 4;
        const iB = (y * width + srcB) * 4;

        resultData.data[i] = sourceData.data[iR];
        resultData.data[i + 1] = sourceData.data[iG + 1];
        resultData.data[i + 2] = sourceData.data[iB + 2];
      }
    }
  }

  // Add some horizontal line shifts
  const numShifts = Math.floor(intensity * 10);
  for (let s = 0; s < numShifts; s++) {
    const shiftY = Math.floor(random() * height);
    const shiftHeight = Math.floor(random() * 5) + 1;
    const shiftAmount = Math.floor((random() - 0.5) * intensity * 50);

    for (let y = shiftY; y < Math.min(shiftY + shiftHeight, height); y++) {
      for (let x = 0; x < width; x++) {
        const destI = (y * width + x) * 4;
        const srcX = Math.max(0, Math.min(width - 1, x + shiftAmount));
        const srcI = (y * width + srcX) * 4;

        resultData.data[destI] = sourceData.data[srcI];
        resultData.data[destI + 1] = sourceData.data[srcI + 1];
        resultData.data[destI + 2] = sourceData.data[srcI + 2];
      }
    }
  }

  ctx.putImageData(resultData, 0, 0);
  return result;
}

/**
 * Color palettes for dithering
 */
const DITHER_PALETTES: Record<string, number[][]> = {
  bw: [
    [0, 0, 0],
    [255, 255, 255],
  ],
  gameboy: [
    [15, 56, 15],
    [48, 98, 48],
    [139, 172, 15],
    [155, 188, 15],
  ],
  cga: [
    [0, 0, 0],
    [0, 170, 170],
    [170, 0, 170],
    [170, 170, 170],
  ],
  '4bit': [
    [0, 0, 0],
    [128, 0, 0],
    [0, 128, 0],
    [128, 128, 0],
    [0, 0, 128],
    [128, 0, 128],
    [0, 128, 128],
    [192, 192, 192],
    [128, 128, 128],
    [255, 0, 0],
    [0, 255, 0],
    [255, 255, 0],
    [0, 0, 255],
    [255, 0, 255],
    [0, 255, 255],
    [255, 255, 255],
  ],
  '8bit': (() => {
    // Generate 256-color palette (6x6x6 color cube + grayscale)
    const palette: number[][] = [];
    // 6x6x6 color cube
    for (let r = 0; r < 6; r++) {
      for (let g = 0; g < 6; g++) {
        for (let b = 0; b < 6; b++) {
          palette.push([r * 51, g * 51, b * 51]);
        }
      }
    }
    // Grayscale ramp
    for (let i = 0; i < 24; i++) {
      const v = Math.round(i * 10.625);
      palette.push([v, v, v]);
    }
    return palette;
  })(),
};

/**
 * Find closest color in palette
 */
function findClosestColor(r: number, g: number, b: number, palette: number[][]): number[] {
  let minDist = Infinity;
  let closest = palette[0];

  for (const color of palette) {
    const dr = r - color[0];
    const dg = g - color[1];
    const db = b - color[2];
    const dist = dr * dr + dg * dg + db * db;

    if (dist < minDist) {
      minDist = dist;
      closest = color;
    }
  }

  return closest;
}

/**
 * Apply dithering effect (Floyd-Steinberg)
 */
export function applyDither(
  canvas: HTMLCanvasElement,
  paletteType: 'bw' | '4bit' | '8bit' | 'gameboy' | 'cga'
): HTMLCanvasElement {
  const width = canvas.width;
  const height = canvas.height;
  const result = createCanvas(width, height);
  const ctx = getContext(result);

  ctx.drawImage(canvas, 0, 0);
  const imageData = ctx.getImageData(0, 0, width, height);
  const data = imageData.data;

  const palette = DITHER_PALETTES[paletteType] || DITHER_PALETTES['8bit'];

  // Create a copy of the data for error diffusion
  const pixels: number[][] = [];
  for (let y = 0; y < height; y++) {
    pixels[y] = [];
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      pixels[y][x * 3] = data[i];
      pixels[y][x * 3 + 1] = data[i + 1];
      pixels[y][x * 3 + 2] = data[i + 2];
    }
  }

  // Floyd-Steinberg dithering
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const oldR = pixels[y][x * 3];
      const oldG = pixels[y][x * 3 + 1];
      const oldB = pixels[y][x * 3 + 2];

      // Find closest palette color
      const newColor = findClosestColor(oldR, oldG, oldB, palette);

      // Set the new color
      const i = (y * width + x) * 4;
      data[i] = newColor[0];
      data[i + 1] = newColor[1];
      data[i + 2] = newColor[2];

      // Calculate quantization error
      const errR = oldR - newColor[0];
      const errG = oldG - newColor[1];
      const errB = oldB - newColor[2];

      // Distribute error to neighboring pixels
      // Right: 7/16
      if (x + 1 < width) {
        pixels[y][(x + 1) * 3] += errR * 7 / 16;
        pixels[y][(x + 1) * 3 + 1] += errG * 7 / 16;
        pixels[y][(x + 1) * 3 + 2] += errB * 7 / 16;
      }
      // Bottom-left: 3/16
      if (y + 1 < height && x - 1 >= 0) {
        pixels[y + 1][(x - 1) * 3] += errR * 3 / 16;
        pixels[y + 1][(x - 1) * 3 + 1] += errG * 3 / 16;
        pixels[y + 1][(x - 1) * 3 + 2] += errB * 3 / 16;
      }
      // Bottom: 5/16
      if (y + 1 < height) {
        pixels[y + 1][x * 3] += errR * 5 / 16;
        pixels[y + 1][x * 3 + 1] += errG * 5 / 16;
        pixels[y + 1][x * 3 + 2] += errB * 5 / 16;
      }
      // Bottom-right: 1/16
      if (y + 1 < height && x + 1 < width) {
        pixels[y + 1][(x + 1) * 3] += errR * 1 / 16;
        pixels[y + 1][(x + 1) * 3 + 1] += errG * 1 / 16;
        pixels[y + 1][(x + 1) * 3 + 2] += errB * 1 / 16;
      }
    }
  }

  ctx.putImageData(imageData, 0, 0);
  return result;
}
