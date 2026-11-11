import type { ReactNode } from 'react';
import type { SoftQPResult, SoftQPRun } from '../lib/softqp';
import { methodRowView, sparseProblemView, methodFormulation, rowPrice, liftedEncoding } from './sceneModel';
import { coefficientLayout, type CoefficientWidths } from './coefficientLayout';
import { LinkedConstraintRow } from './LinkedConstraintPanel';

type Marker = (id: string, x: number, y: number, en: string, es: string, value: number | string | null | undefined, unit: string) => ReactNode;
interface DomainProps {
  doc: SoftQPResult; run: SoftQPRun | undefined; rowIndex: number; width: number; height: number;
  lang: 'en' | 'es'; number: (value: number | null | undefined) => string; marker: Marker;
  onRowSelect: (index: number) => void;
}
const activate = (action: () => void) => (event: React.KeyboardEvent<SVGGElement>) => {
  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); action(); }
};
function wrapped(value: string, x: number, y: number, chars = 40) {
  const lines: string[] = [];
  for (const word of value.split(' ')) {
    if (!lines.length || lines.at(-1)!.length + word.length + 1 > chars) lines.push(word);
    else lines[lines.length - 1] += ` ${word}`;
  }
  return <text x={x} y={y}>{lines.map((line, index) => <tspan key={index} x={x} dy={index ? 21 : 0}>{line}</tspan>)}</text>;
}

/** Actual CSC coefficients. A window never stands in for the complete original operator. */
export function SystemDomain({ doc, run, rowIndex, width, height, lang, number, marker, onRowSelect }: DomainProps) {
  const t = (en: string, es: string) => lang === 'es' ? es : en;
  const compact = width < 640;
  const requested = compact ? 2 : width < 1200 ? 4 : 6;
  const probe = sparseProblemView(doc, run, rowIndex, requested, compact ? 3 : 5)!;
  const labels = { p: probe.P.values.flat().map(number), a: probe.A.values.flat().map(number),
    q: probe.q.map(number), x: probe.x?.map(number) ?? ['∅'],
    row: probe.rowIndices.map(index => `▸${doc.rows[index].id}`) };
  // A local browser monospace face keeps 14px numbers stable across web-font loading and shell fonts.
  // This callback is invoked directly by Stage: it must not introduce React hooks or defer marker registration.
  const context = typeof document === 'undefined' ? null : document.createElement('canvas').getContext('2d');
  if (context) context.font = '14px monospace';
  const widths = Object.fromEntries(Object.entries(labels).map(([key, values]) =>
    [key, Math.max(0, ...values.map(value => context?.measureText(value).width ?? value.length * 9))])) as unknown as CoefficientWidths;
  // Row identifiers inherit the shell font; one em per glyph is a conservative width reservation.
  widths.row = Math.max(...labels.row.map(value => value.length * 14));
  const layout = coefficientLayout(width, probe.columns.length, widths);
  if (!layout) return <g data-domain-system="insufficient-space" data-state="insufficient-space" data-domain-row-value={probe.value ?? undefined} className="softqp-domain-math">
    <foreignObject x={18} y={145} width={Math.max(1, width - 36)} height={Math.max(1, height - 163)}>
      <div className="softqp-domain-insufficient" role="status">
        <p>{t('The coefficient diagram does not fit this width at 14px. Widen the drawing to view its cells.', 'El diagrama de coeficientes no cabe a este ancho con 14px. Amplía el dibujo para ver sus celdas.')}</p>
        <p>{t('No coefficient cells are drawn; original data are unchanged.', 'No se dibujan celdas de coeficientes; los datos originales no cambian.')} P [{probe.n}×{probe.n}], A [{probe.m}×{probe.n}], nnz(P/A)={probe.P.nnz}/{probe.A.nnz}.</p>
        <p>{probe.policy.row.id} · {t('complete Aᵢx', 'Aᵢx completo')} = <span className="softqp-domain-vector">{number(probe.value)}</span> [{probe.policy.row.unit}]</p>
        <p>{t('Omitted P columns/rows; A rows', 'Columnas/filas P omitidas; filas A')}: {probe.n}; {probe.m}.</p>
        <button type="button" disabled={rowIndex === 0} onClick={() => onRowSelect(rowIndex - 1)}>{t('Previous row', 'Fila anterior')}</button>{' '}
        <button type="button" disabled={rowIndex === doc.rows.length - 1} onClick={() => onRowSelect(rowIndex + 1)}>{t('Next row', 'Fila siguiente')}</button>
      </div>
    </foreignObject>
  </g>;
  const model = sparseProblemView(doc, run, rowIndex, layout.count, compact ? 3 : 5)!;
  const { policy, columns } = model;
  if (compact) {
    const { pCell: cell, pX, vectorX, xVectorX, braceX, matrixX: aX, cell: aCell } = layout;
    const rowH = 31, pY = 220, aY = 372;
    const xOffset = layout.stackVectors ? columns.length * rowH + 36 : 0;
    const vectorHeadingY = pY + 1;
    const plotY = height - 100, plotLeft = 34, plotRight = width - 30;
    const values = [policy.lower, policy.upper, model.value].filter((v): v is number => v !== null);
    const lo = Math.min(...values, 0) - 1, hi = Math.max(...values, 0) + 1;
    const sx = (v: number) => plotLeft + (v - lo) / (hi - lo) * (plotRight - plotLeft);
    return <g data-domain-system="sparse-operators" data-domain-row-value={model.value ?? undefined} className="softqp-domain-math">
      <text x={18} y={153} className="softqp-scene-heading">min ½xᵀPx + qᵀx + ∑ φᵢ(Aᵢx)</text>
      <text x={18} y={177}>{t('Algebraic x; units not exported', 'x algebraico; unidades no exportadas')}</text>
      <text x={pX} y={201}>P [{model.n}×{model.n}]</text>
      <text x={vectorX} y={vectorHeadingY}>q</text><text x={xVectorX} y={vectorHeadingY + xOffset}>x</text>
      {columns.map((column, j) => <text key={column} x={pX + (j + .5) * cell} y={pY - 5} textAnchor="middle">{column + 1}</text>)}
      {model.P.values.map((row, i) => <g key={i}><text x={pX - 8} y={pY + i * rowH + 20} textAnchor="end">{columns[i] + 1}</text>{row.map((v, j) => <g key={j} data-matrix="P" data-matrix-row={columns[i]} data-matrix-column={columns[j]} data-coefficient={v}><title>{`${doc.case_id}: ${v}`}</title><rect x={pX + j * cell} y={pY + i * rowH} width={cell - 2} height={rowH - 2} className={`softqp-domain-coefficient${v ? ' present' : ''}`} /><text x={pX + (j + .5) * cell} y={pY + i * rowH + 20} textAnchor="middle">{number(v)}</text></g>)}<text className="softqp-domain-vector" x={vectorX} y={pY + i * rowH + 20}>{number(model.q[i])}</text><text className="softqp-domain-vector" x={xVectorX} y={pY + i * rowH + 20 + xOffset}>{model.x ? number(model.x[i]) : '∅'}</text></g>)}
      <path d={`M${braceX},${pY}h8v${columns.length * rowH + xOffset}h-8`} fill="none" className="softqp-scene-axis" />
      <text x={aX} y={348}>A [{model.m}×{model.n}] → Ax</text>
      {columns.map((column, j) => <text key={column} x={aX + (j + .5) * aCell} y={aY - 5} textAnchor="middle">x{column + 1}</text>)}
      {model.A.values.map((row, i) => { const index = model.rowIndices[i], item = doc.rows[index], selected = index === rowIndex; return <LinkedConstraintRow key={item.id} doc={doc} index={index} selected={selected} onSelect={() => onRowSelect(index)}><rect x={18} y={aY + i * rowH} width={width - 36} height={rowH - 2} className={selected ? 'softqp-domain-row selected' : 'softqp-domain-row'} /><text x={aX - 8} y={aY + i * rowH + 20} textAnchor="end">{selected ? '▸' : ''}{item.id}</text>{row.map((v, j) => <g key={j} data-matrix="A" data-matrix-row={index} data-matrix-column={columns[j]} data-coefficient={v}><title>{`${doc.case_id}: ${v}`}</title><rect x={aX + j * aCell} y={aY + i * rowH + 1} width={aCell - 2} height={rowH - 4} className={`softqp-domain-coefficient${v ? ' present' : ''}`} /><text x={aX + (j + .5) * aCell} y={aY + i * rowH + 20} textAnchor="middle">{number(v)}</text></g>)}<text x={aX + columns.length * aCell + 10} y={aY + i * rowH + 20}>{item.soft ? 'S' : 'H'}</text></LinkedConstraintRow>; })}
      <text x={18} y={height - 128}>{t('Omitted P cols/rows; A rows', 'Omitidos P cols/filas; filas A')}: {model.omittedColumns}; {model.omittedRows} [1]</text>
      <line x1={plotLeft} x2={plotRight} y1={plotY} y2={plotY} className="softqp-scene-axis" />
      {[policy.lower, policy.upper].map((v, i) => <g key={i}><line x1={sx(v ?? (i ? hi : lo))} x2={sx(v ?? (i ? hi : lo))} y1={plotY - 12} y2={plotY + 12} className="softqp-scene-bound" /><text x={sx(v ?? (i ? hi : lo))} y={plotY + 30} textAnchor="middle">{v === null ? i ? '+∞' : '−∞' : number(v)}</text></g>)}
      {marker('variables', braceX + 8, pY + columns.length * rowH + xOffset, 'Original n', 'n original', model.n, '1')}
      {marker('policy', aX + columns.length * aCell + 28, aY + model.rowIndices.indexOf(rowIndex) * rowH + 15, 'Soft mask', 'Máscara blanda', policy.row.soft ? 1 : 0, '1')}
      {marker('row-value', model.value === null ? plotLeft : sx(model.value), plotY, 'Returned Ax', 'Ax devuelto', model.value, policy.row.unit)}
      <text x={18} y={height - 38}>{policy.row.id} · {t('complete Aᵢx', 'Aᵢx completo')} = {number(model.value)} [{policy.row.unit}]</text>
      <text x={18} y={height - 13}>{t('Select a row · H hard / S soft', 'Selecciona · H dura / S blanda')}</text>
    </g>;
  }
  const x0 = 30, { split, matrixX, cell, pCell, pX, vectorX, xVectorX, braceX } = layout;
  const matrixY = 218, rh = Math.min(62, (height - 430) / Math.max(columns.length, model.rowIndices.length));
  const intervalY = height - 114;
  const v = model.value;
  const values = [policy.lower, policy.upper, v].filter((x): x is number => x !== null);
  const lo = Math.min(...values, 0) - 1, hi = Math.max(...values, 0) + 1;
  const sx = (x: number) => matrixX + (x - lo) / (hi - lo) * (width - matrixX - 34);
  const selectedY = matrixY + model.rowIndices.indexOf(rowIndex) * rh;
  const coefficients = model.rowTerms.slice(0, 4).map(term => `${number(term.coefficient)}x${term.column + 1}`).join(' + ');
  return <g data-domain-system="sparse-operators" data-domain-row-value={model.value ?? undefined} className="softqp-domain-math">
    <text x={x0} y={143} className="softqp-scene-heading">min ½xᵀPx + qᵀx + ∑ φᵢ(Aᵢx)</text>
    <text x={x0} y={165}>{t('Stored algebraic coordinates; decision units not exported', 'Coordenadas algebraicas; unidades de x no exportadas')}</text>
    <text x={pX} y={190} className="softqp-scene-heading">P [{model.n}×{model.n}]</text>
    <text x={vectorX} y={matrixY - 6} className="softqp-scene-heading">q</text><text x={xVectorX} y={matrixY - 6} className="softqp-scene-heading">x</text>
    {model.P.values.map((row, i) => <g key={i}><text x={pX - 18} y={matrixY + (i + .5) * rh + 5} textAnchor="end">{columns[i] + 1}</text>{row.map((value, j) => <g key={j} data-matrix="P" data-matrix-row={columns[i]} data-matrix-column={columns[j]} data-coefficient={value}><title>{`${doc.case_id}: ${value}`}</title><rect x={pX + j * pCell} y={matrixY + i * rh} width={pCell - 2} height={rh - 2} className={`softqp-domain-coefficient${value ? ' present' : ''}`} /><text x={pX + (j + .5) * pCell} y={matrixY + (i + .5) * rh + 5} textAnchor="middle">{number(value)}</text></g>)}<text className="softqp-domain-vector" x={vectorX} y={matrixY + (i + .5) * rh + 5} data-vector-column={columns[i]}>{number(model.q[i])}</text><text className="softqp-domain-vector" x={xVectorX} y={matrixY + (i + .5) * rh + 5}>{model.x ? number(model.x[i]) : '∅'}</text></g>)}
    <path d={`M${braceX},${matrixY}h8v${rh * columns.length}h-8`} className="softqp-scene-axis" fill="none" />
    <path d={`M${braceX + 8},${matrixY + rh * columns.length / 2} L${split - 8},${selectedY + rh / 2} l-7,-4 m7,4 l-7,4`} className="softqp-scene-axis" fill="none" data-decision-row-link={policy.row.id} />
    {columns.map((column, j) => <text key={column} x={pX + (j + .5) * pCell} y={matrixY - 5} textAnchor="middle" className="softqp-domain-index">{column + 1}</text>)}
    <text x={matrixX} y={190} className="softqp-scene-heading">A [{model.m}×{model.n}] → Ax</text>
    {columns.map((column, j) => <text key={column} x={matrixX + (j + .5) * cell} y={matrixY - 5} textAnchor="middle" className="softqp-domain-index">x{column + 1}</text>)}
    {model.A.values.map((row, i) => {
      const index = model.rowIndices[i], original = doc.rows[index], selected = index === rowIndex, y = matrixY + i * rh;
      return <LinkedConstraintRow key={original.id} doc={doc} index={index} selected={selected} onSelect={() => onRowSelect(index)}>
        <rect x={split + 2} y={y} width={width - split - 20} height={rh - 2} className={selected ? 'softqp-domain-row selected' : 'softqp-domain-row'} />
        <text x={matrixX - 9} y={y + rh / 2 + 5} textAnchor="end">{selected ? '▸' : ''}{original.id}</text>
        {row.map((value, j) => <g key={j} data-matrix="A" data-matrix-row={index} data-matrix-column={columns[j]} data-coefficient={value}><title>{`${doc.case_id}: ${value}`}</title><rect x={matrixX + j * cell} y={y + 1} width={cell - 2} height={rh - 4} className={`softqp-domain-coefficient${value ? ' present' : ''}`} /><text x={matrixX + (j + .5) * cell} y={y + rh / 2 + 5} textAnchor="middle">{number(value)}</text></g>)}
        <text x={matrixX + columns.length * cell + 18} y={y + rh / 2 + 5}>{original.soft ? 'S' : 'H'}</text>
      </LinkedConstraintRow>;
    })}
    <text x={x0} y={intervalY - 69}>{t('Omitted P rows/cols', 'Filas/cols P omitidas')}: {model.omittedColumns}; {t('A rows', 'filas A')}: {model.omittedRows} · nnz(P/A)={model.P.nnz}/{model.A.nnz} [1]</text>
    <text x={x0} y={intervalY - 40}>{policy.row.id}: {coefficients || '0'}{model.rowTerms.length > 4 ? ' + …' : ''}{model.rowTerms.length > 4 ? t(' (terms omitted)', ' (términos omitidos)') : ''}</text>
    <text x={x0} y={intervalY + 9} className="softqp-scene-heading">{t('Complete Aᵢx', 'Aᵢx completo')} = {number(v)} [{policy.row.unit}]</text>
    <line x1={matrixX} x2={width - 34} y1={intervalY} y2={intervalY} className="softqp-scene-axis" />
    {[policy.lower, policy.upper].map((bound, i) => <g key={i}><line x1={sx(bound ?? (i ? hi : lo))} x2={sx(bound ?? (i ? hi : lo))} y1={intervalY - 13} y2={intervalY + 13} className="softqp-scene-bound" /><text x={sx(bound ?? (i ? hi : lo))} y={intervalY + 31} textAnchor="middle">{bound === null ? i ? '+∞' : '−∞' : number(bound)}</text></g>)}
    {marker('variables', braceX + 8, matrixY + rh * columns.length, 'Original n', 'n original', model.n, '1')}
    {marker('row-value', v === null ? matrixX : sx(v), intervalY, 'Returned Ax', 'Ax devuelto', v, policy.row.unit)}
    {marker('policy', matrixX + columns.length * cell + 38, selectedY + rh / 2, 'Soft mask', 'Máscara blanda', policy.row.soft ? 1 : 0, '1')}
    <text x={x0} y={height - 54}>{t('Recorded objective', 'Objetivo registrado')}: {number(run?.state === 'available' ? run.result?.metrics?.base_objective : null)} + {number(run?.state === 'available' ? run.result?.metrics?.penalty_objective : null)} ≈ {number(run?.state === 'available' ? run.result?.metrics?.objective : null)} [cost]</text>
    <text x={x0} y={height - 13}>{t('Select an original A row · H hard / S soft · cells: exact stored operator, including zeros', 'Selecciona una fila A · H dura / S blanda · celdas: operador original, incluidos ceros')}</text>
  </g>;
}

export function MethodDomain({ doc, run, rowIndex, width, height, lang, number, marker, phaseIndex, onPhaseSelect }: DomainProps & { phaseIndex: number; onPhaseSelect?: (index: number) => void }) {
  const t = (en: string, es: string) => lang === 'es' ? es : en;
  const formulation = methodFormulation(doc, run)!;
  const model = methodRowView(doc, run, rowIndex);
  const phase = formulation.phases[phaseIndex];
  const x = 28, w = width - 56, middle = width * .53;
  const policy = model?.policy;
  const low = policy?.lower, high = policy?.upper;
  const bound = (v: number | null | undefined, side: string) => v === null ? side : number(v);
  const rowName = policy?.row.id ?? t('original row unavailable', 'fila original no disponible');
  const dimensions = `x ∈ ℝ${formulation.originalVariables ?? '?'} → ${t('solver', 'solver')} ℝ${formulation.variables ?? '?'} · ${formulation.originalRows} → ${formulation.rows ?? '?'} ${t('rows', 'filas')}`;
  const lift = liftedEncoding(doc, run);
  const liftExpressions = !lift || lift.agreesWithRecord === false
    ? [t('Lift coefficients unavailable or inconsistent', 'Coeficientes de elevación ausentes o inconsistentes'), t('Recorded terminal dimensions only', 'Solo dimensiones finales registradas'), 'x = x̃[1:n]; yᵢ = ∑ⱼ→ᵢ ỹⱼ', 'F(x), Ax']
    : lift.kind === 'separate-sides'
      ? [t('x̃ = [x; sfinite], s ≥ 0', 'x̃ = [x; sfinitos], s ≥ 0'), t('l − sₗ ≤ Ax ≤ u + sᵤ (finite sides)', 'l − sₗ ≤ Ax ≤ u + sᵤ (lados finitos)'), 'x = x̃[1:n]; yᵢ = ∑ⱼ→ᵢ ỹⱼ', 'F(x) = ½xᵀPx + qᵀx + ∑φᵢ(Aᵢx)']
      : [lift.signed && lift.shared ? t(`x̃=[x;ξ;s], ξ free (${lift.signed}), s≥0 (${lift.shared})`, `x̃=[x;ξ;s], ξ libre (${lift.signed}), s≥0 (${lift.shared})`) : lift.signed ? t(`x̃=[x;ξ], ξ∈ℝ${lift.signed} (signed)`, `x̃=[x;ξ], ξ∈ℝ${lift.signed} (con signo)`) : `x̃=[x;s], s≥0 (${lift.shared})`,
         lift.signed && lift.shared ? t('ξ rows: l≤Ax+ξ≤u; s rows: l−s≤Ax≤u+s', 'Filas ξ: l≤Ax+ξ≤u; filas s: l−s≤Ax≤u+s') : lift.signed ? t('l ≤ Ax + ξ ≤ u; cost ½ξᵀdiag(b)ξ', 'l ≤ Ax + ξ ≤ u; costo ½ξᵀdiag(b)ξ') : t('l − s ≤ Ax ≤ u + s; cost aᵀs+½sᵀdiag(b)s', 'l − s ≤ Ax ≤ u + s; costo aᵀs+½sᵀdiag(b)s'),
         'x = x̃[1:n]; yᵢ = ∑ⱼ→ᵢ ỹⱼ', 'F(x) = ½xᵀPx + qᵀx + ∑φᵢ(Aᵢx)'];
  const subgradient = model?.subgradient;
  const slopeText = !subgradient || subgradient.state === 'unavailable' ? t('unavailable', 'no disponible')
    : subgradient.state === 'empty' ? '∅'
    : subgradient.lower === null && subgradient.upper === null ? 'ℝ'
    : subgradient.lower === subgradient.upper ? `{${number(subgradient.lower)}}`
    : `${subgradient.lower === null ? '(−∞' : `[${number(subgradient.lower)}`}, ${subgradient.upper === null ? '+∞)' : `${number(subgradient.upper)}]`}`;
  const expressions: Record<string, string[]> = {
    lifted: liftExpressions,
    generalized: [t('φᵢ(d) = φᵢ(−d) (symmetric domain)', 'φᵢ(d) = φᵢ(−d) (dominio simétrico)'), 'ΠC(v) + proxφ/ρ(v − ΠC(v))', t('x ∈ ℝⁿ ; y ∈ ℝᵐ (original scale)', 'x ∈ ℝⁿ ; y ∈ ℝᵐ (escala original)'), t('F(x), hard departures, original side costs', 'F(x), incumplimientos duros, costos originales')],
    asymmetric: ['φᵢ = aₗdₗ + ½bₗdₗ² + aᵤdᵤ + ½bᵤdᵤ²', 'd⁺ = max(0, (ρ|v − ΠC(v)| − a)/(ρ + b))', t('z = Ax ; original x and signed row duals', 'z = Ax ; x original y duales con signo'), 'F(x), vₗ = (l − Ax)₊, vᵤ = (Ax − u)₊'],
    daqp: ['φside(d) = ad + ½bd² ; b > 0', t('x = −P⁻¹(q + Aᵀy) ; active row set', 'x = −P⁻¹(q + Aᵀy) ; conjunto activo'), t('Recover x ; lower/upper dual signs', 'Recuperar x ; signos de duales por lado'), t('Original F(x) and hard error; soft status', 'F(x) original y error duro; estado blando')],
    flex: ['min ½xᵀPx + qᵀx + wᵀs ; Gx − s ≤ h', t('K = P + σₓI + cGᵀG (fixed splitting)', 'K = P + σₓI + cGᵀG (separación fija)'), t('x ; y = μᵤ − μₗ ; proximal terms excluded', 'x ; y = μᵤ − μₗ ; sin términos proximales'), t('Finite-price restoration ≠ hard feasibility', 'Restauración a precio finito ≠ factibilidad dura')],
    elastiqp: ['min ½xᵀPx + qᵀx + ∑wⱼ(Gⱼx − hⱼ)₊', 'Px + Eᵀν = −q − Gᵀμ ; 0 ≤ μ ≤ w', t('Hard equalities Ex=e ; y = μᵤ − μₗ', 'Igualdades duras Ex=e ; y = μᵤ − μₗ'), t('Pure L1, P ≻ 0; hard inequalities refused', 'L1 puro, P ≻ 0; desigualdades duras no admitidas')],
  };
  const formula = expressions[run!.method][phaseIndex];
  const y = 294, plotTop = 346, plotBottom = height - 89;
  const rowValues = [low, high, model?.value].filter((v): v is number => typeof v === 'number');
  const lo = Math.min(...rowValues, 0) - 1, hi = Math.max(...rowValues, 0) + 1;
  const px = (v: number) => middle + (v - lo) / (hi - lo) * (width - middle - 32);
  const samples = Array.from({ length: 81 }, (_, i) => lo + (hi - lo) * i / 80);
  const prices = policy ? samples.map(v => rowPrice(policy, v)) : [];
  const maxPrice = Math.max(1, ...prices.filter((v): v is number => v !== null));
  const py = (v: number) => plotBottom - v / maxPrice * (plotBottom - plotTop);
  const curve = samples.map((v, i) => prices[i] === null || prices[i] === undefined ? '' : `${!i || prices[i - 1] === null ? 'M' : 'L'}${px(v)},${py(prices[i]!)}`).join(' ');
  const exactHardOutside = !!policy && !policy.row.soft && model?.value !== null && model?.price === null;
  const reportedF = run?.state === 'available' ? run.result?.metrics?.objective : null;
  const lines = !policy ? [t('Original separable row unavailable', 'Fila separable original no disponible'), t('No row coefficients or price invented', 'Sin coeficientes ni costos inventados'), t('Recorded method dimensions retained', 'Se conservan las dimensiones registradas')]
    : !policy.row.soft ? [`${bound(low, '−∞')} ≤ Aᵢx ≤ ${bound(high, '+∞')}`, `${t('Recorded departure', 'Incumplimiento registrado')} = ${number(model?.recordedDeparture)} [${policy.row.unit}]`, `${t('Reported F', 'F registrado')} = ${number(reportedF)} [cost]`]
    : run!.method === 'daqp' ? [`ρsoft,L = 1/bₗ = ${number(model?.daqpWeights.lower)}`, `ρsoft,U = 1/bᵤ = ${number(model?.daqpWeights.upper)}`, t('Algebraic inverse-curvature weights', 'Pesos algebraicos de curvatura inversa')]
    : run!.method === 'lifted' && lift?.kind === 'compact' ? policy.lowerLinear === 0
      ? ['lᵢ ≤ Aᵢx + ξᵢ ≤ uᵢ', 'ξᵢ* = Π[lᵢ,uᵢ](Aᵢx) − Aᵢx', `ξᵢ* = ${number(model?.value === null || model?.value === undefined ? null : Math.min(policy.upper ?? Infinity, Math.max(policy.lower ?? -Infinity, model.value)) - model.value)} [${policy.row.unit}]`]
      : ['lᵢ − sᵢ ≤ Aᵢx ≤ uᵢ + sᵢ', 'sᵢ* = max(dₗ, dᵤ), sᵢ ≥ 0', `sᵢ* = ${number(model ? Math.max(model.lowerSlack ?? 0, model.upperSlack ?? 0) : null)} [${policy.row.unit}]`]
    : ['lifted', 'flex', 'elastiqp'].includes(run!.method) ? [low === null ? t('Lower side absent; no slack', 'Lado inferior ausente; sin holgura') : `−Aᵢx − sₗ ≤ ${number(low === undefined ? undefined : -low)}`, high === null ? t('Upper side absent; no slack', 'Lado superior ausente; sin holgura') : ` Aᵢx − sᵤ ≤ ${number(high)}`, `sₗ* = ${number(model?.lowerSlack)} ; sᵤ* = ${number(model?.upperSlack)}`]
    : [`dₗ = (${bound(low, '−∞')} − z)₊ ; dᵤ = (z − ${bound(high, '+∞')})₊`, `aₗ/aᵤ = ${number(policy?.lowerLinear)}/${number(policy?.upperLinear)}`, `bₗ/bᵤ = ${number(policy?.lowerQuadratic)}/${number(policy?.upperQuadratic)}`];
  if (width < 640) {
    const compactLines = policy && !policy.row.soft ? [`${bound(low, '−∞')} ≤ Aᵢx ≤ ${bound(high, '+∞')}`, `Δrec = ${number(model?.recordedDeparture)} [${policy.row.unit}]`, `Frec = ${number(reportedF)} [cost]`] : lines;
    const left = 44, right = width - 26, lowerY = height - 112, upperY = 510;
    const cx = (value: number) => left + (value - lo) / (hi - lo) * (right - left);
    const cy = (value: number) => lowerY - value / maxPrice * (lowerY - upperY);
    const d = samples.map((v, i) => prices[i] === null || prices[i] === undefined ? '' : `${!i || prices[i - 1] === null ? 'M' : 'L'}${cx(v)},${cy(prices[i]!)}`).join(' ');
    return <g data-domain-method="formulation-and-terminal" data-domain-row-value={model?.value ?? undefined} data-domain-row-price={model?.price ?? undefined} data-method-phase={phase.id} className="softqp-domain-math">
      {formulation.phases.map((item, index) => <g key={item.id} role="button" tabIndex={0} aria-label={`${index + 1}. ${item.label[lang]}`} aria-pressed={index === phaseIndex} data-method-step={index} onClick={() => onPhaseSelect?.(index)} onKeyDown={activate(() => onPhaseSelect?.(index))}><rect x={18 + index * (width - 36) / 4} y={145} width={(width - 36) / 4 - 5} height={32} rx={4} className={index === phaseIndex ? 'softqp-scene-step selected' : 'softqp-scene-step'} /><text x={18 + (index + .5) * (width - 36) / 4} y={167} textAnchor="middle">{index + 1}</text></g>)}
      <text x={18} y={202} className="softqp-scene-heading">{phase.label[lang]}</text>
      {wrapped(formula, 18, 229, 37)}
      <text x={18} y={310}>x ∈ ℝ{formulation.originalVariables ?? '?'} → {t('solver', 'solver')} ℝ{formulation.variables ?? '?'}</text>
      <path d="M18,317h83m30,0h138" className="softqp-scene-axis" />
      <text x={18} y={341}>{t('Rows', 'Filas')}: {formulation.originalRows} → {formulation.rows ?? '?'} [1]</text>
      <text x={18} y={366}>{t('Soft sides / auxiliaries', 'Lados blandos / auxiliares')}: {number(model?.finiteSoftSides)}/{number(formulation.auxiliaryVariables)} [1]</text>
      <text x={18} y={397} className="softqp-scene-heading">{rowName}</text>
      {compactLines.map((line, i) => <text key={i} x={18} y={421 + i * 23}>{line}</text>)}
      <text x={left} y={492}>{t('Original row price [cost]', 'Costo original de fila [costo]')}</text>
      {policy && <><line x1={left} x2={left} y1={upperY} y2={lowerY} className="softqp-scene-axis" /><line x1={left} x2={right} y1={lowerY} y2={lowerY} className="softqp-scene-axis" /><text x={left - 5} y={upperY + 4} textAnchor="end">{number(maxPrice)}</text><text x={left - 5} y={lowerY + 4} textAnchor="end">0</text><path d={d} className="softqp-scene-line" data-method-row-price="" />{[policy.lower, policy.upper].map((v, i) => <g key={i}><line x1={cx(v ?? (i ? hi : lo))} x2={cx(v ?? (i ? hi : lo))} y1={upperY} y2={lowerY} className="softqp-scene-bound" /><text x={cx(v ?? (i ? hi : lo))} y={lowerY + 22} textAnchor="middle">{v === null ? i ? '+∞' : '−∞' : number(v)}</text></g>)}<text x={left} y={lowerY + 44}>z = Aᵢx [{policy.row.unit}]</text></>}
      {marker('original-n', 101, 317, 'Original n', 'n original', formulation.originalVariables, '1')}
      {marker('formulated-n', 269, 317, 'Formulated n', 'n formulado', formulation.variables, '1')}
      {model?.value !== null && model?.value !== undefined && model.price === null && policy && <><line x1={cx(model.value)} x2={cx(model.value)} y1={upperY} y2={lowerY} className="softqp-scene-cursor" /><text x={cx(model.value) + 9} y={upperY - 8}>{policy.row.soft ? 'φ = ∅' : 'φ = ∞'}</text></>}
      {marker('row-value', model?.value === null || !model ? left : cx(model.value), model?.price === null || !model ? upperY : cy(model.price), 'Returned Ax', 'Ax devuelto', model?.value, policy?.row.unit ?? '1')}
      <text x={18} y={height - 40}>{exactHardOutside ? t('φ=∞ exact; F uses numerical tolerances', 'φ=∞ exacta; F usa tolerancias numéricas') : t('Terminal reconstruction; no stored iterates', 'Reconstrucción final; sin iterados registrados')}</text>
      <text x={18} y={height - 15}>∂φ={slopeText}; {t('recorded', 'registrado')} yᵢ={number(model?.recordedDual)} [cost/({policy?.row.unit ?? '?'})]</text>
    </g>;
  }
  return <g data-domain-method="formulation-and-terminal" data-domain-row-value={model?.value ?? undefined} data-domain-row-price={model?.price ?? undefined} data-method-phase={phase.id} className="softqp-domain-math">
    {formulation.phases.map((item, index) => <g key={item.id} role="button" tabIndex={0} aria-label={`${index + 1}. ${item.label[lang]}`} aria-pressed={index === phaseIndex} data-method-step={index} onClick={() => onPhaseSelect?.(index)} onKeyDown={activate(() => onPhaseSelect?.(index))}><rect x={x + index * w / 4} y={120} width={w / 4 - 6} height={32} rx={4} className={index === phaseIndex ? 'softqp-scene-step selected' : 'softqp-scene-step'} /><text x={x + (index + .5) * w / 4} y={142} textAnchor="middle">{index + 1}</text></g>)}
    <text x={x} y={179} className="softqp-scene-heading">{phase.label[lang]}</text>
    <text x={x} y={205} data-method-equation="">{formula}</text>
    <text x={x} y={232}>{dimensions}</text>
    <text x={x} y={257}>{t('Finite soft sides', 'Lados blandos finitos')}: {number(model?.finiteSoftSides)} · {t('recorded auxiliary decisions', 'decisiones auxiliares registradas')}: {number(formulation.auxiliaryVariables)}</text>
    <line x1={x} x2={width - x} y1={274} y2={274} className="softqp-scene-grid" />
    <text x={x} y={y} className="softqp-scene-heading">{rowName} · {policy ? policy.row.soft ? t('priced sides', 'lados con precio') : t('hard original row', 'fila original dura') : '∅'}</text>
    {lines.map((line, i) => <text x={x} y={y + 27 + i * 26} key={i}>{line}</text>)}
    <text x={middle} y={y}>{t('Original row price [cost]', 'Costo de fila original [costo]')}</text>
    {policy && <><line x1={middle} x2={middle} y1={plotTop} y2={plotBottom} className="softqp-scene-axis" /><line x1={middle} x2={width - 32} y1={plotBottom} y2={plotBottom} className="softqp-scene-axis" /><text x={middle - 6} y={plotTop + 4} textAnchor="end">{number(maxPrice)}</text><text x={middle - 6} y={plotBottom + 4} textAnchor="end">0</text><path d={curve} className="softqp-scene-line" data-method-row-price="" />{[policy.lower, policy.upper].map((v, i) => <g key={i}><line x1={px(v ?? (i ? hi : lo))} x2={px(v ?? (i ? hi : lo))} y1={plotTop} y2={plotBottom} className="softqp-scene-bound" /><text x={px(v ?? (i ? hi : lo))} y={plotBottom + 21} textAnchor="middle">{v === null ? i ? '+∞' : '−∞' : number(v)}</text></g>)}<text x={middle} y={plotBottom + 41}>z = Aᵢx [{policy.row.unit}]</text></>}
    <path d={`M${x},240h100m30,0h130`} className="softqp-scene-axis" />
    {marker('original-n', x + 100, 240, 'Original n', 'n original', formulation.originalVariables, '1')}
    {marker('formulated-n', x + 260, 240, 'Formulated n', 'n formulado', formulation.variables, '1')}
    {model?.value !== null && model?.value !== undefined && model.price === null && policy && <><line x1={px(model.value)} x2={px(model.value)} y1={plotTop} y2={plotBottom} className="softqp-scene-cursor" /><text x={px(model.value) + 9} y={plotTop - 8}>{policy.row.soft ? 'φ = ∅' : 'φ = ∞'}</text></>}
    {marker('row-value', model?.value === null || !model ? middle : px(model.value), model?.price === null || !model ? plotTop : py(model.price), 'Returned Ax', 'Ax devuelto', model?.value, policy?.row.unit ?? '1')}
    <text x={x} y={height - 36}>{exactHardOutside ? t('φ=∞ is the exact interval indicator. Reported finite F and hard-row acceptance use numerical tolerances.', 'φ=∞ es el indicador exacto. F finito registrado y aceptación de filas duras usan tolerancias numéricas.') : t('Terminal reconstruction only; no intermediate iterates or algorithmic proximal ρ exported.', 'Solo reconstrucción final; sin iterados intermedios ni ρ proximal algorítmico exportados.')}</text>
    <text x={x} y={height - 13}>{t('Row price', 'Costo de fila')}: {exactHardOutside ? '∞' : number(model?.price)} [cost] · ∂φ = {slopeText} [cost/({policy?.row.unit ?? '?'})] · {t('recorded', 'registrado')} yᵢ={number(model?.recordedDual)} [cost/({policy?.row.unit ?? '?'})]</text>
  </g>;
}
