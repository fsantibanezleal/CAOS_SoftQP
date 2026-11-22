import { useEffect, useState } from 'react';
import { useFormat } from '@fasl-work/caos-app-shell';
import { useT } from '../content/bi';
import type { Campaign } from '../lib/experiments';
import { admitDirectionalSummary, timingStudy, type DirectionalSummary } from '../workbench/sceneModel';
import directionalRaw from '../../../docs/teaching/coupled/accepted-summary.json?raw';
import directionalIdentity from '../../../docs/teaching/coupled/identity.json';
import './registeredStudies.css';

/** Historical studies retain their separate estimands, denominators and negative outcomes. */
export function RegisteredStudies({ campaign }: { campaign: Campaign }) {
  const t = useT(), format = useFormat();
  const [selected, setSelected] = useState<'original' | 'directional'>('original');
  const [directional, setDirectional] = useState<DirectionalSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    admitDirectionalSummary(directionalRaw, directionalIdentity['accepted-summary.json'])
      .then(value => { if (active) setDirectional(value); })
      .catch(reason => { if (active) setError(String(reason)); });
    return () => { active = false; };
  }, []);
  const study = timingStudy(campaign, directional, selected);
  const percent = (value: number) => `${format(value, { decimals: 3 })}%`;
  const low = study ? Math.min(0, ...study.interval, study.estimate) - 5 : 0;
  const high = study ? Math.max(10, ...study.interval, study.estimate) + 5 : 10;
  const position = (value: number) => `${100 * (value - low) / (high - low)}%`;
  return <div data-registered-studies="">
    <label htmlFor="registered-study">{t('Frozen timing study', 'Estudio temporal congelado')}</label>
    <select id="registered-study" value={selected} onChange={event => setSelected(event.target.value as 'original' | 'directional')}>
      <option value="original">{t(`Original · ${campaign.primary_endpoint.paired_samples} primary pairs`, `Original · ${campaign.primary_endpoint.paired_samples} pares primarios`)}</option>
      <option value="directional">{t(`Directional · ${directional?.primary.denominator ?? '…'} primary instances`, `Direccional · ${directional?.primary.denominator ?? '…'} instancias primarias`)}</option>
    </select>
    {error && <p role="alert">{error}</p>}
    {!study ? <p role="status">{t('Verified study summary unavailable or loading.', 'Resumen verificado no disponible o cargando.')}</p> : <>
      <figure className="softqp-study-figure" aria-label={t('Registered timing reduction and 95% seed-cluster interval', 'Reducción temporal registrada e intervalo del 95% por semilla')} data-registered-interval="">
        <div className="softqp-study-scale" aria-hidden="true">
          <span className="softqp-study-band" style={{ left: position(study.interval[0]), width: `${100 * (study.interval[1] - study.interval[0]) / (high - low)}%` }} />
          <span className="softqp-study-zero" style={{ left: position(0) }} />
          <span className="softqp-study-target" style={{ left: position(10) }} />
          <span className="softqp-study-estimate" style={{ left: position(study.estimate) }} />
        </div>
        <figcaption>{t('Shaded: 95% interval. Solid: zero. Dashed: registered 10% target. Dot: median reduction. Negative reduction means the candidate took longer.', 'Sombreado: intervalo del 95%. Línea continua: cero. Discontinua: meta registrada del 10%. Punto: reducción mediana. Una reducción negativa indica mayor tiempo del candidato.')}</figcaption>
      </figure>
      <table className="caos-table"><thead><tr><th>{t('Registered quantity', 'Cantidad registrada')}</th><th>{t('Frozen result', 'Resultado congelado')}</th></tr></thead><tbody>
        <tr><th>{t('Median time reduction', 'Reducción temporal mediana')}</th><td>{percent(study.estimate)}</td></tr>
        <tr><th>{t('95% seed-cluster interval', 'Intervalo del 95% por semilla')}</th><td>{study.interval.map(percent).join(' / ')}</td></tr>
        <tr><th>{t('Primary denominator / failed pairs', 'Denominador primario / pares fallidos')}</th><td data-study-provenance="">{study.denominator} / {study.failed}</td></tr>
        <tr><th>{t('Seed clusters', 'Grupos de semillas')}</th><td>{study.clusters}</td></tr>
        <tr><th>{t('Registered criterion', 'Criterio registrado')}</th><td>{study.established ? t('Met in this regime', 'Cumplido en este régimen') : t('Not established', 'No establecido')}</td></tr>
      </tbody></table>
      <p>{selected === 'original'
        ? t('Asymmetric elastic problems with at least 128 variables and density 0.05; candidate versus the faster paired native lift or DAQP cold end-to-end time. The registered criterion requires at least 10% median reduction, an interval above zero and no rejected compared pair.', 'Problemas elásticos asimétricos de al menos 128 variables y densidad 0,05; candidato frente al menor tiempo total frío pareado de holguras nativas o DAQP. El criterio exige reducción mediana de al menos 10%, intervalo sobre cero y ningún par comparado rechazado.')
        : t('Directional SDK 0.2 versus the fastest compatible preregistered baseline, using complete-batch operation times. The 144 registered primary instances include nine failed pairs assigned reduction −1. This population and estimand are distinct from the original study.', 'SDK direccional 0.2 frente a la referencia compatible registrada más rápida, con tiempos de operación del lote completo. Las 144 instancias primarias incluyen nueve pares fallidos con reducción −1. Esta población y cantidad estimada son distintas del estudio original.')}</p>
      <details data-study-policy=""><summary>{t('Immutable protocol and failure rule', 'Protocolo inmutable y regla de fallas')}</summary><p>{study.failureRule}</p><p>{study.source} · SHA-256 <code className="softqp-study-hash">{study.protocol}</code></p></details>
      <p>{t('These completed negative studies establish neither timing superiority nor algorithmic novelty. Their observations and endpoints are unchanged.', 'Estos estudios negativos completados no establecen superioridad temporal ni novedad algorítmica. Sus observaciones y resultados principales permanecen sin cambios.')}</p>
    </>}
  </div>;
}
