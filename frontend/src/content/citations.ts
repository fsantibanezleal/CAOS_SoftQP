// Primary sources for the implemented optimization methods and operating models.
import type { Citation } from '@fasl-work/caos-app-shell';
export const CITATIONS: Citation[] = [
  { id: 'osqp', label: 'OSQP', citation: 'Stellato et al. OSQP: an operator splitting solver for quadratic programs. Mathematical Programming Computation, 2020.', url: 'https://osqp.org/docs/solver/' },
  { id: 'gsp', label: { en: 'Schwan, Lew and Plancher 2026', es: 'Schwan, Lew y Plancher 2026' }, citation: 'Efficient ADMM for Soft-Constrained Quadratic Programs via Generalized Slack Projections, 2026.', doi: '10.48550/arXiv.2610.35631' },
  { id: 'quadratic', label: 'Lew et al. 2025', citation: 'Solving Quadratic Programs with Slack Variables via ADMM without Increasing the Problem Size.', doi: '10.48550/arXiv.2511.08451' },
  { id: 'daqp', label: 'DAQP', citation: 'Official DAQP soft-constraint formulation and original-scale side-specific weight API.', url: 'https://darnstrom.github.io/daqp/start/advanced/soft' },
  { id: 'flex', label: 'Oshin et al. 2026', citation: 'Deep FlexQP: Accelerated Nonlinear Programming via Deep Unfolding. ICLR 2026.', url: 'https://openreview.net/pdf?id=HL3TvE4Afm' },
  { id: 'elasti', label: 'Morton et al. 2026', citation: 'ElastiQP: An Always-Feasible QP Solver for Constrained Robot Control.', doi: '10.48550/arXiv.2609.19080' },
  { id: 'mpc', label: 'MathWorks MPC formulation', citation: 'QP Optimization Problem for Linear MPC. Official formulation reference.', url: 'https://www.mathworks.com/help/mpc/ug/optimization-problem.html' },
];
