// Focused product interaction probe. The full shared shell gate remains a separate release requirement.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { servePages } from '@fasl-work/caos-app-shell/serve';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { execFileSync } from 'node:child_process';
import { LANG_STORAGE_KEY, THEME_STORAGE_KEY } from '@fasl-work/caos-app-shell/keys';
import { installLib } from '../node_modules/@fasl-work/caos-app-shell/gate/inpage.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const urlAt = process.argv.indexOf('--url');
const remote = urlAt >= 0 ? new URL(process.argv[urlAt + 1]) : null;
if (remote && !['http:', 'https:'].includes(remote.protocol)) throw new Error('--url requires an HTTP(S) site');
const at = process.argv.indexOf('--out');
const out = at >= 0 ? process.argv[at + 1] : null;
const pythonAt = process.argv.indexOf('--python');
if (pythonAt < 0) throw new Error('--python must name the validated native scientific environment');
const python = process.argv[pythonAt + 1];
const localDir = mkdtempSync(join(process.env.CAOS_TEMP_ROOT || tmpdir(), 'softqp-ui-'));
if (out) mkdirSync(out, { recursive: true });
const server = remote
  ? { url: remote.href.endsWith('/') ? remote.href : remote.href + '/', close: async () => {} }
  : await servePages(join(root, 'dist'), process.env.VITE_BASE || '/', 0);
let browser;
try {
  browser = await chromium.launch({ headless: true, ...(remote ? {} : { args: ['--no-proxy-server'] }) });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = []; page.on('pageerror', e => errors.push(String(e)));
  await page.goto(new URL('app', server.url).href, { waitUntil: 'networkidle' });
  if (out) await page.screenshot({ path: join(out, 'workbench-initial.png'), fullPage: true });
  console.log(JSON.stringify({ url: page.url(), alerts: await page.getByRole('alert').allTextContents(), errors }));
  await page.getByRole('tab', { name: 'Result', exact: true }).click();
  const [file] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Export record', exact: true }).click()]);
  if (!file.suggestedFilename().includes('C01-lifted')) throw new Error('Wrong case/method export');
  await page.getByRole('tab', { name: 'Method', exact: true }).click();
  await page.getByRole('button', { name: 'Edit costs and solve locally', exact: true }).click();
  await page.getByLabel('Lower cost factor', { exact: true }).fill('2');
  await page.getByLabel('Upper cost factor', { exact: true }).fill('3');
  await page.getByLabel('Quadratic cost factor', { exact: true }).fill('1.5');
  const [request] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download solve request', exact: true }).click()]);
  const requestPath = join(localDir, 'C01-request.json'), resultPath = join(localDir, 'result.json');
  await request.saveAs(requestPath);
  execFileSync(python, ['data-pipeline/run_request.py', requestPath, '--output', resultPath], { cwd: join(root, '..'), stdio: 'pipe' });
  await page.getByLabel('Import native result', { exact: true }).setInputFiles(resultPath);
  await page.getByText('Imported native result verified.', { exact: true }).waitFor();
  const corrupted = JSON.parse(readFileSync(resultPath, 'utf8'));
  corrupted.result.runs[0].result.metrics.objective += 1;
  const badPath = join(localDir, 'corrupted.json'); writeFileSync(badPath, JSON.stringify(corrupted));
  await page.getByLabel('Import native result', { exact: true }).setInputFiles(badPath);
  await page.getByRole('alert').filter({ hasText: 'verification failed' }).waitFor();
  await page.getByRole('button', { name: 'Restore recorded result', exact: true }).click();
  await page.getByLabel('Quadratic cost factor', { exact: true }).fill('0');
  const [l1Request] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download solve request', exact: true }).click()]);
  const l1RequestPath = join(localDir, 'l1-request.json'), l1ResultPath = join(localDir, 'l1-result.json');
  await l1Request.saveAs(l1RequestPath);
  execFileSync(python, ['data-pipeline/run_request.py', l1RequestPath, '--output', l1ResultPath], { cwd: join(root, '..'), stdio: 'pipe' });
  await page.getByLabel('Import native result', { exact: true }).setInputFiles(l1ResultPath);
  await page.getByText('Imported native result verified.', { exact: true }).waitFor();
  await page.getByRole('combobox', { name: 'Method', exact: true }).selectOption('flex');
  await page.getByRole('combobox', { name: 'Method', exact: true }).selectOption('elastiqp');
  const l1Record = JSON.parse(readFileSync(l1ResultPath, 'utf8'));
  if (l1Record.result.runs.length !== 6 || l1Record.result.runs.filter(r => ['flex', 'elastiqp'].includes(r.method)).some(r => r.state !== 'available')) throw new Error('L1 references did not execute');
  await page.getByRole('button', { name: 'Restore recorded result', exact: true }).click();
  await page.getByRole('tab', { name: 'Comparison', exact: true }).click();
  await page.locator('[data-plot="Matched formulations"]').waitFor();
  const chartHeight = await page.locator('[data-plot="Matched formulations"]').evaluate(el => Math.max(0, ...Array.from(el.querySelectorAll('svg,canvas'), drawing => drawing.getBoundingClientRect().height)));
  if (chartHeight < 300) throw new Error('Comparison plot collapsed');
  if (out) await page.screenshot({ path: join(out, 'workbench-comparison.png'), fullPage: true });
  await page.getByRole('combobox', { name: 'Case selector', exact: true }).selectOption('C12');
  await page.getByRole('combobox', { name: 'Method', exact: true }).selectOption('asymmetric');
  await page.getByRole('tab', { name: 'C12 stream', exact: true }).click();
  const streamPlot = page.locator('[data-plot="C12 cold and warm stream"]');
  await streamPlot.locator('canvas').first().waitFor();
  if (await streamPlot.locator('canvas').first().evaluate(el => el.getBoundingClientRect().height) < 300) throw new Error('Stream plot collapsed');
  if (out) await page.screenshot({ path: join(out, 'workbench-stream.png'), fullPage: true });
  await page.getByRole('combobox', { name: 'Method', exact: true }).selectOption('generalized');
  await streamPlot.getByText(/The recorded stream requires unedited C12/).waitFor();
  if (await streamPlot.locator('canvas').count()) throw new Error('Incompatible stream retained a numeric plot');
  await page.getByRole('tab', { name: 'Violations', exact: true }).click();
  if (out) await page.screenshot({ path: join(out, 'workbench-desktop.png'), fullPage: true });
  await page.getByRole('combobox', { name: 'Case selector', exact: true }).selectOption('C03');
  await page.getByRole('combobox', { name: 'Method', exact: true }).selectOption('generalized');
  await page.getByText('The case is outside this method’s supported assumptions.', { exact: true }).waitFor();
  await page.getByRole('combobox', { name: 'Method', exact: true }).selectOption('asymmetric');
  await page.getByRole('combobox', { name: 'Case selector', exact: true }).selectOption('C14');
  await page.getByLabel('Row unit', { exact: true }).selectOption('kWh');
  await page.getByRole('button', { name: 'Open this case in focus mode', exact: true }).click();
  const focusRail = page.locator('[data-focus-shell] [data-rail]');
  const focusControls = page.getByRole('button', { name: 'Controls', exact: true });
  await focusControls.waitFor();
  if (await focusRail.isVisible() || await focusControls.getAttribute('aria-expanded') !== 'false') throw new Error('Focus starts with an obstructing control rail');
  await focusControls.press('Enter');
  await focusRail.waitFor();
  if (await focusRail.getByRole('combobox', { name: 'Case selector', exact: true }).inputValue() !== 'C14') throw new Error('Disclosed Focus rail lost the case');
  await focusRail.getByRole('tab', { name: 'Method', exact: true }).click();
  if (await focusRail.getByLabel('Row unit', { exact: true }).inputValue() !== 'kWh') throw new Error('Disclosed Focus rail lost the selected unit');
  await page.keyboard.press('Escape');
  if (await page.getByRole('combobox', { name: 'Case selector', exact: true }).inputValue() !== 'C14') throw new Error('Focus lost the selected case');
  await page.getByRole('tab', { name: 'Method', exact: true }).click();
  if (await page.getByLabel('Row unit', { exact: true }).inputValue() !== 'kWh') throw new Error('Focus lost the selected unit');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(250);
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw new Error('Phone page overflows horizontally');
  if (out) await page.screenshot({ path: join(out, 'workbench-phone.png'), fullPage: true });
  for (const viewport of [{ width: 1280, height: 800 }, { width: 1600, height: 900 }]) {
    await page.setViewportSize(viewport);
    await page.goto(new URL('app?case=C04&scene=system', server.url).href);
    for (const mode of ['App', 'Focus']) {
      if (mode === 'Focus') await page.getByRole('button', { name: 'Open this case in focus mode', exact: true }).click();
      const scene = page.locator('.softqp-scene-canvas:not([data-state]) > svg');
      await scene.waitFor();
      const measured = await scene.evaluate(svg => {
        const box = svg.getBoundingClientRect();
        const stage = svg.closest('[data-stage]').getBoundingClientRect();
        const width = Math.max(0, Math.min(box.right, stage.right, innerWidth) - Math.max(box.left, stage.left, 0));
        const height = Math.max(0, Math.min(box.bottom, stage.bottom, innerHeight) - Math.max(box.top, stage.top, 0));
        return { share: width * height / (innerWidth * innerHeight), rows: svg.querySelectorAll('[data-matrix="A"]').length, anchors: svg.querySelectorAll('[data-scene-subject]').length };
      });
      if (measured.share < (mode === 'Focus' ? .8 : .6) || measured.rows === 0 || measured.anchors !== 3) {
        throw new Error(`${mode} did not draw the fitted scientific scene at ${viewport.width}×${viewport.height}: ${JSON.stringify(measured)}`);
      }
      console.log(`${mode} actual scientific SVG ${viewport.width}×${viewport.height}: ${(measured.share * 100).toFixed(3)}%`);
      if (out) await page.screenshot({ path: join(out, `fitted-scene-${mode.toLowerCase()}-${viewport.width}.png`) });
    }
    await page.locator('[data-focus-exit]').click();
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(new URL('benchmark', server.url).href, { waitUntil: 'networkidle' });
  await page.getByText('The original campaign completed 456 of 456 seeded instances.', { exact: false }).waitFor();
  await page.getByRole('cell', { name: 'Not established', exact: true }).waitFor();
  for (let i = 1; i <= 15; i++) {
    const id = `C${String(i).padStart(2, '0')}`;
    await page.getByLabel('Development case', { exact: true }).selectOption(id);
    const rows = page.locator('[data-development-matrix] tbody tr');
    if (await rows.count() !== 4) throw new Error(`${id} lost recorded method states`);
    if ((await rows.locator('th').allTextContents()).some(text => text !== id)) throw new Error('Case filter mixed inputs');
  }
  await page.getByLabel('Penalty family', { exact: true }).selectOption('asymmetric-l1');
  await page.getByLabel('Row density', { exact: true }).selectOption('0.2');
  await page.getByLabel('Hessian condition', { exact: true }).selectOption('1000');
  await page.getByLabel('Physical quantity', { exact: true }).selectOption('control');
  await page.getByLabel('Stream method', { exact: true }).selectOption('daqp');
  for (const title of ['Paired seeded cold observations', 'Same-instance conditioning', 'Oracle-driven plant', 'Same-method cold and warm observations']) {
    const plot = page.locator(`[data-plot="${title}"]`);
    await plot.locator('canvas').first().waitFor();
    if (await plot.locator('canvas').first().evaluate(el => el.getBoundingClientRect().height) < 250) throw new Error(`${title} collapsed`);
  }
  const [csv] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: 'trials.csv', exact: true }).click()]);
  const csvPath = join(localDir, 'trials.csv'); await csv.saveAs(csvPath);
  if (!readFileSync(csvPath).equals(readFileSync(join(root, '..', 'data', 'derived', 'experiments', 'trials.csv')))) throw new Error('Raw CSV download differs from checked evidence');
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw new Error('Phone benchmark overflows horizontally');
  if (out) await page.screenshot({ path: join(out, 'benchmark-phone.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  if (out) await page.screenshot({ path: join(out, 'benchmark-desktop.png'), fullPage: true });
  // Reproduce the locale, contrast and wide-font failures with the same measurements as the full gate.
  const methods = JSON.parse(readFileSync(join(root, '..', 'content', 'methods.json'), 'utf8'));
  for (const [width,height,theme,wide] of [[1280,800,'dark',false],[390,844,'light',true]]) {
    const context = await browser.newContext({ viewport:{width,height} });
    await context.addInitScript(([lk,tk,t])=>{localStorage.setItem(lk,'es');localStorage.setItem(tk,t);},[LANG_STORAGE_KEY,THEME_STORAGE_KEY,theme]);
    await context.addInitScript(installLib);
    const localized = await context.newPage();
    async function inspect() {
      const problems = await localized.evaluate(()=>[
        ...window.__caosGate.decimals(),...window.__caosGate.scrolls(),...window.__caosGate.brokenValues(),
        ...window.__caosGate.contrast(),
      ]);
      const rail = await localized.evaluate(()=>window.__caosGate.facts().rail);
      if(width>=1280 && rail && rail.scroll>rail.client+1) problems.push(`Rail scroll ${rail.scroll}/${rail.client}`);
      if(problems.length) throw new Error(`${localized.url()} ${width}/${theme}: ${problems.join('\n')}`);
    }
    await localized.goto(new URL('benchmark',server.url).href,{waitUntil:'networkidle'});
    if(wide) await localized.addStyleTag({content:':root { --font-sans: Verdana, "DejaVu Sans", sans-serif !important; }'});
    await localized.getByLabel('Magnitud física',{exact:true}).selectOption('velocity');
    await inspect();
    if (!wide) {
      await localized.goto(new URL('methodology',server.url).href,{waitUntil:'networkidle'});
      await localized.getByRole('tab',{name:'Referencias L1',exact:true}).click();await inspect();
      await localized.getByRole('tab',{name:methods.find(m=>m.id==='elasti').title.es,exact:true}).click();await inspect();
      await localized.goto(new URL('implementation',server.url).href,{waitUntil:'networkidle'});
      await localized.getByRole('tab',{name:'Evidencia y entrega',exact:true}).click();await inspect();
      await localized.goto(new URL('app',server.url).href,{waitUntil:'networkidle'});await inspect();
      await localized.getByRole('tab',{name:'Método',exact:true}).click();
      await localized.getByRole('button',{name:'Editar costos y resolver',exact:true}).click();await inspect();
      await localized.goto(new URL('introduction',server.url).href,{waitUntil:'networkidle'});await inspect();
      for(const label of ['La situación actual','La propuesta','Técnica']) {
        await localized.getByRole('tab',{name:label,exact:true}).click();await inspect();
      }
    }
    if(out) await localized.screenshot({path:join(out,`locale-${width}-${theme}.png`),fullPage:true});
    await context.close();
  }
  await page.setViewportSize({ width: 1280, height: 800 });
  const contextPath = 'app?case=C01&view=context&scene=geometry&method=lifted&row=0&frame=7&phase=2';
  const query = () => new URL(page.url()).searchParams;
  const frame = page.locator('[data-focus-shell]');
  const focusScene = frame.locator('.softqp-scene-canvas:not([data-state]) > svg');
  const controls = frame.getByRole('button', { name: 'Controls', exact: true });
  const costPanel = frame.getByRole('tab', { name: 'Method and costs', exact: true });
  const openCosts = async () => {
    await controls.click();
    await costPanel.click();
    await frame.locator('input#focus-local-result').waitFor();
  };
  const selectedContext = (caseId = 'C01') => {
    for (const [key, value] of Object.entries({ case: caseId, view: 'context', scene: 'geometry', method: 'lifted', row: '0', frame: '7', phase: '2' })) {
      assert.equal(query().get(key), value, `Context retained ${key}`);
    }
  };
  await page.goto(new URL(`${contextPath}#before`, server.url).href);
  await page.locator('#local-result').waitFor();
  const historyLength = await page.evaluate(() => {
    const state = { ...history.state, idx: (history.state?.idx ?? 0) + 1, key: crypto.randomUUID(), usr: { probe: 'context-visit' } };
    history.pushState(state, '', `${location.pathname}${location.search}#visited`);
    return history.length;
  });
  await page.locator('[data-focus-enter]').click();
  await focusScene.waitFor();
  assert.equal(await frame.locator('[data-focus-group]').getAttribute('data-focus-group'), 'context');
  await openCosts();
  const caseSelector = frame.getByRole('combobox', { name: 'Case selector', exact: true });
  await caseSelector.selectOption('C04');
  await page.waitForURL(url => url.searchParams.get('case') === 'C04');
  selectedContext('C04');
  assert.equal(query().get('focus'), '1');
  await caseSelector.selectOption('C01');
  await page.waitForURL(url => url.searchParams.get('case') === 'C01');
  await frame.getByLabel('Lower cost factor', { exact: true }).fill('2');
  await frame.getByLabel('Upper cost factor', { exact: true }).fill('3');
  await frame.getByLabel('Quadratic cost factor', { exact: true }).fill('1.5');
  const [focusRequest] = await Promise.all([page.waitForEvent('download'), frame.getByRole('button', { name: 'Download solve request', exact: true }).click()]);
  const focusRequestPath = join(localDir, 'focus-request.json');
  await focusRequest.saveAs(focusRequestPath);
  assert.deepEqual(readFileSync(focusRequestPath), readFileSync(requestPath), 'Focus downloaded the same native request');
  await frame.getByLabel('Import native result', { exact: true }).setInputFiles(resultPath);
  await frame.getByText('Imported native result verified.', { exact: true }).waitFor();
  await frame.locator('[data-source="local-native-import"] svg.softqp-scene-svg').waitFor();
  const token = query().get('native');
  assert.ok(token);
  assert.equal(new URL(page.url()).hash, '#visited');
  assert.deepEqual(await page.evaluate(() => [history.length, history.state.usr]), [historyLength, { probe: 'context-visit' }]);
  assert.deepEqual(await page.locator('[id]').evaluateAll(nodes => nodes.map(node => node.id).filter((id, i, ids) => ids.indexOf(id) !== i)), []);

  await page.goBack();
  await page.locator('#local-result').waitFor();
  assert.equal(query().get('focus'), null);
  assert.equal(query().get('native'), null);
  assert.equal(await frame.count(), 0);
  await page.goForward();
  await focusScene.waitFor();
  selectedContext();
  assert.equal(query().get('native'), token);
  assert.equal(query().get('focus'), '1');
  await openCosts();
  assert.equal(await frame.getByLabel('Lower cost factor', { exact: true }).inputValue(), '2');
  if (out) await page.screenshot({ path: join(out, 'context-focus-native.png') });
  await page.keyboard.press('Escape');
  await page.locator('#local-result').waitFor();
  selectedContext();
  assert.equal(query().get('focus'), null);
  assert.equal(query().get('native'), token);

  for (const [view, witness] of [['violations', '[data-plot="Lower and upper violations"]'], ['comparison', '[data-plot="Matched formulations"]'], ['stream', '[data-plot="C12 cold and warm stream"] canvas'], ['scene', 'svg.softqp-scene-svg']]) {
    await page.goto(new URL(`app?case=C12&view=${view}&method=asymmetric&focus=1`, server.url).href);
    await frame.locator(witness).first().waitFor();
    assert.equal(await frame.locator('[data-focus-group]').getAttribute('data-focus-group'), view);
    assert.equal(await frame.locator('svg.softqp-scene-svg').count(), view === 'scene' ? 1 : 0);
  }
  await page.goto(new URL('app?case=C04&view=violations&scene=system&focus=1', server.url).href);
  await controls.click();
  await frame.getByRole('tab', { name: 'Method', exact: true }).click();
  await frame.getByRole('button', { name: 'Edit costs and solve locally', exact: true }).click();
  await frame.locator('#focus-local-result').waitFor();
  await focusScene.waitFor();
  assert.equal(query().get('focus'), '1');
  assert.equal(query().get('view'), 'context');
  assert.equal(await costPanel.getAttribute('aria-selected'), 'true');

  await page.goto(new URL(`${contextPath}&focus=1`, server.url).href);
  await page.setViewportSize({ width: 390, height: 844 });
  await focusScene.waitFor();
  await openCosts();
  if (out) await page.screenshot({ path: join(out, 'context-focus-phone.png') });
  await page.setViewportSize({ width: 390, height: 560 });
  const phoneRail = frame.locator('[data-rail]');
  assert.equal(await phoneRail.evaluate(el => el.scrollHeight > el.clientHeight), true, 'native controls scroll inside the rail');
  await frame.locator('#focus-local-result').scrollIntoViewIfNeeded();
  assert.equal(await frame.locator('#focus-local-result').isEnabled(), true);
  await frame.locator('[data-focus-exit]').click();
  await page.locator('#local-result').waitFor();

  console.log('SoftQP probe: native solve/import, tamper rejection, C12 cold/warm and incompatibility, campaign filters/plots, exact raw CSV download, Focus groups, history, Context native editing and phone rail passed');
  if (errors.length) throw new Error(errors.join('\n'));
  if (out) {
    // Keep the genuine downloaded requests and native answers for reproducible review/video imports.
    for (const name of ['C01-request.json', 'result.json', 'corrupted.json', 'l1-request.json', 'l1-result.json', 'focus-request.json']) {
      copyFileSync(join(localDir, name), join(out, name));
    }
  }
} finally {
  if (browser) await browser.close();
  await server.close();
}
