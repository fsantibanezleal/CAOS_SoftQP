import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const frontend = fileURLToPath(new URL('..', import.meta.url));
const require = createRequire(join(frontend, 'package.json'));
const { chromium } = require('playwright');
const { servePages } = require('@fasl-work/caos-app-shell/serve');

test('Focus keeps Context while displaying the visualization in Focus', async () => {
  const server = await servePages(join(frontend, 'dist'), process.env.VITE_BASE || '/', 0);
  let browser;
  try {
    browser = await chromium.launch({ headless: true, args: ['--no-proxy-server'] });
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto(`${server.url}app?case=C01&view=context`);
    await page.locator('[data-focus-enter]').click();
    await page.locator('[data-focus-shell] .softqp-scene-svg').waitFor();
    assert.equal(new URL(page.url()).searchParams.get('focus'), '1');
    assert.equal(new URL(page.url()).searchParams.get('view'), 'context');
    assert.equal(await page.locator('[data-focus-group="context"]').count(), 1);
    const rail = page.locator('[data-focus-shell] [data-rail]');
    const controls = page.getByRole('button', { name: 'Controls', exact: true });
    assert.equal(await controls.getAttribute('aria-expanded'), 'false');
    assert.equal(await rail.isVisible(), false);
    await controls.click();
    assert.equal(await controls.getAttribute('aria-expanded'), 'true');
    assert.equal(await rail.getByRole('combobox', { name: 'Case' }).inputValue(), 'C01');
    await page.locator('[data-focus-exit]').click();
    assert.equal(new URL(page.url()).searchParams.get('focus'), null);
    assert.equal(new URL(page.url()).searchParams.get('view'), 'context');

    await page.goto(`${server.url}app?case=C01&view=context&focus=1`);
    await page.locator('[data-focus-shell] .softqp-scene-svg').waitFor();
    assert.equal(new URL(page.url()).searchParams.get('view'), 'context');
    assert.equal(await page.locator('[data-focus-group="context"]').count(), 1);
  } finally {
    await browser?.close();
    await server.close();
  }
});
