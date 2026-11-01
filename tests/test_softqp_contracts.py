import copy
import json
from pathlib import Path
import pytest
from jsonschema import ValidationError
from pipeline.softqp_run import validate_document

ROOT=Path(__file__).resolve().parents[1]
ROOTS=[ROOT/'data/derived/softqp',ROOT/'docs/contracts/fixtures/data/derived/softqp']

@pytest.mark.parametrize('root',ROOTS)
def test_producer_documents_and_provider_match_schema(root):
    index=json.loads((root/'index.json').read_text(encoding='utf-8'))
    validate_document(index,'softqp-index')
    for row in index['cases']:
        validate_document(json.loads((root/row['path']).read_text(encoding='utf-8')),'softqp-case-result')

def test_rejects_boolean_unknown_key_and_missing_objective():
    value=json.loads((ROOTS[0]/'C01.json').read_text(encoding='utf-8'))
    for mutate in [lambda x:x.update(unexpected=True),
                   lambda x:x['runs'][0]['result']['metrics'].update(objective=True),
                   lambda x:x['runs'][0]['result']['metrics'].pop('objective')]:
        changed=copy.deepcopy(value);mutate(changed)
        with pytest.raises(ValidationError):validate_document(changed,'softqp-case-result')

def test_nonfinite_result_is_rejected_before_json_export():
    value=json.loads((ROOTS[0]/'C01.json').read_text(encoding='utf-8'))
    value['runs'][0]['result']['metrics']['objective']=float('nan')
    with pytest.raises(ValueError,match='nonfinite'):validate_document(value,'softqp-case-result')
