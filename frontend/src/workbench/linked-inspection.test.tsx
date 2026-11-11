import { LinkedViewProvider, formatNumber } from '@fasl-work/caos-app-shell';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { chromium, type Browser, type Page } from 'playwright';
import rawC04 from '../../../data/derived/softqp/C04.json';
import rawC12 from '../../../data/derived/softqp/C12.json';
import rawGrouped from '../../../data/derived/softqp/C05.json';
import { validateSoftQPResult, type SoftQPResult, type SoftQPRun } from '../lib/softqp';
import { LinkedConstraintPanel, constraintEntityId, constraintIndex } from './LinkedConstraintPanel';
import { SystemDomain } from './DomainViews';

const c04 = validateSoftQPResult(rawC04), c12 = validateSoftQPResult(rawC12);
const method = (doc: SoftQPResult) => doc.runs.find(run => run.method === 'lifted')!;
// Independent full CSC calculation: no sceneModel helper is used as its own oracle.
function originalAx(doc: SoftQPResult, row: number) {
  const A = doc.problem!.A, x = method(doc).result!.x!;
  let value = 0;
  for (let col = 0; col < A.shape[1]; col++) {
    for (let k = A.indptr[col]; k < A.indptr[col + 1]; k++) if (A.indices[k] === row) value += A.data[k] * x[col];
  }
  return value;
}
function panel(doc: SoftQPResult | null, rowIndex: number, run: SoftQPRun | null = doc ? method(doc) : null, error: string | null = null) {
  return renderToStaticMarkup(<LinkedViewProvider initial={{ selectedId: doc?.problem ? constraintEntityId(doc, rowIndex) : null, cursor: doc?.problem ? rowIndex + 1 : null }}>
    <LinkedConstraintPanel doc={doc} run={run ?? undefined} rowIndex={rowIndex} ordinalCursor edited={false} error={error} onRowSelect={() => {}} />
  </LinkedViewProvider>);
}

describe('source-bound original-row inspection', () => {
  it('adversarial: keeps identity case-qualified and the ordinal finite, integral and bounded', () => {
    expect(constraintEntityId(c04, 0)).not.toBe(constraintEntityId(c12, 0));
    expect(constraintIndex(1, 3)).toBe(0); expect(constraintIndex(2, 3)).toBe(1);
    expect(constraintIndex(-30, 3)).toBe(0); expect(constraintIndex(99, 3)).toBe(2);
    expect(constraintIndex(2.4, 3)).toBe(1);
    expect(constraintIndex(NaN, 3)).toBeNull(); expect(constraintIndex(Infinity, 3)).toBeNull();
    expect(constraintIndex(1, 0)).toBeNull();
  });
  it('adversarial: checks the full operator and stored row policy against independent arithmetic', () => {
    for (const doc of [c04, c12]) {
      for (const row of [0, 1]) {
        const html = panel(doc, row), data = doc.rows[row], p = doc.problem!;
        expect(html).toContain(`data-linked-id="${constraintEntityId(doc, row)}"`);
        expect(html).toContain(`aria-valuetext="${row + 1}: ${data.id}`);
        expect(html).toContain(`data-linked-cursor-position="${row + 1}"`);
        expect(html).toContain(`value="${row + 1}"`);
        expect(html).toContain(`<strong>${formatNumber(originalAx(doc, row), 'en')}</strong>`);
        expect(html).toContain(`Aᵢx [${data.unit}]`);
        expect(html).toContain(`${p.lower[row] === null ? '−∞' : formatNumber(p.lower[row], 'en')} ≤ Aᵢx ≤ ${p.upper[row] === null ? '+∞' : formatNumber(p.upper[row], 'en')}`);
        expect(html).toContain(data.soft ? 'Soft' : 'Hard');
        const matrix = renderToStaticMarkup(<LinkedViewProvider initial={{ selectedId: constraintEntityId(doc, row), cursor: row + 1 }}><svg>{SystemDomain({ doc, run: method(doc), rowIndex: row, width: 1600, height: 800, lang: 'en', number: value => formatNumber(value, 'en'), marker: () => null, onRowSelect: () => {} })}</svg></LinkedViewProvider>);
        expect(matrix).toContain(`data-domain-row-value="${originalAx(doc, row)}"`);
        expect(matrix).toContain(`data-linked-id="${constraintEntityId(doc, row)}" data-linked-view="scene" data-linked-selected="true"`);
        expect(matrix).toContain(`data-linked-cursor-position="${row + 1}"`);
      }
    }
  });
  it('adversarial: shows exported policy but no invented candidate for an incompatible or unknown method', () => {
    for (const run of [null, { ...method(c04), state: 'incompatible' as const, result: null }]) {
      const html = panel(c04, 1, run);
      expect(html).toContain(c04.rows[1].id);
      expect(html).toContain('No compatible returned vector.');
      expect(html).not.toContain('data-inspection-candidate');
    }
  });
  it('adversarial: clears missing/native-expired and grouped sources rather than borrowing another case', () => {
    const expired = panel(null, 0, null, 'Native import expired.');
    expect(expired).toContain('Native import expired.');
    expect(expired).not.toContain('data-linked-id'); expect(expired).not.toContain('data-inspection-candidate');
    const grouped = panel(validateSoftQPResult(rawGrouped), 0);
    expect(grouped).toContain('no exported separable coefficients');
    expect(grouped).not.toContain('data-inspection-candidate'); expect(grouped).not.toContain('type="range"');
  });
  it('adversarial: does not expose a row-ordinal cursor in a different coordinate system', () => {
    const html = renderToStaticMarkup(<LinkedViewProvider><LinkedConstraintPanel doc={c04} run={method(c04)} rowIndex={1} ordinalCursor={false} edited error={null} onRowSelect={() => {}} /></LinkedViewProvider>);
    expect(html).toContain('verified native import'); expect(html).not.toContain('type="range"');
    expect(html).not.toContain('data-linked-cursor-position');
  });
});

// Explicit opt-in production-path browser controls. No server is started by a unit test.
// Run only after the resource owner releases its window and supplies the actual product URL.
const productURL = process.env.SOFTQP_LINKED_INSPECTION_URL;
describe.skipIf(!productURL)('actual Workbench reciprocal inspection (requires approved product URL)', () => {
  let browser: Browser, page: Page;
  beforeAll(async () => { browser = await chromium.launch({ headless: true }); page = await browser.newPage({ viewport: { width: 1600, height: 900 } }); });
  afterAll(async () => { await browser?.close(); });
  async function checkRow(doc: SoftQPResult, row: number) {
    const id = constraintEntityId(doc, row);
    await page.waitForFunction(({ rowId, value }) => document.querySelector('.softqp-scene')?.getAttribute('data-selected-row') === rowId && Number(document.querySelector('[data-domain-row-value]')?.getAttribute('data-domain-row-value')) === value, { rowId: doc.rows[row].id, value: originalAx(doc, row) });
    expect(new URL(page.url()).searchParams.get('row')).toBe(String(row));
    expect(await page.locator(`[data-linked-id="${id}"][data-linked-view="scene"]`).getAttribute('data-linked-selected')).toBe('true');
    expect(await page.locator(`[data-linked-id="${id}"][data-linked-view="panel"]`).getAttribute('data-linked-selected')).toBe('true');
    expect(await page.locator('.softqp-inspection figcaption').innerText()).toContain(formatNumber(originalAx(doc, row), 'en'));
    const positions = await page.locator('[data-linked-cursor-marker]').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-linked-cursor-position')));
    expect(positions.length).toBeGreaterThanOrEqual(2); expect(positions.every(value => value === String(row + 1))).toBe(true);
  }
  for (const doc of [c04, c12]) it(`${doc.case_id}: selects different real rows both ways and scrubs by keyboard`, async () => {
    await page.goto(`${productURL}/story/formulate?case=${doc.case_id}&method=lifted&row=0`);
    const second = `[data-linked-id="${constraintEntityId(doc, 1)}"]`;
    await page.locator(`${second}[data-linked-view="scene"]`).click(); await checkRow(doc, 1);
    await page.locator(`[data-linked-id="${constraintEntityId(doc, 0)}"][data-linked-view="panel"]`).click(); await checkRow(doc, 0);
    await page.locator('#softqp-row-ordinal').focus(); await page.keyboard.press('ArrowRight'); await checkRow(doc, 1);
    await page.locator(`[data-linked-id="${constraintEntityId(doc, 0)}"][data-linked-view="scene"]`).focus(); await page.keyboard.press('Enter'); await checkRow(doc, 0);
  });
  it('refutes stale case/method/native content across URL changes and reload', async () => {
    await page.goto(`${productURL}/story/formulate?case=C04&method=lifted&row=1`); await checkRow(c04, 1);
    await page.locator('#story-case').selectOption('C12'); await checkRow(c12, 1);
    expect(await page.locator('[data-linked-id^="C04:"]').count()).toBe(0);
    // A direct unknown-method URL exercises the public unavailable path without modifying artifacts.
    await page.goto(`${productURL}/story/formulate?case=C12&method=unknown-method&row=1`);
    await page.locator('.softqp-inspection').filter({ hasText: 'No compatible returned vector.' }).waitFor();
    expect(await page.locator('[data-inspection-candidate]').count()).toBe(0);
    await page.goto(`${productURL}/story/formulate?case=C04&method=lifted&row=1&native=expired`);
    await page.reload(); await page.locator('.softqp-inspection').filter({ hasText: 'unavailable after reload' }).waitFor();
    expect(await page.locator('[data-linked-id]').count()).toBe(0); expect(await page.locator('[data-inspection-candidate]').count()).toBe(0);
  });
});
