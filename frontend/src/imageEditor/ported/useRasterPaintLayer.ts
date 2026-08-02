/**
 * One raster Paint layer: color paint plus the inherited pixel-reading
 * engines (clone, heal, patch, dodge/burn, sponge, blur/sharpen), all applied
 * through the active selection mask.
 *
 * Ported from the retired editor on 2026-07-27, with imports repointed here.
 */

import { ref, shallowRef, markRaw } from 'vue';
import type { Size, Point } from './geometry';
import type { BrushSettings } from './geometry';
import {
  createBrushMask,
  adjustLuminosity,
  adjustSaturation,
  sampleRegion,
  sampleSurroundingPixels,
  interpolateFromSamples,
  applyPatch,
} from './pixelOps';
import { advanceStroke } from './strokeSpacing';
import { applyLocalBlur, applyLocalSharpen } from './imageFilters';
import type { GradientPaint } from './shapeTypes';
import type { PaintGradientType } from '../stack/paintEngineSettings';
import {
  rasterGradientStops,
  reflectedGradientStops,
} from '../stack/rasterGradient';

/**
 * Composable for managing one raster Paint layer.
 */
export function useRasterPaintLayer() {
  // The Paint layer canvas (stores all pixel edits)
  const layerCanvas = shallowRef<HTMLCanvasElement | null>(null);
  const layerCtx = shallowRef<CanvasRenderingContext2D | null>(null);

  // Layer size (should match image size)
  const layerSize = ref<Size | null>(null);

  // Brush state
  const currentBrushMask = shallowRef<ImageData | null>(null);

  // Small LRU: direction-driven tips revisit quantized angles constantly.
  const brushMaskCache = new Map<string, ImageData>();

  // Clone stamp state
  const cloneSourceCanvas = shallowRef<HTMLCanvasElement | null>(null);
  const cloneOffset = ref<Point | null>(null);

  // Selection mask reference (for constraining operations)
  let selectionMaskCtx: CanvasRenderingContext2D | null = null;

  // Reusable work canvas for blur/sharpen (avoids allocation per dab)
  let workCanvas: HTMLCanvasElement | null = null;
  let workCtx: CanvasRenderingContext2D | null = null;
  let workCanvasSize = 0;

  // Stroke tracking for spacing
  let lastStrokePoint: Point | null = null;

  /**
   * Return spatially spaced dabs and keep the unconsumed distance.
   *
   * `lastStrokePoint` is deliberately the last DAB, not the last pointer event.
   * Sub-spacing events therefore accumulate until they cover one interval
   * instead of each becoming another dose of dodge/burn/sponge.
   */
  function brushStrokePoints(point: Point, size: number, spacing: number): Point[] {
    const advanced = advanceStroke(
      lastStrokePoint,
      point,
      size * (spacing / 100)
    );
    lastStrokePoint = advanced.lastDab;
    return advanced.points;
  }

  /**
   * Set the selection mask canvas for constraining operations
   */
  function setSelectionMask(ctx: CanvasRenderingContext2D | null): void {
    selectionMaskCtx = ctx;
  }

  /**
   * Get selection alpha at a specific pixel (0 = not selected, 1 = fully selected)
   */
  function getSelectionAlpha(x: number, y: number): number {
    if (!selectionMaskCtx) return 1; // No selection = everything selected

    const width = selectionMaskCtx.canvas.width;
    const height = selectionMaskCtx.canvas.height;

    if (x < 0 || x >= width || y < 0 || y >= height) return 0;

    const pixel = selectionMaskCtx.getImageData(Math.floor(x), Math.floor(y), 1, 1);
    // Selection mask uses alpha channel (or could use any channel since it's grayscale)
    return pixel.data[3] / 255;
  }

  /**
   * Get selection mask data for a region
   */
  function getSelectionMaskRegion(x: number, y: number, w: number, h: number): Uint8Array | null {
    if (!selectionMaskCtx) return null; // No selection = no mask needed

    const maskData = selectionMaskCtx.getImageData(x, y, w, h);
    // Return just the alpha values
    const alphas = new Uint8Array(w * h);
    for (let i = 0; i < alphas.length; i++) {
      alphas[i] = maskData.data[i * 4 + 3];
    }
    return alphas;
  }

  /**
   * Initialize or resize the Paint layer
   */
  function initLayer(size: Size): void {
    if (
      layerCanvas.value &&
      layerSize.value?.width === size.width &&
      layerSize.value?.height === size.height
    ) {
      return;
    }

    const canvas = document.createElement('canvas');
    canvas.width = size.width;
    canvas.height = size.height;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });

    if (!ctx) {
      throw new Error('Failed to get Paint layer canvas context');
    }

    // If we have existing content, copy it
    if (layerCanvas.value && layerCtx.value) {
      ctx.drawImage(layerCanvas.value, 0, 0);
    }

    layerCanvas.value = canvas;
    layerCtx.value = ctx;
    layerSize.value = { ...size };
  }

  /**
   * Clear the Paint layer
   */
  function clearLayer(): void {
    if (!layerCtx.value || !layerSize.value) return;
    layerCtx.value.clearRect(0, 0, layerSize.value.width, layerSize.value.height);
  }

  /**
   * Load Paint layer from data URL (used for project deserialization)
   */
  async function loadFromDataUrl(dataUrl: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        if (!layerCtx.value || !layerCanvas.value) {
          reject(new Error('Paint layer canvas not initialized before restore'));
          return;
        }

        layerCtx.value.clearRect(
          0,
          0,
          layerCanvas.value.width,
          layerCanvas.value.height
        );
        layerCtx.value.drawImage(
          img,
          0,
          0,
          layerCanvas.value.width,
          layerCanvas.value.height
        );
        resolve();
      };
      img.onerror = reject;
      img.src = dataUrl;
    });
  }

  /**
   * Export Paint layer to data URL (used for project serialization)
   */
  function toDataUrl(): string | null {
    if (!layerCanvas.value) return null;
    return layerCanvas.value.toDataURL('image/png');
  }

  /**
   * Create a fast canvas snapshot for history (drawImage clone, ~1ms vs 100-300ms for PNG).
   * markRaw prevents Vue from deeply proxying the canvas DOM element.
   */
  function toSnapshot(): HTMLCanvasElement | null {
    if (!layerCanvas.value || !layerSize.value) return null;
    const snap = document.createElement('canvas');
    snap.width = layerSize.value.width;
    snap.height = layerSize.value.height;
    const ctx = snap.getContext('2d');
    if (ctx) {
      ctx.drawImage(layerCanvas.value, 0, 0);
    }
    return markRaw(snap);
  }

  /**
   * Restore from a canvas snapshot (fast, ~1ms)
   */
  function loadFromSnapshot(snapshot: HTMLCanvasElement): void {
    if (!layerCtx.value || !layerSize.value) return;
    layerCtx.value.clearRect(0, 0, layerSize.value.width, layerSize.value.height);
    layerCtx.value.drawImage(snapshot, 0, 0);
  }

  /**
   * Get or create brush mask for current settings (cached by size+hardness)
   */
  function getBrushMask(
    size: number,
    hardness: number,
    aspect = 1,
    rotation = 0,
    tipAssetId?: string,
  ): ImageData {
    const ceilSize = Math.ceil(size);
    const quantizedAspect = Math.round(aspect * 100) / 100;
    const quantizedRotation = Math.round(rotation * 2) / 2;
    const key = `${ceilSize},${hardness},${quantizedAspect},${quantizedRotation},${tipAssetId ?? ''}`;
    const cached = brushMaskCache.get(key);
    if (cached) {
      brushMaskCache.delete(key);
      brushMaskCache.set(key, cached);
      currentBrushMask.value = cached;
      return cached;
    }
    const mask = createBrushMask(
      ceilSize, hardness, quantizedAspect, quantizedRotation, tipAssetId,
    );
    brushMaskCache.set(key, mask);
    if (brushMaskCache.size > 96) {
      const oldest = brushMaskCache.keys().next().value;
      if (oldest !== undefined) brushMaskCache.delete(oldest);
    }
    currentBrushMask.value = mask;
    return mask;
  }

  /**
   * Set clone source from the processed image
   */
  function setCloneSource(
    sourceCanvas: HTMLCanvasElement,
    sourcePoint: Point,
    destinationPoint: Point
  ): void {
    // Store the source canvas reference
    cloneSourceCanvas.value = sourceCanvas;

    // Calculate offset from destination to source
    cloneOffset.value = {
      x: sourcePoint.x - destinationPoint.x,
      y: sourcePoint.y - destinationPoint.y,
    };
  }

  /**
   * Apply clone stamp at position
   * Uses Photoshop-style blending: opacity caps the stroke, flow controls buildup
   */
  function applyCloneStamp(
    sourceCanvas: HTMLCanvasElement,
    destPoint: Point,
    brushSettings: BrushSettings
  ): void {
    if (!layerCtx.value || !cloneOffset.value) return;

    const { size, hardness, opacity, flow, spacing, aspect, rotation, tipAssetId } = brushSettings;
    const brushMask = getBrushMask(size, hardness, aspect, rotation, tipAssetId);

    const points = brushStrokePoints(destPoint, size, spacing);

    // Get source canvas context
    const sourceCtx = sourceCanvas.getContext('2d');
    if (!sourceCtx) return;

    const halfSize = size / 2;
    const maxOpacity = opacity / 100;
    const flowRate = flow / 100;

    for (const point of points) {
      const srcX = point.x + cloneOffset.value.x;
      const srcY = point.y + cloneOffset.value.y;

      // Sample from source (the combined base + current Paint layer)
      const sourceData = sampleRegion(
        sourceCtx,
        srcX - halfSize,
        srcY - halfSize,
        size,
        size
      );

      // Apply to Paint layer with brush mask
      const destX = Math.floor(point.x - halfSize);
      const destY = Math.floor(point.y - halfSize);

      const destData = layerCtx.value!.getImageData(destX, destY, size, size);
      const maskData = brushMask.data;
      const srcPixels = sourceData.data;
      const destPixels = destData.data;

      // Get selection mask for this region
      const selectionMask = getSelectionMaskRegion(destX, destY, size, size);

      for (let i = 0; i < maskData.length; i += 4) {
        const pixelIdx = i / 4;

        // Apply selection mask if present
        const selectionAlpha = selectionMask ? selectionMask[pixelIdx] / 255 : 1;
        if (selectionAlpha === 0) continue;

        // Brush mask determines the shape
        const brushAlpha = maskData[i + 3] / 255;
        if (brushAlpha === 0) continue;

        // Blend strength for this dab: brush shape * flow * opacity * selection
        const blendStrength = brushAlpha * flowRate * maxOpacity * selectionAlpha;
        if (blendStrength === 0) continue;

        // Standard alpha compositing: new over old
        const srcA = blendStrength;
        const dstA = destPixels[i + 3] / 255;
        const outA = srcA + dstA * (1 - srcA);

        if (outA > 0) {
          // Blend colors with proper alpha weighting
          destPixels[i] = (srcPixels[i] * srcA + destPixels[i] * dstA * (1 - srcA)) / outA;
          destPixels[i + 1] = (srcPixels[i + 1] * srcA + destPixels[i + 1] * dstA * (1 - srcA)) / outA;
          destPixels[i + 2] = (srcPixels[i + 2] * srcA + destPixels[i + 2] * dstA * (1 - srcA)) / outA;
          destPixels[i + 3] = outA * 255;
        }
      }

      layerCtx.value!.putImageData(destData, destX, destY);
    }
  }

  /**
   * Apply spot heal at position
   * Uses texture-preserving healing similar to Photoshop's spot healing brush
   */
  function applySpotHeal(
    sourceCanvas: HTMLCanvasElement,
    point: Point,
    brushSettings: BrushSettings
  ): void {
    if (!layerCtx.value) return;

    const sourceCtx = sourceCanvas.getContext('2d');
    if (!sourceCtx) return;

    const { size: brushSize, hardness, opacity, flow, spacing, aspect, rotation, tipAssetId } = brushSettings;
    const points = brushStrokePoints(point, brushSize, spacing);
    if (points.length === 0) return;

    const radius = brushSize / 2;
    const halfSize = brushSize / 2;
    const effectiveOpacity = (opacity / 100) * (flow / 100);
    const brushMask = getBrushMask(brushSize, hardness, aspect, rotation, tipAssetId);
    const maskData = brushMask.data;

    for (const dab of points) {
      const destX = Math.floor(dab.x - halfSize);
      const destY = Math.floor(dab.y - halfSize);

      // Sample surrounding pixels from a wider area for better color matching
      const samples = sampleSurroundingPixels(
        sourceCtx,
        dab.x,
        dab.y,
        radius * 1.2,  // Start sampling just outside the brush
        radius * 3,    // Sample from a wider surrounding area
        24             // More samples for smoother results
      );

      // Get the original pixels to preserve texture/luminosity variation
      const originalData = sourceCtx.getImageData(destX, destY, brushSize, brushSize);
      const originalPixels = originalData.data;

      // Create the healed region
      const destData = layerCtx.value.getImageData(destX, destY, brushSize, brushSize);
      const destPixels = destData.data;
      const selectionMask = getSelectionMaskRegion(destX, destY, brushSize, brushSize);

      // Calculate average luminosity of samples for texture preservation
      let sampleLumSum = 0;
      for (const sample of samples) {
        sampleLumSum += (sample.r * 0.299 + sample.g * 0.587 + sample.b * 0.114);
      }
      const avgSampleLum = sampleLumSum / samples.length;

      for (let py = 0; py < brushSize; py++) {
        for (let px = 0; px < brushSize; px++) {
          const idx = (py * brushSize + px) * 4;
          const pixelIdx = idx / 4;
          const selectionAlpha = selectionMask ? selectionMask[pixelIdx] / 255 : 1;
          const maskAlpha =
            (maskData[idx + 3] / 255) * effectiveOpacity * selectionAlpha;
          if (maskAlpha === 0) continue;

          const targetX = destX + px;
          const targetY = destY + py;

          // Interpolate base color from surrounding samples
          const interpolated = interpolateFromSamples(targetX, targetY, samples);

          // Get original pixel luminosity for texture preservation
          const origLum = originalPixels[idx] * 0.299 + originalPixels[idx + 1] * 0.587 + originalPixels[idx + 2] * 0.114;

          // Preserve some of the original texture variation
          // This prevents the "flat blob" look by maintaining local luminosity differences
          const lumDiff = origLum - avgSampleLum;
          const texturePreserve = 0.3; // How much original texture to preserve (0-1)
          const lumAdjust = lumDiff * texturePreserve;

          // Apply luminosity adjustment to interpolated color
          const finalR = Math.max(0, Math.min(255, interpolated.r + lumAdjust));
          const finalG = Math.max(0, Math.min(255, interpolated.g + lumAdjust));
          const finalB = Math.max(0, Math.min(255, interpolated.b + lumAdjust));

          // Blend with existing using the soft mask
          const srcA = maskAlpha;
          const dstA = destPixels[idx + 3] / 255;
          const outA = srcA + dstA * (1 - srcA);

          if (outA > 0) {
            destPixels[idx] = (finalR * srcA + destPixels[idx] * dstA * (1 - srcA)) / outA;
            destPixels[idx + 1] = (finalG * srcA + destPixels[idx + 1] * dstA * (1 - srcA)) / outA;
            destPixels[idx + 2] = (finalB * srcA + destPixels[idx + 2] * dstA * (1 - srcA)) / outA;
            destPixels[idx + 3] = outA * 255;
          }
        }
      }

      layerCtx.value.putImageData(destData, destX, destY);
    }
  }

  /**
   * Apply dodge or burn at position
   */
  function applyDodgeBurn(
    sourceCanvas: HTMLCanvasElement,
    point: Point,
    brushSettings: BrushSettings,
    exposure: number, // 0-100
    range: 'shadows' | 'midtones' | 'highlights',
    isDodge: boolean
  ): void {
    if (!layerCtx.value) return;

    const sourceCtx = sourceCanvas.getContext('2d');
    if (!sourceCtx) return;

    const { size, hardness, opacity, flow, spacing, aspect, rotation, tipAssetId } = brushSettings;
    const brushMask = getBrushMask(size, hardness, aspect, rotation, tipAssetId);

    const points = brushStrokePoints(point, size, spacing);

    const halfSize = size / 2;
    const amount = (exposure / 100) * (isDodge ? 1 : -1);
    const effectiveOpacity = (opacity / 100) * (flow / 100);

    for (const p of points) {
      const destX = Math.floor(p.x - halfSize);
      const destY = Math.floor(p.y - halfSize);

      // Sample from source (combined image + Paint layer)
      const sourceData = sampleRegion(sourceCtx, destX, destY, size, size);
      const destData = layerCtx.value!.getImageData(destX, destY, size, size);
      const maskData = brushMask.data;
      const srcPixels = sourceData.data;
      const destPixels = destData.data;

      // Get selection mask for this region
      const selectionMask = getSelectionMaskRegion(destX, destY, size, size);

      for (let i = 0; i < maskData.length; i += 4) {
        const pixelIdx = i / 4;

        // Apply selection mask if present
        const selectionAlpha = selectionMask ? selectionMask[pixelIdx] / 255 : 1;
        if (selectionAlpha === 0) continue;

        const maskAlpha = (maskData[i + 3] / 255) * effectiveOpacity * selectionAlpha;
        if (maskAlpha === 0) continue;

        // The dab bakes the FULL-strength adjustment; maskAlpha (brush shape ×
        // flow × pen pressure) accumulates only the MASK coverage. Always
        // derive the preview color from the frozen stroke source: adjusting
        // the previous dab's already-adjusted RGB made overlaps compound
        // toward white/black, while the committed parametric region applies
        // one full-strength adjustment through the accumulated mask.
        const adjusted = adjustLuminosity(
          srcPixels[i],
          srcPixels[i + 1],
          srcPixels[i + 2],
          amount,
          range,
        );

        // Write to Paint layer
        const srcA = maskAlpha;
        const dstA = destPixels[i + 3] / 255;
        const outA = srcA + dstA * (1 - srcA);

        if (outA > 0) {
          destPixels[i] = (adjusted.r * srcA + destPixels[i] * dstA * (1 - srcA)) / outA;
          destPixels[i + 1] = (adjusted.g * srcA + destPixels[i + 1] * dstA * (1 - srcA)) / outA;
          destPixels[i + 2] = (adjusted.b * srcA + destPixels[i + 2] * dstA * (1 - srcA)) / outA;
          destPixels[i + 3] = outA * 255;
        }
      }

      layerCtx.value!.putImageData(destData, destX, destY);
    }
  }

  /**
   * Apply sponge (saturation) brush at position
   */
  function applySaturationBrush(
    sourceCanvas: HTMLCanvasElement,
    point: Point,
    brushSettings: BrushSettings,
    strength: number, // 0-100
    isSaturate: boolean
  ): void {
    if (!layerCtx.value) return;

    const sourceCtx = sourceCanvas.getContext('2d');
    if (!sourceCtx) return;

    const { size, hardness, opacity, flow, spacing, aspect, rotation, tipAssetId } = brushSettings;
    const brushMask = getBrushMask(size, hardness, aspect, rotation, tipAssetId);

    const points = brushStrokePoints(point, size, spacing);

    const halfSize = size / 2;
    const amount = (strength / 100) * (isSaturate ? 1 : -1);
    const effectiveOpacity = (opacity / 100) * (flow / 100);

    for (const p of points) {
      const destX = Math.floor(p.x - halfSize);
      const destY = Math.floor(p.y - halfSize);

      // Sample from source (combined image + Paint layer)
      const sourceData = sampleRegion(sourceCtx, destX, destY, size, size);
      const destData = layerCtx.value!.getImageData(destX, destY, size, size);
      const maskData = brushMask.data;
      const srcPixels = sourceData.data;
      const destPixels = destData.data;

      // Get selection mask for this region
      const selectionMask = getSelectionMaskRegion(destX, destY, size, size);

      for (let i = 0; i < maskData.length; i += 4) {
        const pixelIdx = i / 4;

        // Apply selection mask if present
        const selectionAlpha = selectionMask ? selectionMask[pixelIdx] / 255 : 1;
        if (selectionAlpha === 0) continue;

        const maskAlpha = (maskData[i + 3] / 255) * effectiveOpacity * selectionAlpha;
        if (maskAlpha === 0) continue;

        // Get the current color (prefer Paint layer if has content, else source)
        let r = srcPixels[i];
        let g = srcPixels[i + 1];
        let b = srcPixels[i + 2];

        if (destPixels[i + 3] > 0) {
          // Blend existing Paint layer data
          const existingAlpha = destPixels[i + 3] / 255;
          r = destPixels[i] * existingAlpha + srcPixels[i] * (1 - existingAlpha);
          g = destPixels[i + 1] * existingAlpha + srcPixels[i + 1] * (1 - existingAlpha);
          b = destPixels[i + 2] * existingAlpha + srcPixels[i + 2] * (1 - existingAlpha);
        }

        // Full-strength adjustment, attenuated only via compositing alpha —
        // mirrors the committed region's parametric render (see dodge/burn).
        const adjusted = adjustSaturation(r, g, b, amount);

        // Write to Paint layer
        const srcA = maskAlpha;
        const dstA = destPixels[i + 3] / 255;
        const outA = srcA + dstA * (1 - srcA);

        if (outA > 0) {
          destPixels[i] = (adjusted.r * srcA + destPixels[i] * dstA * (1 - srcA)) / outA;
          destPixels[i + 1] = (adjusted.g * srcA + destPixels[i + 1] * dstA * (1 - srcA)) / outA;
          destPixels[i + 2] = (adjusted.b * srcA + destPixels[i + 2] * dstA * (1 - srcA)) / outA;
          destPixels[i + 3] = outA * 255;
        }
      }

      layerCtx.value!.putImageData(destData, destX, destY);
    }
  }

  /**
   * Paint pixels from an already-adjusted copy of the stroke source through
   * the brush mask.
   *
   * Retouch adjustment brushes use this instead of maintaining a second,
   * approximate implementation of dodge/burn/sponge/blur/sharpen. The layer's
   * alpha is therefore the accumulated brush coverage, while its RGB is the
   * exact parametric result that will be recomputed after release.
   */
  function applyAdjustedSourceBrush(
    adjustedSource: HTMLCanvasElement,
    point: Point,
    brushSettings: BrushSettings,
  ): void {
    if (!layerCtx.value) return;

    const sourceCtx = adjustedSource.getContext('2d');
    if (!sourceCtx) return;

    const { size, hardness, opacity, flow, spacing, aspect, rotation, tipAssetId } = brushSettings;
    const brushMask = getBrushMask(size, hardness, aspect, rotation, tipAssetId);
    const points = brushStrokePoints(point, size, spacing);
    const brushSize = Math.ceil(size);
    const halfSize = size / 2;
    const effectiveOpacity = (opacity / 100) * (flow / 100);

    for (const dab of points) {
      const destX = Math.floor(dab.x - halfSize);
      const destY = Math.floor(dab.y - halfSize);
      const sourceData = sampleRegion(sourceCtx, destX, destY, brushSize, brushSize);
      const destData = layerCtx.value.getImageData(destX, destY, brushSize, brushSize);
      const selectionMask = getSelectionMaskRegion(destX, destY, brushSize, brushSize);

      for (let i = 0; i < brushMask.data.length; i += 4) {
        const pixel = i / 4;
        const selectionAlpha = selectionMask ? selectionMask[pixel] / 255 : 1;
        const sourceAlpha = sourceData.data[i + 3] / 255;
        const brushAlpha = (brushMask.data[i + 3] / 255)
          * effectiveOpacity
          * selectionAlpha;
        if (brushAlpha === 0 || sourceAlpha === 0) continue;

        // The persisted compositor uses min(adjusted source alpha, brush mask).
        // Accumulate the mask by source-over, then apply that same cap here so
        // partially transparent images preview exactly as they will re-render.
        const dstA = destData.data[i + 3] / 255;
        const outA = dstA >= sourceAlpha
          ? sourceAlpha
          : Math.min(sourceAlpha, brushAlpha + dstA * (1 - brushAlpha));
        destData.data[i] = sourceData.data[i];
        destData.data[i + 1] = sourceData.data[i + 1];
        destData.data[i + 2] = sourceData.data[i + 2];
        destData.data[i + 3] = outA * 255;
      }

      layerCtx.value.putImageData(destData, destX, destY);
    }
  }

  /**
   * Get or resize a reusable work canvas for blur/sharpen operations.
   * Uses a small region canvas sized to brushSize + padding instead of full image.
   */
  function getWorkCanvas(neededSize: number): { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D } {
    if (!workCanvas || workCanvasSize < neededSize) {
      workCanvas = document.createElement('canvas');
      workCanvas.width = neededSize;
      workCanvas.height = neededSize;
      workCtx = workCanvas.getContext('2d', { willReadFrequently: true })!;
      workCanvasSize = neededSize;
    } else if (workCanvas.width !== neededSize || workCanvas.height !== neededSize) {
      workCanvas.width = neededSize;
      workCanvas.height = neededSize;
    }
    return { canvas: workCanvas, ctx: workCtx! };
  }

  /**
   * Apply blur or sharpen brush at position using a small local-region work canvas
   */
  function applyBlurSharpenBrush(
    sourceCanvas: HTMLCanvasElement,
    point: Point,
    brushSettings: BrushSettings,
    strength: number,
    isBlur: boolean
  ): void {
    if (!layerCtx.value) return;

    const sourceCtx = sourceCanvas.getContext('2d');
    if (!sourceCtx) return;

    const { size, hardness, opacity, flow, spacing, aspect, rotation, tipAssetId } = brushSettings;
    const brushMask = getBrushMask(size, hardness, aspect, rotation, tipAssetId);

    const points = brushStrokePoints(point, size, spacing);

    const brushBlend = (opacity / 100) * (flow / 100);
    const blurRadius = isBlur ? Math.max(1, Math.ceil(strength / 25)) : 1;
    const padding = blurRadius + 2; // Extra padding for filter kernel
    const regionSize = Math.ceil(size) + padding * 2;
    const halfSize = size / 2;

    // Get a reusable work canvas sized to the region (not the full image)
    const { ctx: localCtx } = getWorkCanvas(regionSize);

    for (const p of points) {
      // Calculate the region bounds in image coordinates
      const regionX = Math.max(0, Math.floor(p.x - halfSize) - padding);
      const regionY = Math.max(0, Math.floor(p.y - halfSize) - padding);
      const maxX = Math.min(sourceCanvas.width, Math.ceil(p.x + halfSize) + padding);
      const maxY = Math.min(sourceCanvas.height, Math.ceil(p.y + halfSize) + padding);
      const regionW = maxX - regionX;
      const regionH = maxY - regionY;

      if (regionW <= 0 || regionH <= 0) continue;

      // Draw only the needed region from source + Paint layer into the small work canvas
      localCtx.clearRect(0, 0, regionW, regionH);
      localCtx.drawImage(sourceCanvas, regionX, regionY, regionW, regionH, 0, 0, regionW, regionH);
      if (layerCanvas.value) {
        localCtx.drawImage(layerCanvas.value, regionX, regionY, regionW, regionH, 0, 0, regionW, regionH);
      }

      // Apply blur/sharpen on the local region canvas
      // Adjust point coordinates to be relative to the region
      const localX = p.x - regionX;
      const localY = p.y - regionY;

      if (isBlur) {
        applyLocalBlur(
          localCtx,
          localX,
          localY,
          size,
          brushMask,
          blurRadius,
          brushBlend * (strength / 100)
        );
      } else {
        applyLocalSharpen(
          localCtx,
          localX,
          localY,
          size,
          brushMask,
          strength,
          brushBlend
        );
      }

      // Copy the processed region back to Paint layer, respecting selection
      const destX = Math.floor(p.x - halfSize);
      const destY = Math.floor(p.y - halfSize);
      // Read back just the brush-sized area from the local canvas
      const localReadX = Math.floor(localX - halfSize);
      const localReadY = Math.floor(localY - halfSize);
      const processedData = localCtx.getImageData(localReadX, localReadY, size, size);

      // Get selection mask for this region
      const selectionMask = getSelectionMaskRegion(destX, destY, size, size);

      if (selectionMask) {
        const destData = layerCtx.value!.getImageData(destX, destY, size, size);
        const processedPixels = processedData.data;
        const destPixels = destData.data;

        for (let i = 0; i < processedPixels.length; i += 4) {
          const pixelIdx = i / 4;
          const selectionAlpha = selectionMask[pixelIdx] / 255;
          if (selectionAlpha === 0) continue;

          if (selectionAlpha >= 1) {
            destPixels[i] = processedPixels[i];
            destPixels[i + 1] = processedPixels[i + 1];
            destPixels[i + 2] = processedPixels[i + 2];
            destPixels[i + 3] = processedPixels[i + 3];
          } else {
            destPixels[i] = destPixels[i] * (1 - selectionAlpha) + processedPixels[i] * selectionAlpha;
            destPixels[i + 1] = destPixels[i + 1] * (1 - selectionAlpha) + processedPixels[i + 1] * selectionAlpha;
            destPixels[i + 2] = destPixels[i + 2] * (1 - selectionAlpha) + processedPixels[i + 2] * selectionAlpha;
            destPixels[i + 3] = destPixels[i + 3] * (1 - selectionAlpha) + processedPixels[i + 3] * selectionAlpha;
          }
        }
        layerCtx.value!.putImageData(destData, destX, destY);
      } else {
        layerCtx.value!.putImageData(processedData, destX, destY);
      }
    }
  }

  /**
   * Apply blur brush at position
   */
  function applyBlurBrush(
    sourceCanvas: HTMLCanvasElement,
    point: Point,
    brushSettings: BrushSettings,
    strength: number
  ): void {
    applyBlurSharpenBrush(sourceCanvas, point, brushSettings, strength, true);
  }

  /**
   * Apply sharpen brush at position
   */
  function applySharpenBrush(
    sourceCanvas: HTMLCanvasElement,
    point: Point,
    brushSettings: BrushSettings,
    strength: number
  ): void {
    applyBlurSharpenBrush(sourceCanvas, point, brushSettings, strength, false);
  }

  /**
   * Apply paint brush at position (paints with solid color)
   */
  function applyPaintBrush(
    point: Point,
    brushSettings: BrushSettings,
    color: { r: number; g: number; b: number; a?: number }
  ): void {
    if (!layerCtx.value) return;

    const { size, spacing } = brushSettings;
    const points = brushStrokePoints(point, size, spacing);

    for (const dab of points) applyPaintDab(dab, brushSettings, color);
  }

  /** Paint exactly one resolved dab; spacing and dynamics live in the new runtime. */
  function applyPaintDab(
    point: Point,
    brushSettings: BrushSettings,
    color: { r: number; g: number; b: number; a?: number }
  ): void {
    if (!layerCtx.value) return;

    const { size, hardness, opacity, flow, aspect, rotation, tipAssetId } = brushSettings;
    const brushMask = getBrushMask(size, hardness, aspect, rotation, tipAssetId);

    const halfSize = size / 2;
    const effectiveOpacity = (opacity / 100) * (flow / 100);
    const colorAlpha = color.a ?? 1;
    const brushSize = Math.ceil(size);

    {
      const destX = Math.floor(point.x - halfSize);
      const destY = Math.floor(point.y - halfSize);

      const destData = layerCtx.value!.getImageData(destX, destY, brushSize, brushSize);
      const maskData = brushMask.data;
      const destPixels = destData.data;

      // Get selection mask for this region
      const selectionMask = getSelectionMaskRegion(destX, destY, brushSize, brushSize);

      for (let i = 0; i < maskData.length; i += 4) {
        const pixelIdx = i / 4;

        // Apply selection mask if present
        const selectionAlpha = selectionMask ? selectionMask[pixelIdx] / 255 : 1;
        if (selectionAlpha === 0) continue;

        const maskAlpha = (maskData[i + 3] / 255) * effectiveOpacity * colorAlpha * selectionAlpha;
        if (maskAlpha === 0) continue;

        // Alpha compositing: paint over existing
        const srcA = maskAlpha;
        const dstA = destPixels[i + 3] / 255;
        const outA = srcA + dstA * (1 - srcA);

        if (outA > 0) {
          destPixels[i] = (color.r * srcA + destPixels[i] * dstA * (1 - srcA)) / outA;
          destPixels[i + 1] = (color.g * srcA + destPixels[i + 1] * dstA * (1 - srcA)) / outA;
          destPixels[i + 2] = (color.b * srcA + destPixels[i + 2] * dstA * (1 - srcA)) / outA;
          destPixels[i + 3] = outA * 255;
        }
      }

      layerCtx.value!.putImageData(destData, destX, destY);
    }
  }

  /**
   * Flat fill: the selection (feather and all), or the whole layer without
   * one. No sampling, no tolerance — region-finding belongs to the selection
   * tools; this just lays color into whatever region they made.
   */
  function applyFlatFill(color: { r: number; g: number; b: number; a?: number }): void {
    const ctx = layerCtx.value;
    const size = layerSize.value;
    if (!ctx || !size) return;
    ctx.save();
    if (selectionMaskCtx) {
      // The mask's alpha becomes the fill's alpha: source-in keeps the fill
      // color and multiplies in the mask coverage, so feathered edges land
      // feathered.
      ctx.drawImage(selectionMaskCtx.canvas, 0, 0);
      ctx.globalCompositeOperation = 'source-in';
    }
    ctx.fillStyle = `rgba(${color.r}, ${color.g}, ${color.b}, ${color.a ?? 1})`;
    ctx.fillRect(0, 0, size.width, size.height);
    ctx.restore();
  }

  /**
   * Gradient fill for one canvas drag. The start/end geometry is authored in
   * image pixels; the active selection clips the result after the spectrum is
   * rendered so feathered selection edges retain their coverage.
   */
  function applyGradientFill(
    paint: GradientPaint,
    start: Point,
    end: Point,
    type: PaintGradientType,
    reverse = false,
    preview = false,
  ): void {
    const ctx = layerCtx.value;
    const size = layerSize.value;
    if (!ctx || !size) return;

    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const extent = Math.hypot(dx, dy);
    if (extent < 0.5) return;

    const colorCss = (color: { r: number; g: number; b: number; a?: number }) =>
      `rgba(${color.r}, ${color.g}, ${color.b}, ${color.a ?? 1})`;
    const addStops = (gradient: CanvasGradient, reflected = false) => {
      const stops = reflected
        ? reflectedGradientStops(paint, reverse)
        : rasterGradientStops(paint, reverse);
      for (const stop of stops) gradient.addColorStop(stop.offset, colorCss(stop.color));
    };

    ctx.clearRect(0, 0, size.width, size.height);
    ctx.save();

    if (type === 'diamond') {
      const stops = rasterGradientStops(paint, reverse);
      // Canvas has no diamond gradient primitive. Render exact L1 distance;
      // cap only the live preview, then render at source resolution on release.
      const previewScale = preview
        ? Math.min(1, 768 / Math.max(size.width, size.height))
        : 1;
      const width = Math.max(1, Math.round(size.width * previewScale));
      const height = Math.max(1, Math.round(size.height * previewScale));
      const diamond = document.createElement('canvas');
      diamond.width = width;
      diamond.height = height;
      const diamondCtx = diamond.getContext('2d')!;
      const pixels = diamondCtx.createImageData(width, height);
      const sx = start.x * previewScale;
      const sy = start.y * previewScale;
      const radius = extent * previewScale;
      const angle = Math.atan2(dy, dx);
      const ux = Math.cos(angle);
      const uy = Math.sin(angle);
      const vx = -uy;
      const vy = ux;
      const stopMax = stops.length - 1;
      for (let y = 0; y < height; y += 1) {
        for (let x = 0; x < width; x += 1) {
          const px = x + 0.5 - sx;
          const py = y + 0.5 - sy;
          const t = Math.min(1, (Math.abs(px * ux + py * uy) + Math.abs(px * vx + py * vy)) / radius);
          const position = t * stopMax;
          const leftIndex = Math.min(stopMax, Math.floor(position));
          const rightIndex = Math.min(stopMax, leftIndex + 1);
          const mix = position - leftIndex;
          const left = stops[leftIndex].color;
          const right = stops[rightIndex].color;
          const offset = (y * width + x) * 4;
          pixels.data[offset] = Math.round(left.r + (right.r - left.r) * mix);
          pixels.data[offset + 1] = Math.round(left.g + (right.g - left.g) * mix);
          pixels.data[offset + 2] = Math.round(left.b + (right.b - left.b) * mix);
          pixels.data[offset + 3] = Math.round(
            ((left.a ?? 1) + ((right.a ?? 1) - (left.a ?? 1)) * mix) * 255,
          );
        }
      }
      diamondCtx.putImageData(pixels, 0, 0);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(diamond, 0, 0, size.width, size.height);
    } else {
      let gradient: CanvasGradient;
      if (type === 'radial') {
        gradient = ctx.createRadialGradient(start.x, start.y, 0, start.x, start.y, extent);
        addStops(gradient);
      } else if (type === 'angle') {
        gradient = ctx.createConicGradient(Math.atan2(dy, dx), start.x, start.y);
        addStops(gradient);
      } else if (type === 'reflected') {
        gradient = ctx.createLinearGradient(
          start.x - dx,
          start.y - dy,
          start.x + dx,
          start.y + dy,
        );
        addStops(gradient, true);
      } else {
        gradient = ctx.createLinearGradient(start.x, start.y, end.x, end.y);
        addStops(gradient);
      }
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, size.width, size.height);
    }

    if (selectionMaskCtx) {
      ctx.globalCompositeOperation = 'destination-in';
      ctx.drawImage(selectionMaskCtx.canvas, 0, 0);
    }
    ctx.restore();
  }

  /**
   * Apply patch tool: copy pixels from source region (at offset) to destination using selection mask.
   * The selection mask's alpha channel provides feathered edge blending.
   *
   * @param sourceCanvas - The source image canvas to sample from
   * @param offset - The drag offset (source position relative to destination)
   * @param bounds - Bounding box of the selection
   * @param blendWidth - Additional edge blend radius for softer transitions (0-50)
   */
  function applyPatchTool(
    sourceCanvas: HTMLCanvasElement,
    offset: { x: number; y: number },
    bounds: { x: number; y: number; width: number; height: number },
    blendWidth: number = 15
  ): void {
    if (!layerCtx.value || !selectionMaskCtx) return;

    const sourceCtx = sourceCanvas.getContext('2d');
    if (!sourceCtx) return;

    applyPatch(sourceCtx, layerCtx.value, selectionMaskCtx, offset, bounds, blendWidth);
  }

  /**
   * Start a new stroke (reset spacing tracking)
   */
  function startStroke(): void {
    lastStrokePoint = null;
  }

  /**
   * End the current stroke
   */
  function endStroke(): void {
    lastStrokePoint = null;
  }

  return {
    layerCanvas,
    layerCtx,
    layerSize,
    cloneOffset,
    initLayer,
    clearLayer,
    loadFromDataUrl,
    toDataUrl,
    toSnapshot,
    loadFromSnapshot,
    setCloneSource,
    applyCloneStamp,
    applySpotHeal,
    applyDodgeBurn,
    applySaturationBrush,
    applyAdjustedSourceBrush,
    applyBlurBrush,
    applySharpenBrush,
    applyPaintBrush,
    applyPaintDab,
    applyFlatFill,
    applyGradientFill,
    applyPatchTool,
    setSelectionMask,
    startStroke,
    endStroke,
  };
}
