// Focused product interaction probe. The full shared shell gate remains a separate release requirement.
import { chromium } from 'playwright';
import { servePages } from '@fasl-work/caos-app-shell/serve';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdirSync } from 'node:fs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const at = process.argv.indexOf('--out');
const out = at >= 0 ? process.argv[at + 1] : null;
if (out) mkdirSync(out, { recursive: true });
const server = await servePages(join(root, 'dist'), '/', 0);
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = []; page.on('pageerror', e => errors.push(String(e)));
  await page.goto(new URL('app', server.url).href, { waitUntil: 'networkidle' });
  if (out) await page.screenshot({ path: join(out, 'workbench-initial.png'), fullPage: true });
  console.log(JSON.stringify({ url: page.url(), alerts: await page.getByRole('alert').allTextContents(), errors }));
  const [file] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Export record', exact: true }).click()]);
  if (!file.suggestedFilename().includes('C01-lifted')) throw new Error('Wrong case/method export');
  console.log(JSON.stringify({ roles: await page.locator('[role="radio"], [role="option"]').evaluateAll(nodes => nodes.map(n => ({ role: n.getAttribute('role'), text: n.textContent }))), buttons: await page.getByRole('button').evaluateAll(nodes => nodes.map(n => ({ text: n.textContent, label: n.getAttribute('aria-label') }))), errors }));
  if (out) await page.screenshot({ path: join(out, 'workbench-desktop.png'), fullPage: true });
  await page.getByRole('combobox', { name: 'Case selector', exact: true }).selectOption('C03');
  await page.getByRole('radio', { name: 'Generalized projection', exact: true }).click();
  await page.getByText('The penalty is outside this method’s supported family.', { exact: true }).waitFor();
  await page.getByRole('radio', { name: 'Asymmetric projection', exact: true }).click();
  await page.getByRole('combobox', { name: 'Case selector', exact: true }).selectOption('C14');
  await page.getByLabel('Row unit', { exact: true }).selectOption('kWh');
  await page.getByRole('button', { name: 'Open this case in focus mode', exact: true }).click();
  await page.keyboard.press('Escape');
  if (await page.getByRole('combobox', { name: 'Case selector', exact: true }).inputValue() !== 'C14') throw new Error('Focus lost the selected case');
  if (await page.getByLabel('Row unit', { exact: true }).inputValue() !== 'kWh') throw new Error('Focus lost the selected unit');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(250);
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw new Error('Phone page overflows horizontally');
  if (out) await page.screenshot({ path: join(out, 'workbench-phone.png'), fullPage: true });
  console.log('SoftQP probe: case selection, checksum-backed export, unit selection, Focus return and phone width passed');
  if (errors.length) throw new Error(errors.join('\n'));
} finally {
  if (browser) await browser.close();
  await server.close();
}
