import { PlotCard, useShellLang, useWorkbenchState } from '@fasl-work/caos-app-shell';
import { UPlotChart } from '@fasl-work/caos-app-shell/chart';
import { useExperiments } from '../lib/experiments';

export function StreamStage({caseId,method,edited}:{caseId:string;method:string;edited:boolean}){
  const {evidence,error}=useExperiments();const lang=useShellLang();const key=useWorkbenchState()?.stateKey;
  const unavailable=caseId!=='C12'||edited||!['lifted','asymmetric','daqp'].includes(method);
  return <PlotCard fill dataKey={key} title={{en:'C12 cold and warm stream',es:'Flujo frío y cálido C12'}} lane="replay" provenance="synthetic" note={{en:'32 identical oracle-driven state inputs. Warm timing excludes the separately recorded initial workspace setup. One observation per frame, not a statistical speed claim.',es:'32 estados idénticos conducidos por el oráculo. El tiempo cálido excluye la preparación inicial registrada por separado. Una observación por cuadro, sin afirmación estadística de rapidez.'}}>
    {unavailable?<p data-state="unavailable">{lang==='es'?'El flujo registrado requiere C12 sin ediciones y holguras explícitas, proyección asimétrica o DAQP. La proyección generalizada no admite los costos asimétricos.':'The recorded stream requires unedited C12 and lifting, asymmetric projection or DAQP. Generalized projection cannot represent its unequal side costs.'}</p>:error?<p role="alert">{error}</p>:!evidence?<p role="status">{lang==='es'?'Cargando flujo verificado…':'Loading verified stream…'}</p>:<UPlotChart height="fill" title={{en:'Paired solve time by frame',es:'Tiempo pareado por cuadro'}} x={{values:evidence.stream.frames.map(f=>f.frame),time:false,label:{en:'Frame',es:'Cuadro'}}} y={{label:{en:'Elapsed time',es:'Tiempo transcurrido'},unit:{en:'ms',es:'ms'}}} solo series={(['cold','warm'] as const).map(mode=>({id:mode,label:{en:mode==='cold'?'Cold':'Warm',es:mode==='cold'?'Frío':'Cálido'},dots:true,values:evidence.stream.frames.map(f=>{const r=f.runs.find(r=>r.method===method&&r.mode===mode);return r?.state==='accepted'&&r.elapsed_seconds!=null?r.elapsed_seconds*1000:null;})}))}/>}
  </PlotCard>;
}
