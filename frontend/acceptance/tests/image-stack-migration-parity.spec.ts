import { test, expect } from '@playwright/test'

/**
 * Golden parity for the snapshot-editor migration — the canary-flip criterion.
 *
 * v2 has to open legacy documents and LOOK THE SAME. Unit tests prove the field
 * mapping; only rendering both pipelines over the same pixels proves the
 * result, because the risk is order, inclusion and convention — a stage applied
 * in the wrong place, one quietly left out, or a coordinate read the wrong way —
 * not the colour math, which both paths share by construction.
 *
 * (It earned this on its first run: the snapshot editor's crop rect is stored
 * by its CENTRE, and the migrator had been reading it as a top-left.)
 *
 * Both renders happen in the page, through the shared harness in
 * `src/imageEditor/stack/migrationParity.ts`, so this spec and any ad-hoc
 * runner exercise identical code.
 */

/** Names must match PARITY_FAMILIES so a failure says which family broke. */
const FAMILY_NAMES = [
  'light',
  'colour',
  'filter-preset',
  'effects-tonal',
  'effects-spatial',
  'film-split-tone',
  'film-colour-isolation',
  'geometry-crop',
  'geometry-flip',
  'geometry-quarter-turn',
  'geometry-straighten',
  'geometry-crop-tilt',
  'combined',
]

test('every migrated field family renders identically to the snapshot editor', async ({ page }) => {
  await page.goto('/')
  await page.waitForLoadState('domcontentloaded')

  const results = await page.evaluate(async () => {
    const harness: any = await import('/src/imageEditor/stack/migrationParity.ts')
    const reports = []
    for (const family of harness.PARITY_FAMILIES) {
      reports.push({
        name: family.name,
        ...(await harness.compareMigrationParity(family.state)),
      })
    }
    return reports
  })

  expect(results.map((r: any) => r.name)).toEqual(FAMILY_NAMES)

  for (const report of results as any[]) {
    expect(report.dimsMismatch, `${report.name}: migrated output changed size`).toBeUndefined()
    // Both paths run the same math on the same canvas implementation, so an
    // exact match is the honest bar; the tolerance is only for PNG round-trip
    // rounding.
    expect(report.maxDelta, `${report.name}: max channel delta`).toBeLessThanOrEqual(1)
    expect(report.overPct, `${report.name}: share of differing pixels`).toBeLessThanOrEqual(0.001)
  }
})
