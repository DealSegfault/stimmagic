export type AssetProjection = {
  id?: number | null
  asset_id?: number | null
  media_id?: number | null
  revision_id?: number | null
  file_hash?: string | null
  [key: string]: unknown
}

/**
 * The part of an Asset projection that changes when its current Revision does.
 * Asset id alone is deliberately insufficient: it is the stable identity.
 */
export function assetHeadSignature(item: AssetProjection | null | undefined): string | null {
  const assetId = item?.asset_id ?? item?.id
  if (assetId == null) return null
  return [
    assetId,
    item?.revision_id ?? '',
    item?.media_id ?? '',
    item?.file_hash ?? '',
  ].join(':')
}

/** Keep the browser-facing id stable while replacing its current payload. */
export function normalizeAssetHead(
  assetId: number,
  projection: AssetProjection,
): AssetProjection {
  return {
    ...projection,
    id: assetId,
    asset_id: assetId,
  }
}

/**
 * Replace an Asset projection wherever it appears in an indexed slideshow
 * cache. Returns the original Map when the Asset is not present.
 */
export function replaceAssetHeadInCache<T extends AssetProjection>(
  cache: ReadonlyMap<number, T>,
  assetId: number,
  projection: AssetProjection,
): Map<number, T> | ReadonlyMap<number, T> {
  let next: Map<number, T> | null = null
  const normalized = normalizeAssetHead(assetId, projection)
  for (const [index, item] of cache.entries()) {
    if ((item.asset_id ?? item.id) !== assetId) continue
    next ??= new Map(cache)
    next.set(index, { ...item, ...normalized } as T)
  }
  return next ?? cache
}
