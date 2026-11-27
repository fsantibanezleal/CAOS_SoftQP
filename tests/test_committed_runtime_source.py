"""Actual Git objects, checkout filters and hostile committed-source metadata."""

import importlib.util
import os
from pathlib import Path
import json
import hashlib
import subprocess
from types import SimpleNamespace

import pytest


HELPER = Path(__file__).resolve().parents[1] / "environments/method-extension-scientific/committed_source.py"
spec = importlib.util.spec_from_file_location("committed_source_control", HELPER)
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Fixture Owner")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "core.autocrlf", "false")
    (root / ".gitattributes").write_bytes(b"* text=auto eol=lf\n")
    paths = [prefix + "/control.py" for prefix in source.PREFIXES] + list(source.SUPPORT + source.GUARDS)
    for name in paths:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (("# " + name + "\n") if name in source.GUARDS else "") + "value = 1\n"
        path.write_bytes(raw.encode())
    git(root, "add", ".")
    git(root, "commit", "-qm", "Create excluded source control")
    return root, git(root, "rev-parse", "HEAD")


def test_committed_snapshot_uses_complete_exact_git_objects(repo, tmp_path):
    root, commit = repo
    rows, blobs = source.admitted_checkout(root, commit)
    manifest = source.source_manifest(rows)
    assert source.verify(root, commit, manifest, rows) == rows
    destination = tmp_path / "snapshot"
    assert source.snapshot(root, commit, destination) == rows
    assert all((destination / name).read_bytes() == blobs[rows[name]["blob"]] for name in manifest)
    assert not any((destination / name).exists() for name in source.GUARDS)
    with pytest.raises(ValueError, match="already exists"):
        source.snapshot(root, commit, destination)


@pytest.mark.parametrize("mutation", ["tracked", "untracked", "guard", "wrong-head"])
def test_adversarial_changed_scope_or_head_cannot_claim_committed_source(repo, mutation):
    root, commit = repo
    if mutation == "tracked":
        (root / "data-pipeline/control.py").write_bytes(b"value = 2\n")
    elif mutation == "untracked":
        (root / "data-pipeline/foreign.py").write_bytes(b"value = 1\n")
    elif mutation == "guard":
        (root / source.GUARDS[1]).write_bytes(b"value = 2\n")
    else:
        commit = "0" * 40
    with pytest.raises(ValueError, match="dirty|HEAD differs"):
        source.admitted_checkout(root, commit)


def test_adversarial_clean_filtered_crlf_checkout_is_not_git_blob_bytes(repo):
    root, commit = repo
    path = root / "data-pipeline/control.py"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    git(root, "add", "--renormalize", "data-pipeline/control.py")
    assert git(root, "status", "--porcelain", "--", "data-pipeline") == ""
    with pytest.raises(ValueError, match="checkout bytes differ"):
        source.admitted_checkout(root, commit)


def test_adversarial_rehashed_subset_metadata_cannot_omit_a_source_file(repo):
    root, commit = repo
    rows, _ = source.admitted_checkout(root, commit)
    shortened = {name: row for name, row in rows.items() if name != "data-pipeline/control.py"}
    with pytest.raises(ValueError, match="Git inventory differs"):
        source.verify(root, commit, source.source_manifest(shortened), shortened)
    with pytest.raises(ValueError, match="not the complete Git scope"):
        source.verify(root, commit, source.source_manifest(shortened), rows)


def test_adversarial_hardlink_is_refused_even_with_clean_git_status(repo, tmp_path):
    root, commit = repo
    alias = tmp_path / "outside.py"
    os.link(root / "data-pipeline/control.py", alias)
    try:
        assert git(root, "status", "--porcelain") == ""
        with pytest.raises(ValueError, match="file alias"):
            source.admitted_checkout(root, commit)
    finally:
        alias.unlink()


def test_adversarial_casefold_and_symlink_git_entries_are_refused():
    blob = "1" * 40
    with pytest.raises(ValueError, match="casefold collision"):
        source.tree_records(f"100644 blob {blob}\tdata-pipeline/Foo.py\0"
                            f"100644 blob {blob}\tdata-pipeline/foo.py\0".encode())
    with pytest.raises(ValueError, match="unsupported Git entry"):
        source.tree_records(f"120000 blob {blob}\tdata-pipeline/link.py\0".encode())


def test_adversarial_head_drift_during_blob_admission_is_refused(repo, monkeypatch):
    root, commit = repo
    original = source.git
    changed = False

    def drift(directory, *arguments, **kwargs):
        nonlocal changed
        raw = original(directory, *arguments, **kwargs)
        if arguments[:1] == ("cat-file",) and not changed:
            changed = True
            (root / "outside.txt").write_bytes(b"Unrelated changed commit\n")
            git(root, "add", "outside.txt")
            git(root, "commit", "-qm", "Move excluded source head")
        return raw

    monkeypatch.setattr(source, "git", drift)
    with pytest.raises(ValueError, match="changed during admission"):
        source.admitted_checkout(root, commit)


def live_profile(root, commit, profile):
    """Exercise the independent verifier against real Git blobs, not helper output alone."""
    import runpy

    verifier = runpy.run_path(str(HELPER.with_name("verify.py")))
    rows, _ = source.admitted_checkout(root, commit)
    profile.mkdir()
    for name in source.GUARDS:
        if Path(name).name != "build_profile.py":
            (profile / Path(name).name).write_bytes((root / name).read_bytes())
    inventory = json.dumps(rows, sort_keys=True).encode()
    (profile / "committed-source.json").write_bytes(inventory)
    stamp = dict(source_head=commit, committed_git_manifest_sha256=hashlib.sha256(inventory).hexdigest(),
                 committed_source_sha256=rows["environments/method-extension-scientific/committed_source.py"]["sha256"])
    return verifier, stamp, dict(source=source.source_manifest(rows))


def test_live_verifier_independently_rebuilds_full_committed_scope(repo, tmp_path, monkeypatch):
    root, commit = repo
    profile = tmp_path / "profile"
    verifier, stamp, manifest = live_profile(root, commit, profile)
    monkeypatch.setattr(source, "admitted_checkout", lambda *_: pytest.fail("helper cannot approve itself"))
    verifier["verify_committed_source"](SimpleNamespace(source=root, profile=profile), stamp, manifest)
    assert verifier["source_kind_allowed"]({"source_kind": "committed-product-checkout"}, False)
    assert not verifier["source_kind_allowed"]({"source_kind": "qualification-snapshot-of-product-worktree"}, False)
    assert verifier["source_kind_allowed"]({"source_kind": "qualification-snapshot-of-product-worktree"}, True)


@pytest.mark.parametrize("mutation", ["subset", "guard", "helper-stamp", "wrong-head", "filtered-crlf", "hardlink"])
def test_adversarial_live_verifier_refuses_rehashed_or_changed_source(repo, tmp_path, mutation):
    root, commit = repo
    profile = tmp_path / "profile"
    verifier, stamp, manifest = live_profile(root, commit, profile)
    alias = None
    if mutation == "subset":
        manifest["source"].pop("data-pipeline/control.py")
        inventory = json.loads((profile / "committed-source.json").read_bytes())
        inventory.pop("data-pipeline/control.py")
        raw = json.dumps(inventory).encode()
        (profile / "committed-source.json").write_bytes(raw)
        stamp["committed_git_manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    elif mutation == "guard":
        (profile / "heldout_runtime.py").write_bytes(b"value = 2\n")
    elif mutation == "helper-stamp":
        stamp["committed_source_sha256"] = "0" * 64
    elif mutation == "wrong-head":
        stamp["source_head"] = "0" * 40
    elif mutation == "filtered-crlf":
        path = root / "data-pipeline/control.py"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        git(root, "add", "--renormalize", "data-pipeline/control.py")
        assert git(root, "status", "--porcelain") == ""
    else:
        alias = tmp_path / "foreign.py"
        os.link(root / "data-pipeline/control.py", alias)
    try:
        with pytest.raises(ValueError):
            verifier["verify_committed_source"](SimpleNamespace(source=root, profile=profile), stamp, manifest)
    finally:
        if alias is not None:
            alias.unlink()


@pytest.mark.parametrize("keep_approved_checkout", [True, False])
@pytest.mark.parametrize("reader", ["factory", "verifier"])
def test_adversarial_git_replacement_cannot_change_approved_commit_tree(repo, tmp_path, keep_approved_checkout, reader):
    root, commit = repo
    profile = tmp_path / "profile"
    verifier, stamp, manifest = live_profile(root, commit, profile)
    path = root / "data-pipeline/control.py"
    path.write_bytes(b"value = 2\n")
    git(root, "add", "data-pipeline/control.py")
    git(root, "commit", "-qm", "Create alternative excluded tree")
    replacement = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "HEAD", commit)
    if keep_approved_checkout:
        path.write_bytes(b"value = 1\n")
        git(root, "read-tree", commit)
    git(root, "replace", commit, replacement)
    assert git(root, "rev-parse", "HEAD") == commit
    args = SimpleNamespace(source=root, profile=profile)
    def admit():
        if reader == "factory":
            return source.admitted_checkout(root, commit)
        return verifier["verify_committed_source"](args, stamp, manifest)
    if keep_approved_checkout:
        assert git(root, "status", "--porcelain") != ""
        admit()
    else:
        assert git(root, "status", "--porcelain") == ""
        if reader == "verifier":
            # Rehashing attempted metadata cannot change the reviewed tree.
            attempted = source.tree_records(git(root, "ls-tree", "-rz", "--full-tree", commit,
                                                 "--", *source.SCOPES).encode())
            for name, row in attempted.items():
                raw = (root / name).read_bytes()
                row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            raw = json.dumps(attempted).encode()
            (profile / "committed-source.json").write_bytes(raw)
            stamp["committed_git_manifest_sha256"] = hashlib.sha256(raw).hexdigest()
            manifest["source"] = source.source_manifest(attempted)
        with pytest.raises(ValueError):
            admit()


@pytest.mark.parametrize("late_drift", [False, True])
def test_committed_factory_publishes_only_after_final_checkout_check(repo, tmp_path, monkeypatch, late_drift, capsys):
    monkeypatch.syspath_prepend(str(HELPER.parent))
    monkeypatch.setitem(__import__("sys").modules, "committed_source", source)
    factory_spec = importlib.util.spec_from_file_location("committed_factory_control", HELPER.with_name("build_profile.py"))
    factory = importlib.util.module_from_spec(factory_spec)
    factory_spec.loader.exec_module(factory)
    root, commit = repo
    scratch, runtime, baseline, tools = (tmp_path / part for part in ("scratch", "runtime", "baseline", "tools"))
    for path in (scratch, runtime, baseline, tools):
        path.mkdir()
    destination = tmp_path / "published"
    summary = {"status": "excluded-test-only"}

    def fake_build(product, work, installed, parent, support, stage, *, source_commit):
        assert not destination.exists() and source_commit == commit
        source.admitted_checkout(product, source_commit)
        stage.mkdir()
        (stage / "provenance.json").write_bytes(b"excluded test profile\n")
        if late_drift:
            (root / "data-pipeline/control.py").write_bytes(b"value = 2\n")
        return summary

    monkeypatch.setattr(factory, "_build", fake_build)
    if late_drift:
        with pytest.raises(ValueError, match="dirty"):
            factory.build(root, scratch, runtime, baseline, tools, destination, source_commit=commit)
        assert not destination.exists()
        assert len(list(tmp_path.glob("published.pending-*"))) == 1
    else:
        assert factory.build(root, scratch, runtime, baseline, tools, destination, source_commit=commit) == summary
        assert (destination / "provenance.json").read_bytes() == b"excluded test profile\n"
        assert not list(tmp_path.glob("published.pending-*"))
    assert capsys.readouterr().out == ""
