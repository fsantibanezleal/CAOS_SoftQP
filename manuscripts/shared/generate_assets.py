"""Generate vector figures and literal evidence tables; never run a solver or bootstrap."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SLUGS = ['soft-constraint-study', 'coupled-peak-study']
SOURCE = '2d3f299d80edad49c2599e61bb6e3c875c119043'
INPUTS = {}
def read_blob(name):
    path = ROOT / name
    raw = path.read_bytes()
    canonical = subprocess.check_output(['git', 'show', SOURCE + ':' + name], cwd=ROOT)
    if raw != canonical and raw.replace(b'\r\n', b'\n') != canonical.replace(b'\r\n', b'\n'):
        raise ValueError('Frozen evidence differs: ' + name)
    # Git text normalization is not a scientific data change. Read the immutable
    # Git blob and record its digest rather than silently hashing checkout CRLF.
    INPUTS[name] = hashlib.sha256(canonical).hexdigest()
    return canonical

def read(name):
    return json.loads(read_blob(name))

def tex(value):
    return str(value).translate(str.maketrans({'\\':r'\textbackslash{}','_':r'\_','&':r'\&','%':r'\%','#':r'\#',
                                             '$':r'\$','^':r'\textasciicircum{}','~':r'\textasciitilde{}',
                                             '{':r'\{','}':r'\}'}))

def cell(value):
    result=tex(value).replace(r'\_',r'\_\allowbreak{}').replace('.',r'.\allowbreak{}').replace('/',r'/\allowbreak{}')
    result=result.replace('|',r'\textbar{}\allowbreak{}').replace('=',r'=\allowbreak{}')
    import re
    result=re.sub(r'(?<=[A-Za-z])-(?=[A-Za-z])',lambda m:r'-\allowbreak{}',result)
    result=re.sub(r'(?<![A-Za-z0-9])([0-9a-f]{32,})(?![A-Za-z0-9])',lambda m:r'\allowbreak{}'.join(m.group()[i:i+8] for i in range(0,len(m.group()),8)),result)
    return result

def literal_schema_line(line):
    return line + (' % voice-ok: literal schema identifier or archived schema value, not manuscript narrative' if 'campaign' in line.lower() else '')

def number(value):
    return 'N/A' if value is None else f'{value:.6g}'

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,
                     'axes.spines.right':False,'pdf.fonttype':42,'savefig.bbox':'tight'})
COLORS=['#182c45','#507998','#9b6232','#5a7260','#795e80','#6a6a6a']
for slug in SLUGS:
    for folder in ['figures', 'generated']:
        (ROOT/'manuscripts'/slug/folder).mkdir(parents=True,exist_ok=True)

cases=[read(f'data/derived/softqp/C{i:02d}.json') for i in range(1,16)]
campaign=read('data/derived/experiments/campaign.json')
stream=read('data/derived/experiments/stream.json')
summary=read('manuscripts/coupled-peak-study/results/summary/summary.json')
lesson=read('docs/contracts/examples/softqp-coupled-lesson.json')
catalog=[]
for line in read_blob('docs/contracts/catalog.md').decode('utf-8').splitlines():
    cells=[v.strip().strip('`') for v in line.strip().strip('|').split('|')]
    if len(cells)==13 and cells[3].startswith('docs/contracts/'):catalog.append(cells)
assert len(catalog)==18
SCHEMAS={cells[0]:read(cells[3]) for cells in catalog}
read_blob('docs/architecture/01_overview.md')
CASE_SOURCES=[f'data/derived/softqp/C{i:02d}.json' for i in range(1,16)]
primary=summary['primary']
assert primary['established'] is False and primary['denominator']==144 and primary['failed_pairs']==9
assert campaign['primary_endpoint']['state']=='not-established' and campaign['completed_instances']==456
assert campaign['primary_endpoint']['paired_samples']==168

FIGURES=[]
def save(fig, name, caption, sources, label=None):
    path=ROOT/'manuscripts/soft-constraint-study/figures'/f'{name}.pdf'
    fig.tight_layout()
    fig.savefig(path,metadata={'Title':caption,'Author':'Felipe Santibáñez-Leal','CreationDate':None,'ModDate':None})
    plt.close(fig)
    FIGURES.append({'file':f'figures/{name}.pdf','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'caption':caption,'label':label or 'fig:'+name,'sources':sources})

fig,ax=plt.subplots(figsize=(6.5,2.3));ax.axis('off')
boxes=[(.02,.42,'Original model\nP,q,A,bounds\nphysical row units'),(.28,.42,'Native methods\noriginal/lifted\nlocal execution'),(.54,.42,'Independent checks\nobjective, hard rows\nprimal-dual metrics'),(.80,.42,'Versioned export\nverified static reader\nno hosted solving')]
for x,y,text in boxes:
    ax.text(x+.08,y,text,ha='center',va='center',bbox={'boxstyle':'round,pad=.5','fc':'#f3f3f3','ec':'#303030'},transform=ax.transAxes,fontsize=8)
for x in [.20,.46,.72]: ax.annotate('',xy=(x+.05,.42),xytext=(x,.42),xycoords='axes fraction',arrowprops={'arrowstyle':'->','color':'black'})
save(fig,'architecture','Implemented data flow from original physical model through native solving and independent acceptance to a versioned static reader. This is an architecture diagram, not a measured speed or reliability result.',['docs/contracts/catalog.md','docs/architecture/01_overview.md'])

d=cases[0]['problem'];x=np.linspace(-3,2,241);p=d['P']['data'][0];q=d['q'][0];lo=d['lower'][0];up=d['upper'][0];pen=d['penalty']
lower=np.maximum(lo-x,0);upper=np.maximum(x-up,0)
cost=.5*p*x*x+q*x+pen['lower_linear'][0]*lower+pen['upper_linear'][0]*upper+.5*pen['lower_quadratic'][0]*lower**2+.5*pen['upper_quadratic'][0]*upper**2
fig,ax=plt.subplots(figsize=(6,3));ax.plot(x,cost,color=COLORS[0]);ax.axvspan(lo,up,color='.92');ax.set(xlabel='Original scalar decision (normalized unit)',ylabel='Original objective (normalized cost)')
for run in cases[0]['runs']:
    if run['state']=='available': ax.plot(run['result']['x'][0],run['result']['metrics']['objective'],'o',mfc='none',label=run['method'])
ax.legend(ncol=2,fontsize=7)
save(fig,'scalar-objective','Analytic evaluation of the stored C01 objective and actual exported method optima. The shaded interval is the preferred band, and the curve is a mathematical illustration rather than a new timed observation.',['data/derived/softqp/C01.json'])

methods=['lifted','generalized','asymmetric','daqp'];dims=[];states=[]
for case in cases:
    runs={r['method']:r for r in case['runs']};dims.append([runs[m]['result']['dimensions']['variables'] if m in runs and runs[m]['state']=='available' else np.nan for m in methods]);states.append([1 if m in runs and runs[m]['state']=='available' else 0 for m in methods])
fig,ax=plt.subplots(figsize=(6.5,3));z=np.arange(15)
for j,m in enumerate(methods): ax.plot(z,np.array(dims)[:,j],marker=['o','s','^','x'][j],label=m,color=COLORS[j],lw=1)
ax.set(xticks=z,xticklabels=[c['case_id'] for c in cases],ylabel='Exported formulation variables (count)');ax.tick_params(axis='x',rotation=45);ax.set_yscale('log');ax.legend(ncol=2,fontsize=7)
save(fig,'formulation-size','Exported variable counts for all fifteen stored catalog cases and four catalog paths. Missing points denote unsupported objectives; the counts describe formulation size and do not measure factorization fill or computational advantage.',CASE_SOURCES)

fig,ax=plt.subplots(figsize=(6,3));ax.pcolormesh(np.arange(16)-.5,np.arange(5)-.5,np.array(states).T,cmap='Greys',vmin=0,vmax=1,rasterized=False);ax.invert_yaxis();ax.set(xticks=range(15),xticklabels=[c['case_id'] for c in cases],yticks=range(4),yticklabels=methods);ax.tick_params(axis='x',rotation=45)
for i,row in enumerate(states):
    for j,value in enumerate(row): ax.text(i,j,'A' if value else 'I',ha='center',va='center',color='white' if value else 'black',fontsize=7)
save(fig,'compatibility','Full catalog method-case compatibility: A denotes an available exported solution and I an incompatible requested objective. This four-path catalog is distinct from the six-path original timing study and the separate grouped study.',CASE_SOURCES)

fig,ax=plt.subplots(figsize=(6,2.2));ep=campaign['primary_endpoint'];estimate=100*ep['median_relative_reduction'];ci=np.array(ep['confidence_interval_95'])*100
ax.errorbar(estimate,0,xerr=[[estimate-ci[0]],[ci[1]-estimate]],fmt='o',color=COLORS[0],capsize=5);ax.axvline(0,color='.5',lw=.8);ax.axvline(10,color='.4',ls='--');ax.set(yticks=[0],yticklabels=['168 paired observations'],xlabel='Median relative cold end-to-end reduction (%)',ylim=(-.5,.5));
save(fig,'original-effect','Original held-out timing estimate with its stored 95 percent seed-cluster confidence interval and registered ten percent reference. The interval crosses zero; neither interval nor population is recomputed for this figure.',['data/derived/experiments/campaign.json'])

fig,ax=plt.subplots(figsize=(6,3.1))
for j,m in enumerate(['lifted','asymmetric','daqp']):
    rows=sorted([r for r in campaign['cells'] if r['split']=='heldout' and r['family']=='asymmetric-elastic' and r['density']==.05 and r['condition']==1 and r['method']==m and r['median_seconds'] is not None],key=lambda r:r['n'])
    if rows:
        ns=[r['n'] for r in rows];mid=np.array([r['median_seconds'] for r in rows])*1000;low=np.array([r['quantile_25_seconds'] for r in rows])*1000;high=np.array([r['quantile_75_seconds'] for r in rows])*1000
        ax.plot(ns,mid,'o-',label=m,color=COLORS[j]);ax.fill_between(ns,low,high,color=COLORS[j],alpha=.12)
ax.set(xlabel='Original decision dimension (count)',ylabel='Cold complete-operation time (ms)');ax.legend(fontsize=8)
save(fig,'cold-times','Stored held-out asymmetric-elastic timing cells at density 0.05 and unit diagonal condition. Lines are stored medians and bands stored interquartile ranges; this descriptive subset does not replace the complete primary endpoint.',['data/derived/experiments/campaign.json'])

fig,ax=plt.subplots(figsize=(6,3))
for j,m in enumerate(['lifted','generalized','asymmetric','daqp','flex','elastiqp']):
    rows=[r for r in campaign['cells'] if r['split']=='robustness' and r['method']==m and r.get('max_normalized_gap') is not None]
    groups={r['condition'] for r in rows}
    if groups: ax.plot(sorted(groups),[max(r['max_normalized_gap'] for r in rows if r['condition']==c) for c in sorted(groups)],'o-',label=m,color=COLORS[j],lw=1)
ax.set_xscale('log');ax.set_yscale('symlog',linthresh=1e-12);ax.set(xlabel='Stored diagonal Hessian condition (dimensionless)',ylabel='Maximum normalized objective discrepancy');ax.axhline(1e-6,color='black',ls='--',lw=.8);ax.legend(ncol=3,fontsize=7)
save(fig,'conditioning','Maximum stored objective discrepancy in each compatible robustness cell by diagonal condition. The dashed line is the original external objective criterion; absent methods remain absent rather than receiving an invented zero discrepancy.',['data/derived/experiments/campaign.json'])

frames=stream['frames'];time=np.array([f['time_seconds'] for f in frames]);state=np.array([f['state'] for f in frames])
fig,axes=plt.subplots(3,1,figsize=(6,5),sharex=True)
axes[0].plot(time,state[:,0],color=COLORS[0]);axes[0].set_ylabel('Position (m)')
axes[1].plot(time,state[:,1],color=COLORS[1]);axes[1].set_ylabel('Velocity (m/s)')
dt=float(time[1]-time[0]);assert np.allclose(np.diff(time),dt) and dt>0
axes[2].stairs([f['applied_control'] for f in frames],np.r_[time,time[-1]+dt],color=COLORS[2]);axes[2].axhline(1,color='.4',ls='--');axes[2].axhline(-1,color='.4',ls='--');axes[2].set(ylabel='Held acceleration (m/s²)',xlabel='Physical model time (s)')
save(fig,'control-stream','The stored common C12 plant trajectory and interval-held oracle acceleration across thirty-two frames. Steps retain each complete physical sampling interval; these curves are not separate closed-loop controller performance measurements.',['data/derived/experiments/stream.json'])

fig,ax=plt.subplots(figsize=(6,3));values=[];labels=[]
for m in ['lifted','asymmetric','daqp']:
    for mode in ['cold','warm']:
        v=[1000*r['elapsed_seconds'] for f in frames for r in f['runs'] if r['method']==m and r['mode']==mode and r['state']=='accepted'];values.append(v);labels.append(m+'\n'+mode)
ax.boxplot(values,tick_labels=labels,showfliers=True);ax.set(ylabel='Per-frame reported operation time (ms)');ax.tick_params(axis='x',labelsize=7)
save(fig,'stream-reuse','Stored cold and warm C12 operation durations for every accepted frame of each compatible method. The box summaries are descriptive paired-path evidence, not a randomized causal isolation of warm starting from all other implementation choices.',['data/derived/experiments/stream.json'])

pairs=primary['pairs'];failed=np.array([bool(p['failure_reasons']) for p in pairs]);reductions=np.array([p['reduction']*100 for p in pairs]);fig,axes=plt.subplots(2,1,figsize=(6,4.7),sharex=True)
axes[0].plot(np.arange(144),reductions,color=COLORS[0],lw=.7);axes[0].scatter(np.arange(144)[failed],reductions[failed],marker='x',color='black',label='Prespecified failed-pair score');axes[0].axhline(0,color='.5',lw=.8);axes[0].set_ylabel('Paired reduction (%)');axes[0].legend(fontsize=7)
for method,label,color in [('native','native',COLORS[0]),('selected','selected compatible baseline',COLORS[2])]:
    y=[p['median_seconds'].get('native') if method=='native' else p['median_seconds'].get(p['fastest_baseline']) if p['fastest_baseline'] else None for p in pairs]
    axes[1].plot(range(144),[np.nan if x is None else x for x in y],'.',label=label,color=color,ms=3)
axes[1].set(xlabel='Stored held-out instance order (index)',ylabel='Complete 32-update median (s)');axes[1].legend(fontsize=7)
save(fig,'coupled-population','All 144 stored grouped-study primary members in original order, with nine failed scores retained. Complete-operation medians preserve missing values as gaps and do not impute a comparator where the primary rule selected none.',['manuscripts/coupled-peak-study/results/summary/summary.json'])

fig,ax=plt.subplots(figsize=(6,3));splits=list(summary['counts']);states_order=['accepted','accuracy-rejected','incompatible','oracle-failed','timeout'];bottom=np.zeros(3)
for j,state_name in enumerate(states_order):
    values=np.array([summary['counts'][s].get(state_name,0) for s in splits]);ax.bar(splits,values,bottom=bottom,label=state_name,color=COLORS[j],edgecolor='white',hatch=['','//','xx','..','++'][j]);bottom+=values
ax.set(ylabel='Measured method observations (count)');ax.legend(ncol=3,fontsize=7,loc='lower center',bbox_to_anchor=(.5,1.02))
save(fig,'coupled-states','All 5670 measured method observations of the grouped study, separated by their original development, held-out and robustness splits. Acceptance, accuracy rejection, incompatibility, dependent oracle failure and supervised timeout remain different categories.',['manuscripts/coupled-peak-study/results/summary/summary.json'])

fig,ax=plt.subplots(figsize=(6,3));methods=sorted({m for p in pairs for m in p['median_seconds']});values=[];labels=[]
for m in methods:
    v=[p['median_seconds'][m] for p in pairs if m in p['median_seconds']];values.append(v);labels.append(m+'\n(n='+str(len(v))+')')
ax.boxplot(values,tick_labels=labels,showfliers=True);ax.set(ylabel='Stored complete-operation median (s)');ax.tick_params(axis='x',rotation=30,labelsize=6)
save(fig,'coupled-formulations','Distributions of stored held-out per-instance medians for each returned compatible formulation. Sample counts differ because compatibility and failures differ; these unmatched descriptive distributions are not the registered paired comparison or a causal ablation.',['manuscripts/coupled-peak-study/results/summary/summary.json'])

fig,axes=plt.subplots(1,2,figsize=(6,3));rr=[r for r in lesson['records'] if r['state']=='accepted'];axes[0].bar([r['method'] for r in rr],[r['objective'] for r in rr],color=COLORS[:len(rr)]);axes[0].set_ylabel('Original objective (normalized cost)');axes[0].tick_params(axis='x',rotation=25,labelsize=7)
for j,r in enumerate(rr): axes[1].plot([0,1],r['x'],'o-',label=r['method'],color=COLORS[j])
axes[1].set(xticks=[0,1],xticklabels=['x₁','x₂'],ylabel='Physical decision (m)');axes[1].legend(fontsize=7)
save(fig,'directional-lesson','Stored native, epigraph and directional row-split answers for the same two-variable physical teaching input. Objective and decision agreement are a small numerical illustration, not additional timing evidence or an independent experiment.',['docs/contracts/examples/softqp-coupled-lesson.json'])

for slug in SLUGS:
    folder=ROOT/'manuscripts'/slug
    for row in FIGURES:
        src=ROOT/'manuscripts/soft-constraint-study'/row['file'];dst=folder/row['file']
        if src!=dst: shutil.copyfile(src,dst)
        float_tex='\\begin{figure}[htbp]\\centering\n\\includegraphics[width=.94\\textwidth]{'+row['file']+'}\n\\caption{'+row['caption']+'}\\label{'+row['label']+'}\n\\end{figure}\n'
        (folder/'generated'/('figure-'+Path(row['file']).stem+'.tex')).write_text(float_tex,encoding='utf-8',newline='\n')
    old=campaign['primary_endpoint']
    macros={'OriginalEstimate':100*old['median_relative_reduction'],'OriginalLower':100*old['confidence_interval_95'][0],
            'OriginalUpper':100*old['confidence_interval_95'][1],'OriginalPairs':old['paired_samples']}
    lines=['% Exact exported original-study summary; no inferential recomputation.']
    for name,value in macros.items(): lines.append('\\newcommand{\\'+name+'}{'+(str(value) if name=='OriginalPairs' else f'{value:.6f}')+'}')
    (folder/'original-results.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    used=FIGURES if slug=='soft-constraint-study' else [f for f in FIGURES if Path(f['file']).stem in {'scalar-objective','original-effect','cold-times','conditioning','stream-reuse','coupled-population','coupled-states','coupled-formulations','directional-lesson'}]
    manifest={'source_commit':SOURCE,'source_inputs':INPUTS,'figures':used,'no_new_solver_or_bootstrap':True}
    (folder/'generated/asset-manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')

report=ROOT/'manuscripts/soft-constraint-study/generated'
def table(path,caption,label,columns,rows,widths=None):
    spec=widths or ('l'*len(columns))
    spec=spec.replace('X',r'>{\raggedright\arraybackslash}X')
    if path.startswith('contract-') and len(rows)>14:
        fixed=r'>{\raggedright\arraybackslash}p{.22\textwidth}>{\raggedright\arraybackslash}p{.12\textwidth}>{\raggedright\arraybackslash}p{.32\textwidth}>{\raggedright\arraybackslash}p{.25\textwidth}'
        lines=['\\begingroup\\footnotesize','\\begin{longtable}{@{}'+fixed+'@{}}',
               '\\caption{'+caption+'}\\label{'+label+'}\\\\',
               '\\toprule '+' & '.join(columns)+r'\\\midrule\endfirsthead',
               '\\toprule '+' & '.join(columns)+r'\\\midrule\endhead',
               r'\bottomrule\endfoot']
        lines += [' & '.join(map(cell,row))+r'\\' for row in rows]
        lines += [r'\end{longtable}\endgroup']
        (report/path).write_text('\n'.join(literal_schema_line(line) for line in lines)+'\n',encoding='utf-8',newline='\n')
        return
    lines=['\\begin{table}[htbp]\\centering\\footnotesize','\\caption{'+caption+'}\\label{'+label+'}',
           '\\begin{tabularx}{\\textwidth}{@{}'+spec+'@{}}\\toprule',' & '.join(columns)+r'\\\midrule']
    lines += [' & '.join(map(cell,row))+r'\\' for row in rows]
    lines += ['\\bottomrule\\end{tabularx}','\\end{table}']
    (report/path).write_text('\n'.join(literal_schema_line(line) for line in lines)+'\n',encoding='utf-8',newline='\n')

for part,subset in enumerate([cases[:8],cases[8:]],1):
    rows=[]
    for c in subset:
        for run in c['runs']:
            rr=run.get('result');mm=rr['metrics'] if rr else {}
            rows.append([c['case_id'],run['method'],run['state'],number(mm.get('objective')),number(mm.get('hard_violation')),number(mm.get('objective_gap_against_lifted'))])
    table(f'catalog-results-{part}.tex','Complete stored catalog outcomes for the indicated cases and every catalog method. N/A means no compatible returned objective, and hard error is evaluated in original row coordinates.','tab:catalog-'+str(part),['Case','Method','State','Objective','Hard error','Gap'],rows,'llXrrr')

table('study-results.tex','Distinct primary populations, stored effect estimates and uncertainty for the two completed timing studies. Failed-pair rules are not transferred between experiments and neither registered ten percent improvement criterion is established.','tab:main-results',['Study','Population','Pairs','Effect (\\%)','95\\% limits'],[
    ['Separable',456,168,number(100*campaign['primary_endpoint']['median_relative_reduction']),', '.join(number(100*x) for x in campaign['primary_endpoint']['confidence_interval_95'])],
    ['Grouped',210,144,number(100*primary['estimate']),', '.join(number(100*x) for x in primary['confidence_interval'])]],'Xrrrr')

table('coupled-states.tex','Measured grouped-study method states by split, including dependent oracle failures and supervised timeouts. Counts cover all measured method rows, while warm-up and oracle observations remain in the larger raw archive.','tab:coupled-states',['Split','Accepted','Accuracy','Incompat.','Oracle','Timeout'],[[s,*[summary['counts'][s].get(t,0) for t in states_order]] for s in splits],'Xrrrrr')

def collect(node,root,seen=None):
    seen=set() if seen is None else seen
    if '$ref' in node and node['$ref'].startswith('#/'):
        key=node['$ref']
        if key in seen:return {}
        seen.add(key);target=root
        for p in key[2:].split('/'):target=target[p]
        return collect(target,root,seen)
    return node

def units(field,node=None):
    import re
    indexed=field
    field=re.sub(r' \((?:(?:anyOf|oneOf|allOf)\d+|if|then|else|not|contains)\)', '', field)
    field=re.sub(r'\[\d*\]', '', field)
    last=field.rsplit('.',1)[-1]
    if '.seeds.' in field:return 'integer random seed'
    if '.velocity_impulses.' in field:return 'm/s; key is frame index'
    if last=='initial_state':return 'm' if indexed.endswith('[0]') else 'm/s' if indexed.endswith('[1]') else 'components: m and m/s'
    if last in {'hard_row_error_limit'}:return 'original row unit; synthetic coordinates'
    if last in {'normalized_objective_gap_limit','asymmetric_upper_factor_range','hard_row_fraction_elastic','hard_row_fraction_l1','hessian_condition','m_per_n','minimum_reduction'}:return 'dimensionless'
    if last=='q_standard_deviation':return 'cost / decision unit'
    if last=='row_norm':return 'row / decision unit; generator coordinates'
    if last=='linear_cost_range':return 'cost / row unit'
    if last=='quadratic_cost_range':return 'cost / row unit squared'
    if last.endswith('_seconds') or last=='time_seconds':return 's'
    if last.endswith('_bytes') or last in {'bytes','peak_worker_rss','worker_peak_rss_bytes'}:return 'bytes'
    if last in {'lower_multiplier','upper_multiplier','quadratic_multiplier','row_scale'}:return 'dimensionless factor'
    if last in {'lower','upper'}:return 'original row unit'
    if last in {'lower_linear','upper_linear'}:return 'cost / row unit'
    if last in {'lower_quadratic','upper_quadratic'}:return 'cost / row unit squared'
    if last in {'objective','objectives','base_objective','penalty_objective','oracle_objective','oracle_objectives','oracle_horizon_cost','objective_constant','objective_gap_against_lifted'}:return 'model cost unit'
    if last in {'normalized_gap','max_normalized_gap','objective_gap','reduction','density','condition','confidence_interval','confidence_interval_95','estimate','median_relative_reduction','eps_rel','stationarity','dual_domain','dual_repair','fenchel','aggregate_fenchel','kkt_max'}:return 'dimensionless normalized diagnostic / factor'
    if last=='eps_abs':return 'solver coordinate tolerance; model scaling applies'
    if last=='stationarity_residual':return 'cost / decision unit; raw gradient norm'
    if last in {'x','q'}:return 'decision unit' if last=='x' else 'cost / decision unit'
    if last=='y':return 'cost / original row unit'
    if last in {'hard_violation','max_hard_violation','lower_violation','upper_violation','slack','total_lower_violation','total_upper_violation'}:return 'original row units; see unit map'
    if last=='data' and '.P.' in '.'+field:return 'cost / decision units squared'
    if last=='data' and '.A.' in '.'+field:return 'row / decision unit'
    if field=='input.upper_scale':return 'dimensionless policy multiplier'
    if last in {'lower_scale','upper_scale'}:return 'peak unit / row unit; model map'
    if last in {'peak','peaks'}:return 'group peak unit; model map'
    if last=='linear':return 'cost / peak unit'
    if last=='quadratic':return 'cost / peak unit squared'
    if last in {'state','next_state'} and (indexed.endswith('state[]') or (node or {}).get('type')=='array'):return 'C12 components: m and m/s'
    if last in {'applied_control','oracle_control'}:return 'm/s squared'
    if last=='velocity_impulse':return 'm/s'
    if '.counts.' in '.'+field or last in {'n','m','n_cases','seed','repetition','frame','frames','iterations','variables','rows','nnz','indptr','indices','shape','horizon','zones','group_size','planned_instances','completed_instances','worker_restarts','paired_samples','rejected_pairs','seed_clusters','denominator','failed_pairs','max_iter','adaptive_rho_interval','status_code','blas_threads','parallel_workers','n_minimum','bootstrap_seed_clusters','measured','warmup_per_backend'}:return 'count / integer identifier'
    return 'structural metadata / nested units'

def node_type(node):
    if 'type' in node:
        kind=node['type']
        return ' / '.join(kind) if isinstance(kind,list) else kind
    if 'const' in node:
        value=node['const']
        return 'null' if value is None else 'boolean' if isinstance(value,bool) else 'integer' if isinstance(value,int) else 'number' if isinstance(value,float) else 'string' if isinstance(value,str) else 'object'
    if any(k in node for k in ['oneOf','anyOf','allOf']):return 'union / composition'
    if 'enum' in node:return 'enumerated value'
    return 'object'

def restrictions(body):
    keys=['const','enum','minimum','exclusiveMinimum','maximum','exclusiveMaximum','minItems','maxItems','pattern','minLength','maxLength','additionalProperties','required','uniqueItems','multipleOf','minProperties','maxProperties','dependentRequired','minContains','maxContains']
    return '; '.join(key+'='+str(body[key]) for key in keys if key in body) or 'See defined object / value type'

def flattened(node,root,prefix='',stack=()):
    if isinstance(node,bool):return [(prefix,'boolean schema','admitted' if node else 'forbidden', 'structural predicate')]
    if not isinstance(node,dict):return []
    if '$ref' in node:
        ref=node['$ref'];assert ref.startswith('#/'),ref
        if ref in stack:return [(prefix,'recursive reference',ref,units(prefix))]
        target=root
        for segment in ref[2:].split('/'):target=target[segment]
        return flattened(target,root,prefix,(*stack,ref))
    rows=[]
    if prefix:rows.append((prefix,node_type(node),restrictions(node),units(prefix,node)))
    for key,value in node.get('properties',{}).items():rows+=flattened(value,root,(prefix+'.' if prefix else '')+key,stack)
    if isinstance(node.get('items'),dict):rows+=flattened(node['items'],root,prefix+'[]',stack)
    for index,value in enumerate(node.get('prefixItems',[])):rows+=flattened(value,root,prefix+'['+str(index)+']',stack)
    for op in ['oneOf','anyOf','allOf']:
        for index,value in enumerate(node.get(op,[])):rows+=flattened(value,root,prefix+' ('+op+str(index+1)+')',stack)
    for op in ['if','then','else','not','contains']:
        if op in node:rows+=flattened(node[op],root,prefix+' ('+op+')',stack)
    return rows

for cells in catalog:
    name,version,owner,path=cells[:4];schema=SCHEMAS[name]
    node=schema
    if name=='api':node=schema['components']['schemas']['UnavailableBody']
    if node.get('type')=='array':node=collect(node.get('items',{}),schema)
    props=node.get('properties',{});rows=[]
    for field,body in props.items():
        body=collect(body,schema);kind=node_type(body)
        if isinstance(kind,list):kind=' / '.join(kind)
        summary_body={key:value for key,value in body.items() if key!='required'}
        rows.append([field,str(kind),restrictions(summary_body),units(field,body)])
    table('contract-'+name+'.tex','Schema-derived top-level fields, dimensions and literal structural restrictions for '+name+' schema '+version+'. Complete nested numerical definitions are expanded in the contract appendix; physical maps remain those of the original model.','tab:contract-'+name,['Field','Type','Constraint','Unit / role'],rows,r'>{\raggedright\arraybackslash}p{.22\textwidth}>{\raggedright\arraybackslash}p{.12\textwidth}XX')
    flat=flattened(node,schema)
    lines=['\\begingroup\\footnotesize\\setlength{\\tabcolsep}{3pt}',
           '\\begin{longtable}{@{}>{\\raggedright\\arraybackslash}p{.25\\textwidth}>{\\raggedright\\arraybackslash}p{.11\\textwidth}>{\\raggedright\\arraybackslash}p{.37\\textwidth}>{\\raggedright\\arraybackslash}p{.20\\textwidth}@{}}',
           '\\caption{Complete nested fields, value types, literal schema restrictions and physical or structural dimensions for '+tex(name)+'. Required and optional structures retain the original schema and model interpretation.}\\label{tab:nested-'+name+'}\\\\',
           '\\toprule Field path & Type & Restrictions & Unit / role\\\\\\midrule\\endfirsthead',
           '\\toprule Field path & Type & Restrictions & Unit / role\\\\\\midrule\\endhead',
           '\\bottomrule\\endfoot']
    for row in flat:lines.append(' & '.join(cell(value) for value in row)+r'\\')
    lines+=['\\end{longtable}\\endgroup']
    (report/('nested-'+name+'.tex')).write_text('\n'.join(literal_schema_line(line) for line in lines)+'\n',encoding='utf-8',newline='\n')
    catalog_entry={'id':name,'version':version,'schema':path,'schema_sha256':INPUTS[path],'producer':owner,'fields':list(props),'consumer_test':cells[7],'missing':cells[8],'nested_fields':flat}
    (report/('contract-'+name+'.json')).write_text(json.dumps(catalog_entry,indent=2)+'\n',encoding='utf-8')
for name in ['study-results.tex','coupled-states.tex']:
    shutil.copyfile(report/name,ROOT/'manuscripts/coupled-peak-study/generated'/name)
(ROOT/'manuscripts/shared/evidence-inputs.json').write_text(json.dumps({'frozen_source':SOURCE,'inputs':INPUTS},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'DERIVED_ASSETS_ONLY','figures_per_document':len(FIGURES),'contracts':len(catalog),'cases':len(cases),'source_files':len(INPUTS)}))
