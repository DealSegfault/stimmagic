function clamp(value: number, min = 0, max = 1): number {
  return Math.min(max, Math.max(min, Number.isFinite(value) ? value : min))
}
function assetSeed(assetId: string): number {
  return Array.from(assetId).reduce(
    (value, character) => Math.imul(value ^ character.charCodeAt(0), 16777619),
    2166136261,
  ) >>> 0
}

function textureNoise(seed: number, x: number, y: number): number {
  let value = seed ^ Math.imul(x, 0x45d9f3b) ^ Math.imul(y, 0x119de1f3)
  value = Math.imul(value ^ (value >>> 16), 0x45d9f3b)
  value = Math.imul(value ^ (value >>> 16), 0x45d9f3b)
  return ((value ^ (value >>> 16)) >>> 0) / 4294967295
}

/**
 * Alpha at a normalized point in a transformed brush tip.
 *
 * This is deliberately independent of Canvas gradients and transforms: the
 * preset preview and raster output must not disagree because a browser applies
 * a gradient's coordinate space differently from its path transform.
 */
export function brushTipAlpha(
  x: number,
  y: number,
  hardness: number,
  aspect = 1,
  rotation = 0,
  tipAssetId?: string,
): number {
  const radians = -rotation * Math.PI / 180
  const cosine = Math.cos(radians)
  const sine = Math.sin(radians)
  const tx = cosine * x - sine * y
  const ty = (sine * x + cosine * y) / clamp(aspect, 0.08, 1)
  const distance = Math.hypot(tx, ty)
  if (distance >= 1) return 0

  const hard = clamp(hardness / 100)
  const edge = distance <= hard || hard >= 0.999
    ? 1
    : 1 - (distance - hard) / (1 - hard)
  if (!tipAssetId) return clamp(edge)

  const grain = textureNoise(
    assetSeed(tipAssetId),
    Math.floor((tx + 1) * 47),
    Math.floor((ty + 1) * 47),
  )
  let texture = 1
  if (tipAssetId.includes('dry-nib')) {
    const fibres = Math.abs(Math.sin((ty + grain * 0.08) * 42))
    texture = fibres > 0.24 ? 0.38 + grain * 0.62 : grain * 0.12
  } else if (tipAssetId.includes('graphite-fine')) {
    texture = grain > 0.18 ? 0.35 + grain * 0.65 : 0.04
  } else if (tipAssetId.includes('graphite-broad')) {
    texture = grain > 0.28 ? 0.22 + grain * 0.7 : 0.03
  } else if (tipAssetId.includes('chalk')) {
    texture = grain > 0.42 ? 0.32 + grain * 0.68 : grain * 0.08
  } else if (tipAssetId.includes('spatter')) {
    texture = grain > 0.64 ? 0.75 + grain * 0.25 : 0
  }
  return clamp(edge * texture)
}
