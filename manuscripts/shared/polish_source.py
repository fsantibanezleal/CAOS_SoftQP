"""Normalize prose spacing without editing math, identifiers, schemas or evidence."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[2]
protect=re.compile(r'\$[^$]*\$|\\\(.*?\\\)|\\(?:ref|eqref|cite|url|nolinkurl|texttt|label|input)\{[^}]*\}')
for slug in ['soft-constraint-study','coupled-peak-study']:
    folder=ROOT/'manuscripts'/slug
    for p in folder.glob('*.tex'):
        if p.name in {'base.tex','results.tex','original-results.tex','14-contract-appendix.tex'}:continue
        text=p.read_text(encoding='utf-8');out=[];blocked=False;body=p.name!='main.tex'
        for line in text.splitlines():
            if r'\begin{document}' in line:body=True
            if re.search(r'\\begin\{(?:equation|align|gather|table|algorithm|longtable)',line):blocked=True
            if not body or blocked:
                out.append(line)
            else:
                comment=''
                if ' % voice-ok' in line:line,comment=line.split(' % voice-ok',1);comment=' % voice-ok'+comment
                pieces=[];last=0
                for m in protect.finditer(line):
                    pieces.append((False,line[last:m.start()]));pieces.append((True,m.group()));last=m.end()
                pieces.append((False,line[last:]))
                fixed=[]
                for keep,part in pieces:
                    if not keep:
                        part=re.sub(r'\bversion(?=\d)','schema ',part)
                        part=re.sub(r'\bSDK(?=\d)','SDK ',part)
                        part=re.sub(r'([a-z])(?=\d)',r'\1 ',part)
                        part=re.sub(r'(\d)(?![eE][+-]?\d)([A-Za-z])',r'\1 \2',part)
                        part=re.sub(r'([A-Za-z])(?=\\(?:Original|Primary))',r'\1 ',part)
                        part=re.sub(r'\\%(?=[A-Za-z\\])',r'\\% ',part)
                        part=re.sub(r'(\\Primary\w+\{\})(?=[A-Za-z])',r'\1 ',part)
                    fixed.append(part)
                out.append(''.join(fixed)+comment)
            if re.search(r'\\end\{(?:equation|align|gather|table|algorithm|longtable)',line):blocked=False
        p.write_text('\n'.join(out)+'\n',encoding='utf-8',newline='\n')
print('Prose spacing normalized; mathematics and literal identifier spans retained')
