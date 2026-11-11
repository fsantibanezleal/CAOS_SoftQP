import { BarChart, CaseSelector, CaseWorkbench, LinkedViewProvider, PlotCard, Readout, StoryFrame, formatNumber, useLinkedView, useShellLang, useWorkbenchState, type RailSection, type StoryStep } from '@fasl-work/caos-app-shell';
import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router';
import { loadSoftQPCase, loadSoftQPIndex, softQPSource, type SoftQPIndex, type SoftQPResult, type SoftQPRun } from '../lib/softqp';
import { methodNames } from '../lib/methodNames';
import { StreamStage } from './StreamStage';
import { makeLocalRequest, verifyLocalResult } from '../lib/softqp.local';
import { ReadinessNote } from '../readiness/ReadinessNote';
import { useExperiments } from '../lib/experiments';
import { ProblemScene, sceneNames } from './ProblemScene';
import { SCENE_VIEWS, createNativeSceneMemory, methodFormulation, sceneStateFromSearch, selectedInterval, type SceneView } from './sceneModel';
import { LinkedConstraintPanel, constraintEntityId } from './LinkedConstraintPanel';


const names: Record<string, {en:string;es:string}> = methodNames;
const nativeMemory = createNativeSceneMemory();

function CaseStatus({ error }: { error: string | null }) {
  const lang = useShellLang();
  return <p role={error ? 'alert' : 'status'} data-state={error ? 'unavailable' : 'loading'}>{error
    ? (lang === 'es' ? `No se puede cargar el registro del caso: ${error}` : `The case record could not be loaded: ${error}`)
    : (lang === 'es' ? 'Cargando…' : 'Loading…')}</p>;
}

function Violations({ doc, run, unit, error }: { doc: SoftQPResult | null; run: SoftQPRun | undefined; unit: string; error: string | null }) {
  const lang = useShellLang(); const key = useWorkbenchState()?.stateKey;
  const metrics = run?.result?.metrics;
  const all = doc?.rows.map((r, i) => ({ ...r, lower: metrics?.lower_violation[i] ?? 0, upper: metrics?.upper_violation[i] ?? 0 })).filter(r => r.unit === unit) ?? [];
  const nonzero = all.filter(r => r.lower > 1e-7 || r.upper > 1e-7);
  const rows = (nonzero.length ? nonzero : all).slice(0, 18);
  return <PlotCard fill title={{ en: 'Lower and upper violations', es: 'Incumplimientos por lado' }} note={{ en: 'Lower and upper bounds are separate series. Only rows with the same unit are compared. Values above 1e-7 are prioritized; up to 18 rows are shown. The export includes all values.', es: 'Los lados inferior y superior son series separadas. Solo se comparan filas con la misma unidad. Se priorizan valores mayores que 1e-7; se muestran hasta 18 filas. La exportación conserva todos los valores.' }} lane="replay" provenance="synthetic" dataKey={key}>
    {!doc ? <CaseStatus error={error} /> : !metrics ? <p data-state="unavailable">{lang === 'es' ? 'Sin resultado compatible para este método.' : 'No compatible result for this method.'}</p> : <>
      <BarChart height="fill" title={{ en: 'Violation by row and bound side', es: 'Incumplimiento por fila y lado' }}
        axis={{ label: { en: 'Violation', es: 'Incumplimiento' }, ...(unit === '1' ? {} : { unit: { en: unit, es: unit } }) }}
        data={rows.flatMap(r => [
          { id: `${r.id}-lower`, label: { en: 'Lower', es: 'Inferior' }, value: r.lower, tone: 'warn' as const, group: { id: r.id, label: r.label }, hint: { en: r.soft ? 'Soft row' : 'Hard row', es: r.soft ? 'Fila blanda' : 'Fila dura' } },
          { id: `${r.id}-upper`, label: { en: 'Upper', es: 'Superior' }, value: r.upper, tone: 'accent' as const, group: { id: r.id, label: r.label }, hint: { en: r.soft ? 'Soft row' : 'Hard row', es: r.soft ? 'Fila blanda' : 'Fila dura' } },
        ])}
        legend={[{ tone: 'warn', label: { en: 'Lower', es: 'Inferior' } }, { tone: 'accent', label: { en: 'Upper', es: 'Superior' } }]} />
    </>}
  </PlotCard>;
}

function Comparison({ doc, active, error }: { doc: SoftQPResult | null; active: string; error: string | null }) {
  const key = useWorkbenchState()?.stateKey;
  const good = doc?.runs.filter(r => r.result) ?? [];
  return <PlotCard fill title={{ en: 'Matched formulations', es: 'Formulaciones equivalentes' }} note={{ en: 'One development run per method; timing superiority remains unestablished.', es: 'Una medición de desarrollo por método; no se establece superioridad de tiempo.' }} lane="replay" provenance="synthetic" dataKey={key}>
    {!doc ? <CaseStatus error={error} /> : <BarChart height="fill" title={{ en: 'Formulation dimensions', es: 'Dimensiones de formulación' }}
      axis={{ label: { en: 'Primal variables', es: 'Variables primales' }, format: { decimals: 0 } }}
      data={good.map(r => ({ id: r.method, label: names[r.method], value: r.result!.dimensions.variables, tone: r.method === active ? 'accent' as const : r.method === 'lifted' ? 'warn' as const : 'neutral' as const }))} />}
  </PlotCard>;
}

export function Workbench() {
  return <LinkedViewProvider><WorkbenchContent /></LinkedViewProvider>;
}

function WorkbenchContent() {
  const lang = useShellLang();
  const [params, setParams] = useSearchParams();
  const requestedGroup = params.get('view');
  const group = requestedGroup && ['scene', 'violations', 'comparison', 'stream', 'context'].includes(requestedGroup) ? requestedGroup : 'scene';
  const setGroup = (value: string) => updateParam('view', value);
  const navigate = useNavigate();
  const location = useLocation();
  const route = useParams<{ step: string }>();
  const { evidence, error: evidenceError } = useExperiments();
  const selectLinked = useLinkedView(state => state.select);
  const cursorLinked = useLinkedView(state => state.scrub);
  const linkedSelection = useLinkedView(state => state.selectedId);
  const linkedSource = useRef('');
  const [storyStageMinimum, setStoryStageMinimum] = useState(620);
  const parsedScene = sceneStateFromSearch(params.toString());
  const selected = params.get('case') ?? 'C01';
  const method = params.get('method') ?? 'lifted';
  const nativeToken = params.get('native');
  function updateParam(name: string, value: string) {
    const next = new URLSearchParams(typeof window === 'undefined' ? params : window.location.search);
    next.set(name, value); setParams(next, { replace: true });
  }
  const setSelected = (value: string) => {
    setEdits({ lower: '1', upper: '1', quadratic: '1' });
    const next = new URLSearchParams(params); next.set('case', value); next.delete('native');
    setParams(next, { replace: true });
  };
  const setMethod = (value: string) => updateParam('method', value);
  const [index, setIndex] = useState<SoftQPIndex | null>(null); const [doc, setDoc] = useState<SoftQPResult | null>(null);
  const [unit, setUnit] = useState('1'); const [error, setError] = useState<string | null>(null);
  const [localResult, setLocalResult] = useState<SoftQPResult | null>(null);
  const [edits, setEdits] = useState({ lower: '1', upper: '1', quadratic: '1' });
  const importKey = `${selected}|${edits.lower}|${edits.upper}|${edits.quadratic}`;
  const activeImportKey = useRef(importKey); activeImportKey.current = importKey;
  useEffect(() => { loadSoftQPIndex().then(setIndex).catch(e => setError(String(e))); }, []);
  useEffect(() => {
    if (!index) return;
    const entry = index.cases.find(c => c.case_id === selected);
    if (!entry) { setDoc(null); setLocalResult(null); setError(lang === 'es' ? 'Identificador de caso desconocido.' : 'Unknown case identifier.'); return; }
    const restored = nativeMemory.get(nativeToken, selected, entry.sha256);
    const abort = new AbortController(); setDoc(null); setError(null); setLocalResult(null);
    if (restored) setEdits(restored.edits);
    loadSoftQPCase(entry, abort.signal).then(result => {
      if (!abort.signal.aborted) { setDoc(result); setLocalResult(restored?.result ?? null); setUnit(result.rows.find(r => r.soft)?.unit ?? result.rows[0]?.unit ?? '1'); }
    }).catch(e => { if (!abort.signal.aborted) setError(String(e)); });
    return () => abort.abort();
  }, [selected, index, nativeToken, lang]);
  const baseline = doc?.case_id === selected ? doc : null;
  const nativeExpired = !!nativeToken && !!index && !nativeMemory.get(nativeToken, selected, index.cases.find(c => c.case_id === selected)?.sha256);
  const nativeError = nativeExpired ? (lang === 'es' ? 'La importación nativa no está disponible después de recargar o cambiar su fuente. Impórtala otra vez o restaura el registro original.' : 'The native import is unavailable after reload or a source change. Import it again or restore the recorded result.') : null;
  const current = nativeToken ? (localResult?.case_id === selected ? localResult : null) : baseline; const run = current?.runs.find(r => r.method === method); const units = [...new Set(current?.rows.map(r => r.unit) ?? ['1'])];
  const rowIndex = Math.min(parsedScene.row, Math.max(0, (current?.rows.length ?? 1) - 1));
  const selectedRow = current?.rows[rowIndex];
  const storyViews = { formulate: 'system', price: 'geometry', compute: 'method', compare: 'comparison' } as const;
  const story = location.pathname.startsWith('/story/');
  const knownStory = !!route.step && Object.prototype.hasOwnProperty.call(storyViews, route.step);
  const storyId = knownStory ? route.step as keyof typeof storyViews : 'formulate';
  const sceneView: SceneView = story ? storyViews[storyId] : parsedScene.view;
  // URL and verified artifact remain authoritative; direct actions retain their scene/panel origin.
  // Frame is deliberately not reused as a row cursor: these coordinates have different meanings.
  useEffect(() => {
    const source = `${selected}|${method}|${nativeToken ?? 'replay'}`;
    const id = current?.problem && selectedRow ? constraintEntityId(current, rowIndex) : null;
    if (linkedSource.current !== source || linkedSelection !== id) selectLinked(id, 'external');
    linkedSource.current = source;
    cursorLinked(id !== null && sceneView === 'system' ? rowIndex + 1 : null);
  }, [current, selectedRow, rowIndex, selected, method, nativeToken, sceneView, selectLinked, cursorLinked]);
  function selectRow(value: number, origin: 'scene' | 'panel') {
    if (!current?.rows[value] || !Number.isInteger(value)) return;
    selectLinked(current.problem ? constraintEntityId(current, value) : null, origin);
    cursorLinked(current.problem && sceneView === 'system' ? value + 1 : null);
    setUnit(current.rows[value].unit);
    updateParam('row', String(value));
  }
  const scene = <ProblemScene doc={current} run={run} view={sceneView} rowIndex={rowIndex} frameIndex={parsedScene.frame} phaseIndex={parsedScene.phase} onFrameSelect={value => updateParam('frame', String(value))} onPhaseSelect={value => updateParam('phase', String(value))} stream={evidence?.stream} onStageMinimum={story ? setStoryStageMinimum : undefined} edited={!!localResult} error={nativeError ?? error ?? evidenceError} onRowSelect={value => selectRow(value, 'scene')} onMethodSelect={setMethod} />;
  const sceneControls = <>
    <label htmlFor="softqp-scene-view">{lang === 'es' ? 'Vista del problema' : 'Problem view'}</label>
    <select id="softqp-scene-view" value={sceneView} onChange={e => { if (story) { const next = new URLSearchParams(params); next.set('scene', e.target.value); next.set('view', 'scene'); navigate(`/app?${next}`); } else updateParam('scene', e.target.value); }}>{SCENE_VIEWS.map(id => <option key={id} value={id}>{sceneNames[id][lang]}</option>)}</select>
    <label htmlFor="softqp-scene-row">{lang === 'es' ? 'Fila del intervalo' : 'Interval row'}</label>
    <select id="softqp-scene-row" value={rowIndex} disabled={!current} title={current?.rows[rowIndex]?.label[lang]} onChange={e => selectRow(Number(e.target.value), 'panel')}>{current?.rows.map((row, i) => <option key={row.id} value={i} title={row.label[lang]}>{row.id} · {row.unit}</option>)}</select>
    {sceneView === 'method' && <><label htmlFor="softqp-scene-phase">{lang === 'es' ? 'Fase de formulación' : 'Formulation phase'}</label><select id="softqp-scene-phase" value={parsedScene.phase} onChange={e => updateParam('phase', e.target.value)}>{methodFormulation(current, run)?.phases.map((phase, index) => <option key={phase.id} value={index}>{index + 1}. {phase.label[lang]}</option>)}</select></>}{sceneView === 'dynamics' && <><label htmlFor="softqp-scene-frame">{lang === 'es' ? 'Cuadro registrado' : 'Recorded frame'}: {parsedScene.frame}</label><input id="softqp-scene-frame" type="range" min="0" max="31" step="1" value={parsedScene.frame} disabled={selected !== 'C12' || !!localResult} onChange={e => updateParam('frame', e.target.value)} /></>}
  </>;
  const rowInspection = ['system', 'interval', 'geometry', 'method'].includes(sceneView)
    ? <LinkedConstraintPanel doc={current} run={run} rowIndex={rowIndex} ordinalCursor={sceneView === 'system'} edited={!!localResult}
      error={nativeError ?? error} onRowSelect={value => selectRow(value, 'panel')} /> : null;
  const hardRows = current?.rows.map((r,i) => ({ ...r, index: i })).filter(r => !r.soft && r.unit === unit) ?? [];
  const hardInUnit = run?.result?.metrics && hardRows.length ? Math.max(0, ...hardRows.map(r => Math.max(run.result!.metrics!.lower_violation[r.index], run.result!.metrics!.upper_violation[r.index]))) : null;
  function download(value: unknown, filename: string) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function request() {
    const entry = index?.cases.find(c => c.case_id === selected);
    if (!entry || !baseline?.problem) throw new Error(lang === 'es' ? 'El caso no admite edición separable.' : 'This case does not support separable cost edits.');
    return makeLocalRequest(selected, entry.sha256, Number(edits.lower), Number(edits.upper), Number(edits.quadratic));
  }
  function exportRequest() {
    try { download(request(), `${selected}-request.json`); setError(null); } catch(e) { setError(String(e)); }
  }
  async function importResult(file?: File) {
    if (!file || !baseline) return;
    try {
      if (file.size > 32 * 1024 * 1024) throw new Error('Local result exceeds 32 MiB');
      const expected = request(); const original = baseline; const started = importKey;
      const result = verifyLocalResult(JSON.parse(await file.text()), expected, original);
      if (activeImportKey.current !== started) return;
      const entry = index?.cases.find(c => c.case_id === selected);
      if (!entry) throw new Error('Original case identity is unavailable.');
      const id = crypto.randomUUID();
      nativeMemory.put({ id, caseId: selected, baseSha256: entry.sha256, result, edits: { ...edits } });
      setLocalResult(result); setError(null); updateParam('native', id);
    } catch(e) { setError(String(e)); }
  }
  function exportResult() {
    if (!current) return;
    download({ lane: 'replay', origin: localResult ? 'local-native-import' : softQPSource, selected_method: method, result: current }, `${selected}-${method}.json`);
  }
  function restoreRecordedResult() {
    nativeMemory.clear();
    setLocalResult(null);
    setEdits({ lower: '1', upper: '1', quadratic: '1' });
    const next = new URLSearchParams(params);
    next.delete('native');
    next.set('method', 'lifted');
    setParams(next, { replace: true });
    setError(null);
  }
  const restoreButton = nativeToken && <button className="btn" type="button" onClick={restoreRecordedResult}>{lang === 'es' ? 'Volver al registro original' : 'Restore recorded result'}</button>;
  const editor = <>
    <details open><summary>{lang === 'es' ? 'Configuración de ejecución local' : 'Local execution settings'}</summary>
      <p>{lang === 'es' ? 'Los factores modifican costos blandos; las filas duras se conservan. Descargue la solicitud, ejecútela con el paquete científico e importe el resultado. El navegador verifica entradas, objetivo e incumplimientos.' : 'Factors change soft costs; hard rows are preserved. Download the request, execute it with the scientific package, then import the result. The browser verifies inputs, objective and violations.'}</p>
      {(['lower', 'upper', 'quadratic'] as const).map(key => <div key={key}><label htmlFor={`cost-${key}`}>{key === 'lower' ? (lang === 'es' ? 'Factor inferior' : 'Lower cost factor') : key === 'upper' ? (lang === 'es' ? 'Factor superior' : 'Upper cost factor') : (lang === 'es' ? 'Factor cuadrático' : 'Quadratic cost factor')}</label><input id={`cost-${key}`} type="number" min={key === 'quadratic' ? 0 : 0.01} max="100" step="0.1" value={edits[key]} disabled={!baseline?.problem} onChange={e => { setEdits({ ...edits, [key]: e.target.value }); setLocalResult(null); const next = new URLSearchParams(params); next.delete('native'); if (method === 'flex' || method === 'elastiqp') next.set('method', 'lifted'); setParams(next, { replace: true }); }} /></div>)}
      {!baseline?.problem && <p>{lang === 'es' ? 'Las penalizaciones acopladas de este caso no admiten esta edición.' : 'This case’s coupled penalties do not support these edits.'}</p>}
      <button className="btn" type="button" onClick={exportRequest} disabled={!baseline?.problem}>{lang === 'es' ? 'Descargar solicitud' : 'Download solve request'}</button>
      <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}><code>{`python data-pipeline/run_request.py ${selected}-request.json --output local-result.json`}</code></pre>
      <label htmlFor="local-result">{lang === 'es' ? 'Importar resultado nativo' : 'Import native result'}</label><input id="local-result" type="file" accept="application/json,.json" disabled={!baseline?.problem} onChange={e => { void importResult(e.target.files?.[0]); e.target.value = ''; }} />
      {nativeToken && <p role="status">{nativeError ?? (lang === 'es' ? 'Resultado nativo importado y verificado.' : 'Imported native result verified.')}</p>}
    </details>
  </>;
  const methodControls = <>
    {softQPSource === 'fixture' && <p data-state="provider">{lang === 'es' ? 'Proveedor de prueba: solo C01. No es la matriz científica completa.' : 'Fixture provider: C01 only. This is not the full scientific matrix.'}</p>}
    <label htmlFor="softqp-method">{lang === 'es' ? 'Método' : 'Method'}</label>
    <select id="softqp-method" value={method} onChange={e => setMethod(e.target.value)}>
      {current && !run && <option value={method}>{lang === 'es' ? 'Método desconocido' : 'Unknown method'}</option>}{(current?.runs.map(r => r.method) ?? ['lifted', 'generalized', 'asymmetric', 'daqp']).map(id =>
        <option key={id} value={id}>{names[id][lang]}</option>)}
    </select>
    <label htmlFor="softqp-unit">{lang === 'es' ? 'Unidad de las filas' : 'Row unit'}</label><select id="softqp-unit" value={unit} onChange={e => setUnit(e.target.value)}>{units.map(u => <option key={u}>{u}</option>)}</select>
    <button className="btn" type="button" onClick={() => setGroup('context')}>{lang === 'es' ? 'Editar costos y resolver' : 'Edit costs and solve locally'}</button>
    {run?.state === 'incompatible' && <p data-state="unavailable">{lang === 'es' ? 'El caso no cumple los supuestos que admite este método.' : 'The case is outside this method’s supported assumptions.'}</p>}
  </>;
  const resultControls = <><ReadinessNote ids={['softqp-index', 'softqp-case-result']} />
    <Readout title={{ en: localResult ? 'Verified local result' : 'Recorded result', es: localResult ? 'Resultado local verificado' : 'Resultado registrado' }} lane="replay" provenance="synthetic" items={[
      { label: { en: 'Objective', es: 'Objetivo' }, value: run?.result?.metrics?.objective ?? null, unitless: true },
      { label: { en: 'Hard-row error', es: 'Error de filas duras' }, value: hardInUnit, ...(unit === '1' ? { unitless: true } : { unit: { en: unit, es: unit } }), hint: { en: 'Maximum hard-row violation in the selected unit. Unavailable when no hard row shares that unit.', es: 'Incumplimiento duro máximo en la unidad seleccionada. No disponible si ninguna fila dura comparte esa unidad.' } },
    ]} /><button className="btn" type="button" disabled={!current} onClick={exportResult}>{lang === 'es' ? 'Exportar registro' : 'Export record'}</button>
  </>;
  const storyHref = (id: keyof typeof storyViews) => { const next = new URLSearchParams(params); next.set('case', selected); next.set('method', method); next.set('row', String(rowIndex)); next.set('frame', String(parsedScene.frame)); next.set('scene', storyViews[id]); next.set('view', 'scene'); return `/story/${id}?${next}`; };
  const recovery = <>{(nativeError ?? error) && <p role="alert">{nativeError ?? error}</p>}{restoreButton}</>;
  const rail: RailSection[] = [
    { id: 'scene', label: { en: 'Scene', es: 'Escena' }, content: <><ReadinessNote ids={['softqp-index', 'softqp-case-result']} />{sceneControls}<Link className="btn" to={storyHref('formulate')}>{lang === 'es' ? 'Recorrido guiado' : 'Guided walkthrough'}</Link>{recovery}</> },
    { id: 'method', label: { en: 'Method', es: 'Método' }, content: <>{methodControls}{recovery}</> },
    { id: 'result', label: { en: 'Result', es: 'Resultado' }, content: <>{resultControls}{recovery}</> },
    { id: 'inspection', label: { en: 'Inspect row', es: 'Inspeccionar fila' }, content: <>{rowInspection ?? <p>{lang === 'es' ? 'La inspección de fila está en las vistas de estructura, intervalo, costo y método.' : 'Row inspection is available in the structure, interval, price and method views.'}</p>}{recovery}</> },
  ];
  const interval = selectedInterval(current, run, rowIndex);
  const steps: StoryStep[] = [
    { id: 'formulate', number: 1, accent: 1, verb: { en: 'Formulate', es: 'Formular' }, headline: { en: current ? `${current.rows.length} interval rows define the problem` : 'Problem rows unavailable', es: current ? `${current.rows.length} filas de intervalo definen el problema` : 'Filas del problema no disponibles' }, summary: { en: 'Trace the actual sparse decision-to-row map.', es: 'Sigue el mapa disperso real de decisiones a filas.' }, href: storyHref('formulate'), stage: scene, panel: null },
    { id: 'price', number: 2, accent: 2, verb: { en: 'Price', es: 'Asignar costos' }, headline: { en: interval ? `${formatNumber(interval.value, 'en')} ${interval.row.unit} is the returned row value` : 'Returned separable row value unavailable', es: interval ? `${formatNumber(interval.value, 'es')} ${interval.row.unit} es el valor devuelto de la fila` : 'Valor separable devuelto no disponible' }, summary: { en: 'Inspect separate side prices without relaxing hard rows.', es: 'Inspecciona costos por lado sin relajar filas duras.' }, href: storyHref('price'), stage: scene, panel: null },
    { id: 'compute', number: 3, accent: 3, verb: { en: 'Compute', es: 'Calcular' }, headline: { en: run?.result ? `${run.result.iterations} terminal iterations were recorded` : 'Terminal solver record unavailable', es: run?.result ? `Se registraron ${run.result.iterations} iteraciones finales` : 'Registro final del solver no disponible' }, summary: { en: 'Read formulation, solve, recovery and evaluation boundaries.', es: 'Lee los límites de formulación, resolución, recuperación y evaluación.' }, href: storyHref('compute'), stage: scene, panel: null },
    { id: 'compare', number: 4, accent: 5, verb: { en: 'Compare', es: 'Comparar' }, headline: { en: current ? `${current.runs.filter(r => r.state === 'available').length} compatible methods on this selected case` : 'Compatible method population unavailable', es: current ? `${current.runs.filter(r => r.state === 'available').length} métodos compatibles en este caso seleccionado` : 'Población de métodos compatibles no disponible' }, summary: { en: 'Compare original objectives and hard-row errors for this case.', es: 'Compara objetivos originales y errores duros de este caso.' }, href: storyHref('compare'), stage: scene, panel: null },
  ];
  const casePicker = {
    cases: index?.cases.map(c => ({ id: c.case_id, name: c.title[lang], category: c.category[lang] })) ?? [],
    selectedId: selected,
    onSelect: setSelected,
    layout: 'select' as const,
  };
  const storyPanel = <>{rowInspection}<ReadinessNote ids={['softqp-index', 'softqp-case-result']} /><div className="softqp-story-selects"><CaseSelector {...casePicker} lang={lang} ariaLabel={lang === 'es' ? 'Caso' : 'Case'} /><label htmlFor="story-method">{lang === 'es' ? 'Método' : 'Method'}</label><select id="story-method" value={method} onChange={e => setMethod(e.target.value)}>{current?.runs.map(r => <option key={r.method} value={r.method}>{names[r.method][lang]}</option>)}</select>{sceneControls}</div>{storyId === 'compare' && <Link to="/benchmark">{lang === 'es' ? 'Estudios poblacionales y sus resultados negativos' : 'Population studies and their negative results'}</Link>}{nativeError && <><p role="alert">{nativeError}</p><Link to={`/app?${params.toString()}&view=context`}>{lang === 'es' ? 'Restaurar o importar en App' : 'Restore or import in App'}</Link></>}<p>{lang === 'es' ? 'Evidencia sintética registrada o importación nativa verificada. El navegador no ejecuta un nuevo QP.' : 'Recorded synthetic evidence or a verified native import. The browser does not execute a new QP.'}</p></>;
  if (story && !knownStory) return <div role="alert"><p>{lang === 'es' ? 'Paso guiado desconocido.' : 'Unknown guided step.'}</p><Link to={`/app?${params}`}>{lang === 'es' ? 'Volver al problema' : 'Return to the problem'}</Link></div>;
  if (story) return <StoryFrame steps={steps.map(step => ({ ...step, panel: storyPanel }))} activeId={storyId} mobileStageMinHeight={storyStageMinimum} onStepChange={id => navigate(storyHref(id as keyof typeof storyViews))} onExit={() => { const next = new URLSearchParams(params); next.set('scene', sceneView); next.set('view', 'scene'); navigate(`/app?${next}`); }} />;
  return <CaseWorkbench group={group} onGroupChange={setGroup} caseId={selected} source="synthetic" cases={{ ...casePicker, deepLink: true }} controls={{ method, unit, scene: sceneView, row: rowIndex, frame: parsedScene.frame, origin: localResult ? 'local-native' : softQPSource, ...(localResult ? edits : {}) }} replayOnly rail={rail} focus
    groups={[{ id: 'scene', label: { en: 'Problem scene', es: 'Escena del problema' }, lane: 'replay', provenance: 'synthetic', content: scene }, { id: 'violations', label: { en: 'Violations', es: 'Incumplimientos' }, lane: 'replay', provenance: 'synthetic', content: <Violations doc={current} run={run} unit={unit} error={error} /> }, { id: 'comparison', label: { en: 'Comparison', es: 'Comparación' }, lane: 'replay', provenance: 'synthetic', content: <Comparison doc={current} active={method} error={error} /> }, {id: 'stream',label:{en:'C12 stream',es:'Flujo C12'},lane:'replay',provenance:'synthetic',content:<StreamStage caseId={selected} method={method} edited={!!localResult}/>}]}
    context={{ content: <div><h2>{current?.title[lang]}</h2>{editor}<p>{lang === 'es' ? 'Las unidades y la política dura/blanda se conservan por fila. Un resultado elástico factible no certifica seguridad operativa. Estos registros provienen del pipeline nativo y no son nuevas optimizaciones en vivo.' : 'Units and hard/soft policy are retained per row. An elastic feasible result does not certify operational safety. These records come from the native offline pipeline and are not new live optimizations.'}</p><p>{lang === 'es' ? 'Un factor cuadrático cero declara una variante puramente L1 e incorpora FlexQP y ElastiQP cuando sus supuestos coinciden. La reconstrucción FlexQP ejecuta ecuaciones del artículo y no una política aprendida. Comparación conserva la campaña temporal registrada, el barrido controlado y el flujo pareado C12. La aceptación científica y de publicación son verificaciones separadas.' : 'A zero quadratic factor declares a pure L1 variant and includes FlexQP and ElastiQP where their assumptions match. The FlexQP reconstruction executes paper equations, not a learned policy. The Benchmark page retains the registered timing campaign, controlled conditioning sweep and paired C12 stream. Release and scientific acceptance remain separate gates.'}</p><p>{lang === 'es' ? 'Iteraciones del método seleccionado: ' : 'Selected method iterations: '}{run?.result?.iterations ?? '-'}</p></div> }} />;
}
