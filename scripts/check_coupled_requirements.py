"""The independent coupled study profile is exactly its frozen protocol package map."""

import json
from pathlib import Path
import re
import sys

from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NAMES = {'softqp', 'numpy', 'scipy', 'osqp', 'daqp', 'jsonschema', 'elastiqp', 'pytest', 'packaging'}


def check(root):
    protocol = json.loads((root/'docs/design/coupled-experiments-v1.json').read_text(encoding='utf-8'))
    pins = {}
    for raw in (root/'experiments/coupled-v1/requirements.txt').read_text(encoding='utf-8').splitlines():
        if raw.lstrip().startswith('#'):
            continue
        line = re.split(r'\s+#', raw, maxsplit=1)[0].strip()
        if not line:
            continue
        requirement = Requirement(line)
        specifiers = list(requirement.specifier)
        if (requirement.extras or requirement.marker or requirement.url or len(specifiers) != 1
                or specifiers[0].operator != '==' or '*' in specifiers[0].version):
            raise ValueError(f'coupled study dependency is not exactly pinned: {line}')
        name = re.sub(r'[-_.]+', '-', requirement.name.lower())
        version = str(Version(specifiers[0].version))
        if name in pins:
            raise ValueError(f'duplicate coupled dependency: {name}')
        pins[name] = version
    if pins != protocol['packages']:
        raise ValueError('coupled requirements differ from the independent protocol package map')
    if set(pins) != EXPECTED_NAMES:
        raise ValueError('coupled v1 requires exactly its nine declared distributions')
    tag = protocol['engine']['release_tag']
    if (pins['softqp'] != protocol['engine']['distribution_version'] or not isinstance(tag, str) or not tag.startswith('v')
            or Version(tag[1:]) != Version(pins['softqp'])):
        raise ValueError('SDK package pin and engine release metadata disagree')
    return len(pins)


if __name__ == '__main__':
    try:
        print(f'coupled requirements: {check(Path(sys.argv[1]) if len(sys.argv)>1 else ROOT)} exact pins match')
    except (OSError, ValueError, KeyError) as error:
        print(f'coupled requirements: FAILED: {error}')
        raise SystemExit(1)
