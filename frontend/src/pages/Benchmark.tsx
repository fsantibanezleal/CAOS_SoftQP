import { BarChart, Callout, DocPage, DocSection, PlotCard, useFormat } from '@fasl-work/caos-app-shell';
import { useState } from 'react';
import { methodNames as names } from '../lib/methodNames';
import { MeasuredExperiments } from './MeasuredExperiments';
import { P, useT } from '../content/bi';
import { useScientificRecords } from '../lib/useScientificRecords';
import { ReadinessNote } from '../readiness/ReadinessNote';
const local={en:'Computed from verified committed scientific records.',es:'Calculado desde registros científicos versionados y verificados.'};
export function Benchmark(){
  const t=useT();const format=useFormat();const {records,error}=useScientificRecords();const [method,setMethod]=useState('asymmetric');
  const [matrixCase,setMatrixCase]=useState('C01');
  const cells=records?.flatMap(doc=>doc.runs.map(run=>({doc,run})))??[];
  const fmt=(value:number|null|undefined)=>format(value,{digits:5});
  const good=cells.filter(c=>c.run.state==='available');
  return <DocPage title={{en:'Benchmark',es:'Comparación'}} lede={t('This page reads the committed development matrix and exposes agreement, formulation size and compatibility. It separates those correctness observations from the repeated held-out timing experiment required for a performance claim. Every cell retains its method state, so an unsupported formulation or failed solve cannot disappear from the comparison.', 'Esta página lee la matriz de desarrollo versionada y muestra concordancia, dimensiones y compatibilidad. Separa esas observaciones de corrección del experimento repetido y reservado necesario para afirmar desempeño. Cada celda conserva su estado, evitando que una formulación incompatible o una solución fallida desaparezcan de la comparación.')} floorWaivers={[
    {floor:'live',reason:{en:'The actual solver is a native C extension. The browser verifies recorded and locally imported results. A compiled browser solver has not passed its parity and resource gates.',es:'El solver real es una extensión nativa C. El navegador verifica registros y resultados locales. Un solver compilado para navegador no ha superado paridad y recursos.'}},
    {floor:'comparison',reason:{en:'No learned method is implemented or trained, so no same-data learned-versus-classical benchmark exists. This section reports deterministic method scope and matched-comparison requirements only.',es:'No se implementa ni entrena un método aprendido, por lo que no existe una comparación de referencia con los mismos datos. Esta sección informa el alcance determinista y los requisitos de comparación equivalente.'}},
  ]}>
    {error&&<p role="alert">{error}</p>}
    {!records&&<p role="status">{t('Loading verified comparison records…','Cargando registros comparativos verificados…')}</p>}
    <DocSection area="results" title={{en:'Development matrix',es:'Matriz de desarrollo'}} noRefsReason={local}>
      <ReadinessNote ids={['softqp-index', 'softqp-case-result']} />
      <p>{t(`${records?.length??0} cases; ${good.length} successful compatible cells; ${cells.filter(c=>c.run.state==='incompatible').length} incompatible; ${cells.filter(c=>c.run.state==='failed').length} failed.`,`${records?.length??0} casos; ${good.length} celdas compatibles exitosas; ${cells.filter(c=>c.run.state==='incompatible').length} incompatibles; ${cells.filter(c=>c.run.state==='failed').length} fallidas.`)}</p>
      <label htmlFor="matrix-case">{t('Development case','Caso de desarrollo')}</label>
      <select id="matrix-case" value={matrixCase} onChange={e=>setMatrixCase(e.target.value)}>
        {(records??[]).map(doc=><option key={doc.case_id} value={doc.case_id}>{doc.case_id}: {t(doc.title.en,doc.title.es)}</option>)}
      </select>
      <p>{t('Select a case to inspect all four recorded method states. The totals above cover the complete matrix.', 'Seleccione un caso para examinar sus cuatro estados de método. Los totales anteriores abarcan la matriz completa.')}</p>
      <div style={{overflowX:'auto'}}><table className="caos-table" data-development-matrix><thead><tr>{[t('Case','Caso'),t('Method','Método'),t('State','Estado'),t('Objective gap','Brecha de objetivo'),t('Hard-row error','Error duro'),t('Variables / rows','Variables / filas')].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{cells.filter(({doc})=>doc.case_id===matrixCase).map(({doc,run})=><tr key={`${doc.case_id}-${run.method}`}><th>{doc.case_id}</th><td>{t(names[run.method].en,names[run.method].es)}</td><td title={run.reason??undefined}>{run.state==='available'?t('Available','Disponible'):run.state==='failed'?t('Failed','Fallido'):t('Incompatible','Incompatible')}</td><td>{fmt(run.result?.metrics?.objective_gap_against_lifted)}</td><td>{fmt(run.result?.metrics?.hard_violation)}</td><td>{run.result?`${run.result.dimensions.variables} / ${run.result.dimensions.rows}`:'-'}</td></tr>)}</tbody></table></div>
      <h3>{t('Method support and evidence','Ámbito de métodos y evidencia')}</h3>
      <P en="This table states the supported original problems and the execution evidence for each implementation. Compatibility does not imply a speed ranking; the registered timing results are reported separately above."
        es="Esta tabla indica los problemas originales admitidos y la evidencia de ejecución de cada implementación. La compatibilidad no implica un orden de velocidad; los resultados temporales registrados se informan por separado arriba." />
      <div style={{overflowX:'auto'}}><table className="caos-table" data-method-support><thead><tr><th>{t('Method','Método')}</th><th>{t('Supported original objective','Objetivo original admitido')}</th><th>{t('Evidence state','Estado de evidencia')}</th></tr></thead><tbody>{[
        [t('Explicit lifting','Holguras explícitas'),t('Compact symmetric and separate-side convex costs','Costos convexos simétricos compactos y por lado'),t('Executed independent reference','Referencia independiente ejecutada')],
        [t('Generalized projection','Proyección generalizada'),t('Published symmetric separable, Huber and group costs','Costos publicados simétricos separables, Huber y de grupo'),t('Executed pinned source','Fuente fija ejecutada')],
        [t('Asymmetric projection','Proyección asimétrica'),t('Separable nonnegative linear-quadratic side costs','Costos separables por lado lineales y cuadráticos no negativos'),t('Executed candidate; novelty unestablished','Candidato ejecutado; novedad no establecida')],
        ['DAQP',t('Positive definite separable elastic cases','Casos elásticos separables definidos positivos'),t('Executed compatible cells','Celdas compatibles ejecutadas')],
        ['FlexQP',t('Pure L1 soft inequalities','Desigualdades blandas L1'),t('Executed fixed-parameter paper reconstruction','Reconstrucción fija del artículo ejecutada')],
        ['ElastiQP',t('Positive definite pure L1 with hard equalities','L1 definida positiva con igualdades duras'),t('Executed published 0.2.0 DAS backend','Backend DAS 0.2.0 publicado ejecutado')],
      ].map(([a,b,c])=><tr key={a}><th>{a}</th><td>{b}</td><td>{c}</td></tr>)}</tbody></table></div>
    </DocSection>
    <DocSection area="comparison" title={{en:'What is a matched comparison?',es:'¿Qué es una comparación equivalente?'}} refs={['gsp','daqp','flex']}>
      <P en="Explicit lifting and the native projections are compared only when their penalties and hard rows are identical. DAQP joins on supported positive definite elastic problems. The inventory's setup and solve times are individual development observations using different solver builds; they do not establish a ranking. A controlled timing run must compare the ordinary lift and projection under the same native backend and retain a separate independent stock-solver oracle."
        es="Las holguras explícitas y las proyecciones se comparan solo con penalizaciones y filas duras idénticas. DAQP participa en problemas elásticos definidos positivos compatibles. Los tiempos del inventario son observaciones individuales con compilaciones distintas y no establecen un orden. Un experimento controlado debe usar el mismo backend nativo para holguras y proyección y conservar una referencia estándar independiente." />
    </DocSection>
    <MeasuredExperiments />
    <DocSection area="robustness" title={{en:'Accuracy across declared structures',es:'Precisión según estructura declarada'}} noRefsReason={local}>
      <P en="The chart uses a dimensionless objective discrepancy, divided by the larger of one and the absolute lifted objective. It is a descriptive check across different authored cases, not a controlled conditioning curve or a held-out success-rate estimate. Unsupported cells are listed in the matrix and omitted from the numeric series, rather than assigned a zero discrepancy."
        es="El gráfico usa discrepancia de objetivo adimensional, dividida por el mayor entre uno y el valor absoluto del objetivo explícito. Es una verificación descriptiva entre casos propios, no una curva controlada de condicionamiento ni una tasa de éxito reservada. Las celdas incompatibles figuran en la matriz y se omiten de la serie, sin asignarles discrepancia cero." />
      <label htmlFor="benchmark-method">{t('Comparison method','Método comparado')}</label><select id="benchmark-method" value={method} onChange={e=>setMethod(e.target.value)}>{Object.entries(names).filter(([id])=>id!=='lifted').map(([id,name])=><option key={id} value={id}>{t(name.en,name.es)}</option>)}</select>
      <PlotCard title={{en:'Relative objective agreement',es:'Concordancia relativa del objetivo'}} lane="replay" provenance="synthetic"><BarChart height={320} title={{en:'Objective discrepancy by case',es:'Discrepancia por caso'}} axis={{label:{en:'Relative discrepancy',es:'Discrepancia relativa'}}} data={(records??[]).flatMap(doc=>{
        const run=doc.runs.find(r=>r.method===method&&r.state==='available')?.result;const oracle=doc.runs.find(r=>r.method==='lifted'&&r.state==='available')?.result;
        if(!run?.metrics||!oracle?.metrics||run.metrics.objective_gap_against_lifted==null)return[];
        return[{id:doc.case_id,label:{en:doc.case_id,es:doc.case_id},value:run.metrics.objective_gap_against_lifted/Math.max(1,Math.abs(oracle.metrics.objective)),tone:'accent' as const}];
      })}/></PlotCard>
    </DocSection>
    <DocSection area="provenance" title={{en:'Per-case provenance',es:'Procedencia por caso'}} noRefsReason={local}>
      <table className="caos-table"><thead><tr>{[t('Case','Caso'),t('Dataset / model','Datos / modelo'),t('Difficulty source','Fuente de dificultad'),t('Redistribution','Redistribución')].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{records?.map(doc=><tr key={doc.case_id}><th>{doc.case_id}</th><td>{doc.case_id==='C13'?t('Published synthetic building','Edificio sintético publicado'):t('Authored synthetic case','Caso sintético propio')}</td><td>{t(doc.title.en,doc.title.es)}</td><td>{['C13','C14','C15'].includes(doc.case_id)?'MIT / OSQPSlack':'MIT'}</td></tr>)}</tbody></table>
    </DocSection>
    <DocSection area="caveat" title={{en:'What these numbers establish',es:'Qué establecen estos números'}} refs={['gsp','flex']}>
      <Callout variant="honest" title={t('Correctness evidence before performance claims','Evidencia de corrección antes de afirmar desempeño')}>{t('The catalog and the separately exported experimental campaign answer different questions. The measured outcome is bounded by its preregistered instances, source, tolerances and implementation languages. Neither asymmetry nor elastic feasibility is new by itself. Scientific novelty, operational safety and release acceptance do not follow from a completed experiment.', 'El catálogo y la campaña experimental exportada responden preguntas distintas. El resultado medido se limita a instancias, código, tolerancias y lenguajes prerregistrados. La asimetría y la factibilidad elástica no son nuevas por sí solas. Completar un experimento no establece novedad científica, seguridad operativa ni aceptación de publicación.')}</Callout>
    </DocSection>
  </DocPage>;
}
