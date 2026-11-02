import type { SoftQPRun } from './softqp';

/** Complete over the versioned method enum, including locally imported L1 variants. */
export const methodNames: Record<SoftQPRun['method'], {en:string;es:string}> = {
  lifted: {en:'Explicit lifting',es:'Holguras explícitas'},
  generalized: {en:'Generalized projection',es:'Proyección generalizada'},
  asymmetric: {en:'Asymmetric projection',es:'Proyección asimétrica'},
  daqp: {en:'DAQP',es:'DAQP'},
  flex: {en:'FlexQP reconstruction',es:'Reconstrucción FlexQP'},
  elastiqp: {en:'ElastiQP',es:'ElastiQP'},
};
