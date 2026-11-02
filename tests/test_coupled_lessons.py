"""Real public-SDK worked cases and adversaries at the separate-runtime seam."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from jsonschema import ValidationError

from pipeline import coupled_lessons as lessons
from pipeline.lesson_process import execute
from pipeline.lesson_process import WorkerCleanupError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def external(monkeypatch, tmp_path):
    configured = os.environ.get("SOFTQP_COUPLED_PYTHON")
    if not configured:
        pytest.skip("Local-only: actual separately pinned public SDK2 interpreter required")
    monkeypatch.setenv("SOFTQP_COUPLED_PYTHON", configured)
    monkeypatch.setenv("CAOS_TEMP_ROOT", str(tmp_path))
    return configured


def test_adversarial_external_lesson_boundary(monkeypatch, tmp_path):
    valid = dict(linear=0.6, quadratic=0, upper_scale=1, row_scale=1)
    lessons.validate_input(valid)
    for key, bad in [("linear", True), ("quadratic", float("nan")), ("row_scale", 1e-320),
                     ("upper_scale", 0), ("linear", -1), ("quadratic", 11)]:
        with pytest.raises((ValueError, ValidationError)):
            lessons.validate_input({**valid, key: bad})
    monkeypatch.delenv("SOFTQP_COUPLED_PYTHON", raising=False)
    with pytest.raises(ValueError, match="SOFTQP_COUPLED_PYTHON"):
        lessons.run_comparison()
    for wrong in ("python", str(tmp_path / "missing.exe"), str(ROOT / "frontend/package.json")):
        with pytest.raises(ValueError):
            lessons.runtime_identity(wrong)
    if os.name == "nt":
        fake = tmp_path / "broker-env"
        (fake / "Scripts").mkdir(parents=True)
        (fake / "Scripts/python.exe").write_bytes(b"MZ-not-executed")
        broker = tmp_path / "broker.exe"
        broker.write_bytes(b"")
        (fake / "pyvenv.cfg").write_text(f"version = 3.12.10\nexecutable = {broker}\n")
        with pytest.raises(ValueError, match="Brokered Windows Python"):
            lessons.runtime_identity(str(fake / "Scripts/python.exe"))
    for raw in ('{"x":NaN}', '{"x":1,"x":2}', 'not-json'):
        with pytest.raises(ValueError):
            lessons.strict_json(raw)


def test_adversarial_uncertain_cleanup_preserves_recovery(external, monkeypatch, tmp_path):
    def uncertain(command, request, scratch, env):
        (Path(scratch) / "stderr.txt").write_text("owned-job cleanup could not be confirmed")
        raise WorkerCleanupError(f"Owned worker cleanup uncertain; recovery directory: {scratch}")

    monkeypatch.setattr(lessons, "execute", uncertain)
    with pytest.raises(WorkerCleanupError, match="recovery directory"):
        lessons.run_comparison()
    remaining = list(tmp_path.glob("softqp-lesson-*/stderr.txt"))
    assert len(remaining) == 1 and "could not be confirmed" in remaining[0].read_text()


def test_adversarial_real_methods_share_the_original_objective(external):
    base = lessons.run_comparison()
    assert [r["state"] for r in base["records"]] == ["accepted"] * 3
    assert all(r["x"] == pytest.approx([2.05, -2.05], abs=1e-7) for r in base["records"])
    assert all(r["objective"] == pytest.approx(-5.1025, abs=1e-7) for r in base["records"])
    quadratic = lessons.run_comparison(linear=0, quadratic=1)
    assert [r["state"] for r in quadratic["records"]] == ["accepted", "accepted", "incompatible"]
    assert quadratic["records"][2]["reason"] and quadratic["records"][2]["x"] is None
    unpriced = lessons.run_comparison(linear=0, quadratic=0)
    assert [r["state"] for r in unpriced["records"]] == ["accepted"] * 3
    assert all(r["x"] == pytest.approx([2.5, -2.5], abs=1e-7) for r in unpriced["records"])
    assert all(r["dimensions"] == dict(variables=2, rows=1, nnz=4) for r in unpriced["records"][1:])
    for mutation in ("duplicate", "null", "negative", "wrong-input", "wrong-worker", "wrong-x", "wrong-cost",
                     "wrong-dimensions", "false-incompatible"):
        bad = copy.deepcopy(base)
        if mutation == "duplicate":
            bad["records"][2] = copy.deepcopy(bad["records"][0])
        elif mutation == "null":
            bad["records"][0]["x"] = None
        elif mutation == "negative":
            bad["records"][0]["kkt_max"] = -1
        elif mutation == "wrong-input":
            bad["input_sha256"] = "0" * 64
        elif mutation == "wrong-worker":
            bad["worker_sha256"] = "0" * 64
        elif mutation == "wrong-x":
            bad["records"][0]["x"][0] += 0.1
        elif mutation == "wrong-dimensions":
            bad["records"][0]["dimensions"]["rows"] += 1
        elif mutation == "false-incompatible":
            bad["records"][0].update(state="incompatible", reason="fabricated unsupported state")
            for name in ("x", "objective", "peak", "hard_violation", "kkt_max", "dimensions"):
                bad["records"][0][name] = None
        else:
            bad["records"][0]["objective"] += 1
        with pytest.raises((ValueError, ValidationError)):
            lessons.validate_envelope(bad, base["input"], base["worker_sha256"])


def test_adversarial_directional_row_unit_covariance(external):
    base = lessons.run_comparison(upper_scale=2)
    for scale in (0.01, 100):
        converted = lessons.run_comparison(upper_scale=2, row_scale=scale)
        for original, current in zip(base["records"], converted["records"]):
            assert current["state"] == original["state"] == "accepted"
            assert current["x"] == pytest.approx(original["x"], abs=1e-6)
            assert current["objective"] == pytest.approx(original["objective"], abs=1e-6)
    different = lessons.run_comparison(upper_scale=4)
    assert abs(different["records"][0]["x"][0] - base["records"][0]["x"][0]) > 0.1


def test_adversarial_coupled_curriculum_and_evidence_identity(tmp_path, monkeypatch):
    original = lessons.AUTHORITY
    summary = lessons.accepted_summary()
    assert summary["primary"]["denominator"] == 144
    assert summary["primary"]["seed_clusters"] == 6
    assert summary["primary"]["failed_pairs"] == 9
    assert summary["primary"]["established"] is False
    import shutil
    shutil.copytree(original, tmp_path / "authority")
    monkeypatch.setattr(lessons, "AUTHORITY", tmp_path / "authority")
    for name in lessons.IDENTITIES:
        path = lessons.AUTHORITY / name
        old = path.read_bytes()
        path.write_bytes(old + b" ")
        with pytest.raises(ValueError, match="authority differs"):
            lessons.authorities()
        path.write_bytes(old)
    assert lessons.accepted_summary() == summary
    for lang in ("en", "es"):
        path = ROOT / f"notebooks/{lang}/01-soft-constraint-decisions/05-directional-group-peaks.ipynb"
        book = json.loads(path.read_text(encoding="utf-8"))
        assert book["metadata"]["caos"]["level"] == 4
        assert book["metadata"]["caos"]["beyond"] == ["BS-2"]
        calls = [c for c in book["cells"] if c["cell_type"] == "code"
                 and "run_comparison(" in "".join(c["source"])]
        assert len(calls) >= 5
        assert all(c["execution_count"] is not None for c in calls)


@pytest.mark.parametrize("mode", ["stdout", "stderr", "timeout", "exit", "descendant"])
def test_adversarial_owned_worker_resource_limits(tmp_path, mode):
    python = os.environ.get("SOFTQP_COUPLED_PYTHON", sys.executable)
    if os.name == "nt":
        if not os.environ.get("SOFTQP_COUPLED_PYTHON"):
            pytest.skip("Local-only: direct native-base external Python required for tree ownership")
        lessons.runtime_identity(python)  # refuse brokered Store launchers; no false cleanup pass
    scratch = tmp_path / mode
    scratch.mkdir()
    pid_file = scratch / "descendant.pid"
    code = {
        "stdout": "import sys;sys.stdout.write('x'*200000);sys.stdout.flush()",
        "stderr": "import sys;sys.stderr.write('x'*200000);sys.stderr.flush()",
        "timeout": "import time;time.sleep(20)",
        "exit": "raise SystemExit(7)",
        "descendant": ("import subprocess,sys,pathlib; p=subprocess.Popen([sys.executable,'-c',"
                       "'import time;time.sleep(20)']);pathlib.Path(" + repr(str(pid_file))
                       + ").write_text(str(p.pid));print('{}')"),
    }[mode]
    control = subprocess.Popen([python, "-c", "import time;time.sleep(30)"])
    start = time.monotonic()
    try:
        if mode == "descendant":
            output = execute([python, "-c", code], b"{}", scratch, os.environ.copy(), timeout=1)
            assert output.strip() == b"{}"
            pid = int(pid_file.read_text())
            if os.name == "nt":
                import ctypes
                api = ctypes.WinDLL("kernel32", use_last_error=True)
                api.OpenProcess.restype = ctypes.c_void_p
                handle = api.OpenProcess(0x1000, False, pid)
                if handle:
                    status = ctypes.c_ulong()
                    api.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(status))
                    api.CloseHandle(ctypes.c_void_p(handle))
                    assert status.value != 259
            else:
                # A reparented zombie is dead even if init has not reaped it yet.
                proc = Path(f"/proc/{pid}/stat")
                assert not proc.exists() or proc.read_text().split()[2] == "Z"
        else:
            with pytest.raises((ValueError, RuntimeError, TimeoutError)):
                execute([python, "-c", code], b"{}", scratch, os.environ.copy(), timeout=0.2)
        assert time.monotonic() - start < 5
        assert control.poll() is None
    finally:
        control.terminate()
        control.wait(timeout=3)
