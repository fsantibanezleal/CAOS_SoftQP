import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import scalar from '../../../data/derived/softqp/C01.json';
import coupled from '../../../data/derived/softqp/C05.json';
import stream from '../../../data/derived/experiments/stream.json';
import { validateSoftQPResult } from '../lib/softqp';
import { validateExperiment } from '../lib/experiments';
import { admitDirectionalSummary, comparisonPopulation, selectedCaseComparison, createNativeSceneMemory, heldTrajectory, methodFormulation, recordedFrame, rowPrice, sceneStateFromSearch, selectedInterval, timingStudy } from './sceneModel';
import directionalRaw from '../../../docs/teaching/coupled/accepted-summary.json?raw';
import directionalIdentity from '../../../docs/teaching/coupled/identity.json';
import control from '../../../data/derived/softqp/C12.json';
import integrity from '../../../data/derived/softqp/C04.json';
import { sparseProblemView, methodRowView, liftedEncoding, intervalPolicy, rowSubgradient } from './sceneModel';

describe('recorded lifting and exact indicator subgradients', () => {
  it('matches every exported separable lift dimension and refuses absent grouped coefficients', () => {
    const folder = new URL('../../../data/derived/softqp/', import.meta.url);
    let checked = 0, unavailable = 0;
    for (const name of readdirSync(folder).filter(name => /^C\d+\.json$/.test(name))) {
      const doc = validateSoftQPResult(JSON.parse(readFileSync(new URL(name, folder), 'utf8')));
      const lift = liftedEncoding(doc, doc.runs.find(run => run.method === 'lifted'));
      if (doc.problem) { expect(lift?.agreesWithRecord, name).toBe(true); checked++; }
      else { expect(lift, name).toBeNull(); unavailable++; }
    }
    expect(checked).toBe(13); expect(unavailable).toBe(2);
    const c01 = validateSoftQPResult(scalar);
    const compact = liftedEncoding(c01, c01.runs.find(run => run.method === 'lifted'))!;
    expect(compact.kind).toBe('compact');
    expect(compact.signed + compact.shared).toBe(1);
    expect(compact.sides).toBe(0);
    const c04 = validateSoftQPResult(integrity);
    expect(liftedEncoding(c04, c04.runs.find(run => run.method === 'lifted'))?.kind).toBe('separate-sides');
  });
  it('detects a dimensional mismatch rather than presenting an unverified formulation', () => {
    const doc = structuredClone(validateSoftQPResult(scalar));
    const run = doc.runs.find(run => run.method === 'lifted')!;
    run.result!.dimensions.variables++;
    expect(liftedEncoding(doc, run)?.agreesWithRecord).toBe(false);
  });
  it('distinguishes interior, boundary rays, equality and exact infeasibility of hard rows', () => {
    const policy = structuredClone(intervalPolicy(validateSoftQPResult(integrity), 0)!);
    policy.row.soft = false; policy.lower = -1; policy.upper = 1;
    expect(rowSubgradient(policy, 0.25)).toEqual({ state: 'interval', lower: 0, upper: 0 });
    expect(rowSubgradient(policy, -1)).toEqual({ state: 'interval', lower: null, upper: 0 });
    expect(rowSubgradient(policy, 1)).toEqual({ state: 'interval', lower: 0, upper: null });
    expect(rowSubgradient(policy, 1 + Number.EPSILON)).toEqual({ state: 'empty' });
    policy.lower = 1;
    expect(rowSubgradient(policy, 1)).toEqual({ state: 'interval', lower: null, upper: null });
    policy.lower = null; policy.upper = null;
    expect(rowSubgradient(policy, 1e6)).toEqual({ state: 'interval', lower: 0, upper: 0 });
    expect(rowSubgradient(policy, null)).toEqual({ state: 'unavailable' });
  });
});

describe('selected-case descriptive comparison', () => {
  it('keeps the named peer reference when a native import has no lifted result', () => {
    const doc = structuredClone(validateSoftQPResult(integrity));
    doc.runs = doc.runs.filter(run => run.method !== 'lifted');
    const result = selectedCaseComparison(doc, doc.rows[0].unit);
    expect(result.reference).toBe(result.available[0]);
    for (const value of result.values) {
      expect(value.delta).toBe(value.run.result!.metrics!.objective - result.referenceCost!);
      expect(value.normalizedGap).toBe(Math.abs(value.delta!) / Math.max(1, Math.abs(result.referenceCost!)));
    }
    expect(selectedCaseComparison(null, 'm').maxNormalizedGap).toBeNull();
  });
  it('separates hard-row units and refuses to turn absent hard rows into zero error', () => {
    const doc = structuredClone(validateSoftQPResult(integrity));
    doc.rows[0].soft = false; doc.rows[0].unit = 'm';
    doc.rows[1].soft = false; doc.rows[1].unit = 's';
    doc.rows[2].soft = true;
    for (const run of doc.runs) if (run.result?.metrics) {
      run.result.metrics.lower_violation[0] = 0.25;
      run.result.metrics.upper_violation[0] = 0.5;
      run.result.metrics.lower_violation[1] = 999;
    }
    const result = selectedCaseComparison(doc, 'm');
    expect(result.hardRows).toEqual([0]);
    expect(result.values.every(value => value.hardError === 0.5)).toBe(true);
    expect(selectedCaseComparison(doc, 'kg').values.every(value => value.hardError === null)).toBe(true);
  });
});

describe('source-bound mathematical views', () => {
  const c04 = validateSoftQPResult(integrity);
  const exact = c04.runs.find(run => run.method === 'daqp')!;
  it('exposes the actual C04 CSC coefficients and complete original row product', () => {
    const model = sparseProblemView(c04, exact, 2, 6, 5)!;
    expect(model.A.values).toEqual([[1, 0], [0, 1], [1, 1]]);
    expect(model.P.values).toEqual([[1, 0], [0, 1]]);
    expect(model.q).toEqual([-3, 2]);
    expect(model.x).toEqual([1.1875, -1.1875]);
    expect(model.rowTerms).toEqual([{ column: 0, coefficient: 1 }, { column: 1, coefficient: 1 }]);
    expect(model.value).toBe(0);
    // Manual C04: 1/2*(19/16)^2*2 - 5*(19/16), plus actual side prices.
    const base = 1.1875 ** 2 - 5 * 1.1875;
    const penalty = 1.2 * .1875 + 4 * .1875 ** 2 / 2 + .3 * .1875 + 2 * .1875 ** 2 / 2;
    expect(base + penalty).toBeCloseTo(exact.result!.metrics!.objective, 12);
  });
  it('bounds sparse windows yet retains the full row product and original identities', () => {
    const c12 = validateSoftQPResult(control), run = c12.runs[0];
    const full = selectedInterval(c12, run, 31)!;
    const model = sparseProblemView(c12, run, 31, 3, 4)!;
    expect(model.columns).toHaveLength(3); expect(model.rowIndices).toHaveLength(4);
    expect(model.rowIndices).toContain(31);
    expect(model.omittedColumns).toBe(c12.problem!.A.shape[1] - 3);
    expect(model.value).toBeCloseTo(full.value, 12);
    expect(model.rowTerms.length).toBeGreaterThan(3);
    expect(model.A.values.flat().every(Number.isFinite)).toBe(true);
  });
  it('does not densify a large sparse operator or equate an omitted nonzero with zero', () => {
    const large = structuredClone(c04), n = 2000, m = 1000;
    large.rows = Array.from({ length: m }, (_, i) => ({ ...c04.rows[0], id: `r${i}` }));
    const p = large.problem!;
    p.A = { shape: [m, n], data: [2, -3], indices: [999, 999], indptr: Array.from({ length: n + 1 }, (_, column) => column === 0 ? 0 : column < n ? 1 : 2) };
    p.P = { shape: [n, n], data: [1], indices: [0], indptr: [0, ...Array(n).fill(1)] };
    p.q = Array(n).fill(0); p.lower = Array(m).fill(null); p.upper = Array(m).fill(4);
    p.penalty = { soft: Array(m).fill(true), lower_linear: Array(m).fill(0), upper_linear: Array(m).fill(1), lower_quadratic: Array(m).fill(0), upper_quadratic: Array(m).fill(0) };
    const run = structuredClone(exact); run.result!.x = Array(n).fill(0); run.result!.x[0] = 1; run.result!.x[n - 1] = 2;
    const model = sparseProblemView(large, run, 999, 3, 3)!;
    expect(model.P.values.flat()).toHaveLength(9); expect(model.A.values.flat()).toHaveLength(9);
    expect(model.value).toBe(-4); expect(model.rowTerms).toEqual([{ column: 0, coefficient: 2 }, { column: 1999, coefficient: -3 }]);
    expect(model.columns).not.toContain(1999); expect(model.omittedColumns).toBe(1997);
    const malformed = structuredClone(exact); malformed.result!.x = [NaN, 1];
    expect(sparseProblemView(c04, malformed, 0)!.x).toBeNull();
    expect(methodRowView(c04, malformed, 0)!.price).toBeNull();
  });
  it('keeps unknown vectors, grouped geometry, absent bounds and invalid rows unavailable', () => {
    expect(sparseProblemView(c04, c04.runs.find(r => r.method === 'generalized'), 0)!.value).toBeNull();
    expect(sparseProblemView(c04, undefined, 0)!.x).toBeNull();
    expect(sparseProblemView(validateSoftQPResult(coupled), undefined, 0)).toBeNull();
    expect(sparseProblemView(c04, exact, 99)).toBeNull();
    const missing = structuredClone(c04); missing.problem!.lower[0] = null;
    const row = methodRowView(missing, exact, 0)!;
    expect(row.lowerSlack).toBeNull(); expect(row.upperSlack).toBeCloseTo(.1875);
  });
  it('derives minimal terminal slacks and the real side slope without inventing rho or duals', () => {
    const row = methodRowView(c04, exact, 0)!;
    expect(row.finiteSoftSides).toBe(4);
    expect(row.lowerSlack).toBe(0); expect(row.upperSlack).toBe(.1875);
    expect(row.price).toBeCloseTo(.2953125);
    expect(row.slope).toEqual([1.95, 1.95]);
    expect(row.recordedDual).toBeCloseTo(1.95, 12);
    expect(row.daqpWeights).toEqual({ lower: .5, upper: .25 });
    expect(methodRowView(c04, exact, 2)!.slope).toBeNull();
    const hardNumericalDeparture = methodRowView(c04, c04.runs.find(r => r.method === 'asymmetric'), 2)!;
    expect(hardNumericalDeparture.value).not.toBeNull();
    expect(hardNumericalDeparture.price).toBeNull(); // Never plot a finite price for a nonzero hard departure.
    expect(hardNumericalDeparture.recordedDeparture).toBeGreaterThan(0);
    const unknown = methodRowView(c04, c04.runs.find(r => r.method === 'generalized'), 0)!;
    expect(unknown.lowerSlack).toBeNull(); expect(unknown.price).toBeNull();
    const kink = structuredClone(c04); kink.problem!.upper[0] = 1.1875;
    expect(methodRowView(kink, exact, 0)!.slope).toEqual([0, 1.2]);
  });
});

describe('recorded scene semantics', () => {
  const doc = validateSoftQPResult(scalar);
  it('reads original-space row values and actual half-quadratic price', () => {
    const row = selectedInterval(doc, doc.runs[0], 0)!;
    expect(row.value).toBeCloseTo(-1.56666666666);
    expect(rowPrice(row, row.value)).toBeCloseTo(doc.runs[0].result!.metrics!.penalty_objective);
    expect(rowPrice(row, 0)).toBe(0);
  });
  it('keeps absent bounds, hard rows and unsupported grouped policies distinct', () => {
    const row = selectedInterval(doc, doc.runs[0], 0)!;
    expect(rowPrice({ ...row, lower: null }, -100)).toBe(0);
    expect(rowPrice({ ...row, row: { ...row.row, soft: false } }, -100)).toBeNull();
    const grouped = validateSoftQPResult(coupled);
    expect(selectedInterval(grouped, grouped.runs[0], 0)).toBeNull();
    expect(selectedInterval(doc, undefined, 0)).toBeNull();
    expect(selectedInterval(doc, doc.runs[0], -1)).toBeNull();
  });
  it('never substitutes a recorded stream for edited or incompatible scenarios', () => {
    const data = validateExperiment('stream', stream);
    expect(recordedFrame(data, 'C12', 'lifted', false, 8)?.velocity_impulse).toBe(0.8);
    expect(recordedFrame(data, 'C12', 'lifted', true, 8)).toBeNull();
    expect(recordedFrame(data, 'C01', 'lifted', false, 8)).toBeNull();
    expect(recordedFrame(data, 'C12', 'generalized', false, 8)).toBeNull();
    expect(recordedFrame(data, 'C12', 'lifted', false, 99)).toBeNull();
  });
  it('bounds URL state without accepting fractional, negative or unknown selections', () => {
    expect(sceneStateFromSearch('?scene=geometry&row=3&frame=40&phase=9')).toEqual({ view: 'geometry', row: 3, frame: 31, phase: 3 });
    expect(sceneStateFromSearch('?scene=unknown&row=-1&frame=2.5&phase=NaN')).toEqual({ view: 'system', row: 0, frame: 0, phase: 0 });
  });
  it('retains held controls, exact final endpoints and instantaneous velocity impulses', () => {
    const data = validateExperiment('stream', stream);
    const trajectory = heldTrajectory(data)!;
    expect(trajectory.endTime).toBeCloseTo(6.4);
    const last = trajectory.acceleration.at(-1)!;
    expect(last.time).toBeCloseTo(6.4);
    expect(last.value).toBe(data.frames[31].applied_control);
    expect(trajectory.events.map(event => [event.frame, event.time, event.impulse])).toEqual([[8, 1.6, .8], [20, 4, -.6]]);
    const jump = trajectory.velocity.filter(point => Math.abs(point.time - 1.6) < 1e-10);
    expect(jump.some(point => Math.abs(point.value - data.frames[7].next_state[1]) < 1e-10)).toBe(true);
    expect(jump.some(point => Math.abs(point.value - data.frames[8].state[1]) < 1e-10)).toBe(true);
    expect(trajectory.position.at(-1)!.value).toBe(data.frames[31].next_state[0]);
    expect(trajectory.acceleration.every((point, index, points) => index === 0 || point.time === points[index - 1].time || point.value === points[index - 1].value)).toBe(true);
    expect(trajectory.acceleration.slice(0, 2).map(point => point.value)).toEqual(Array(2).fill(data.frames[0].applied_control));
  });
  it('keeps compatible peers when the selected control method is incompatible', () => {
    const c12 = validateSoftQPResult(control);
    const peers = comparisonPopulation(c12);
    expect(c12.runs.find(run => run.method === 'generalized')!.state).toBe('incompatible');
    expect(peers.available.map(run => run.method)).toEqual(['lifted', 'asymmetric', 'daqp']);
    expect(peers.unavailable.map(run => run.method)).toContain('generalized');
  });
  it('explains distinct actual method formulations without inventing iterates', () => {
    const c12 = validateSoftQPResult(control);
    const lifted = methodFormulation(c12, c12.runs.find(run => run.method === 'lifted'));
    const native = methodFormulation(c12, c12.runs.find(run => run.method === 'asymmetric'));
    const active = methodFormulation(c12, c12.runs.find(run => run.method === 'daqp'));
    expect(lifted!.auxiliaryVariables).toBe(80);
    expect(native!.auxiliaryVariables).toBe(0);
    expect(lifted!.phases.map(phase => phase.id)).not.toEqual(native!.phases.map(phase => phase.id));
    expect(active!.phases[1].detail.en).toContain('active');
    expect(native!.phases[1].detail.en).toContain('side-specific');
  });
  it('admits exact directional evidence, preserves failure denominator and never mistakes ratios for percentages', async () => {
    const summary = await admitDirectionalSummary(directionalRaw, directionalIdentity['accepted-summary.json']);
    const study = timingStudy(undefined, summary, 'directional')!;
    expect(study.denominator).toBe(144); expect(study.failed).toBe(9);
    expect(study.estimate).toBeCloseTo(-212.449874656751);
    expect(study.interval).toEqual(summary.primary.confidence_interval.map(v => 100 * v));
    expect(timingStudy(undefined, null, 'directional')).toBeNull();
    await expect(admitDirectionalSummary(directionalRaw + ' ', directionalIdentity['accepted-summary.json'])).rejects.toThrow('identity');
  });
  it('retains a verified native import only for its exact case and source within one page lifetime', () => {
    const memory = createNativeSceneMemory();
    const value = { id: 'opaque-token', caseId: 'C01', baseSha256: 'fixed-base', result: doc,
      edits: { lower: '2', upper: '3', quadratic: '1.5' } };
    memory.put(value);
    expect(memory.get('opaque-token', 'C01', 'fixed-base')).toBe(value);
    expect(memory.get('opaque-token', 'C12', 'fixed-base')).toBeNull();
    expect(memory.get('opaque-token', 'C01', 'changed-base')).toBeNull();
    expect(createNativeSceneMemory().get('opaque-token', 'C01', 'fixed-base')).toBeNull();
    memory.clear();
    expect(memory.get('opaque-token', 'C01', 'fixed-base')).toBeNull();
  });
  it('refuses malformed or discontinuous stored dynamics instead of drawing a repaired trajectory', () => {
    const data = validateExperiment('stream', stream);
    const changed = structuredClone(data);
    changed.frames[8].state[1] += .5;
    expect(heldTrajectory(changed)).toBeNull();
    expect(heldTrajectory(null)).toBeNull();
  });
});
