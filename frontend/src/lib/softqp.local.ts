import { validateSoftQPLocalExport, validateSoftQPRequest, type SoftQPProblem, type SoftQPRequest, type SoftQPResult } from './softqp';

export function makeLocalRequest(caseId: string, digest: string, lower: number, upper: number, quadratic: number): SoftQPRequest {
  return validateSoftQPRequest({ schema_version: 'softqp.run-request/v1', case_id: caseId, base_sha256: digest, lower_multiplier: lower, upper_multiplier: upper, quadratic_multiplier: quadratic });
}
function equal(a: unknown, b: unknown): boolean {
  if (typeof a === 'number' && typeof b === 'number') return Number.isFinite(a) && Number.isFinite(b) && Math.abs(a-b) <= 1e-12*Math.max(1,Math.abs(a),Math.abs(b));
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((v,i) => equal(v,b[i]));
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    const x=a as Record<string,unknown>, y=b as Record<string,unknown>;
    return Object.keys(x).length===Object.keys(y).length && Object.keys(x).every(k => Object.hasOwn(y,k) && equal(x[k],y[k]));
  }
  return a===b;
}
function multiply(matrix: SoftQPProblem['A'], x: number[]): number[] {
  const [m,n]=matrix.shape;
  if (x.length!==n || matrix.indptr.length!==n+1 || matrix.data.length!==matrix.indices.length || matrix.indptr[0]!==0 || matrix.indptr[n]!==matrix.data.length) throw new Error('Invalid sparse dimensions');
  const y=Array<number>(m).fill(0);
  for (let j=0;j<n;j++) {
    if (matrix.indptr[j]>matrix.indptr[j+1]) throw new Error('Invalid sparse offsets');
    for(let k=matrix.indptr[j];k<matrix.indptr[j+1];k++) {
      const row=matrix.indices[k]; if(row>=m) throw new Error('Invalid sparse row');
      y[row]+=matrix.data[k]*x[j];
    }
  }
  return y;
}
const close=(a:number,b:number) => Number.isFinite(a) && Number.isFinite(b) && Math.abs(a-b)<=5e-7*Math.max(1,Math.abs(a),Math.abs(b));
export function verifyLocalResult(value: unknown, request: SoftQPRequest, baseline: SoftQPResult): SoftQPResult {
  const envelope=validateSoftQPLocalExport(value);
  if (!equal(envelope.request,request)) throw new Error('The local result does not match the current request');
  if (!baseline.problem) throw new Error('Cost editing is unavailable for coupled penalties');
  const expected=structuredClone(baseline.problem);
  expected.penalty.lower_linear=expected.penalty.lower_linear.map((x,i)=>expected.penalty.soft[i]?x*request.lower_multiplier:x);
  expected.penalty.upper_linear=expected.penalty.upper_linear.map((x,i)=>expected.penalty.soft[i]?x*request.upper_multiplier:x);
  expected.penalty.lower_quadratic=expected.penalty.lower_quadratic.map((x,i)=>expected.penalty.soft[i]?x*request.lower_multiplier*request.quadratic_multiplier:x);
  expected.penalty.upper_quadratic=expected.penalty.upper_quadratic.map((x,i)=>expected.penalty.soft[i]?x*request.upper_multiplier*request.quadratic_multiplier:x);
  const doc=envelope.result;
  if(doc.case_id!==baseline.case_id || !equal(doc.problem,expected) || !equal(doc.rows,baseline.rows) || !equal(doc.settings,baseline.settings)) throw new Error('Local result changed undeclared inputs or row policy');
  const expectedMethods=request.quadratic_multiplier===0?['lifted','generalized','asymmetric','daqp','flex','elastiqp']:['lifted','generalized','asymmetric','daqp'];
  if(doc.runs.length!==expectedMethods.length || new Set(doc.runs.map(r=>r.method)).size!==expectedMethods.length || expectedMethods.some(method=>!doc.runs.some(r=>r.method===method))) throw new Error('Incomplete or duplicated comparison');
  for(const run of doc.runs) {
    if(run.state!=='available') continue;
    const result=run.result, p=expected;
    if(!result?.x || !result.metrics || result.method!==run.method || !(result.status_code===1 || (run.method==='daqp' && result.status_code===2))) throw new Error('Invalid successful result');
    const x=result.x, z=multiply(p.A,x), px=multiply(p.P,x), metrics=result.metrics;
    const lower=z.map((v,i)=>p.lower[i]===null ? 0:Math.max(p.lower[i]!-v,0));
    const upper=z.map((v,i)=>p.upper[i]===null ? 0:Math.max(v-p.upper[i]!,0));
    const base=x.reduce((s,v,i)=>s+.5*v*px[i]+p.q[i]*v,0);
    const cost=lower.reduce((s,v,i)=>s+(p.penalty.soft[i] ? p.penalty.lower_linear[i]*v+p.penalty.upper_linear[i]*upper[i]+.5*p.penalty.lower_quadratic[i]*v*v+.5*p.penalty.upper_quadratic[i]*upper[i]**2:0),0);
    const hard=Math.max(0,...lower.map((v,i)=>p.penalty.soft[i]?0:v+upper[i]));
    if(!close(metrics.objective,base+cost) || !close(metrics.base_objective,base) || !close(metrics.penalty_objective,cost) || !close(metrics.hard_violation,hard)) throw new Error('Local objective or hard violation verification failed');
    for(const [actual,recomputed] of [[metrics.lower_violation,lower],[metrics.upper_violation,upper],[metrics.slack,lower.map((v,i)=>v-upper[i])]]) {
      if(actual.length!==recomputed.length || !actual.every((v,i)=>close(v,recomputed[i]))) throw new Error('Local violation verification failed');
    }
  }
  const oracle=doc.runs.find(r=>r.method==='lifted' && r.state==='available')?.result?.metrics?.objective;
  for(const run of doc.runs) if(run.state==='available' && run.result?.metrics && oracle!==undefined) {
    const gap=run.result.metrics.objective_gap_against_lifted;
    if(gap==null || !close(gap,Math.abs(run.result.metrics.objective-oracle))) throw new Error('Local comparison gap verification failed');
  }
  return doc;
}
