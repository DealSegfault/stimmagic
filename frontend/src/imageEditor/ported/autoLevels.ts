/**
 * Ported from the retired editor's histogram analysis.
 *
 * Auto Levels, Auto Contrast and Auto Balance — the three buttons the old
 * Levels panel led with. They read a 256px thumbnail's histogram and propose
 * slider values; nothing here touches pixels, which is why an auto result stays
 * a normal, adjustable, undoable parametric step rather than a bake.
 *
 * Adapted only in how the image arrives: the old panel pulled it off the editor
 * instance, and here it is the composite below the step.
 */

export function analyzeImage(img: HTMLCanvasElement | HTMLImageElement | null): { r: number[]; g: number[]; b: number[]; avg: number; minR: number; maxR: number; minG: number; maxG: number; minB: number; maxB: number } | null {
  if (!img) return null

  // Create temp canvas to read pixels
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  // Use smaller size for faster analysis
  const maxSize = 256;
  const scale = Math.min(1, maxSize / Math.max(img.width, img.height));
  canvas.width = Math.floor(img.width * scale);
  canvas.height = Math.floor(img.height * scale);

  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const data = imageData.data;

  // Build histograms
  const histR = new Array(256).fill(0);
  const histG = new Array(256).fill(0);
  const histB = new Array(256).fill(0);
  let totalBrightness = 0;

  for (let i = 0; i < data.length; i += 4) {
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    histR[r]++;
    histG[g]++;
    histB[b]++;
    totalBrightness += (r + g + b) / 3;
  }

  const pixelCount = data.length / 4;
  const avg = totalBrightness / pixelCount;

  // Find min/max with 0.5% threshold to ignore outliers
  const threshold = pixelCount * 0.005;
  let minR = 0, maxR = 255, minG = 0, maxG = 255, minB = 0, maxB = 255;
  let countR = 0, countG = 0, countB = 0;

  for (let i = 0; i < 256; i++) {
    countR += histR[i];
    if (countR > threshold) { minR = i; break; }
  }
  for (let i = 255; i >= 0; i--) {
    countR += histR[i];
    if (countR > threshold) { maxR = i; break; }
  }
  countR = 0;
  for (let i = 0; i < 256; i++) {
    countG += histG[i];
    if (countG > threshold) { minG = i; break; }
  }
  for (let i = 255; i >= 0; i--) {
    countG += histG[i];
    if (countG > threshold) { maxG = i; break; }
  }
  countG = 0;
  for (let i = 0; i < 256; i++) {
    countB += histB[i];
    if (countB > threshold) { minB = i; break; }
  }
  for (let i = 255; i >= 0; i--) {
    countB += histB[i];
    if (countB > threshold) { maxB = i; break; }
  }

  return { r: histR, g: histG, b: histB, avg, minR, maxR, minG, maxG, minB, maxB };
}

/** Auto Contrast: stretch the histogram toward the full range. */
export function autoContrast(img: HTMLCanvasElement | HTMLImageElement | null): Record<string, number> | null {
  const analysis = analyzeImage(img)
  if (!analysis) return null

  const range = Math.max(
    analysis.maxR - analysis.minR,
    analysis.maxG - analysis.minG,
    analysis.maxB - analysis.minB
  )
  const contrastBoost = Math.round(((255 - range) / 255) * 50)
  return { contrast: Math.min(50, contrastBoost) }
}

/** Auto Levels: brightness and contrast from the histogram's centre and spread. */
export function autoLevels(img: HTMLCanvasElement | HTMLImageElement | null): Record<string, number> | null {
  const analysis = analyzeImage(img)
  if (!analysis) return null

  const midpoint = 127.5
  const brightnessAdjust = Math.round((midpoint - analysis.avg) / 2.55)

  const avgMin = (analysis.minR + analysis.minG + analysis.minB) / 3
  const avgMax = (analysis.maxR + analysis.maxG + analysis.maxB) / 3
  const range = avgMax - avgMin
  const contrastAdjust = Math.round(((255 - range) / 255) * 30)

  return {
    brightness: Math.max(-50, Math.min(50, brightnessAdjust)),
    contrast: Math.max(0, Math.min(50, contrastAdjust)),
  }
}

/** Auto Balance: warm or cool the image by its red/blue imbalance. */
export function autoBalance(img: HTMLCanvasElement | HTMLImageElement | null): Record<string, number> | null {
  const analysis = analyzeImage(img)
  if (!analysis) return null

  const avgR = analysis.r.reduce((sum, count, val) => sum + count * val, 0) / analysis.r.reduce((a, b) => a + b, 0)
  const avgB = analysis.b.reduce((sum, count, val) => sum + count * val, 0) / analysis.b.reduce((a, b) => a + b, 0)

  const tempAdjust = Math.round((avgB - avgR) / 2.55 * 0.5)
  return { temperature: Math.max(-50, Math.min(50, tempAdjust)) }
}
