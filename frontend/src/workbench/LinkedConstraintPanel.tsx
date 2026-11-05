import { formatNumber, useLinkedCursor, useLinkedItem, useShellLang } from '@fasl-work/caos-app-shell';
import type { ReactNode } from 'react';
import type { SoftQPResult, SoftQPRun } from '../lib/softqp';
import { intervalPolicy, selectedInterval, sparseProblemView } from './sceneModel';

/** Stable artifact identity, not a row label shared accidentally by two cases. */
export const constraintEntityId = (doc: SoftQPResult, index: number) => `${doc.case_id}:${doc.rows[index].id}`;

/** The only cursor introduced here is a dimensionless, integral constraint ordinal. */
export function constraintIndex(ordinal: number, count: number) {
  return Number.isFinite(ordinal) && count > 0 ? Math.min(count - 1, Math.max(0, Math.round(ordinal) - 1)) : null;
}

/** A real original-operator row; the children retain their reviewed coefficient geometry. */
export function LinkedConstraintRow({ doc, index, selected, onSelect, children }: {
  doc: SoftQPResult; index: number; selected: boolean; onSelect: () => void; children: ReactNode;
}) {
  const lang = useShellLang();
  const linked = useLinkedItem(constraintEntityId(doc, index), 'scene');
  const cursor = useLinkedCursor();
  const activate = () => { linked.onClick(); onSelect(); };
  return <g {...linked} {...(selected && cursor.cursor !== null ? cursor.markerProps : {})}
    role="button" tabIndex={0} aria-label={`${doc.rows[index].id} ${doc.rows[index].label[lang]}`}
    data-linked-row={doc.rows[index].id} data-original-row={index}
    onClick={activate} onKeyDown={event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); }
    }}>{children}</g>;
}

function ConstraintChoice({ doc, run, index, onSelect }: {
  doc: SoftQPResult; run: SoftQPRun | undefined; index: number; onSelect: (index: number) => void;
}) {
  const lang = useShellLang(), linked = useLinkedItem(constraintEntityId(doc, index), 'panel');
  const policy = intervalPolicy(doc, index)!, candidate = selectedInterval(doc, run, index);
  const number = (value: number) => formatNumber(value, lang);
  return <button type="button" {...linked} className="softqp-inspection-choice" onClick={() => { linked.onClick(); onSelect(index); }}>
    <strong>{policy.row.id} · {policy.row.label[lang]}</strong>
    <span>{policy.row.soft ? (lang === 'es' ? 'Blanda' : 'Soft') : (lang === 'es' ? 'Dura' : 'Hard')} · [{policy.row.unit}]</span>
    <span>{policy.lower === null ? '−∞' : number(policy.lower)} ≤ Aᵢx ≤ {policy.upper === null ? '+∞' : number(policy.upper)}; Aᵢx = {candidate ? number(candidate.value) : '∅'}</span>
  </button>;
}

/** Public-path numerical companion to the original A rows. Never runs a QP. */
export function LinkedConstraintPanel({ doc, run, rowIndex, ordinalCursor, edited, error, onRowSelect }: {
  doc: SoftQPResult | null; run: SoftQPRun | undefined; rowIndex: number; ordinalCursor: boolean;
  edited: boolean; error: string | null; onRowSelect: (index: number) => void;
}) {
  const lang = useShellLang(), cursor = useLinkedCursor();
  const t = (en: string, es: string) => lang === 'es' ? es : en;
  const number = (value: number | null) => value === null ? '∅' : formatNumber(value, lang);
  const model = sparseProblemView(doc, run, rowIndex, 4, 3);
  if (!doc || !model) return <section className="softqp-inspection" aria-label={t('Original-row inspection', 'Inspección de fila original')} data-state="unavailable">
    <p role="status">{error ?? (!doc ? t('No current verified case is available for row inspection.', 'No hay un caso verificado actual para inspeccionar filas.') : t('This grouped record has no exported separable coefficients. Row inspection is unavailable.', 'Este registro acoplado no exporta coeficientes separables. La inspección de filas no está disponible.'))}</p>
  </section>;
  const { policy, value, rowTerms } = model;
  const finite = [policy.lower, policy.upper, value].filter((v): v is number => v !== null);
  const low = Math.min(0, ...finite), high = Math.max(0, ...finite), padding = Math.max(1, (high - low) * .15);
  const lo = low - padding, hi = high + padding;
  const fraction = (v: number) => (v - lo) / (hi - lo);
  const sx = (v: number) => `${6 + fraction(v) * 88}%`;
  const source = `${doc.case_id} · ${run?.method ?? t('unknown method', 'método desconocido')} · ${edited ? t('verified native import', 'importación nativa verificada') : t('verified replay', 'registro verificado')}`;
  return <section className="softqp-inspection" aria-label={t('Original-row inspection', 'Inspección de fila original')}>
    <p className="softqp-inspection-source">{source}</p>
    {ordinalCursor && <div className="caos-field">
      <label htmlFor="softqp-row-ordinal">{t('Constraint row ordinal [1]', 'Ordinal de fila de restricción [1]')}: {rowIndex + 1}/{doc.rows.length}</label>
      <input {...cursor.inputProps} id="softqp-row-ordinal" type="range" min={1} max={doc.rows.length} step={1} value={rowIndex + 1}
        aria-valuetext={`${rowIndex + 1}: ${policy.row.id} · ${policy.row.label[lang]}`}
        onChange={event => { const index = constraintIndex(Number(event.currentTarget.value), doc.rows.length); if (index !== null) { cursor.scrub(index + 1); onRowSelect(index); } }} />
      <small>{t('Ordinal inspection, not time or solver iterations.', 'Inspección ordinal, no tiempo ni iteraciones del solver.')}</small>
    </div>}
    <div className="softqp-inspection-choices" aria-label={t('Nearby original rows', 'Filas originales cercanas')}>
      {model.rowIndices.map(index => <ConstraintChoice key={constraintEntityId(doc, index)} doc={doc} run={run} index={index} onSelect={onRowSelect} />)}
    </div>
    <figure className="softqp-inspection-interval">
      <svg width="100%" height={112} role="img" aria-label={`${policy.row.id}: ${t('original interval and returned Ax', 'intervalo original y Ax devuelto')} [${policy.row.unit}]`}>
        <title>{source}</title>
        <line x1="6%" x2="94%" y1={34} y2={34} className="softqp-scene-axis" />
        {[policy.lower, policy.upper].map((bound, side) => <g key={side}>
          <line x1={sx(bound ?? (side ? hi : lo))} x2={sx(bound ?? (side ? hi : lo))} y1={20} y2={48} className="softqp-scene-bound" />
          <text x={sx(bound ?? (side ? hi : lo))} y={65 + side * 17} textAnchor={fraction(bound ?? (side ? hi : lo)) < .2 ? 'start' : fraction(bound ?? (side ? hi : lo)) > .8 ? 'end' : 'middle'}>{bound === null ? side ? '+∞' : '−∞' : number(bound)}</text>
        </g>)}
        {value !== null && <circle {...(ordinalCursor ? cursor.markerProps : {})} data-inspection-candidate="" cx={sx(value)} cy={34} r={6} className="softqp-scene-point"><title>{policy.row.id}: {number(value)} [{policy.row.unit}] · {source}</title></circle>}
        <text x="50%" y={105} textAnchor="middle">Aᵢx [{policy.row.unit}] · {policy.row.id}</text>
      </svg>
      <figcaption>{t('Full original Aᵢx', 'Aᵢx original completo')} = <strong>{number(value)}</strong> [{policy.row.unit}]{value === null && ` · ${t('No compatible returned vector.', 'Sin vector devuelto compatible.')}`}</figcaption>
    </figure>
    <details><summary>{t('Original coefficients', 'Coeficientes originales')} · {policy.row.id}</summary>
      <p>{rowTerms.slice(0, 4).map(term => `${number(term.coefficient)}·x${term.column + 1}`).join(' + ') || '0'}{rowTerms.length > 4 && ` + … (${rowTerms.length - 4} ${t('terms omitted', 'términos omitidos')})`}</p>
      <p>{t('Algebraic x; decision units were not exported. Ax uses every stored column, including omitted terms.', 'x algebraico; no se exportaron unidades de decisión. Ax usa todas las columnas guardadas, incluso términos omitidos.')}</p>
    </details>
  </section>;
}
