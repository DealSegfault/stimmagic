import { expect, test } from '@playwright/test';
import { generateMedia, openMediaFromBrowse, waitForShell } from '../helpers/app';

test('asset viewer keeps media, details and close controls accessible on small screens', async ({ page }) => {
  await page.goto('/browse');
  await waitForShell(page);
  const media = await generateMedia(page, `acceptance mobile viewer ${Date.now()}`);
  await openMediaFromBrowse(page, media.id);

  for (const width of [320, 390, 768, 1024]) {
    await page.setViewportSize({ width, height: 844 });
    const details = page.getByRole('button', { name: 'Asset details', exact: true });
    const close = page.getByRole('button', { name: 'Close slideshow', exact: true });
    await expect(details).toHaveAttribute('aria-expanded', 'false');
    await expect(page.getByTestId('media-info-panel')).toHaveCount(0);
    for (const control of [close, page.getByTestId('slideshow-controls')]) {
      await expect(control).toBeInViewport({ ratio: 1 });
    }

    await details.click();
    await expect(page.getByTestId('media-info-panel')).toBeInViewport({ ratio: 1 });
    await expect(close).toBeInViewport({ ratio: 1 });
    await page.keyboard.press('Escape');
    await expect(details).toHaveAttribute('aria-expanded', 'false');
    await expect(close).toBeVisible();
  }

  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByTestId('media-info-panel')).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Close slideshow', exact: true }).click();
  await expect(page.getByTestId(`media-grid-item-${media.id}`)).toBeVisible();
});
