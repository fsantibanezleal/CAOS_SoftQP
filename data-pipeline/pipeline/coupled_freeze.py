"""A separate registration manifest pins protocol, source and accepted review."""

import hashlib
import json
import importlib.metadata
from pathlib import Path
import subprocess


def canonical_digest(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode('utf-8')).hexdigest()


def local_path(root, relative):
    path = (root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('registration path escapes the repository')
    return path


def source_hashes(root, protocol):
    if len(protocol['source_files']) != len(set(protocol['source_files'])):
        raise ValueError('duplicate frozen source path')
    return {path: hashlib.sha256(local_path(root, path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for path in protocol['source_files']}


def verify_registration(root, protocol):
    registration_path = root/'docs/design/coupled-experiments-v1.registration.json'
    if not registration_path.is_file():
        raise RuntimeError('Study has not completed independent registration')
    registration = json.loads(registration_path.read_text(encoding='utf-8'))
    if registration['protocol_sha256'] != canonical_digest(protocol):
        raise RuntimeError('protocol differs from the independent registration manifest')
    if source_hashes(root, protocol) != registration['source_sha256']:
        raise RuntimeError('source differs from the independent registration manifest')
    review_path = local_path(root, registration['review_path'])
    review = json.loads(review_path.read_text(encoding='utf-8'))
    if (canonical_digest(review) != registration['review_sha256'] or review['decision'] != 'ACCEPT'
            or review['source_sha256'] != registration['source_sha256']
            or review['protocol_sha256'] != registration['protocol_sha256']):
        raise RuntimeError('independent review does not accept this exact protocol/source identity')
    protected = protocol['source_files']+[
        'docs/design/coupled-experiments-v1.json',
        'docs/design/coupled-experiments-v1.registration.json', registration['review_path']]
    subprocess.run(['git', '-C', str(root), 'ls-files', '--error-unmatch', '--', *protected],
                   check=True, capture_output=True, timeout=5)
    status = subprocess.run(['git', '-C', str(root), 'status', '--porcelain', '--', *protected],
                            check=True, capture_output=True, text=True, timeout=5)
    if status.stdout:
        raise RuntimeError('registered protocol/source/review has uncommitted changes')
    commit = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], check=True,
                            capture_output=True, text=True, timeout=5).stdout.strip()
    return dict(commit=commit, protocol_sha256=registration['protocol_sha256'],
                review_sha256=registration['review_sha256'])


def verify_installed_sdk(protocol):
    import softqp
    from softqp import ext_builtin

    installed = Path(softqp.__file__).resolve().parent
    distribution = importlib.metadata.distribution('softqp')
    if 'site-packages' not in installed.parts or distribution.read_text('direct_url.json'):
        raise RuntimeError('registered study requires a public-index SDK install')
    actual = {path.relative_to(installed).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in installed.rglob('*.py')}
    binary = hashlib.sha256(Path(ext_builtin.__file__).read_bytes()).hexdigest()
    if actual != protocol['engine']['python_sha256_by_binary'].get(binary):
        raise RuntimeError('installed SDK Python sources differ from the verified public wheel')
    return actual


def verify_recorded_commit(root, commit, protocol):
    registration_name = 'docs/design/coupled-experiments-v1.registration.json'
    registration = json.loads((root/registration_name).read_text(encoding='utf-8'))
    names = protocol['source_files']+['docs/design/coupled-experiments-v1.json',
                                      registration_name, registration['review_path']]
    requested = ''.join(f'{commit}:{name}\n' for name in names).encode('utf-8')
    result = subprocess.run(['git', '-C', str(root), 'cat-file', '--batch'], input=requested,
                            capture_output=True, check=True, timeout=15).stdout
    blobs, offset = {}, 0
    for name in names:
        end = result.index(b'\n', offset)
        header = result[offset:end].split()
        if len(header) != 3 or header[1] != b'blob':
            raise ValueError('claimed run commit lacks registered source/review blobs')
        length = int(header[2])
        blobs[name] = result[end+1:end+1+length]
        offset = end+length+2
    for name in protocol['source_files']:
        if hashlib.sha256(blobs[name].replace(b'\r\n', b'\n')).hexdigest() != registration['source_sha256'][name]:
            raise ValueError('claimed run commit contains different registered source')
    if (canonical_digest(json.loads(blobs['docs/design/coupled-experiments-v1.json'])) != registration['protocol_sha256']
            or canonical_digest(json.loads(blobs[registration['review_path']])) != registration['review_sha256']
            or canonical_digest(json.loads(blobs[registration_name])) != canonical_digest(registration)):
        raise ValueError('claimed run commit contains different registration/protocol/review')
