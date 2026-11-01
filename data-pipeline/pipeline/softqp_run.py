"""Offline solver execution and explicit checksummed export; no browser computation."""
import hashlib
import importlib.metadata
import json
import math
import platform
from pathlib import Path
import time
import numpy as np
from softqp.solvers import solve
from .softqp_cases import cases
from .softqp_rows import rows_for

SETTINGS=dict(eps_abs=1e-7,eps_rel=1e-7,max_iter=200000,adaptive_rho_interval=25)

def validate_document(value,name):
    from jsonschema import Draft202012Validator
    def finite(node):
        if isinstance(node,float) and not math.isfinite(node):raise ValueError('nonfinite numerical result')
        if isinstance(node,dict):
            for child in node.values():finite(child)
        if isinstance(node,list):
            for child in node:finite(child)
    finite(value)
    schema=Path(__file__).resolve().parents[2]/'docs/contracts/schemas'/f'{name}.schema.json'
    Draft202012Validator(json.loads(schema.read_text(encoding='utf-8'))).validate(value)
    return value

def reference_cost(reference,x):
    from softqp.reference import NONE,L1L2,HUBER,NORMINF
    P,q,A,l,u,pen=reference
    residual=A@x-np.clip(A@x,l,u)
    mag=np.abs(residual)
    cost=0.
    for i,t in enumerate(pen.type):
        if t==L1L2:cost+=pen.alpha1[i]*mag[i]+.5*pen.alpha2[i]*mag[i]**2
        elif t==HUBER:
            d=pen.delta[i];cost+=pen.alpha1[i]*(.5*mag[i]**2 if mag[i]<=d else d*mag[i]-.5*d*d)
    for group in np.unique(pen.group[pen.group>=0]):
        rows=pen.group==group
        if np.any(pen.type[rows]!=NORMINF):raise ValueError('unsupported group objective')
        cost+=pen.alpha1[rows][0]*np.max(mag[rows],initial=0.)
    base=float(.5*x@(P@x)+q@x)
    return dict(base_objective=base,penalty_objective=float(cost),objective=base+float(cost),
                lower_violation=np.maximum(l-A@x,0.).tolist(),upper_violation=np.maximum(A@x-u,0.).tolist(),
                slack=(-residual).tolist(),hard_violation=float(np.max(mag[pen.type==NONE],initial=0.)))

def run_reference(case,method):
    import osqp
    from softqp import OSQP
    from softqp.reference import lift
    ref=case.reference
    P,q,A,l,u,pen=ref
    start=time.perf_counter()
    if method=='lifted':
        P1,q1,A1,l1,u1=lift(*ref)
        solver=osqp.OSQP()
        solver.setup(P1,q1,A1,l1,u1,verbose=False,polishing=False,**SETTINGS)
        dimension=dict(variables=q1.size,rows=A1.shape[0],nnz=P1.nnz+A1.nnz)
    else:
        solver=OSQP()
        solver.setup(P,q,A,l,u,verbose=False,polishing=False,**SETTINGS)
        pen.setup(solver)
        dimension=dict(variables=q.size,rows=A.shape[0],nnz=P.nnz+A.nnz)
    result=solver.solve()
    accepted=result.info.status_val==1
    x=result.x[:q.size]
    return dict(method=method,status=result.info.status,status_code=int(result.info.status_val),
                x=x.tolist() if accepted else None,metrics=reference_cost(ref,x) if accepted else None,
                dimensions=dimension,iterations=int(result.info.iter),setup_seconds=float(result.info.setup_time),
                solve_seconds=float(result.info.solve_time),elapsed_seconds=time.perf_counter()-start)

def run_case(case):
    rows=[]
    for method in ['lifted','generalized','asymmetric']:
        reason=None
        if method=='asymmetric' and case.reference is not None:
            reason='The separable asymmetric candidate does not support grouped or Huber penalties.'
        if method=='generalized' and case.problem is not None:
            p=case.problem.penalty
            if not(np.array_equal(p.lower_linear,p.upper_linear) and np.array_equal(p.lower_quadratic,p.upper_quadratic)):
                reason='The published unconditional penalty reference requires symmetric side costs.'
        if reason:
            rows.append(dict(method=method,state='incompatible',reason=reason,result=None));continue
        try:
            result=run_reference(case,method) if case.reference is not None else solve(case.problem,method,**SETTINGS)
            good=result['status_code']==1
            rows.append(dict(method=method,state='available' if good else 'failed',reason=None if good else result['status'],result=result))
        except Exception as error:
            rows.append(dict(method=method,state='failed',reason=f'{type(error).__name__}: {error}',result=None))
    successful=[r for r in rows if r['state']=='available']
    oracle=next((r for r in successful if r['method']=='lifted'),None)
    for row in successful:
        row['result']['metrics']['objective_gap_against_lifted']=None if oracle is None else abs(row['result']['metrics']['objective']-oracle['result']['metrics']['objective'])
    return dict(schema_version='softqp.case-result/v2',case_id=case.id,title=case.title,category=case.category,
                rows=rows_for(case),
                seed=case.seed,source='OSQPSlack MIT source model' if case.id=='C13' else 'authored synthetic case',
                settings=SETTINGS,runs=rows)

def bake(output:Path,selected=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    inventory=[]
    catalog=cases()
    ids=[c.id for c in catalog]
    if ids!=[f'C{i:02}' for i in range(1,16)]:
        raise ValueError('catalog must contain the fifteen case IDs exactly once in order')
    if selected is not None and (not selected or set(selected)-{c.id for c in catalog}):
        raise ValueError('selected case IDs must be nonempty and belong to the catalog')
    for case in catalog:
        if selected is not None and case.id not in selected:continue
        result=run_case(case)
        validate_document(result,'softqp-case-result')
        path=f'{case.id}.json'
        raw=(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8')
        (output/path).write_bytes(raw)
        inventory.append(dict(case_id=case.id,title=case.title,category=case.category,path=path,
                              sha256=hashlib.sha256(raw).hexdigest(),
                              failed=any(r['state']=='failed' for r in result['runs'])))
        print(case.id,', '.join(f"{r['method']}={r['state']}" for r in result['runs']),flush=True)
    index=dict(schema_version='softqp.index/v1',state='development',default_case=inventory[0]['case_id'] if inventory else None,cases=inventory,
               environment=dict(python=platform.python_version(),platform=platform.platform(),
               packages={p:importlib.metadata.version(p) for p in ['numpy','scipy','osqp','softqp']}),
               limitations=['Development bake, not the complete release experiment matrix.',
                            'DAQP and FlexQP comparison cells are not implemented in this bake.',
                            'C12 includes the initial state only; stream and warm-start measurements remain pending.',
                            'No timing superiority or novelty is established.'])
    validate_document(index,'softqp-index')
    (output/'index.json').write_text(json.dumps(index,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    verify_inventory(output,index)
    return index

def verify_inventory(output,index):
    validate_document(index,'softqp-index')
    for row in index['cases']:
        raw=(Path(output)/row['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['sha256']:
            raise ValueError(f"{row['path']}: checksum mismatch")
        doc=validate_document(json.loads(raw),'softqp-case-result')
        if doc['case_id']!=row['case_id']:raise ValueError('case ID mismatch')
