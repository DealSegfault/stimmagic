/**
 * Pixel sampling, brush masks, color maths and the patch solver.
 *
 * Ported from the retired editor on 2026-07-27, with imports repointed here.
 */

import type { Point } from './geometry';
import { brushTipAlpha } from '../brush/tipMask.ts';
import { solveSeamlessPatch } from '../stack/seamlessPatchClient.ts';

/**
 * Sample a pixel color from a canvas at the given position
 */
export function samplePixel(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number
): { r: number; g: number; b: number; a: number } {
  const imageData = ctx.getImageData(Math.floor(x), Math.floor(y), 1, 1);
  const [r, g, b, a] = imageData.data;
  return { r, g, b, a };
}

/**
 * Sample a region of pixels from a canvas
 */
export function sampleRegion(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number
): ImageData {
  return ctx.getImageData(
    Math.floor(x),
    Math.floor(y),
    Math.floor(width),
    Math.floor(height)
  );
}

/**
 * Calculate color distance (Euclidean) between two colors
 */
export function colorDistance(
  r1: number, g1: number, b1: number,
  r2: number, g2: number, b2: number
): number {
  const dr = r1 - r2;
  const dg = g1 - g2;
  const db = b1 - b2;
  return Math.sqrt(dr * dr + dg * dg + db * db);
}

/**
 * Convert RGB to HSL
 */
export function rgbToHsl(
  r: number, g: number, b: number
): { h: number; s: number; l: number } {
  r /= 255;
  g /= 255;
  b /= 255;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0;
  let s = 0;

  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);

    switch (max) {
      case r:
        h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
        break;
      case g:
        h = ((b - r) / d + 2) / 6;
        break;
      case b:
        h = ((r - g) / d + 4) / 6;
        break;
    }
  }

  return { h, s, l };
}

/**
 * Convert HSL to RGB
 */
export function hslToRgb(
  h: number, s: number, l: number
): { r: number; g: number; b: number } {
  let r: number, g: number, b: number;

  if (s === 0) {
    r = g = b = l;
  } else {
    const hue2rgb = (p: number, q: number, t: number) => {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };

    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1 / 3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1 / 3);
  }

  return {
    r: Math.round(r * 255),
    g: Math.round(g * 255),
    b: Math.round(b * 255),
  };
}

/**
 * Adjust saturation of a pixel (for sponge tool)
 */
export function adjustSaturation(
  r: number, g: number, b: number,
  amount: number // -1 to 1 (negative = desaturate, positive = saturate)
): { r: number; g: number; b: number } {
  const { h, s, l } = rgbToHsl(r, g, b);

  // Apply the adjustment - saturate increases s, desaturate decreases s
  // Scale by current saturation for more natural effect (less effect on already saturated/desaturated colors)
  const effectiveAmount = amount * 0.3; // Scale down for subtle effect like Photoshop
  const newS = Math.max(0, Math.min(1, s + effectiveAmount));

  return hslToRgb(h, newS, l);
}

/**
 * Adjust luminosity of a pixel (for dodge/burn)
 */
export function adjustLuminosity(
  r: number, g: number, b: number,
  amount: number, // -1 to 1 (negative = burn, positive = dodge)
  range: 'shadows' | 'midtones' | 'highlights'
): { r: number; g: number; b: number } {
  const { h, s, l } = rgbToHsl(r, g, b);

  // Determine weight based on luminosity and target range
  let weight = 1;
  if (range === 'shadows') {
    weight = 1 - l; // More effect on dark pixels
  } else if (range === 'highlights') {
    weight = l; // More effect on light pixels
  } else {
    // Midtones: bell curve centered at 0.5
    weight = 1 - Math.abs(l - 0.5) * 2;
  }

  // Apply the adjustment
  const newL = Math.max(0, Math.min(1, l + amount * weight * 0.2));

  return hslToRgb(h, s, newL);
}

/**
 * Blend two colors with given alpha
 */
export function blendColors(
  srcR: number, srcG: number, srcB: number, srcA: number,
  dstR: number, dstG: number, dstB: number, dstA: number
): { r: number; g: number; b: number; a: number } {
  const outA = srcA + dstA * (1 - srcA);
  if (outA === 0) {
    return { r: 0, g: 0, b: 0, a: 0 };
  }

  const outR = (srcR * srcA + dstR * dstA * (1 - srcA)) / outA;
  const outG = (srcG * srcA + dstG * dstA * (1 - srcA)) / outA;
  const outB = (srcB * srcA + dstB * dstA * (1 - srcA)) / outA;

  return {
    r: Math.round(outR),
    g: Math.round(outG),
    b: Math.round(outB),
    a: outA,
  };
}

/**
 * Create a brush mask (radial gradient for softness)
 */
export function createBrushMask(
  size: number,
  hardness: number, // 0-100
  aspect = 1,
  rotation = 0,
  tipAssetId?: string,
): ImageData {
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });

  if (!ctx) {
    return new ImageData(size, size);
  }

  const image = ctx.createImageData(size, size);
  const radius = size / 2;
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const alpha = brushTipAlpha(
        (x + 0.5 - radius) / radius,
        (y + 0.5 - radius) / radius,
        hardness,
        aspect,
        rotation,
        tipAssetId,
      );
      const offset = (y * size + x) * 4;
      image.data[offset] = 255;
      image.data[offset + 1] = 255;
      image.data[offset + 2] = 255;
      image.data[offset + 3] = Math.round(alpha * 255);
    }
  }
  return image;
}

/**
 * Apply a brush stamp to a canvas at the given position
 */
export function applyBrushStamp(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  brushMask: ImageData,
  color: { r: number; g: number; b: number },
  opacity: number, // 0-1
  flow: number // 0-1
): void {
  const size = brushMask.width;
  const halfSize = size / 2;
  const startX = Math.floor(x - halfSize);
  const startY = Math.floor(y - halfSize);

  // Get the destination region
  const destData = ctx.getImageData(startX, startY, size, size);
  const maskData = brushMask.data;
  const destPixels = destData.data;

  const effectiveOpacity = opacity * flow;

  for (let i = 0; i < size * size; i++) {
    const maskAlpha = maskData[i * 4 + 3] / 255;
    if (maskAlpha === 0) continue;

    const pixelAlpha = maskAlpha * effectiveOpacity;
    const idx = i * 4;

    // Blend with existing pixel
    const srcA = pixelAlpha;
    const dstA = destPixels[idx + 3] / 255;

    const outA = srcA + dstA * (1 - srcA);
    if (outA > 0) {
      destPixels[idx] = (color.r * srcA + destPixels[idx] * dstA * (1 - srcA)) / outA;
      destPixels[idx + 1] = (color.g * srcA + destPixels[idx + 1] * dstA * (1 - srcA)) / outA;
      destPixels[idx + 2] = (color.b * srcA + destPixels[idx + 2] * dstA * (1 - srcA)) / outA;
      destPixels[idx + 3] = outA * 255;
    }
  }

  ctx.putImageData(destData, startX, startY);
}

/**
 * Calculate average color in a circular region
 */
export function getAverageColorInRegion(
  ctx: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number
): { r: number; g: number; b: number } {
  const x = Math.max(0, Math.floor(centerX - radius));
  const y = Math.max(0, Math.floor(centerY - radius));
  const size = Math.ceil(radius * 2);

  const imageData = ctx.getImageData(x, y, size, size);
  const data = imageData.data;

  let totalR = 0, totalG = 0, totalB = 0;
  let count = 0;

  for (let py = 0; py < size; py++) {
    for (let px = 0; px < size; px++) {
      const dx = px - radius;
      const dy = py - radius;
      if (dx * dx + dy * dy <= radius * radius) {
        const idx = (py * size + px) * 4;
        const alpha = data[idx + 3] / 255;
        if (alpha > 0) {
          totalR += data[idx] * alpha;
          totalG += data[idx + 1] * alpha;
          totalB += data[idx + 2] * alpha;
          count += alpha;
        }
      }
    }
  }

  if (count === 0) {
    return { r: 128, g: 128, b: 128 };
  }

  return {
    r: Math.round(totalR / count),
    g: Math.round(totalG / count),
    b: Math.round(totalB / count),
  };
}

/**
 * Sample pixels around a point for content-aware fill (spot heal)
 * Uses denser sampling at multiple radii for better coverage
 */
export function sampleSurroundingPixels(
  ctx: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  innerRadius: number,
  outerRadius: number,
  numSamples: number
): Array<{ x: number; y: number; r: number; g: number; b: number; a: number }> {
  const samples: Array<{ x: number; y: number; r: number; g: number; b: number; a: number }> = [];

  // Sample at multiple rings with increasing density at outer rings
  const numRings = 4;
  for (let ring = 0; ring < numRings; ring++) {
    const t = ring / (numRings - 1);
    const radius = innerRadius + (outerRadius - innerRadius) * t;
    // More samples at outer rings
    const ringsamples = Math.floor(numSamples * (1 + t));
    const angleStep = (Math.PI * 2) / ringsamples;
    // Offset angle for each ring to avoid aligned samples
    const angleOffset = ring * 0.3;

    for (let i = 0; i < ringsamples; i++) {
      const angle = i * angleStep + angleOffset;
      const sx = centerX + Math.cos(angle) * radius;
      const sy = centerY + Math.sin(angle) * radius;
      const pixel = samplePixel(ctx, sx, sy);
      samples.push({ x: sx, y: sy, ...pixel });
    }
  }

  return samples;
}

/**
 * Apply the donor-driven Patch tool with gradient-domain seamless cloning.
 *
 * Donor gradients carry texture and structure. Destination pixels around the
 * selection provide boundary conditions, so color and illumination are
 * reconstructed throughout the region instead of alpha-feathered at its edge.
 *
 * @param baseCtx - Context of the base processed image
 * @param destCtx - Context of the destination raster Paint layer
 * @param selectionCtx - Context of the selection mask (the solve domain)
 * @param offset - Offset from destination to source (source = dest + offset)
 * @param bounds - Bounding box of the selection in image coordinates
 */
export async function applyPatch(
  baseCtx: CanvasRenderingContext2D,
  destCtx: CanvasRenderingContext2D,
  selectionCtx: CanvasRenderingContext2D,
  offset: { x: number; y: number },
  bounds: { x: number; y: number; width: number; height: number }
): Promise<void> {
  const { x, y, width, height } = bounds;

  // Image dimensions
  const imageWidth = baseCtx.canvas.width;
  const imageHeight = baseCtx.canvas.height;

  // One destination pixel around the selection supplies the Poisson boundary.
  const padding = 1;
  const expandedX = Math.max(0, Math.floor(x) - padding);
  const expandedY = Math.max(0, Math.floor(y) - padding);
  const expandedRight = Math.min(imageWidth, Math.floor(x + width) + padding);
  const expandedBottom = Math.min(imageHeight, Math.floor(y + height) + padding);
  const expandedWidth = expandedRight - expandedX;
  const expandedHeight = expandedBottom - expandedY;

  if (expandedWidth <= 0 || expandedHeight <= 0) {
    return;
  }

  // Calculate source region (destination + offset)
  const srcX = expandedX + offset.x;
  const srcY = expandedY + offset.y;

  // Clamp source to image bounds
  const clampedSrcX = Math.max(0, Math.floor(srcX));
  const clampedSrcY = Math.max(0, Math.floor(srcY));
  const srcRight = Math.min(imageWidth, Math.floor(srcX + expandedWidth));
  const srcBottom = Math.min(imageHeight, Math.floor(srcY + expandedHeight));

  // Adjusted dimensions based on source clamping
  const actualWidth = Math.min(expandedWidth, srcRight - clampedSrcX);
  const actualHeight = Math.min(expandedHeight, srcBottom - clampedSrcY);

  if (actualWidth <= 0 || actualHeight <= 0) {
    return;
  }

  // Offset within expanded region due to source clamping
  const destOffsetX = Math.max(0, Math.floor(-srcX));
  const destOffsetY = Math.max(0, Math.floor(-srcY));

  // Destination region coordinates
  const destRegionX = expandedX + destOffsetX;
  const destRegionY = expandedY + destOffsetY;

  // === BATCH getImageData calls (4 total instead of 6) ===
  // Get all needed data in one batch to minimize GPU→CPU syncs
  const baseSourceData = baseCtx.getImageData(clampedSrcX, clampedSrcY, actualWidth, actualHeight);
  const layerSourceData = destCtx.getImageData(clampedSrcX, clampedSrcY, actualWidth, actualHeight);
  const baseDestData = baseCtx.getImageData(destRegionX, destRegionY, actualWidth, actualHeight);
  const selectionData = selectionCtx.getImageData(destRegionX, destRegionY, actualWidth, actualHeight);

  const sourcePixels = baseSourceData.data;
  const layerSrcPixels = layerSourceData.data;
  const baseDestPixels = baseDestData.data;

  // Composite the current Paint layer over the base for source sampling
  // Also composite for destination in the same loop (saves a pass)
  const layerDestData = destCtx.getImageData(destRegionX, destRegionY, actualWidth, actualHeight);
  const layerDestPixels = layerDestData.data;

  for (let i = 0; i < sourcePixels.length; i += 4) {
    // Composite source region
    const layerSrcA = layerSrcPixels[i + 3] / 255;
    if (layerSrcA > 0) {
      const baseSrcA = sourcePixels[i + 3] / 255;
      const outSrcA = layerSrcA + baseSrcA * (1 - layerSrcA);
      if (outSrcA > 0) {
        const invLayerSrcA = 1 - layerSrcA;
        sourcePixels[i] = (layerSrcPixels[i] * layerSrcA + sourcePixels[i] * baseSrcA * invLayerSrcA) / outSrcA;
        sourcePixels[i + 1] = (layerSrcPixels[i + 1] * layerSrcA + sourcePixels[i + 1] * baseSrcA * invLayerSrcA) / outSrcA;
        sourcePixels[i + 2] = (layerSrcPixels[i + 2] * layerSrcA + sourcePixels[i + 2] * baseSrcA * invLayerSrcA) / outSrcA;
        sourcePixels[i + 3] = outSrcA * 255;
      }
    }

    // Composite destination region
    const layerDstA = layerDestPixels[i + 3] / 255;
    if (layerDstA > 0) {
      const baseDstA = baseDestPixels[i + 3] / 255;
      const outDstA = layerDstA + baseDstA * (1 - layerDstA);
      if (outDstA > 0) {
        const invLayerDstA = 1 - layerDstA;
        baseDestPixels[i] = (layerDestPixels[i] * layerDstA + baseDestPixels[i] * baseDstA * invLayerDstA) / outDstA;
        baseDestPixels[i + 1] = (layerDestPixels[i + 1] * layerDstA + baseDestPixels[i + 1] * baseDstA * invLayerDstA) / outDstA;
        baseDestPixels[i + 2] = (layerDestPixels[i + 2] * layerDstA + baseDestPixels[i + 2] * baseDstA * invLayerDstA) / outDstA;
        baseDestPixels[i + 3] = outDstA * 255;
      }
    }
  }

  const selectionAlpha = new Uint8ClampedArray(actualWidth * actualHeight);
  for (let i = 3, pixel = 0; i < selectionData.data.length; i += 4, pixel++) {
    selectionAlpha[pixel] = selectionData.data[i];
  }
  const reconstructed = await solveSeamlessPatch(
    sourcePixels,
    baseDestPixels,
    selectionAlpha,
    actualWidth,
    actualHeight,
  );

  // Reuse layerDestData as the sparse raster-layer output. Pixels outside the
  // selection remain untouched rather than baking the surrounding rectangle.
  const destPixels = layerDestData.data;
  for (let i = 0; i < reconstructed.length; i += 4) {
    // selectionAlpha may have been transferred and detached by the worker.
    if (selectionData.data[i + 3] === 0) continue;
    destPixels[i] = reconstructed[i];
    destPixels[i + 1] = reconstructed[i + 1];
    destPixels[i + 2] = reconstructed[i + 2];
    destPixels[i + 3] = reconstructed[i + 3];
  }

  destCtx.putImageData(layerDestData, destRegionX, destRegionY);
}

/**
 * Interpolate pixel color based on distance-weighted surrounding samples
 * Uses squared inverse distance for smoother falloff (more Photoshop-like)
 */
export function interpolateFromSamples(
  targetX: number,
  targetY: number,
  samples: Array<{ x: number; y: number; r: number; g: number; b: number; a: number }>
): { r: number; g: number; b: number; a: number } {
  let totalWeight = 0;
  let r = 0, g = 0, b = 0, a = 0;

  for (const sample of samples) {
    const dx = targetX - sample.x;
    const dy = targetY - sample.y;
    const distSq = dx * dx + dy * dy;
    // Squared inverse distance gives smoother interpolation
    const weight = 1 / (distSq + 1);

    r += sample.r * weight;
    g += sample.g * weight;
    b += sample.b * weight;
    a += sample.a * weight;
    totalWeight += weight;
  }

  if (totalWeight === 0) {
    return { r: 128, g: 128, b: 128, a: 255 };
  }

  return {
    r: Math.round(r / totalWeight),
    g: Math.round(g / totalWeight),
    b: Math.round(b / totalWeight),
    a: Math.round(a / totalWeight),
  };
}
