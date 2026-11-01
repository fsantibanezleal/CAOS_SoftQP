"""Keep standalone scientific schemas self-contained for offline consumers."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]/'docs/contracts/schemas'
def load(name):
    return json.loads((ROOT/f'{name}.schema.json').read_text(encoding='utf-8'))
def body(doc):
    return {k:v for k,v in doc.items() if k not in ('$id','$schema','$defs')}
def write(name,doc):
    (ROOT/f'{name}.schema.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':
    problem=load('softqp-case-spec');request=load('softqp-run-request');result=load('softqp-case-result');local=load('softqp-local-export')
    result['$defs']={'SoftQPProblemPayload':body(problem)}
    result['properties']['problem']={'$ref':'#/$defs/SoftQPProblemPayload'}
    local['$defs']={**result['$defs'],'SoftQPRequestPayload':body(request),'SoftQPResultPayload':body(result)}
    local['properties']['request']={'$ref':'#/$defs/SoftQPRequestPayload'}
    local['properties']['result']={'$ref':'#/$defs/SoftQPResultPayload'}
    write('softqp-case-result',result);write('softqp-local-export',local)
