import { readFileSync } from 'node:fs';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Readiness } from '../lib/contract.types';
import { Workbench } from './Workbench';
import { Benchmark } from '../pages/Benchmark';
import { Experiments } from '../pages/Experiments';

const mock = vi.hoisted(() => ({ document: null as Readiness | null }));
vi.mock('../readiness/useReadiness', () => ({ useReadiness: () => mock.document }));
const recorded = JSON.parse(readFileSync(new URL('../../../data/derived/readiness.json', import.meta.url), 'utf8')) as Readiness;
const render = () => renderToStaticMarkup(<MemoryRouter><Workbench /></MemoryRouter>);
const renderBenchmark = () => renderToStaticMarkup(<MemoryRouter><Benchmark /></MemoryRouter>);
const renderExperiments = () => renderToStaticMarkup(<MemoryRouter><Experiments /></MemoryRouter>);
function staleFixture(): Readiness {
  const fixture = structuredClone(recorded);
  for (const row of fixture.contracts) {
    if (['softqp-index', 'softqp-case-result'].includes(row.id)) {
      row.state = 'stale';
      row.reason = { en: 'Stored fixture bake and product versions differ.', es: 'Las versiones de los datos de prueba y del producto son diferentes.' };
    }
    if (row.id === 'api') { row.state = 'missing'; }
  }
  return fixture;
}
afterEach(() => { mock.document = null; });

describe('the actual workbench readiness consumer', () => {
  it('keeps method-domain evidence visible while the asynchronous case matrix loads', () => {
    const html = renderBenchmark();
    expect(html).toContain('data-method-support');
    expect(html).toContain('Executed independent reference');
  });

  it('adversarial: actual Workbench shows the recorded stale reason and keeps unrelated rows separate', () => {
    mock.document = staleFixture();
    const row = mock.document.contracts.find(r => r.id === 'softqp-case-result');
    expect(row?.state).toBe('stale');
    expect(mock.document.contracts.some(r => r.state === 'missing')).toBe(true);
    for (const html of [render(), renderBenchmark(), renderExperiments()]) {
      expect(html).toContain('data-readiness="stale"');
      expect(html).toContain(row!.reason!.en);
      expect(html).not.toContain('data-readiness="missing"');
    }
  });

  it('adversarial: available workbench rows do not inherit unrelated missing states', () => {
    mock.document = staleFixture();
    for (const row of mock.document.contracts) {
      if (['softqp-index', 'softqp-case-result'].includes(row.id)) {
        row.state = 'available'; row.reason = null;
      }
    }
    expect(render()).not.toContain('data-readiness=');
    expect(renderBenchmark()).not.toContain('data-readiness=');
    expect(renderExperiments()).not.toContain('data-readiness=');
  });

  it('adversarial: unreadable readiness keeps the workbench and reports unknown', () => {
    mock.document = null;
    expect(render()).toContain('id="softqp-scene-view"');
    expect(render()).toContain('id="softqp-scene-row"');
    for (const html of [render(), renderBenchmark(), renderExperiments()]) {
      expect(html).toContain('data-readiness="unknown"');
    }
  });
});
