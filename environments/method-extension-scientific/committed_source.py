"""Exact Git-object admission for the fixed numerical source scope."""

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess


PREFIXES = (
    "data-pipeline", "docs/contracts/schemas", "docs/contracts/examples",
    "tests/fixtures/learned-contracts",
)
SUPPORT = tuple("tests/" + name for name in (
    "test_learned_contracts.py", "test_stream_inputs.py", "test_phase_inputs.py",
    "test_native_labels.py", "test_native_runtime.py", "test_heldout_inputs.py", "runtime_config.py",
    "test_candidate_runtime.py",
))
GUARDS = tuple("environments/method-extension-scientific/" + name for name in (
    "build_profile.py", "verify.py", "custody.py", "controls.py", "learning_runtime.py",
    "native_runtime.py", "heldout_runtime.py", "committed_source.py", "evaluation_runtime.py",
))
SCOPES = PREFIXES + SUPPORT + GUARDS


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def git(root, *arguments, input_bytes=None):
    result = subprocess.run(["git", "--no-replace-objects", "-C", str(root), *arguments], input=input_bytes,
                            capture_output=True, timeout=30, check=False)
    need(result.returncode == 0, "committed source Git operation failed")
    return result.stdout


def safe_file(root, relative):
    parts = PurePosixPath(relative).parts
    need(parts and not PurePosixPath(relative).is_absolute() and ".." not in parts
         and "\\" not in relative and ":" not in relative, "unsafe committed source path")
    path = root.joinpath(*parts)
    for item in (*reversed(path.parents), path):
        facts = item.lstat()
        need(not stat.S_ISLNK(facts.st_mode)
             and not getattr(facts, "st_file_attributes", 0) & 0x400, "committed source reparse path")
    facts = path.lstat()
    need(stat.S_ISREG(facts.st_mode) and facts.st_nlink == 1
         and path.resolve(strict=True).parts == path.parts, "committed source file alias")
    return path


def tree_records(raw):
    rows, folded = {}, set()
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        header, name = entry.split(b"\t", 1)
        mode, kind, blob = header.decode("ascii").split()
        name = name.decode("utf8")
        need(mode in ("100644", "100755") and kind == "blob"
             and re.fullmatch("[0-9a-f]{40}", blob), "committed source unsupported Git entry")
        need(name.casefold() not in folded, "committed source casefold collision")
        need("__pycache__" not in PurePosixPath(name).parts and not name.endswith(".pyc"),
             "committed bytecode is not admitted source")
        folded.add(name.casefold())
        rows[name] = {"mode": mode, "blob": blob}
    return rows


def object_bytes(root, rows):
    identifiers = [row["blob"] for row in rows.values()]
    data = git(root, "cat-file", "--batch", input_bytes=("\n".join(identifiers) + "\n").encode())
    offset, blobs = 0, {}
    for expected in identifiers:
        end = data.index(b"\n", offset)
        actual, kind, size = data[offset:end].decode("ascii").split()
        need(actual == expected and kind == "blob" and size.isdecimal(), "committed blob header differs")
        offset, size = end + 1, int(size)
        value = data[offset:offset + size]
        need(len(value) == size and data[offset + size:offset + size + 1] == b"\n",
             "committed blob payload truncated")
        need(hashlib.sha1(b"blob " + str(size).encode() + b"\0" + value).hexdigest() == expected,
             "committed blob identity differs")
        blobs[expected] = value
        offset += size + 1
    need(offset == len(data), "unexpected committed blob trailer")
    return blobs


def admitted_checkout(root, commit):
    root = Path(root)
    need(root.is_absolute() and root.resolve(strict=True).parts == root.parts,
         "committed source requires an exact absolute checkout")
    need(type(commit) is str and re.fullmatch("[0-9a-f]{40}", commit), "explicit commit SHA required")
    need(git(root, "rev-parse", "HEAD^{commit}").decode().strip() == commit, "committed source HEAD differs")
    need(not git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", *SCOPES),
         "committed source scope is dirty or contains untracked files")
    rows = tree_records(git(root, "ls-tree", "-rz", "--full-tree", commit, "--", *SCOPES))
    need(all(any(name.startswith(prefix + "/") for name in rows) for prefix in PREFIXES)
         and set(SUPPORT + GUARDS) <= rows.keys(), "committed source scope incomplete")
    blobs = object_bytes(root, rows)
    for name, row in rows.items():
        raw = safe_file(root, name).read_bytes()
        need(raw == blobs[row["blob"]], "checkout bytes differ from committed source: " + name)
        row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    need(git(root, "rev-parse", "HEAD^{commit}").decode().strip() == commit
         and not git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", *SCOPES),
         "committed source changed during admission")
    return rows, blobs


def source_manifest(rows):
    """The source alphabet is normative, never supplied by attempted metadata."""
    return {name: [row["bytes"], row["sha256"]] for name, row in rows.items()
            if name not in GUARDS}


def snapshot(root, commit, destination):
    rows, blobs = admitted_checkout(root, commit)
    destination = Path(destination)
    need(not destination.exists(), "committed source snapshot already exists")
    destination.mkdir()
    for name in source_manifest(rows):
        path = destination.joinpath(*PurePosixPath(name).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(blobs[rows[name]["blob"]])
            handle.flush()
            os.fsync(handle.fileno())
    again, _ = admitted_checkout(root, commit)
    need(again == rows, "committed source scope changed during snapshot")
    return rows


def verify(root, commit, manifest, expected_git_inventory):
    rows, _ = admitted_checkout(root, commit)
    need(rows == expected_git_inventory, "committed Git inventory differs")
    need(manifest == source_manifest(rows), "committed source manifest is not the complete Git scope")
    return rows
