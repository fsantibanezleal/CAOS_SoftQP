"""Authored deterministic cases and a source-faithful building-energy model."""
from dataclasses import dataclass
import numpy as np
from scipy import sparse
from softqp.problem import Problem, Penalty

@dataclass
class Case:
    id: str
    title: dict
    category: dict
    problem: Problem | None
    seed: int = 1729
    reference: tuple | None = None

def penalty(m, asymmetric=False, hard=None):
    soft=np.ones(m,dtype=bool) if hard is None else ~np.asarray(hard,dtype=bool)
    return Penalty(np.full(m,.3),np.full(m,1.2 if asymmetric else .3),
                   np.full(m,2.),np.full(m,4. if asymmetric else 2.),soft)

def scalar(target, lower=-1., upper=1., asymmetric=False):
    return Problem(sparse.eye(1,format='csc'),np.array([-target]),sparse.eye(1,format='csc'),
                   np.array([lower]),np.array([upper]),penalty(1,asymmetric))

def generated(n=32,m=80,semidefinite=False,ill_conditioned=False,seed=1729):
    rng=np.random.default_rng(seed)
    A=sparse.random(m,n,density=.2,format='csc',random_state=rng)
    diagonal=np.geomspace(1.,1e6,n) if ill_conditioned else np.ones(n)
    if semidefinite: diagonal[n//2:]=0.
    return Problem(sparse.diags(diagonal,format='csc'),rng.normal(size=n)*3.,A,
                   np.full(m,-.4),np.full(m,.6),penalty(m,True))

def mpc(conflict=False,asymmetric=False,initial_position=1.2):
    # Condensed double integrator: state dynamics hold identically, controls stay hard.
    horizon=20;dt=.2
    F=np.array([[1.,dt],[0.,1.]]);B=np.array([.5*dt**2,dt])
    x0=np.array([initial_position,0.])
    G=np.zeros((2*horizon,horizon));offset=np.zeros(2*horizon)
    for k in range(horizon):
        offset[2*k:2*k+2]=np.linalg.matrix_power(F,k+1)@x0
        for j in range(k+1):G[2*k:2*k+2,j]=np.linalg.matrix_power(F,k-j)@B
    W=np.tile([3.,.3],horizon)
    P=G.T@(W[:,None]*G)+.1*np.eye(horizon)
    q=G.T@(W*offset)
    limit=.4 if conflict else 2.
    A=sparse.vstack([sparse.eye(horizon),sparse.csc_matrix(G)],format='csc')
    lower=np.r_[np.full(horizon,-1.),np.tile([-limit,-1.5],horizon)-offset]
    upper=np.r_[np.full(horizon,1.),np.tile([limit,1.5],horizon)-offset]
    return Problem(sparse.csc_matrix(P),q,A,lower,upper,
                   penalty(3*horizon,asymmetric,np.r_[np.ones(horizon,bool),np.zeros(2*horizon,bool)]))

def cases():
    defs=[('C01','Lower-bound undershoot','Incumplimiento inferior','Semantics','Semántica',scalar(-3.)),
          ('C02','Upper-bound overshoot','Incumplimiento superior','Semantics','Semántica',scalar(3.)),
          ('C03','Competing side costs','Costos por lado en conflicto','Semantics','Semántica',scalar(3.,asymmetric=True))]
    mixed=Problem(sparse.eye(2,format='csc'),np.array([-3.,2.]),sparse.csc_matrix([[1.,0.],[0.,1.],[1.,1.]]),
                  np.array([-1.,-1.,0.]),np.array([1.,1.,0.]),penalty(3,True,[False,False,True]))
    defs.append(('C04','Mixed hard and soft rows','Filas duras y blandas','Integrity','Integridad',mixed))
    # The grouped case uses the authors' exact native/reference lift implementation.
    from softqp.reference import Penalty as ReferencePenalty, NORMINF
    grouped=ReferencePenalty.hard(2).soften(np.arange(2),NORMINF,alpha1=1.,group=0)
    grouped_tuple=(sparse.eye(2,format='csc'),np.array([-3.,2.]),sparse.eye(2,format='csc'),
                   np.full(2,-.5),np.full(2,.5),grouped)
    output=[Case(i,dict(en=en,es=es),dict(en=ce,es=cs),p) for i,en,es,ce,cs,p in defs]
    output.append(Case('C05',dict(en='Grouped peak violation',es='Incumplimiento máximo agrupado'),dict(en='Semantics',es='Semántica'),None,reference=grouped_tuple))
    for i,en,es,p in [('C06','Sparse scaling instance','Instancia dispersa',generated()),
                       ('C07','Semidefinite Hessian','Hessiana semidefinida',generated(16,40,semidefinite=True)),
                       ('C08','Ill-conditioned Hessian','Hessiana mal condicionada',generated(16,40,ill_conditioned=True)),
                       ('C09','Feasible double-integrator MPC','MPC factible de doble integrador',mpc()),
                       ('C10','Disturbed state constraints','Restricciones de estado perturbadas',mpc(True)),
                       ('C12','Parameter-stream initial state','Estado inicial de flujo paramétrico',mpc(True,True,1.6))]:
        cat=dict(en='Numerical structure',es='Estructura numérica') if i in ('C06','C07','C08') else dict(en='Repeated control',es='Control repetido')
        output.append(Case(i,dict(en=en,es=es),cat,p))
    conflict=Problem(sparse.eye(1,format='csc'),np.array([0.]),sparse.csc_matrix([[1.],[1.]]),
                     np.array([1.,-np.inf]),np.array([np.inf,-1.]),penalty(2,True))
    output.append(Case('C11',dict(en='Conflicting safety boundaries',es='Fronteras de seguridad en conflicto'),dict(en='Control conflict',es='Conflicto de control'),conflict))
    from .energy_reference import problem as energy_problem
    energy=energy_problem()
    output.append(Case('C13',dict(en='Published building-energy model',es='Modelo energético publicado'),dict(en='Energy',es='Energía'),None,reference=energy))
    P,q,A,l,u,reference=energy
    from softqp.reference import NONE,L1L2
    soft=reference.type!=NONE
    # Authored variants deliberately replace the mixed/grouped penalties with separable elastic costs.
    a=np.where(reference.type==L1L2,reference.alpha1,.2)
    d=np.where(reference.type==L1L2,reference.alpha2,.4)
    for i,factor,en,es in [('C14',3.,'Side-specific energy trade-offs','Compromisos energéticos por lado'),
                           ('C15',1.5,'Mixed elastic side costs','Costos elásticos mixtos por lado')]:
        p=Problem(P,q,A,l,u,Penalty(a,a*factor,d,d*factor,soft))
        output.append(Case(i,dict(en=en,es=es),dict(en='Energy',es='Energía'),p))
    return sorted(output,key=lambda c:c.id)
