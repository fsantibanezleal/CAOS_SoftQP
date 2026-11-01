import { useEffect, useState } from 'react';
import { loadSoftQPCase, loadSoftQPIndex, softQPSource, type SoftQPResult } from './softqp';
/** One cancellable load path for numerical documentation: no example-domain model. */
export function useScientificRecords() {
  const [records,setRecords]=useState<SoftQPResult[]|null>(null);
  const [error,setError]=useState<string|null>(null);
  useEffect(()=>{
    const abort=new AbortController();
    loadSoftQPIndex(abort.signal).then(index=>Promise.all(index.cases.map(entry=>loadSoftQPCase(entry,abort.signal))))
      .then(data=>{if(!abort.signal.aborted)setRecords(data);})
      .catch(e=>{if(!abort.signal.aborted)setError(String(e));});
    return()=>abort.abort();
  },[]);
  return {records,error,source:softQPSource};
}
