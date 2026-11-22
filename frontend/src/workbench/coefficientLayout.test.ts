import { describe, expect, it } from 'vitest';
import { coefficientLayout } from './coefficientLayout';
import { formatNumber } from '@fasl-work/caos-app-shell';
import { renderToStaticMarkup } from 'react-dom/server';
import integrity from '../../../data/derived/softqp/C04.json';
import { validateSoftQPResult } from '../lib/softqp';
import { SystemDomain } from './DomainViews';
import { selectedInterval } from './sceneModel';

describe('coefficient window allocation', () => {
  const widths = { p: 34, a: 34, q: 49, x: 35, row: 30 };
  it('reallocates the real tablet split instead of shrinking four P cells', () => {
    const g = coefficientLayout(736, 4, widths)!;
    expect(g.count).toBe(4);
    expect(g.pCell - 2).toBeGreaterThan(widths.p);
    expect(g.cell - 2).toBeGreaterThan(widths.a);
    expect(g.vectorX).toBeGreaterThan(g.pX + g.count * g.pCell);
    expect(g.xVectorX).toBeGreaterThan(g.vectorX + widths.q);
    expect(g.matrixX).toBeGreaterThan(g.braceX);
  });
  it('reduces a window for wide labels without losing their pixel width', () => {
    const g = coefficientLayout(736, 4, { ...widths, p: 85, a: 85 })!;
    expect(g.count).toBeLessThan(4);
    expect(g.pCell - 2).toBeGreaterThan(85);
    expect(g.cell - 2).toBeGreaterThan(85);
  });
  it('keeps a compact stacked layout and respects actual small model dimensions', () => {
    const g = coefficientLayout(358, 2, widths)!;
    expect(g.count).toBe(2);
    expect(g.braceX + 8).toBeLessThan(340);
    expect(g.cell - 2).toBeGreaterThan(widths.a);
    expect(coefficientLayout(2528, 2, widths)!.count).toBe(2);
  });
  it.each([
    [-123456789, '-123,456,789', 92.3671875],
    [-1.234e-100, '-1.234E-100', 84.669921875],
  ])('checks the smallest window for the actual finite formatter input %s', (value, label, pixels) => {
    expect(formatNumber(value as number, 'en')).toBe(label);
    const measured = pixels as number;
    const g = coefficientLayout(358, 2, { p: measured, a: measured, q: measured, x: measured, row: 42 });
    expect(g?.count).toBe(1);
    expect(g?.stackVectors).toBe(true);
    expect(g === null || g.braceX + 13 <= 350).toBe(true);
    if (g) {
      expect(g.vectorX + measured).toBeLessThanOrEqual(340);
      expect(g.xVectorX + measured).toBeLessThanOrEqual(340);
      expect(g.cell - 2).toBeGreaterThanOrEqual(measured);
    }
  });
  it('refuses a genuinely impossible one-cell width instead of returning overflowing geometry', () => {
    expect(coefficientLayout(358, 1, { p: 400, a: 400, q: 400, x: 400, row: 42 })).toBeNull();
  });
  it.each(['en', 'es'] as const)('renders an honest %s refusal while retaining the full original Ax and source', lang => {
    // A cloned view fixture exercises a finite long q, without altering a canonical/native record or solving it.
    const doc = structuredClone(validateSoftQPResult(integrity));
    doc.problem!.q = doc.problem!.q.map(() => 1e100);
    const run = doc.runs.find(run => run.method === 'asymmetric')!;
    const original = JSON.stringify(doc), value = selectedInterval(doc, run, 2)!.value;
    const markup = renderToStaticMarkup(SystemDomain({ doc, run, rowIndex: 2, width: 358, height: 700,
      lang, number: value => formatNumber(value, lang), marker: () => null, onRowSelect: () => undefined }));
    expect(markup).toContain('data-state="insufficient-space"');
    expect(markup).not.toContain('data-matrix=');
    expect(markup).toContain(formatNumber(value, lang));
    expect(markup).toContain(lang === 'en' ? 'No coefficient cells are drawn' : 'No se dibujan celdas');
    expect(markup).toContain(lang === 'en' ? 'Next row' : 'Fila siguiente');
    expect(JSON.stringify(doc)).toBe(original);
  });
});
