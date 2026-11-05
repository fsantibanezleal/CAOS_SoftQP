import { SceneCallouts, Stage, formatNumber, useShellLang, type SceneCalloutDef, type StageSize } from '@fasl-work/caos-app-shell';
import type { SoftQPResult, SoftQPRun } from '../lib/softqp';
import type { Stream } from '../lib/experiments';
import { methodNames } from '../lib/methodNames';
import { selectedCaseComparison, heldTrajectory, intervalPolicy, methodFormulation, recordedFrame, rowPrice, selectedInterval, type SceneView } from './sceneModel';
import { SystemDomain, MethodDomain } from './DomainViews';
import './scene.css';

export interface ProblemSceneProps {
  doc: SoftQPResult | null; run: SoftQPRun | undefined; view: SceneView;
  rowIndex: number; frameIndex: number; phaseIndex?: number;
  stream?: Stream; edited: boolean; error: string | null;
  onRowSelect: (index: number) => void; onMethodSelect: (id: string) => void;
  onPhaseSelect?: (index: number) => void; onFrameSelect?: (index: number) => void;
}
export const sceneNames = {
  system: { en: 'Problem structure', es: 'Estructura del problema' },
  interval: { en: 'Interval policy', es: 'Política del intervalo' },
  geometry: { en: 'Price geometry', es: 'Geometría del costo' },
  dynamics: { en: 'Recorded dynamics', es: 'Dinámica registrada' },
  method: { en: 'Method at work', es: 'Método en acción' },
  comparison: { en: 'Matched evidence', es: 'Evidencia equivalente' },
};

export function ProblemScene(props: ProblemSceneProps) {
  const { doc, run, view, rowIndex, frameIndex, stream, edited, error } = props;
  const lang = useShellLang();
  const text = (en: string, es: string) => lang === 'es' ? es : en;
  const number = (value: number | null | undefined) => formatNumber(value, lang);
  const policy = intervalPolicy(doc, rowIndex), interval = selectedInterval(doc, run, rowIndex);
  const frame = recordedFrame(stream, doc?.case_id ?? '', run?.method ?? '', edited, frameIndex);
  const trajectory = frame ? heldTrajectory(stream) : null;
  const peers = selectedCaseComparison(doc, doc?.rows[rowIndex]?.unit ?? ''), formulation = methodFormulation(doc, run);
  const incompatible = !!doc && (!run || run.state !== 'available');
  const unavailable = !doc ? error ?? text('Loading the verified case.', 'Cargando el caso verificado.')
    : ['system', 'interval', 'geometry'].includes(view) && !policy ? text('The original separable coefficients were not exported for this grouped case. Its method records remain in Comparison.', 'Este caso acoplado no exporta coeficientes separables originales. Sus resultados siguen en Comparación.')
    : view === 'dynamics' && (!frame || !trajectory) ? text(edited ? 'Edited native scenarios have no recorded C12 trajectory. Importing a result does not create one.' : 'The common C12 trajectory is available only for an unedited case and a recorded compatible method.', edited ? 'Los escenarios nativos editados no tienen trayectoria C12 registrada. Importar un resultado no la crea.' : 'La trayectoria C12 común exige el caso sin ediciones y un método registrado compatible.')
    : view === 'method' && !formulation ? text('No known method formulation is selected.', 'No hay una formulación conocida seleccionada.')
    : view === 'comparison' && !peers.available.length ? text('There are no compatible numerical peers in this record.', 'Este registro no contiene resultados numéricos compatibles.') : null;
  const takeaway = unavailable ?? (view === 'system' ? text('P and q price the decisions; A maps them to the selected original interval.', 'P y q valoran las decisiones; A las lleva al intervalo original seleccionado.')
    : view === 'interval' ? text('The mask fixes hardness. A finite side price changes policy, never that mask.', 'La máscara fija las filas duras. Un precio finito cambia la política, no la máscara.')
    : view === 'geometry' ? text('Only this row price is drawn. No returned vector means no candidate point.', 'Se dibuja solo el costo de esta fila. Sin vector devuelto no hay punto candidato.')
    : view === 'dynamics' ? text('One oracle-driven plant: held input, exact within-step kinematics, instantaneous velocity impulses.', 'Una planta común del oráculo: entrada retenida, cinemática exacta por intervalo e impulsos instantáneos.')
    : view === 'method' ? text('These are formulation and recovery phases. Numerical intermediate iterates were not recorded.', 'Son fases de formulación y recuperación. No se registraron iteraciones numéricas intermedias.')
    : text('Only the selected case is compared. Objective agreement is descriptive; registered population studies are on Benchmark.', 'Se compara solo el caso seleccionado. La concordancia es descriptiva; los estudios poblacionales registrados están en Comparación.'));

  function drawing({ width, height }: StageSize) {
    if (unavailable || !doc) return <div className="softqp-scene-empty" data-state={!doc && !error ? 'loading' : 'unavailable'} role={error ? 'alert' : 'status'}>{unavailable}</div>;
    const compact = width < 640, font = 14;
    const requiredHeight = compact ? ({ system: 620, interval: 340, geometry: 340, dynamics: 470, method: 700, comparison: 560 }[view]) : ['system', 'method'].includes(view) ? 570 : 450;
    if (height < requiredHeight) return <div className="softqp-scene-empty" role="status" data-state="insufficient-space">{text(`The drawing surface is too small (${width}×${height} px). Expand the stage to inspect this view; required drawing height ${requiredHeight} px.`, `La superficie es insuficiente (${width}×${height} px). Amplía la escena para inspeccionar esta vista; altura requerida ${requiredHeight} px.`)}</div>;
    const left = compact ? 48 : 78, right = width - (compact ? 20 : 40);
    const top = compact ? 170 : 112, bottom = height - 58;
    const callouts: SceneCalloutDef[] = [];
    const origin = text(edited ? 'native import' : 'recorded', edited ? 'nativo' : 'registrado');
    const costUnit = text('cost', 'costo');
    const marker = (id: string, x: number, y: number, en: string, es: string, value: number | string | null | undefined, unit: string, source?: { en: string; es: string }) => {
      callouts.push({ id, eyebrow: { en, es }, value: typeof value === 'string' ? value : number(value),
        unit: { en: unit, es: unit }, state: value === null || value === undefined ? 'inactive' : 'normal',
        anchor: { x: x / width, y: y / height }, source: source ?? { en: `${doc.case_id} · ${origin}`, es: `${doc.case_id} · ${origin}` } });
      return value === null || value === undefined ? <g key={id} data-scene-subject={id} data-subject-x={x} data-subject-y={y}><text x={x} y={y} textAnchor="middle" dominantBaseline="central">∅<title>{text('Unavailable', 'No disponible')} · {doc.case_id}</title></text></g> : <circle key={id} data-scene-subject={id} cx={x} cy={y} r={5} className="softqp-scene-point"><title>{`${typeof value === 'string' ? value : number(value)} ${unit}; ${doc.case_id}; ${origin}`}</title></circle>;
    };
    const multiline = (value: string, x: number, y: number, chars = compact ? 32 : 48, anchor: 'start' | 'middle' = 'start') => {
      const lines: string[] = [];
      for (const word of value.split(' ')) {
        if (!lines.length || (lines.at(-1)!.length + word.length + 1 > chars)) lines.push(word);
        else lines[lines.length - 1] += ` ${word}`;
      }
      return <text x={x} y={y} textAnchor={anchor}>{lines.map((line, index) => <tspan key={index} x={x} dy={index ? font + 4 : 0}>{line}</tspan>)}</text>;
    };
    const keyboard = (action: () => void) => (event: React.KeyboardEvent<SVGGElement>) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); action(); }
    };
    const xAxis = (lo: number, hi: number, y: number, title: string) => <>
      <line x1={left} x2={right} y1={y} y2={y} className="softqp-scene-axis" />
      {(compact ? [0, .5, 1] : [0, .25, .5, .75, 1]).map(t => { const x = left + t * (right - left); return <g key={t}><line x1={x} x2={x} y1={y} y2={y + 5} className="softqp-scene-axis" /><text x={x} y={y + 20} textAnchor="middle">{number(lo + t * (hi - lo))}</text></g>; })}
      {multiline(title, (left + right) / 2, y + 39, compact ? 34 : 80, 'middle')}
    </>;
    let body;
    if (view === 'system' && doc.problem && policy) {
      body = SystemDomain({ doc, run, rowIndex, width, height, lang, number, marker, onRowSelect: props.onRowSelect });
    } else if ((view === 'interval' || view === 'geometry') && policy) {
      const values = [policy.lower, policy.upper, interval?.value].filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
      const centerLo = values.length ? Math.min(...values) : -1, centerHi = values.length ? Math.max(...values) : 1;
      const padding = Math.max(1, (centerHi - centerLo) * .3), lo = centerLo - padding, hi = centerHi + padding;
      const sx = (value: number) => left + (value - lo) / (hi - lo) * (right - left);
      const graphBottom = bottom - 34, middle = (top + graphBottom) / 2;
      const xs = Array.from({ length: 161 }, (_, index) => lo + (hi - lo) * index / 160);
      const prices = xs.map(value => rowPrice(policy, value)), maximum = Math.max(1, ...prices.filter((value): value is number => value !== null));
      const sy = (value: number) => graphBottom - value / maximum * (graphBottom - top);
      const curve = xs.map((value, index) => prices[index] === null ? '' : `${index === 0 || prices[index - 1] === null ? 'M' : 'L'}${sx(value)},${sy(prices[index]!)}`).join(' ');
      const pointPrice = interval ? rowPrice(policy, interval.value) : null;
      body = <>{view === 'geometry' ? <>
        <line x1={left} x2={left} y1={top} y2={graphBottom} className="softqp-scene-axis" />
        {[0, maximum / 2, maximum].map(value => <g key={value}><line x1={left} x2={right} y1={sy(value)} y2={sy(value)} className="softqp-scene-grid" /><text x={left - 6} y={sy(value) + 4} textAnchor="end">{number(value)}</text></g>)}
        <path d={curve} className="softqp-scene-line" data-price-curve="" />
        <text x={left} y={top - 20}>{text('Row price [cost]', 'Costo de fila [costo]')}</text>
      </> : <><line x1={left} x2={right} y1={middle} y2={middle} className="softqp-scene-axis" />{multiline(policy.row.soft ? `aₗ=${number(policy.lowerLinear)}, aᵤ=${number(policy.upperLinear)}; bₗ=${number(policy.lowerQuadratic)}, bᵤ=${number(policy.upperQuadratic)}` : text('Hard: finite only inside the interval.', 'Dura: finito solo dentro del intervalo.'), left, top, compact ? 30 : 80)}</>}
      {xAxis(lo, hi, graphBottom, `${text('Original row value', 'Valor original de fila')} [${policy.row.unit}]`)}
      {[policy.lower, policy.upper].map((bound, i) => <g key={i}><line x1={sx(bound ?? (i ? hi : lo))} x2={sx(bound ?? (i ? hi : lo))} y1={top} y2={graphBottom} className="softqp-scene-bound" />{bound === null && <text x={sx(i ? hi : lo)} y={top + 18} textAnchor={i ? 'end' : 'start'}>{i ? '+∞' : '−∞'}</text>}{marker(i ? 'upper' : 'lower', sx(bound ?? (i ? hi : lo)), view === 'geometry' ? graphBottom : middle, i ? 'Upper' : 'Lower', i ? 'Superior' : 'Inferior', bound, policy.row.unit)}</g>)}
      {interval ? (view !== 'geometry' || pointPrice !== null ? marker('value', sx(interval.value), view === 'geometry' ? sy(pointPrice!) : middle, 'Returned Ax', 'Ax devuelto', interval.value, policy.row.unit) : <><line x1={sx(interval.value)} x2={sx(interval.value)} y1={top} y2={graphBottom} className="softqp-scene-cursor" /><text x={sx(interval.value)} y={top - 8}>∞</text>{marker('value', sx(interval.value), top - 14, 'No finite price', 'Costo no finito', '∞', costUnit)}</>) : <>{multiline(text('No returned vector for this method.', 'Este método no devuelve un vector.'), left, top + 30)}{marker('value', left, top + 30, 'Candidate', 'Candidato', null, policy.row.unit)}</>}
      <text x={left} y={height - 8}>{policy.row.id} · {policy.row.soft ? text('soft', 'blanda') : text('hard', 'dura')}</text></>;
    } else if (view === 'dynamics' && frame && stream && trajectory) {
      const panels = [
        { name: text('Position', 'Posición'), unit: 'm', points: trajectory.position, selected: frame.state[0], bounds: [-.4, .4] },
        { name: text('Velocity', 'Velocidad'), unit: 'm/s', points: trajectory.velocity, selected: frame.state[1], bounds: [-1.5, 1.5] },
        { name: text('Held acceleration', 'Aceleración retenida'), unit: 'm/s²', points: trajectory.acceleration, selected: frame.applied_control, bounds: [-1, 1] },
      ];
      const sx = (time: number) => left + time / trajectory.endTime * (right - left), h = (bottom - top) / 3;
      body = <>{panels.map((panel, i) => {
        const values = panel.points.map(point => point.value), low = Math.min(...values, ...panel.bounds), high = Math.max(...values, ...panel.bounds);
        const y0 = top + i * h, sy = (value: number) => y0 + h - 14 - (value - low) / (high - low || 1) * (h - 38);
        return <g key={panel.unit} data-dynamics-panel={i}><text x={left} y={y0}>{panel.name} [{panel.unit}]</text>{panel.bounds.map(bound => <g key={bound}><line x1={left} x2={right} y1={sy(bound)} y2={sy(bound)} className="softqp-scene-bound" /><text x={left - 6} y={sy(bound) + 3} textAnchor="end">{number(bound)}</text></g>)}<path data-trajectory={i === 2 ? 'zero-order-hold' : 'constant-acceleration'} d={panel.points.map((point, j) => `${j ? 'L' : 'M'}${sx(point.time)},${sy(point.value)}`).join(' ')} className="softqp-scene-line" />{trajectory.events.map(event => <g key={event.frame} data-impulse-frame={event.frame}><line x1={sx(event.time)} x2={sx(event.time)} y1={y0 + 5} y2={y0 + h - 10} className="softqp-scene-event" />{i === 1 && <text x={sx(event.time) + 3} y={y0 + 15}>{event.impulse > 0 ? '+' : ''}{number(event.impulse)}</text>}</g>)}<line x1={sx(frame.time_seconds)} x2={sx(frame.time_seconds)} y1={y0 + 6} y2={y0 + h - 10} className="softqp-scene-cursor" />{marker(['position', 'velocity', 'control'][i], sx(frame.time_seconds), sy(panel.selected), ['Position', 'Velocity', 'Held input'][i], ['Posición', 'Velocidad', 'Entrada retenida'][i], panel.selected, panel.unit)}<circle cx={sx(trajectory.endTime)} cy={sy(panel.points.at(-1)!.value)} r={3} className="softqp-scene-endpoint"><title>{number(trajectory.endTime)} s · {number(panel.points.at(-1)!.value)} {panel.unit}</title></circle></g>;
      })}<rect data-scene-scrub="" x={left} y={top} width={right - left} height={bottom - top} className="softqp-scene-scrub" onClick={event => { const svg = event.currentTarget.ownerSVGElement; if (!svg) return; const point = svg.createSVGPoint(); point.x = event.clientX; point.y = event.clientY; const matrix = svg.getScreenCTM(); if (!matrix) return; const local = point.matrixTransform(matrix.inverse()); props.onFrameSelect?.(Math.min(stream.frames.length - 1, Math.max(0, Math.round((local.x - left) / (right - left) * trajectory.endTime / trajectory.dt)))); }} />{xAxis(0, trajectory.endTime, bottom, text('Time [s] · impulses at 1.6 and 4 s', 'Tiempo [s] · impulsos en 1,6 y 4 s'))}<text x={right} y={top - 22} textAnchor="end">{number(frame.time_seconds)} s · {text('after boundary impulse', 'después del impulso')}</text></>;
    } else if (view === 'method' && formulation && run) {
      body = MethodDomain({ doc, run, rowIndex, width, height, lang, number, marker, onRowSelect: props.onRowSelect, phaseIndex: Math.min(3, Math.max(0, props.phaseIndex ?? 0)), onPhaseSelect: props.onPhaseSelect });
    } else {
      const values = peers.available.map(peer => peer.result!.metrics!.objective);
      const min = Math.min(...values), max = Math.max(...values), span = Math.max(Number.EPSILON * Math.max(1, Math.abs(min), Math.abs(max)) * 16, max - min), lo = min - span * .2, hi = max + span * .2;
      const sx = (value: number) => left + (value - lo) / (hi - lo) * (right - left);
      const lineH = Math.min(64, Math.max(30, (bottom - top - 140) / (2 * peers.available.length))), objectiveBottom = top + peers.available.length * lineH + 8;
      const reference = peers.reference!;
      const refCost = peers.referenceCost!;
      const hardUnit = peers.unit;
      const hardIndices = peers.hardRows;
      const errors = peers.values.map(value => value.hardError);
      const maximumError = Math.max(1e-9, ...errors.filter((value): value is number => value !== null));
      const errorTop = objectiveBottom + 68, errorBottom = errorTop + peers.available.length * 16 + 8;
      const errorX = (value: number) => left + value / maximumError * (right - left);
      const errorIndex = errors.findIndex(value => value === Math.max(...errors.filter((v): v is number => v !== null)));
      const agreementIndex = peers.values.findIndex(value => value.normalizedGap === peers.maxNormalizedGap);
      body = <>{peers.available.map((peer, index) => { const y = top + index * lineH, value = peer.result!.metrics!.objective; return <g key={peer.method} role="button" tabIndex={0} aria-label={methodNames[peer.method][lang]} aria-pressed={peer.method === run?.method} data-linked-method={peer.method} onClick={() => props.onMethodSelect(peer.method)} onKeyDown={keyboard(() => props.onMethodSelect(peer.method))}><rect x={left} y={y - 14} width={right - left} height={lineH} className="softqp-scene-hit" /><text x={left} y={y}>{index + 1}. {methodNames[peer.method][lang]} · |ΔF|={number(Math.abs(value - refCost))}</text><line x1={left} x2={right} y1={y + 10} y2={y + 10} className="softqp-scene-grid" />{peer === reference ? marker('reference-cost', sx(value), y + 10, 'Fref', 'Fref', formatNumber(value, lang, { digits: 8 }), costUnit) : <circle cx={sx(value)} cy={y + 10} r={peer.method === run?.method ? 7 : 4} className="softqp-scene-comparator"><title>{number(value)} {costUnit} · {doc.case_id}</title></circle>}</g>; })}{xAxis(lo - refCost, hi - refCost, objectiveBottom, 'F(x) − Fref [cost]')}
      <text x={left} y={errorTop - 8}>{text('Hard-row error', 'Error de filas duras')} [{hardUnit ?? text('unavailable', 'no disponible')}]</text>
      {peers.available.map((peer, index) => <g key={peer.method}><text x={left - 12} y={errorTop + 16 * index + 4} textAnchor="end">{index + 1}</text><line x1={left} x2={right} y1={errorTop + 16 * index} y2={errorTop + 16 * index} className="softqp-scene-grid" />{index === errorIndex ? marker('hard-error', errorX(errors[index]!), errorTop + 16 * index, 'Hard error', 'Error duro', errors[index], hardUnit!) : errors[index] !== null && <circle cx={errorX(errors[index]!)} cy={errorTop + 16 * index} r={3} className="softqp-scene-comparator"><title>{methodNames[peer.method][lang]} · {number(errors[index])} {hardUnit}</title></circle>}</g>)}
      {!hardIndices.length && <>{marker('hard-error', left, errorTop, 'Hard rows', 'Filas duras', null, '1')}<text x={left + 12} y={errorTop}>{text('No hard rows', 'No hay filas duras')}</text></>}
      {xAxis(0, maximumError, errorBottom, text('Maximum hard departure in one unit', 'Máximo incumplimiento duro en una unidad'))}
      {marker('case-agreement', sx(peers.available[agreementIndex].result!.metrics!.objective), top + agreementIndex * lineH + 10, '|ΔF|/scale', '|ΔF|/escala', peers.maxNormalizedGap, '1')}
      {multiline(text(`Reference: ${methodNames[reference.method][lang]}. |ΔF| / max(1, |Fref|); descriptive only.`, `Referencia: ${methodNames[reference.method][lang]}. |ΔF| / max(1, |Fref|); solo descriptivo.`), left, errorBottom + 82, compact ? 32 : 68)}

      </>;
    }
    return <div className="softqp-scene-canvas"><svg className="softqp-scene-svg" width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ fontSize: font }} role={['system', 'comparison', 'method'].includes(view) ? 'group' : 'img'} aria-label={sceneNames[view][lang]}><title>{sceneNames[view][lang]} · {doc.case_id}</title><desc>{takeaway}</desc>{body}</svg><SceneCallouts items={callouts} placement="header" /></div>;
  }
  return <div className="softqp-scene" data-scene-view={view} data-selected-row={doc?.rows[rowIndex]?.id} data-selected-frame={frameIndex} data-source={edited ? 'local-native-import' : 'verified-replay'}>
    <Stage label={sceneNames[view]}>{drawing}</Stage>
    <div className="softqp-scene-takeaway" data-scene-takeaway=""><p>{takeaway}</p>{incompatible && <p data-active-incompatible="">{text('Active method has no compatible returned vector.', 'El método activo no tiene un vector devuelto compatible.')} {run?.reason}</p>}{view === 'comparison' && peers.unavailable.length > 0 && <p data-peer-states="">{peers.unavailable.map(peer => `${methodNames[peer.method][lang]}: ${peer.state}`).join(' · ')}</p>}</div>
  </div>;
}
