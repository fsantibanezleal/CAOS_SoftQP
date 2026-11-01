import { BarChart, CaseWorkbench, PlotCard, Readout, useShellLang, useWorkbenchState } from '@fasl-work/caos-app-shell';
import { useEffect, useState } from 'react';
import { loadSoftQPCase, loadSoftQPIndex, type SoftQPIndex, type SoftQPResult, type SoftQPRun } from '../lib/softqp';

const names: Record<string, { en: string; es: string }> = {
  lifted: { en: 'Explicit lifting', es: 'Holguras explícitas' },
  generalized: { en: 'Generalized projection', es: 'Proyección generalizada' },
  asymmetric: { en: 'Asymmetric projection', es: 'Proyección asimétrica' },
};
const fmt = (n: number | null | undefined, lang: string) => n == null ? '—' : new Intl.NumberFormat(lang, { maximumSignificantDigits: 6 }).format(n);

function Violations({ doc, run, unit }: { doc: SoftQPResult | null; run: SoftQPRun | undefined; unit: string }) {
  const lang = useShellLang(); const key = useWorkbenchState()?.stateKey;
  const metrics = run?.result?.metrics;
  const all = doc?.rows.map((r, i) => ({ ...r, lower: metrics?.lower_violation[i] ?? 0, upper: metrics?.upper_violation[i] ?? 0 })).filter(r => r.unit === unit) ?? [];
  const nonzero = all.filter(r => r.lower > 1e-9 || r.upper > 1e-9);
  const rows = (nonzero.length ? nonzero : all).slice(0, 18);
  return <PlotCard fill title={{ en: 'Lower and upper violations', es: 'Incumplimientos por lado' }} note={{ en: 'Lower and upper bounds are separate series. Only rows with the same unit are compared. Up to 18 are shown; the export includes every row.', es: 'Los lados inferior y superior son series separadas. Solo se comparan filas con la misma unidad. Se muestran hasta 18; la exportación incluye todas.' }} lane="replay" provenance="synthetic" dataKey={key}>
    {!doc ? <p role="status">{lang === 'es' ? 'Cargando…' : 'Loading…'}</p> : !metrics ? <p data-state="unavailable">{lang === 'es' ? 'Sin resultado compatible para este método.' : 'No compatible result for this method.'}</p> : <>
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

function Comparison({ doc }: { doc: SoftQPResult | null }) {
  const lang = useShellLang(); const key = useWorkbenchState()?.stateKey;
  const good = doc?.runs.filter(r => r.result) ?? [];
  return <PlotCard fill title={{ en: 'Matched formulations', es: 'Formulaciones equivalentes' }} note={{ en: 'One development run per method; timing superiority remains unestablished.', es: 'Una medición de desarrollo por método; no se establece superioridad de tiempo.' }} lane="replay" provenance="synthetic" dataKey={key}>
    <div style={{ overflowX: 'auto', maxWidth: '100%' }}><table style={{ width: '100%' }}><thead><tr>{(lang === 'es' ? ['Método', 'Estado', 'Objetivo', 'Brecha', 'Error duro', 'Iteraciones', 'Solución (ms)'] : ['Method', 'Status', 'Objective', 'Gap', 'Hard error', 'Iterations', 'Solve (ms)']).map(h => <th key={h}>{h}</th>)}</tr></thead>
      <tbody>{doc?.runs.map(r => <tr key={r.method}><th>{names[r.method]?.[lang] ?? r.method}</th><td>{r.result?.status ?? (r.state === 'incompatible' ? 'Incompatible' : r.state)}</td><td>{fmt(r.result?.metrics?.objective, lang)}</td><td>{fmt(r.result?.metrics?.objective_gap_against_lifted, lang)}</td><td>{fmt(r.result?.metrics?.hard_violation, lang)}</td><td>{r.result?.iterations ?? '—'}</td><td>{fmt(r.result ? r.result.solve_seconds * 1000 : null, lang)}</td></tr>)}</tbody>
    </table></div>
    <div style={{ flex: 1, minHeight: 0 }}><BarChart height="fill" title={{ en: 'Formulation dimensions', es: 'Dimensiones de formulación' }}
      axis={{ label: { en: 'Primal variables', es: 'Variables primales' }, format: { decimals: 0 } }}
      data={good.map(r => ({ id: r.method, label: names[r.method], value: r.result!.dimensions.variables, tone: r.method === 'lifted' ? 'warn' as const : 'accent' as const }))} /></div>
  </PlotCard>;
}

export function Workbench() {
  const lang = useShellLang();
  const [index, setIndex] = useState<SoftQPIndex | null>(null); const [doc, setDoc] = useState<SoftQPResult | null>(null);
  const [selected, setSelected] = useState('C01'); const [method, setMethod] = useState('lifted'); const [unit, setUnit] = useState('1'); const [error, setError] = useState<string | null>(null);
  useEffect(() => { loadSoftQPIndex().then(setIndex).catch(e => setError(String(e))); }, []);
  useEffect(() => {
    const entry = index?.cases.find(c => c.case_id === selected); if (!entry) return;
    const abort = new AbortController(); setDoc(null); setError(null);
    loadSoftQPCase(entry, abort.signal).then(result => { if (!abort.signal.aborted) { setDoc(result); setUnit(result.rows.find(r => r.soft)?.unit ?? result.rows[0]?.unit ?? '1'); } }).catch(e => { if (!abort.signal.aborted) setError(String(e)); });
    return () => abort.abort();
  }, [selected, index]);
  const current = doc?.case_id === selected ? doc : null; const run = current?.runs.find(r => r.method === method); const units = [...new Set(current?.rows.map(r => r.unit) ?? ['1'])];
  function exportResult() {
    if (!current) return;
    const blob = new Blob([JSON.stringify({ lane: 'replay', selected_method: method, result: current }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `${selected}-${method}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const rail = <><p>{lang === 'es' ? 'Resultados de desarrollo reproducibles. Seleccione caso, método y unidad.' : 'Reproducible development results. Select a case, method and unit.'}</p>
    <label htmlFor="softqp-unit">{lang === 'es' ? 'Unidad de las filas' : 'Row unit'}</label><select id="softqp-unit" value={unit} onChange={e => setUnit(e.target.value)}>{units.map(u => <option key={u}>{u}</option>)}</select>
    <Readout title={{ en: 'Recorded result', es: 'Resultado registrado' }} lane="replay" provenance="synthetic" items={[
      { label: { en: 'Objective', es: 'Objetivo' }, value: run?.result?.metrics?.objective ?? null, unitless: true },
      { label: { en: 'Hard-row error', es: 'Error de filas duras' }, value: run?.result?.metrics?.hard_violation ?? null, unitless: true },
      { label: { en: 'Iterations', es: 'Iteraciones' }, value: run?.result?.iterations ?? null, unitless: true },
    ]} /><button type="button" disabled={!current} onClick={exportResult}>{lang === 'es' ? 'Exportar registro' : 'Export record'}</button>
    {error && <p role="alert">{error}</p>}{run?.state === 'incompatible' && <p data-state="unavailable">{lang === 'es' ? 'La penalización queda fuera de la familia admitida por este método.' : 'The penalty is outside this method’s supported family.'}</p>}</>;
  return <CaseWorkbench caseId={selected} source="synthetic" cases={{ cases: index?.cases.map(c => ({ id: c.case_id, name: c.title[lang], category: c.category[lang] })) ?? [], selectedId: selected, onSelect: setSelected, layout: 'select', deepLink: true }} controls={{ method, unit }} rail={rail} focus
    variants={{ variants: ['lifted', 'generalized', 'asymmetric'].map(id => ({ id, label: names[id], note: { en: 'Recorded offline solve.', es: 'Solución registrada fuera del navegador.' }, lane: 'replay' as const })), activeId: method, onSelect: setMethod, title: { en: 'Method', es: 'Método' } }}
    groups={[{ id: 'violations', label: { en: 'Violations', es: 'Incumplimientos' }, lane: 'replay', provenance: 'synthetic', content: <Violations doc={current} run={run} unit={unit} /> }, { id: 'comparison', label: { en: 'Comparison', es: 'Comparación' }, lane: 'replay', provenance: 'synthetic', content: <Comparison doc={current} /> }]}
    context={{ content: <div><h2>{current?.title[lang]}</h2><p>{lang === 'es' ? 'Las unidades y la política dura/blanda se conservan por fila. Un resultado elástico factible no certifica seguridad operativa. Estos registros provienen del pipeline nativo y no son nuevas optimizaciones en vivo.' : 'Units and hard/soft policy are retained per row. An elastic feasible result does not certify operational safety. These records come from the native offline pipeline and are not new live optimizations.'}</p><p>{lang === 'es' ? 'Faltan las comparaciones DAQP/FlexQP, los experimentos repetidos y de inicio cálido y la aceptación de publicación. No se establece superioridad ni novedad.' : 'DAQP/FlexQP comparisons, repeated and warm-start experiments, and release acceptance remain pending. No superiority or novelty is established.'}</p></div> }} />;
}
