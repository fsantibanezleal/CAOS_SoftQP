"""Adversaries for the real Windows product runtime custody helper."""
import os
from pathlib import Path
import py_compile
import runpy
import subprocess
import sys

import pytest


TOOLS = Path(__file__).resolve().parents[1] / "environments/method-extension-scientific"
CUSTODY = runpy.run_path(str(TOOLS / "custody.py"))
VERIFY = runpy.run_path(str(TOOLS / "verify.py"))
LEARNING = runpy.run_path(str(TOOLS / "learning_runtime.py"))


def test_learning_launch_binds_profile_roles_and_one_workspace(tmp_path):
    encode, digest, scope = (LEARNING[key] for key in ("encode", "digest", "learning_scope"))
    request = dict(schema="softqp.r4.learning-request/1", operation="train-model", method="learned_daqp",
                   seed=41002, resume={"root": str(tmp_path), "sha256": "b" * 64})
    raw = encode(request)
    policy = dict(schema="softqp.r4.learning-policy/1", operation=request["operation"], request_sha256=digest(raw),
                  profile_sha256="a" * 64, admission={}, output_root=str(tmp_path), artifact_roots=[],
                  scope=dict(preflight={}, roles={"train": {}, "validation": {}}, resume=request["resume"]))
    assert scope((raw, encode(policy)), "a" * 64)[2] == tmp_path / "learned_daqp-41002-resume-bbbbbbbbbbbbbbbb" / "worker"
    with pytest.raises(ValueError, match="policy identity"):
        scope((raw, encode(policy)), "c" * 64)
    policy["scope"]["roles"]["test"] = {}
    with pytest.raises(ValueError, match="role or resume"):
        scope((raw, encode(policy)), "a" * 64)
    request["operation"] = "calibrate-model"
    with pytest.raises(ValueError, match="invalid learning resume"):
        scope((encode(request), encode(policy)), "a" * 64)


def test_learning_parent_ancestry_uses_actual_windows_process(tmp_path):
    code = ("import runpy,sys; verifier=runpy.run_path(sys.argv[1]); "
            "verifier['check_learning_parent'](int(sys.argv[2]))")
    command = [sys.executable, "-I", "-S", "-B", "-c", code, str(TOOLS / "verify.py")]
    subprocess.run(command + [str(os.getpid())], check=True, timeout=15)
    refusal = subprocess.run(command + ["2147483647"], check=False, timeout=15, capture_output=True)
    assert refusal.returncode != 0 and b"learning owner process ancestry differs" in refusal.stderr


@pytest.mark.parametrize("launcher_kind", ["base", "scientific"])
def test_learning_leaf_is_in_both_kernel_jobs(launcher_kind):
    # A Microsoft Store-backed arbitrary test venv can drop inherited outer
    # membership in its launcher. Exercise the nominated production interpreter,
    # as well as direct CPython, without weakening either actual kernel check.
    if launcher_kind == "scientific":
        launcher = os.environ.get("SOFTQP_SCIENTIFIC_PYTHON")
        if not launcher:
            pytest.skip("SOFTQP_SCIENTIFIC_PYTHON must nominate the governed runtime")
        assert Path(launcher).is_file(), "nominated scientific interpreter is unavailable"
    else:
        launcher = sys._base_executable
    jobs = TOOLS.parents[1] / "data-pipeline/pipeline/lesson_process.py"
    leaf = ("import runpy,sys; verifier=runpy.run_path(sys.argv[1]); "
            "verifier['check_learning_parent'](int(sys.argv[2])); "
            "verifier['require_owned_job'](sys.argv[3]); verifier['require_owned_job'](sys.argv[4])")
    parent = """
import os,runpy,subprocess,sys
job = runpy.run_path(sys.argv[1])['WindowsJob']()
try:
    command = [sys.executable, '-I', '-S', '-B', '-c', sys.argv[2], sys.argv[3],
               str(os.getpid()), sys.argv[4], job.name]
    child = subprocess.Popen(command, creationflags=4)
    job.attach_and_resume(child)
    assert child.wait(10) == 0
finally:
    job.close()
"""
    outer = runpy.run_path(str(jobs))["WindowsJob"]()
    try:
        command = [launcher, "-I", "-S", "-B", "-c", parent, str(jobs), leaf,
                   str(TOOLS / "verify.py"), outer.name]
        process = subprocess.Popen(command, creationflags=4)
        outer.attach_and_resume(process)
        assert process.wait(15) == 0
    finally:
        outer.close()


def test_learning_leaf_holds_exact_boot_before_worker_dispatch(tmp_path):
    from types import SimpleNamespace

    spec = dict(nonce="1" * 32, operation="train-model", method="learned_osqp", seed=41001,
                request_sha256="a" * 64, policy_sha256="b" * 64, profile_sha256="c" * 64)
    authority = {key: spec[key] for key in ("operation", "request_sha256", "policy_sha256", "profile_sha256")}
    raw = LEARNING["encode"](dict(nonce=spec["nonce"], authority=authority,
                                  task=dict(operation="train", method=spec["method"], seed=spec["seed"],
                                            permit_scope="d" * 64)))
    path = tmp_path / "boot.json"
    path.write_bytes(raw.replace(b"41001", b"41002"))
    spec["boot_sha256"] = LEARNING["digest"](raw)
    args = SimpleNamespace(run=tmp_path)
    with CUSTODY["HeldInventory"]() as held:
        with pytest.raises(ValueError, match="external byte identity differs"):
            VERIFY["hold_learning_boot"](args, held, LEARNING, spec)
        path.write_bytes(raw)
        VERIFY["hold_learning_boot"](args, held, LEARNING, spec)
        with pytest.raises(PermissionError):
            path.write_bytes(raw)


def test_same_size_preserved_time_mutation_fails_full_custody(tmp_path):
    file = tmp_path / "real.py"
    file.write_bytes(b"real")
    expected = CUSTODY["inventory"](tmp_path, "runtime")
    original = file.stat()
    file.write_bytes(b"fake")
    os.utime(file, ns=(original.st_atime_ns, original.st_mtime_ns))
    with CUSTODY["HeldInventory"]() as held, pytest.raises(ValueError, match="file identity differs"):
        held.check(tmp_path, "runtime", expected)


def test_handles_deny_mutation_and_import_guard_refuses_added_origins(tmp_path):
    root = tmp_path / "runtime"
    root.mkdir()
    file = root / "genuine.py"
    file.write_text("value = 42\n", encoding="utf-8")
    expected = CUSTODY["inventory"](root, "runtime")
    with CUSTODY["HeldInventory"]() as held:
        held.check(root, "runtime", expected)
        with pytest.raises(PermissionError):
            file.write_text("even same-size unsafe\n", encoding="utf-8")
        with pytest.raises(PermissionError):
            root.rename(tmp_path / "moved")
        added = root / "injected.py"
        added.write_text("raise AssertionError('not executed')\n", encoding="utf-8")
        guard = VERIFY["CheckedImports"](held)
        with pytest.raises(ValueError, match="unadmitted origin"):
            guard.find_spec("injected", [str(root)])
        with pytest.raises(ValueError, match="inventory changed"):
            held.recheck_names()
    assert file.read_text(encoding="utf-8") == "value = 42\n"


def test_fresh_bytecode_prefix_excludes_a_preexisting_unchecked_cache(tmp_path):
    module = tmp_path / "sample.py"
    module.write_text("value = 'contaminated cache'\n", encoding="utf-8")
    cache = tmp_path / "__pycache__" / ("sample." + sys.implementation.cache_tag + ".pyc")
    cache.parent.mkdir()
    cached = Path(py_compile.compile(str(module), cfile=str(cache), doraise=True,
                                   invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH))
    module.write_text("value = 'verified source'\n", encoding="utf-8")
    assert cached.exists()
    command = [sys.executable, "-I", "-S", "-B"]
    args = ["-c", "import sys;sys.path.append(sys.argv[1]);import sample;print(sample.value)", str(tmp_path)]
    assert subprocess.check_output(command + args, timeout=12, text=True).strip() == "contaminated cache"
    prefix = tmp_path / "never-created"
    assert subprocess.check_output(command + ["-X", f"pycache_prefix={prefix}"] + args,
                                   timeout=12, text=True).strip() == "verified source"
    assert not prefix.exists()


def test_qualification_source_refuses_registered_operation_before_payload_open(tmp_path):
    from types import SimpleNamespace

    args = SimpleNamespace(request=tmp_path/"missing-request", policy=tmp_path/"missing-policy",
                           expected_request_sha256="a"*64, expected_policy_sha256="b"*64)
    with pytest.raises(ValueError, match="qualification snapshot cannot dispatch"):
        VERIFY["launch_inputs"](args, {"source_kind": "qualification-snapshot-of-product-worktree"})


def test_existing_job_name_without_membership_is_refused(monkeypatch):
    process = runpy.run_path(str(TOOLS.parents[1] / "data-pipeline/pipeline/lesson_process.py"))
    job = process["WindowsJob"]()
    try:
        monkeypatch.setenv("SOFTQP_SCIENTIFIC_JOB", job.name)
        with pytest.raises(ValueError, match="outside the nominated Windows job"):
            VERIFY["require_owned_job"]()
    finally:
        job.close()


def test_late_worker_cannot_publish_a_stage_observation(tmp_path):
    import time

    with pytest.raises(ValueError, match="actual worker deadline"):
        VERIFY["stage_file"](tmp_path, "cold", {}, time.monotonic() - 31)
    assert list(tmp_path.iterdir()) == []


def test_owned_teardown_leaves_outside_process_running():
    process = runpy.run_path(str(TOOLS.parents[1] / "data-pipeline/pipeline/lesson_process.py"))
    job = process["WindowsJob"]()
    command = [sys._base_executable, "-I", "-S", "-B", "-c", "import time; time.sleep(30)"]
    external, owned = None, None
    try:
        external = subprocess.Popen(command)
        owned = subprocess.Popen(command, creationflags=4)
        job.attach_and_resume(owned)
        job.close()
        assert owned.wait(timeout=3) != 0
        assert external.poll() is None
    finally:
        job.close()
        for fixture in (external, owned):
            if fixture is not None:
                if fixture.poll() is None:
                    fixture.kill()
                fixture.wait(timeout=3)


@pytest.mark.parametrize("failure", ["foreign", "mutated", "source", "path", None])
def test_derived_recipe_is_exact_and_read_only(tmp_path, monkeypatch, failure):
    from hashlib import sha256
    from importlib.machinery import SourceFileLoader

    name = "torch_geometric.nn.conv.le_conv_LEConv_propagate"
    module = name if failure != "foreign" else "foreign_source"
    runtime, scratch = tmp_path / "runtime", tmp_path / "fresh-job"
    runtime.mkdir()
    scratch.mkdir()
    recipe = runtime / "template"
    recipe.write_bytes(b"pinned recipe")
    approved = b"value = 42\n"
    folder = scratch / "outside" if failure == "path" else scratch
    folder.mkdir(exist_ok=True)
    file = folder / f"{module}_abcd1234.py"
    file.write_bytes(approved if failure != "mutated" else b"value = 43\n")
    profile = {"scientific_runtime": {"derived_python": {name: {
        "identity": [len(approved), sha256(approved).hexdigest()],
        "recipe": {"template": sha256(b"wrong recipe" if failure == "source" else b"pinned recipe").hexdigest()},
    }}}}
    monkeypatch.setattr(SourceFileLoader, "get_code", SourceFileLoader.get_code)
    with CUSTODY["HeldInventory"]() as held:
        held.check(runtime, "runtime", CUSTODY["inventory"](runtime, "runtime"))
        if failure == "source":
            with pytest.raises(ValueError, match="recipe differs"):
                VERIFY["constrain_source_loader"](profile, {"runtime": runtime}, held, scratch)
            return
        violations = VERIFY["constrain_source_loader"](profile, {"runtime": runtime}, held, scratch)
        loader = SourceFileLoader(module, str(file))
        if failure:
            with pytest.raises(ValueError):
                loader.get_code(module)
            assert violations
        else:
            compiled = loader.get_code(module)
            assert compiled.co_filename == str(file)
            assert not violations
            assert held.identify(file)[0] == "derived-runtime"
            VERIFY["write_marker"](scratch, "observation.json", {"ok": True})
            with pytest.raises(PermissionError):
                file.write_bytes(b"value = 99\n")


def test_campaign_bounds_binds_independent_plan_and_resumed_prefix(tmp_path):
    import json
    from hashlib import sha256
    from types import SimpleNamespace

    def ref(name, value):
        payload = json.dumps(value).encode()
        (tmp_path / name).write_bytes(payload)
        return {"path": name, "sha256": sha256(payload).hexdigest()}

    profile_sha = "a" * 64
    plan = ref("plan.json", {"schema": "softqp.r4.generate-campaign-plan/1",
                              "profile_sha256": profile_sha, "entries": [{"slot": k} for k in range(3)]})
    frontier = ref("frontier.json", {"schema": "softqp.r4.generate-campaign-frontier/1",
                                      "plan_sha256": plan["sha256"], "next": 1})
    raw = {"schema": "softqp.r4.generate-campaign-request/1", "plan_sha256": plan["sha256"]}
    policy = {"schema": "softqp.r4.generate-campaign-policy/1", "approval": {"root": str(tmp_path)},
              "plan": plan, "frontier": frontier, "end": 3, "max_wall_seconds": 90}
    args = SimpleNamespace(expected_profile_sha256=profile_sha)
    assert VERIFY["campaign_bounds"](args, (json.dumps(raw), json.dumps(policy)))[:3] == (1, 3, 90)
    policy["end"] = 4
    with pytest.raises(ValueError, match="campaign plan or frontier differs"):
        VERIFY["campaign_bounds"](args, (json.dumps(raw), json.dumps(policy)))
    policy["end"] = 3
    (tmp_path/"frontier.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="byte identity differs"):
        VERIFY["campaign_bounds"](args, (json.dumps(raw), json.dumps(policy)))
