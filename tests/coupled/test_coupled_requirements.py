"""The separate study profile cannot drift outside its protocol dependency identity."""

import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('check_coupled_requirements', ROOT/'scripts/check_coupled_requirements.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture
def profile(tmp_path):
    for relative in ('experiments/coupled-v1/requirements.txt', 'docs/design/coupled-experiments-v1.json'):
        target = tmp_path/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/relative, target)
    return tmp_path


def test_exact_separate_profile_matches_all_protocol_pins(profile):
    document = json.loads((profile/'docs/design/coupled-experiments-v1.json').read_text())
    assert MODULE.check(profile) == len(document['packages']) == 9


@pytest.mark.parametrize('mutation', ['old-sdk', 'range', 'duplicate', 'missing', 'extra', 'option', 'url',
                                    'attached-comment', 'invalid-version', 'empty', 'sdk-metadata'])
def test_adversarial_dependency_drift_or_unpinned_options_are_rejected(profile, mutation):
    path = profile/'experiments/coupled-v1/requirements.txt'
    text = path.read_text()
    if mutation == 'old-sdk':
        text = text.replace('softqp==0.2.0', 'softqp==0.1.0')
    elif mutation == 'range':
        text = text.replace('softqp==0.2.0', 'softqp>=0.2.0')
    elif mutation == 'duplicate':
        text += '\nsoftqp==0.2.0\n'
    elif mutation == 'missing':
        text = text.replace('softqp==0.2.0', '')
    elif mutation == 'extra':
        text += '\nunregistered-library==1.0.0\n'
    elif mutation == 'option':
        text += '\n-r requirements.txt\n'
    elif mutation == 'url':
        text = text.replace('softqp==0.2.0', 'softqp @ https://example.invalid/custom.whl')
    elif mutation == 'attached-comment':
        text = text.replace('softqp==0.2.0', 'softqp==0.2.0#not-a-pip-comment')
    elif mutation == 'invalid-version':
        text = text.replace('softqp==0.2.0', 'softqp==nonsense')
        protocol_path = profile/'docs/design/coupled-experiments-v1.json'
        document = json.loads(protocol_path.read_text())
        document['packages']['softqp'] = 'nonsense'
        protocol_path.write_text(json.dumps(document))
    elif mutation == 'empty':
        text = ''
        protocol_path = profile/'docs/design/coupled-experiments-v1.json'
        document = json.loads(protocol_path.read_text())
        document['packages'] = {}
        protocol_path.write_text(json.dumps(document))
    else:
        protocol_path = profile/'docs/design/coupled-experiments-v1.json'
        document = json.loads(protocol_path.read_text())
        document['engine']['distribution_version'] = '9.9.9'
        protocol_path.write_text(json.dumps(document))
    path.write_text(text)
    with pytest.raises(ValueError):
        MODULE.check(profile)
