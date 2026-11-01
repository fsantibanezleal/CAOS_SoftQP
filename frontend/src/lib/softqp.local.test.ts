import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { validateSoftQPResult, validateSoftQPRequest } from './softqp';
import { makeLocalRequest, verifyLocalResult } from './softqp.local';
const read=(name:string)=>JSON.parse(readFileSync(new URL(`../../../docs/contracts/examples/${name}.json`,import.meta.url),'utf8'));
const baseline=validateSoftQPResult(JSON.parse(readFileSync(new URL('../../../data/derived/softqp/C01.json',import.meta.url),'utf8')));
const request=validateSoftQPRequest(read('softqp-run-request'));
describe('local scientific workflow',()=>{
  it('accepts the actual native producer and independently verifies original costs',()=>{
    expect(verifyLocalResult(read('softqp-local-export'),request,baseline).runs.filter(r=>r.state==='available')).toHaveLength(3);
  });
  it('rejects altered request, problem, row policy and computed costs',()=>{
    const changes=[(d:any)=>d.request.lower_multiplier=4,(d:any)=>d.result.problem.q[0]=1,(d:any)=>d.result.rows[0].soft=false,(d:any)=>d.result.runs[0].result.metrics.objective+=1,(d:any)=>d.result.runs[0].result.metrics.lower_violation[0]+=1];
    for(const change of changes){const doc=read('softqp-local-export');change(doc);expect(()=>verifyLocalResult(doc,request,baseline)).toThrow();}
  });
  it('rejects duplicate runs and boolean numeric inputs',()=>{
    const doc=read('softqp-local-export');doc.result.runs[1]=doc.result.runs[0];expect(()=>verifyLocalResult(doc,request,baseline)).toThrow('duplicated');
    expect(()=>makeLocalRequest('C01',request.base_sha256,0,1,1)).toThrow();
    expect(()=>validateSoftQPRequest({...request,upper_multiplier:true})).toThrow();
  });
});
