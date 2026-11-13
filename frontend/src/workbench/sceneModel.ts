import type { SoftQPResult, SoftQPRun } from '../lib/softqp';
import type { Stream, Campaign } from '../lib/experiments';

export const SCENE_VIEWS = ['system', 'interval', 'geometry', 'dynamics', 'method', 'comparison'] as const;
export type SceneView = typeof SCENE_VIEWS[number];

export function intervalPolicy(doc: SoftQPResult | null, rowIndex: number) {
  const row = doc?.rows[rowIndex], problem = doc?.problem;
  if (!row || !problem || !Number.isInteger(rowIndex) || rowIndex < 0 || rowIndex >= problem.A.shape[0]) return null;
  return { row, lower: problem.lower[rowIndex], upper: problem.upper[rowIndex],
    lowerLinear: problem.penalty.lower_linear[rowIndex], upperLinear: problem.penalty.upper_linear[rowIndex],
    lowerQuadratic: problem.penalty.lower_quadratic[rowIndex], upperQuadratic: problem.penalty.upper_quadratic[rowIndex] };
}
export type RowPolicy = NonNullable<ReturnType<typeof intervalPolicy>>;

/** Branches mirror SDK lift_problem/reference.lift; missing coefficients never imply a lift family. */
export function liftedEncoding(doc: SoftQPResult | null, run: SoftQPRun | undefined) {
  if (!doc?.problem || run?.method !== 'lifted') return null;
  const p = doc.problem, n = p.A.shape[1], m = p.A.shape[0];
  const symmetric = p.penalty.lower_linear.every((v, i) => v === p.penalty.upper_linear[i])
    && p.penalty.lower_quadratic.every((v, i) => v === p.penalty.upper_quadratic[i]);
  const soft = p.penalty.soft.flatMap((v, i) => v ? [i] : []);
  const signed = symmetric ? soft.filter(i => p.penalty.lower_linear[i] === 0).length : 0;
  const shared = symmetric ? soft.length - signed : 0;
  const sides = symmetric ? 0 : soft.reduce((count, i) => count + Number(p.lower[i] !== null) + Number(p.upper[i] !== null), 0);
  const variables = n + signed + shared + sides;
  const rows = symmetric ? m + shared + soft.filter(i => p.penalty.lower_linear[i] !== 0 && p.lower[i] !== null && p.upper[i] !== null).length : m - soft.length + 2 * sides;
  const recorded = run.state === 'available' ? run.result?.dimensions : undefined;
  return { kind: symmetric ? 'compact' as const : 'separate-sides' as const, signed, shared, sides, variables, rows,
    agreesWithRecord: recorded ? recorded.variables === variables && recorded.rows === rows : null };
}

export type RowSubgradient = { state: 'unavailable' } | { state: 'empty' } | { state: 'interval'; lower: number | null; upper: number | null };

/** Exact convex subdifferential; numerical feasibility tolerances do not change the hard indicator. */
export function rowSubgradient(row: RowPolicy, value: number | null): RowSubgradient {
  if (value === null || !Number.isFinite(value)) return { state: 'unavailable' };
  if (!row.row.soft) {
    if ((row.lower !== null && value < row.lower) || (row.upper !== null && value > row.upper)) return { state: 'empty' };
    return { state: 'interval', lower: row.lower !== null && value === row.lower ? null : 0,
      upper: row.upper !== null && value === row.upper ? null : 0 };
  }
  const lower = row.lower === null ? 0 : -(row.lowerLinear + row.lowerQuadratic * Math.max(0, row.lower - value));
  const upper = row.upper === null ? 0 : row.upperLinear + row.upperQuadratic * Math.max(0, value - row.upper);
  const left = row.lower !== null && value <= row.lower ? lower : row.upper !== null && value > row.upper ? upper : 0;
  const right = row.lower !== null && value < row.lower ? lower : row.upper !== null && value >= row.upper ? upper : 0;
  return Number.isFinite(left) && Number.isFinite(right) ? { state: 'interval', lower: left, upper: right } : { state: 'unavailable' };
}

/** Bounded CSC windows are a view of stored coefficients, never a truncated Ax computation. */
export function sparseProblemView(doc: SoftQPResult | null, run: SoftQPRun | undefined, rowIndex: number, columnLimit = 6, rowLimit = 5) {
  const policy = intervalPolicy(doc, rowIndex), p = doc?.problem;
  if (!policy || !p) return null;
  const n = p.A.shape[1], m = p.A.shape[0];
  const limit = (value: number, maximum: number) => Math.min(maximum, Math.max(1, Number.isFinite(value) ? Math.floor(value) : 1));
  const rowTerms: { column: number; coefficient: number }[] = [];
  for (let column = 0; column < n; column++) {
    let coefficient = 0;
    for (let k = p.A.indptr[column]; k < p.A.indptr[column + 1]; k++) if (p.A.indices[k] === rowIndex) coefficient += p.A.data[k];
    if (coefficient !== 0) rowTerms.push({ column, coefficient });
  }
  const columnCount = limit(columnLimit, n), rowCount = limit(rowLimit, m);
  const start = Math.min(rowTerms[0]?.column ?? 0, n - columnCount);
  const columns = Array.from({ length: columnCount }, (_, i) => start + i);
  const rowStart = Math.min(Math.max(0, rowIndex - Math.floor(rowCount / 2)), m - rowCount);
  const rowIndices = Array.from({ length: rowCount }, (_, i) => rowStart + i);
  const window = (matrix: typeof p.A, rows: number[]) => ({
    shape: matrix.shape, nnz: matrix.data.filter(value => value !== 0).length,
    values: rows.map(row => columns.map(column => {
      let value = 0;
      for (let k = matrix.indptr[column]; k < matrix.indptr[column + 1]; k++) if (matrix.indices[k] === row) value += matrix.data[k];
      return value;
    })),
  });
  const candidate = run?.state === 'available' ? run.result?.x : undefined;
  const x = candidate?.length === n && candidate.every(Number.isFinite) ? columns.map(column => candidate[column]) : null;
  return { policy, n, m, columns, rowIndices, rowTerms, P: window(p.P, columns), A: window(p.A, rowIndices),
    q: columns.map(column => p.q[column]), x, value: selectedInterval(doc, run, rowIndex)?.value ?? null,
    omittedColumns: n - columns.length, omittedRows: m - rowIndices.length };
}

/** Explanatory minimal departures at returned x; these are not stored auxiliary variables or iterates. */
export function methodRowView(doc: SoftQPResult | null, run: SoftQPRun | undefined, rowIndex: number) {
  const policy = intervalPolicy(doc, rowIndex), p = doc?.problem;
  if (!policy || !p) return null;
  const selected = selectedInterval(doc, run, rowIndex);
  const value = selected?.value ?? null;
  const lowerSlack = value === null || policy.lower === null ? null : Math.max(0, policy.lower - value);
  const upperSlack = value === null || policy.upper === null ? null : Math.max(0, value - policy.upper);
  let slope: [number, number] | null = null;
  if (policy.row.soft && value !== null) {
    const lower = lowerSlack === null ? 0 : -(policy.lowerLinear + policy.lowerQuadratic * lowerSlack);
    const upper = upperSlack === null ? 0 : policy.upperLinear + policy.upperQuadratic * upperSlack;
    const left = policy.lower !== null && value <= policy.lower ? lower : policy.upper !== null && value > policy.upper ? upper : 0;
    const right = policy.lower !== null && value < policy.lower ? lower : policy.upper !== null && value >= policy.upper ? upper : 0;
    slope = [left, right];
  }
  // DAQP also supports mixed linear/quadratic sides through its wrapper's linear term.
  const sideWeight = (bound: number | null, quadratic: number) => policy.row.soft && bound !== null && quadratic > 0 ? 1 / quadratic : null;
  const duals = run?.state === 'available' ? run.result?.y : undefined;
  const recordedDual = duals?.length === p.A.shape[0] && Number.isFinite(duals[rowIndex]) ? duals[rowIndex] : null;
  const recordedDeparture = selected && Number.isFinite(selected.lowerViolation) && Number.isFinite(selected.upperViolation)
    ? Math.max(0, selected.lowerViolation, selected.upperViolation) : null;
  return { policy, value, lowerSlack, upperSlack, slope, subgradient: rowSubgradient(policy, value), recordedDual, recordedDeparture, price: value === null ? null : rowPrice(policy, value),
    finiteSoftSides: p.penalty.soft.reduce((count, soft, i) => count + (soft ? Number(p.lower[i] !== null) + Number(p.upper[i] !== null) : 0), 0),
    daqpWeights: { lower: sideWeight(policy.lower, policy.lowerQuadratic), upper: sideWeight(policy.upper, policy.upperQuadratic) } };
}

/** A read model of an already verified export. It never runs an optimization. */
export function selectedInterval(doc: SoftQPResult | null, run: SoftQPRun | undefined, rowIndex: number) {
  const policy = intervalPolicy(doc, rowIndex);
  const problem = doc?.problem;
  if (!policy || !problem || !run?.result?.metrics || run.state !== 'available') return null;
  const matrix = problem.A;
  const x = run.result.x;
  if (!Array.isArray(x) || x.length !== matrix.shape[1] || !x.every(Number.isFinite)) return null;
  let value = 0;
  for (let column = 0; column < matrix.shape[1]; column++) {
    for (let k = matrix.indptr[column]; k < matrix.indptr[column + 1]; k++) {
      if (matrix.indices[k] === rowIndex) value += matrix.data[k] * x[column];
    }
  }
  if (!Number.isFinite(value)) return null;
  return {
    ...policy, value,
    lowerViolation: run.result.metrics.lower_violation[rowIndex],
    upperViolation: run.result.metrics.upper_violation[rowIndex],
  };
}

/** Isolated separable row price, not the complete QP objective or a coupled policy. */
export function rowPrice(row: RowPolicy, value: number): number | null {
  if (!Number.isFinite(value)) return null;
  const lower = row.lower === null ? 0 : Math.max(0, row.lower - value);
  const upper = row.upper === null ? 0 : Math.max(0, value - row.upper);
  if (!row.row.soft) return lower > 0 || upper > 0 ? null : 0;
  const price = row.lowerLinear * lower + row.lowerQuadratic * lower * lower / 2
    + row.upperLinear * upper + row.upperQuadratic * upper * upper / 2;
  return Number.isFinite(price) ? price : null;
}

export function recordedFrame(stream: Stream | null | undefined, caseId: string, method: string, edited: boolean, frame: number) {
  if (!stream || caseId !== 'C12' || edited || !['lifted', 'asymmetric', 'daqp'].includes(method)) return null;
  if (!Number.isInteger(frame) || frame < 0 || frame >= stream.frames.length) return null;
  const selected = stream.frames[frame];
  if (!selected.runs.some(run => run.method === method && run.state === 'accepted')) return null;
  return selected;
}

export function sceneStateFromSearch(search: string) {
  const params = new URLSearchParams(search);
  const view = params.get('scene');
  const integer = (name: string, max: number) => {
    const raw = params.get(name);
    if (raw === null || !/^\d+$/.test(raw)) return 0;
    return Math.min(max, Number(raw));
  };
  return {
    view: SCENE_VIEWS.includes(view as SceneView) ? view as SceneView : 'system' as SceneView,
    row: integer('row', 100000), frame: integer('frame', 31), phase: integer('phase', 3),
  };
}

export function comparisonPopulation(doc: SoftQPResult | null) {
  const available = doc?.runs.filter(run => run.state === 'available' && run.result?.metrics
    && Number.isFinite(run.result.metrics.objective)) ?? [];
  return { available, unavailable: doc?.runs.filter(run => !available.includes(run)) ?? [] };
}

/** Descriptive agreement within one case; neither an uncertainty estimate nor a certificate. */
export function selectedCaseComparison(doc: SoftQPResult | null, unit: string) {
  const peers = comparisonPopulation(doc);
  const reference = peers.available.find(run => run.method === 'lifted') ?? peers.available[0];
  const referenceCost = reference?.result?.metrics?.objective;
  const hardRows = doc?.rows.flatMap((row, index) => !row.soft && row.unit === unit ? [index] : []) ?? [];
  const values = peers.available.map(run => {
    const metrics = run.result!.metrics!;
    const delta = referenceCost === undefined ? null : metrics.objective - referenceCost;
    return { run, delta, normalizedGap: delta === null ? null : Math.abs(delta) / Math.max(1, Math.abs(referenceCost!)),
      hardError: hardRows.length ? Math.max(0, ...hardRows.flatMap(index => [metrics.lower_violation[index], metrics.upper_violation[index]])) : null };
  });
  return { ...peers, reference, referenceCost, hardRows, unit, values,
    maxNormalizedGap: values.length ? Math.max(...values.map(value => value.normalizedGap!)) : null };
}

export interface NativeSceneRecord {
  id: string; caseId: string; baseSha256: string; result: SoftQPResult;
  edits: { lower: string; upper: string; quadratic: string };
}
/** One volatile verified import per page lifetime; never persist a user's vectors in a URL/storage. */
export function createNativeSceneMemory() {
  let record: NativeSceneRecord | null = null;
  return {
    put(value: NativeSceneRecord) { record = value; },
    get(id: string | null, caseId: string, baseSha256: string | undefined) {
      return record && record.id === id && record.caseId === caseId && record.baseSha256 === baseSha256 ? record : null;
    },
    clear() { record = null; },
  };
}

export interface TrajectoryPoint { time: number; value: number; frame: number; }
/** Exact within-interval kinematics explain held input; these are not extra observations. */
export function heldTrajectory(stream: Stream | null | undefined) {
  const dt = stream?.specification.dt_seconds;
  if (!stream?.frames.length || typeof dt !== 'number' || !Number.isFinite(dt) || dt <= 0) return null;
  const position: TrajectoryPoint[] = [], velocity: TrajectoryPoint[] = [], acceleration: TrajectoryPoint[] = [];
  const events: { frame: number; time: number; impulse: number; beforeVelocity: number; afterVelocity: number }[] = [];
  for (const [index, frame] of stream.frames.entries()) {
    const { state, next_state: next, applied_control: input, time_seconds: time, velocity_impulse: impulse } = frame;
    if (![...state, ...next, input, time, impulse].every(Number.isFinite) || state.length !== 2 || next.length !== 2) return null;
    const previous = stream.frames[index - 1];
    if (previous && (Math.abs(time - previous.time_seconds - dt) > 1e-8
      || Math.abs(state[0] - previous.next_state[0]) > 1e-6
      || Math.abs(state[1] - previous.next_state[1] - impulse) > 1e-6)) return null;
    if (Math.abs(next[0] - (state[0] + dt * state[1] + dt * dt * input / 2)) > 1e-6
      || Math.abs(next[1] - (state[1] + dt * input)) > 1e-6) return null;
    for (let part = 0; part <= 4; part++) {
      const elapsed = dt * part / 4, pointTime = Number((time + elapsed).toFixed(12));
      position.push({ time: pointTime, value: part === 4 ? next[0] : state[0] + elapsed * state[1] + elapsed * elapsed * input / 2, frame: index });
      velocity.push({ time: pointTime, value: part === 4 ? next[1] : state[1] + elapsed * input, frame: index });
    }
    acceleration.push({ time: Number(time.toFixed(12)), value: input, frame: index }, { time: Number((time + dt).toFixed(12)), value: input, frame: index });
    if (impulse !== 0) events.push({ frame: index, time, impulse, beforeVelocity: state[1] - impulse, afterVelocity: state[1] });
  }
  return { position, velocity, acceleration, events, dt, endTime: acceleration.at(-1)!.time };
}

type Bi = { en: string; es: string };
interface MethodPhase { id: string; label: Bi; detail: Bi; symbol: string; }
export function methodFormulation(doc: SoftQPResult | null, run: SoftQPRun | undefined) {
  if (!doc || !run) return null;
  const phase = (id: string, en: string, es: string, detail: string, detailEs: string, symbol: string): MethodPhase =>
    ({ id, label: { en, es }, detail: { en: detail, es: detailEs }, symbol });
  const phases: Record<string, MethodPhase[]> = {
    lifted: [phase('slacks', 'Build the recorded lift', 'Construir la elevación registrada', 'Use the compact symmetric or finite-side formulation selected by the actual coefficients. Missing coefficients remain unavailable.', 'Usar la formulación compacta simétrica o por lado elegida por los coeficientes reales. Los coeficientes ausentes siguen no disponibles.', 'x̃ = [x; actual auxiliaries]'),
      phase('stock-qp', 'Expanded QP solve', 'Resolver QP ampliado', 'OSQP solves the expanded QP with the same declared costs.', 'OSQP resuelve el QP ampliado con los mismos costos.', '½xᵀPx + qᵀx + φ(s)'),
      phase('recover-x', 'Recover original x', 'Recuperar x original', 'Discard auxiliary coordinates and recover signed original duals.', 'Retirar coordenadas auxiliares y recuperar duales originales.', 'x = x̃[1:n]'),
      phase('check-lift', 'Original evaluation', 'Evaluación original', 'Recompute original costs and departures; no stored iterate path.', 'Recalcular costos e incumplimientos; no hay trayectoria iterativa guardada.', 'F(x), Ax')],
    generalized: [phase('unconditional', 'Admit symmetric price', 'Admitir costo simétrico', 'The published path requires its unconditional penalty assumptions.', 'La implementación publicada exige sus hipótesis de penalización incondicional.', 'φ(r) = φ(−r)'),
      phase('published-prox', 'Generalized projection', 'Proyección generalizada', 'Keep the original QP block and replace its interval projection.', 'Conservar el bloque original y reemplazar su proyección del intervalo.', 'ΠC(v) + proxφ/ρ(v − ΠC(v))'),
      phase('recover-gsp', 'Recover native vectors', 'Recuperar vectores nativos', 'Read the original decision vector and original row duals.', 'Leer decisiones y duales de filas originales.', 'x ∈ ℝⁿ, y ∈ ℝᵐ'),
      phase('check-gsp', 'Evaluate same objective', 'Evaluar el mismo objetivo', 'An incompatible side-price request is retained, never symmetrized.', 'Los costos incompatibles se conservan, nunca se simetrizan.', 'F(x), zᵢ ∈ [lᵢ,uᵢ]')],
    asymmetric: [phase('side-policy', 'Separate side prices', 'Precios por lado', 'Retain lower and upper linear/quadratic prices independently.', 'Conservar precios lineales/cuadráticos por lado.', 'aₗ, aᵤ, bₗ, bᵤ'),
      phase('side-prox', 'Original-row update', 'Actualización por fila', 'The side-specific proximal map replaces the box step without extra x.', 'La operación proximal por lado reemplaza la caja sin ampliar x.', 'ρ(zᵢ − ΠCᵢzᵢ) ↔ φᵢ′'),
      phase('recover-side', 'Recover physical rows', 'Recuperar filas físicas', 'Recover Ax and duals in the original scale; hard rows stay hard.', 'Recuperar Ax y duales originales; las filas duras siguen duras.', 'z = Ax'),
      phase('check-side', 'Original-space check', 'Control original', 'Compare original costs and residuals; terminal evidence only.', 'Comparar costos y residuos originales; evidencia final solamente.', 'F(x), vₗ, vᵤ')],
    daqp: [phase('weighted-rows', 'Original side weights', 'Pesos originales por lado', 'Map positive quadratic prices to reciprocal DAQP weights.', 'Convertir precios cuadráticos positivos a pesos recíprocos DAQP.', 'b = 1 / ρsoft'),
      phase('dual-active', 'Dual active-set solve', 'Conjunto activo dual', 'The dual active-set method works on admitted positive-definite inputs.', 'El conjunto activo dual usa entradas definidas positivas admitidas.', 'A𝒜x ↔ y𝒜'),
      phase('recover-daqp', 'Recover scale and signs', 'Recuperar escala y signos', 'Recover original row dual signs and the primal decision.', 'Recuperar signos de duales originales y decisión primal.', 'x ∈ ℝⁿ, y ∈ ℝᵐ'),
      phase('check-daqp', 'Interpret soft status', 'Interpretar estado blando', 'Its soft-optimal status is checked against original costs, not another backend code.', 'El estado blando se contrasta con costos originales, no con códigos ajenos.', 'Cᵢ, φᵢ, F(x)')],
    flex: [phase('finite-l1', 'Finite-side L1 model', 'Modelo L1 por lado finito', 'Use declared finite positive L1 weights; hard rows are not softened.', 'Usar pesos L1 finitos positivos; no ablandar filas duras.', 'Gx − s ≤ h, s ≥ 0'),
      phase('flex-split', 'Fixed elastic splitting', 'Separación elástica fija', 'The paper-equation reconstruction uses fixed numerical parameters, no learned policy.', 'La reconstrucción usa parámetros fijos, sin política aprendida.', 'x ↔ s, s ≥ 0'),
      phase('recover-flex', 'Recover x and duals', 'Recuperar x y duales', 'Numerical proximal terms do not become extra scientific quadratic costs.', 'Los términos proximales no añaden costos científicos cuadráticos.', 'x ∈ ℝⁿ, y ∈ ℝᵐ'),
      phase('check-flex', 'Fixed-price meaning', 'Sentido del precio fijo', 'Feasibility restoration is not equivalent to every user-priced objective.', 'Restaurar factibilidad no equivale a cualquier objetivo con precios.', 'w, F(x)')],
    elastiqp: [phase('elastic-l1', 'Weighted linear sides', 'Lados lineales ponderados', 'Admit positive-definite L1 inputs and supported hard equalities.', 'Admitir entradas L1 definidas positivas e igualdades duras compatibles.', 'wᵀs, Gx − s ≤ h'),
      phase('elastic-active', 'Published active set', 'Conjunto activo publicado', 'The published dual active-set implementation solves the admitted model.', 'La implementación publicada resuelve el modelo admitido.', '𝒜 ↔ y𝒜'),
      phase('recover-elastic', 'Recover original duals', 'Recuperar duales originales', 'Map expanded finite-side multipliers back to original rows.', 'Llevar multiplicadores de cada lado a las filas originales.', '(yₗ, yᵤ) ↦ yᵤ − yₗ'),
      phase('check-elastic', 'Retain restrictions', 'Conservar restricciones', 'Quadratic soft prices and unsupported hard inequalities remain incompatible.', 'Los costos cuadráticos y desigualdades duras no admitidas son incompatibles.', 'F(x), Ax')],
  };
  const found = phases[run.method];
  if (!found) return null;
  const n = doc.problem?.A.shape[1] ?? run.result?.x?.length ?? null;
  const variables = run.state === 'available' ? run.result?.dimensions.variables ?? null : null;
  return { phases: found, originalVariables: n, originalRows: doc.rows.length, variables,
    rows: run.state === 'available' ? run.result?.dimensions.rows ?? null : null,
    auxiliaryVariables: n !== null && variables !== null && variables >= n ? variables - n : null };
}

/** Projection of the independently accepted frozen study; never recompute its statistics. */
export interface DirectionalSummary {
  protocol_sha256: string; evidence_review_sha256: string; source_commit: string;
  primary: { estimate: number; confidence_interval: number[]; denominator: number; failed_pairs: number; seed_clusters: number; established: boolean; failure_rule: string };
}
export async function admitDirectionalSummary(raw: string, expectedSha256: string): Promise<DirectionalSummary> {
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw))), byte => byte.toString(16).padStart(2, '0')).join('');
  if (digest !== expectedSha256) throw new Error('Directional study source identity mismatch');
  const value = JSON.parse(raw) as DirectionalSummary, p = value.primary;
  if (!p || ![p.estimate, ...p.confidence_interval].every(Number.isFinite) || p.confidence_interval.length !== 2
    || !Number.isInteger(p.denominator) || p.denominator <= 0 || !Number.isInteger(p.failed_pairs) || p.failed_pairs < 0 || p.failed_pairs > p.denominator
    || !Number.isInteger(p.seed_clusters) || p.seed_clusters <= 0 || typeof p.established !== 'boolean'
    || !/^[a-f0-9]{64}$/.test(value.protocol_sha256) || !/^[a-f0-9]{64}$/.test(value.evidence_review_sha256)
    || !/^[a-f0-9]{40}$/.test(value.source_commit) || typeof p.failure_rule !== 'string') throw new Error('Directional study summary is malformed');
  return value;
}
export function timingStudy(campaign: Campaign | undefined, directional: DirectionalSummary | null | undefined, study: 'original' | 'directional') {
  if (study === 'directional') return directional ? { estimate: 100 * directional.primary.estimate, interval: directional.primary.confidence_interval.map(value => 100 * value), denominator: directional.primary.denominator, failed: directional.primary.failed_pairs, clusters: directional.primary.seed_clusters, established: directional.primary.established, protocol: directional.protocol_sha256, source: 'accepted-summary.json', failureRule: directional.primary.failure_rule } : null;
  const p = campaign?.primary_endpoint;
  return p && p.median_relative_reduction !== null && p.confidence_interval_95 ? { estimate: 100 * p.median_relative_reduction, interval: p.confidence_interval_95.map(value => 100 * value), denominator: p.paired_samples, failed: p.rejected_pairs, clusters: p.seed_clusters, established: p.state === 'met', protocol: campaign!.protocol_sha256, source: 'campaign.json', failureRule: campaign!.protocol.failure_policy } : null;
}
