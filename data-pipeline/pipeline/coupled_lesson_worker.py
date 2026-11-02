"""Isolated SDK2 worker. Only didactic examples; never registered trial generation."""

import hashlib
import importlib.util
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
# -S prevents .pth/sitecustomize/editable import hooks. Append only the selected
# venv's exact site directory; load our named package without a broad source path.
PREFIX = Path(sys.executable).parent.parent.resolve()
SITE = PREFIX / ("Lib/site-packages" if os.name == "nt" else "lib/python3.12/site-packages")
sys.path.append(str(SITE))
package_root = ROOT / "data-pipeline/pipeline"
spec = importlib.util.spec_from_file_location("pipeline", package_root / "__init__.py",
                                            submodule_search_locations=[str(package_root)])
package = importlib.util.module_from_spec(spec)
sys.modules["pipeline"] = package
spec.loader.exec_module(package)

from pipeline.coupled_lessons import canonical, runtime_identity, strict_json, validate_input  # noqa: E402


def work(request):
    validate_input(request)
    _, _, admitted = runtime_identity(sys.executable)
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12):
        raise ValueError("The lesson worker requires the reviewed direct CPython3.12 runtime")
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes as w

        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenJobObjectW.argtypes = [w.DWORD, w.BOOL, w.LPCWSTR]
        api.OpenJobObjectW.restype = w.HANDLE
        api.GetCurrentProcess.restype = w.HANDLE
        api.IsProcessInJob.argtypes = [w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)]
        api.CloseHandle.argtypes = [w.HANDLE]
        job = api.OpenJobObjectW(4, False, os.environ.get("SOFTQP_LESSON_JOB", ""))
        if not job:
            raise ValueError("The worker cannot open its caller-owned job")
        try:
            inside = w.BOOL()
            if not api.IsProcessInJob(api.GetCurrentProcess(), job, ctypes.byref(inside)) or not inside.value:
                raise ValueError("The actual worker escaped the caller-owned job")
        finally:
            api.CloseHandle(job)
        physical = ctypes.create_unicode_buffer(32768)
        if not api.GetModuleFileNameW(None, physical, len(physical)):
            raise ValueError("Cannot identify actual direct Python executable")
        if Path(physical.value).resolve() != Path(sys._base_executable).resolve():
            raise ValueError("Actual Python image differs from admitted direct base")
    import numpy as np
    from scipy import sparse
    from softqp.peak import PeakGroup, PeakProblem, solve_peak
    from softqp.solvers import UnsupportedProblemError
    from pipeline.coupled_accuracy import accept

    for name, module in list(sys.modules.items()):
        if name == "softqp" or name.startswith("softqp."):
            origin = Path(module.__file__).resolve()
            expected = admitted.get(str(origin))
            if expected is None or hashlib.sha256(origin.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Actual SDK import origin differs from admitted public wheel: {name}")

    d = request["row_scale"]
    problem = PeakProblem(
        sparse.eye(2, format="csc"), np.array([-3, 2]),
        sparse.csc_matrix([[d, 0], [0, d], [1, 1]]),
        np.array([-d, -d, 0]), np.array([d, d, 0]),
        (PeakGroup(np.array([0, 1]), lower_scale=np.array([1, 1.5])/d,
                   upper_scale=np.array([request["upper_scale"], 1])/d,
                   linear=request["linear"], quadratic=request["quadratic"]),))
    records = []
    for method in ("native", "epigraph", "row-split-gsp"):
        record = dict(method=method, state="failed", reason="No solution candidate", x=None,
                      objective=None, peak=None, hard_violation=None, kkt_max=None, dimensions=None)
        try:
            result = solve_peak(problem, method, eps_abs=1e-9, eps_rel=1e-9, max_iter=200000,
                                alpha=1, adaptive_rho=False, scaling=0)
            checked = accept(problem, result)
            record.update(state=checked["state"], reason=checked["reason"])
            if checked["metrics"] is not None:
                metrics = checked["metrics"]
                record.update(x=result["x"], objective=metrics["objective"], peak=metrics["peaks"][0],
                              hard_violation=metrics["hard_violation"], dimensions=result["dimensions"],
                              kkt_max=max(metrics[k] for k in
                                          ("stationarity", "fenchel", "dual_domain", "dual_repair")))
        except UnsupportedProblemError as error:
            record.update(state="incompatible", reason=str(error))
        records.append(record)
    return dict(schema_version="softqp.coupled-lesson/v1", sdk_version="0.2.0", input=request,
                input_sha256=hashlib.sha256(canonical(request)).hexdigest(), records=records,
                worker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


if __name__ == "__main__":
    raw = sys.stdin.buffer.read(4097)
    if len(raw) > 4096:
        raise ValueError("Lesson request exceeds4KiB")
    sys.stdout.buffer.write(canonical(work(strict_json(raw))))
