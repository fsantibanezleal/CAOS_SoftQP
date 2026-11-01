import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { loadSoftQPCase, loadSoftQPIndex, validateSoftQPIndex, validateSoftQPResult } from './softqp';

const roots = [new URL('../../../data/derived/softqp/', import.meta.url), new URL('../../../docs/contracts/fixtures/data/derived/softqp/', import.meta.url)];
describe('SoftQP producer and consumer contract', () => {
  for (const root of roots) {
    it(`reads the producer and provider at ${root}`, () => {
      const index = validateSoftQPIndex(JSON.parse(readFileSync(new URL('index.json', root), 'utf8')));
      for (const row of index.cases) {
        const result = validateSoftQPResult(JSON.parse(readFileSync(new URL(row.path, root), 'utf8')));
        expect(result.case_id).toBe(row.case_id);
      }
    });
  }
  it('rejects an unknown key and a boolean objective', () => {
    const doc = JSON.parse(readFileSync(new URL('C01.json', roots[0]), 'utf8'));
    expect(() => validateSoftQPResult({ ...doc, unexpected: true })).toThrow();
    doc.runs[0].result.metrics.objective = true;
    expect(() => validateSoftQPResult(doc)).toThrow();
  });
  it('checks the baked artifact checksum and abort state', async () => {
    const index = await loadSoftQPIndex();
    const entry = index.cases[0];
    expect((await loadSoftQPCase(entry)).case_id).toBe(entry.case_id);
    await expect(loadSoftQPCase({ ...entry, sha256: '0'.repeat(64) })).rejects.toThrow('SHA-256');
    const controller = new AbortController(); controller.abort();
    await expect(loadSoftQPCase(entry, controller.signal)).rejects.toThrow();
  });
});
