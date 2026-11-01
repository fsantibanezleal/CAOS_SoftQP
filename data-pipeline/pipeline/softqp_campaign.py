"""Preregistered paired CPU campaign with preserved failures and bounded workers."""

import csv
import ctypes
import hashlib
import itertools
import json
import multiprocessing as mp
import os
from pathlib import Path
import time
import numpy as np
from scipy import sparse
from softqp.problem import Problem, Penalty
from .environment import environment
from .experiment_common import METHODS, cold_observation, oracle
from .softqp_requests import encode_problem

ROOT = Path(__file__).resolve().parents[2]


def generated_problem(spec):
    """Vary P's condition without changing A, q, costs or bounds within a seed."""
    n, density = spec["n"], spec["density"]
    m = 2 * n
    rng = np.random.default_rng(np.random.SeedSequence([spec["seed"], n, round(density * 10000)]))
    A = sparse.random(m, n, density=density, format="lil", random_state=rng,
                      data_rvs=lambda size: rng.normal(size=size))
    for row in range(m):
        if not A.rows[row]:
            A[row, row % n] = 1.0
    A = A.tocsr()
    lengths = np.sqrt(A.multiply(A).sum(axis=1)).A1
    A = (sparse.diags(1.0 / lengths) @ A).tocsc()
    q = rng.normal(size=n) * 3.0
    linear = rng.uniform(0.1, 1.0, m)
    quadratic = rng.uniform(0.5, 4.0, m)
    factor = rng.uniform(1.5, 3.0, m)
    asymmetric = spec["family"] != "symmetric-elastic"
    pure_l1 = spec["family"] == "asymmetric-l1"
    soft = np.ones(m, dtype=bool)
    if not pure_l1:
        soft[:int(0.2 * m)] = False
    if pure_l1:
        quadratic[:] = 0
    p = Penalty(linear, linear * factor if asymmetric else linear.copy(), quadratic,
                quadratic * factor if asymmetric else quadratic.copy(), soft)
    return Problem(sparse.diags(np.geomspace(1.0, spec["condition"], n), format="csc"), q, A,
                   np.full(m, -0.4), np.full(m, 0.6), p)


def instances(protocol, split):
    generator = protocol["generator"]
    if split == "robustness":
        r = protocol["robustness"]
        grid = itertools.product([r["n"]], [r["density"]], r["hessian_condition"],
                                 ["asymmetric-elastic"], protocol["seeds"][split])
    else:
        grid = itertools.product(generator["n"], generator["density"], generator["hessian_condition"],
                                 generator["families"], protocol["seeds"][split])
    return [dict(id=f"{split}-{i:04}", split=split, n=n, density=density, condition=condition,
                 family=family, seed=seed) for i, (n, density, condition, family, seed) in enumerate(grid)]


def worker(connection):
    # Import and shared-library initialization are outside every timed observation.
    while True:
        task = connection.recv()
        if task is None:
            return
        problem, method, objective = task
        observation = cold_observation(problem, method, objective)
        result = observation.pop("result")
        metrics = observation["metrics"]
        if metrics:
            observation["metrics"] = {
                k: metrics[k] for k in ("objective", "base_objective", "penalty_objective",
                                        "hard_violation", "stationarity_residual")
            }
            observation["metrics"]["total_lower_violation"] = sum(metrics["lower_violation"])
            observation["metrics"]["total_upper_violation"] = sum(metrics["upper_violation"])
        observation.update(
            iterations=result["iterations"] if result else None,
            dimensions=result["dimensions"] if result else None,
            native_setup_seconds=result["setup_seconds"] if result else None,
            native_solve_seconds=result["solve_seconds"] if result else None,
            status=result["status"] if result else None,
            status_code=result["status_code"] if result else None,
        )
        connection.send(observation)


def process_memory(pid):
    """Current RSS and OS-observed high-water mark, in bytes, for one worker."""
    if os.name == "nt":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")
            ]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        info = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
        info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
        if not handle:
            raise OSError(ctypes.get_last_error(), "Cannot inspect campaign worker memory")
        try:
            data = Counters()
            data.cb = ctypes.sizeof(data)
            if not info(handle, ctypes.byref(data), data.cb):
                raise OSError(ctypes.get_last_error(), "Cannot read worker RSS")
            return int(data.WorkingSetSize), int(data.PeakWorkingSetSize)
        finally:
            kernel.CloseHandle(handle)
    fields = {}
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith(("VmRSS:", "VmHWM:")):
            key, value, _ = line.split()
            fields[key.rstrip(":")] = int(value) * 1024
    return fields["VmRSS"], fields["VmHWM"]


class BoundedWorker:
    def __init__(self, limits):
        self.limits = limits
        self.process = None
        self.peak_rss = 0
        self.restarts = 0

    def start(self):
        parent, child = mp.get_context("spawn").Pipe()
        self.connection = parent
        self.process = mp.get_context("spawn").Process(target=worker, args=(child,), daemon=True)
        self.process.start()
        child.close()

    def close(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(5)
            self.connection.close()
            self.process = None

    def observe(self, problem, method, objective, deadline):
        if self.process is None:
            self.start()
        start = time.monotonic()
        self.connection.send((problem, method, objective))
        reason = None
        state = "failed"
        while not self.connection.poll(0.01):
            if not self.process.is_alive():
                reason = f"Worker exited with code {self.process.exitcode}"
                break
            rss, high = process_memory(self.process.pid)
            self.peak_rss = max(self.peak_rss, rss, high)
            if rss > self.limits["process_memory_limit_bytes"]:
                reason, state = "Worker RSS exceeded registered limit", "resource-limit"
                break
            if time.monotonic() - start > self.limits["trial_timeout_seconds"]:
                reason, state = "Trial exceeded registered wall limit", "timeout"
                break
            if time.monotonic() > deadline:
                reason, state = "Campaign wall limit reached", "resource-limit"
                break
        if reason is None:
            try:
                observation = self.connection.recv()
                rss, high = process_memory(self.process.pid)
                self.peak_rss = max(self.peak_rss, rss, high)
                return observation
            except (EOFError, BrokenPipeError) as error:
                reason = f"Worker communication failed: {type(error).__name__}"
        self.close()
        self.restarts += 1
        return dict(state=state, reason=reason, elapsed_seconds=None, metrics=None, normalized_gap=None,
                    update_seconds=None, workspace_setup_seconds=None, iterations=None, dimensions=None,
                    native_setup_seconds=None, native_solve_seconds=None, status=None, status_code=None)


def primary_endpoint(records, protocol):
    """Pair by instance/repetition, then resample whole evaluation-seed clusters."""
    endpoint = protocol["primary_endpoint"]
    subset = [r for r in records if not r["warmup"] and r["split"] == "heldout"
              and r["family"] == endpoint["family"] and r["n"] >= endpoint["n_minimum"]
              and r["density"] == endpoint["density"] and r["method"] in ("lifted", "daqp", "asymmetric")]
    groups = {}
    for row in subset:
        groups.setdefault((row["id"], row["repetition"]), {})[row["method"]] = row
    values = {}
    rejected = 0
    for group in groups.values():
        if len(group) != 3 or any(r["state"] != "accepted" for r in group.values()):
            rejected += 1
            continue
        baseline = min(group[m]["elapsed_seconds"] for m in ("lifted", "daqp"))
        reduction = 1.0 - group["asymmetric"]["elapsed_seconds"] / baseline
        values.setdefault(group["asymmetric"]["seed"], []).append(reduction)
    if not values:
        return dict(state="not-established", median_relative_reduction=None, confidence_interval_95=None,
                    paired_samples=0, rejected_pairs=rejected, seed_clusters=0)
    clusters = list(values.values())
    rng = np.random.default_rng(protocol["seeds"]["bootstrap"])
    samples = [float(np.median(np.concatenate([clusters[i] for i in rng.integers(len(clusters), size=len(clusters))])))
               for _ in range(protocol["repetitions"]["bootstrap_seed_clusters"])]
    median = float(np.median(np.concatenate(clusters)))
    interval = np.quantile(samples, [0.025, 0.975]).tolist()
    passed = rejected == 0 and median >= endpoint["minimum_reduction"] and interval[0] > 0
    return dict(state="met" if passed else "not-established", median_relative_reduction=median,
                confidence_interval_95=interval, paired_samples=sum(map(len, clusters)), rejected_pairs=rejected,
                seed_clusters=len(clusters))


def summarize(records, protocol):
    groups = {}
    measured = [r for r in records if not r["warmup"]]
    for r in measured:
        key = (r["split"], r["family"], r["method"], r["n"], r["density"], r["condition"])
        groups.setdefault(key, []).append(r)
    cells = []
    for key, rows in groups.items():
        accepted = [r for r in rows if r["state"] == "accepted"]
        elapsed = [r["elapsed_seconds"] for r in accepted]
        cells.append(dict(zip(("split", "family", "method", "n", "density", "condition"), key)) | dict(
            counts={state: sum(r["state"] == state for r in rows) for state in sorted({r["state"] for r in rows})},
            median_seconds=float(np.median(elapsed)) if elapsed else None,
            quantile_25_seconds=float(np.quantile(elapsed, 0.25)) if elapsed else None,
            quantile_75_seconds=float(np.quantile(elapsed, 0.75)) if elapsed else None,
            max_normalized_gap=max((r["normalized_gap"] for r in accepted), default=None),
            max_hard_violation=max((r["metrics"]["hard_violation"] for r in accepted), default=None),
        ))
    return dict(cells=cells, primary_endpoint=primary_endpoint(records, protocol),
                counts={s: sum(r["state"] == s for r in measured) for s in sorted({r["state"] for r in measured})})


def run_campaign(output, splits=("development", "heldout", "robustness")):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if any((output / name).exists() for name in ("trials.jsonl", "campaign.json")):
        raise FileExistsError("Choose a fresh output directory; prior trial evidence is never overwritten")
    protocol_path = ROOT / "docs/design/experiments-v1.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    provenance = environment()
    if provenance["engine_revision"] != protocol["engine_source"] or provenance["engine_source_dirty"] is not False:
        raise RuntimeError("Campaign requires the exact clean preregistered native engine source")
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(name) != "1":
            raise RuntimeError(f"{name} must be set to 1 before Python imports NumPy")
    started = time.monotonic()
    deadline = started + protocol["operating_limits"]["wall_seconds"]
    runner = BoundedWorker(protocol["operating_limits"])
    order = np.random.default_rng(protocol["seeds"]["order"])
    records, datasets = [], []
    plan = [spec for split in splits for spec in instances(protocol, split)]
    try:
        with (output / "trials.jsonl").open("w", encoding="utf-8") as raw:
            for number, spec in enumerate(plan):
                start = time.perf_counter()
                problem = generated_problem(spec)
                generation_seconds = time.perf_counter() - start
                serialized = json.dumps(encode_problem(problem), sort_keys=True, separators=(",", ":"))
                dataset = dict(**spec, generation_seconds=generation_seconds,
                               problem_sha256=hashlib.sha256(serialized.encode()).hexdigest())
                # Use the bounded worker for the oracle as well; its timeout is retained for the instance.
                # A stock oracle call has its own process so it cannot strand the campaign.
                reference = bounded_oracle(problem, protocol["operating_limits"], deadline)
                dataset["oracle_state"] = reference["state"]
                dataset["oracle_reason"] = reference.get("reason")
                dataset["oracle_objective"] = reference.get("objective")
                datasets.append(dataset)
                for repetition in range(-protocol["repetitions"]["warmup_per_backend"],
                                        protocol["repetitions"]["measured"]):
                    for method in order.permutation(METHODS).tolist():
                        if reference["state"] == "accepted" and time.monotonic() < deadline:
                            observed = runner.observe(problem, method, reference["objective"], deadline)
                        else:
                            observed = dict(state="oracle-failed" if reference["state"] != "accepted" else "resource-limit",
                                            reason=reference.get("reason") or "Campaign wall limit reached",
                                            elapsed_seconds=None, metrics=None, normalized_gap=None, result=None)
                        record = dict(**spec, method=method, repetition=repetition, warmup=repetition < 0, **observed)
                        records.append(record)
                        raw.write(json.dumps(record, allow_nan=False) + "\n")
                    raw.flush()
                print(f"{number + 1}/{len(plan)} {spec['id']} n={spec['n']} {spec['family']} "
                      f"condition={spec['condition']} elapsed={time.monotonic() - started:.1f}s", flush=True)
    finally:
        runner.close()
    (output / "datasets.json").write_text(json.dumps(datasets, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (output / "trials.csv").open("w", newline="", encoding="utf-8") as handle:
        columns = ["id", "split", "seed", "n", "density", "condition", "family", "method", "repetition",
                   "warmup", "state", "reason", "elapsed_seconds", "normalized_gap", "iterations"]
        writer = csv.DictWriter(handle, columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    document = dict(schema_version="softqp.campaign/v1", protocol=protocol, environment=provenance,
                    protocol_sha256=hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
                    source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
                        "data-pipeline/pipeline/softqp_campaign.py", "data-pipeline/pipeline/experiment_common.py")},
                    observed_wall_seconds=time.monotonic() - started, worker_peak_rss_bytes=runner.peak_rss,
                    worker_restarts=runner.restarts, planned_instances=len(plan), completed_instances=len(datasets),
                    **summarize(records, protocol),
                    artifacts=[dict(path=name, bytes=(output / name).stat().st_size,
                                    sha256=hashlib.sha256((output / name).read_bytes()).hexdigest())
                               for name in ("trials.jsonl", "trials.csv", "datasets.json")])
    (output / "campaign.json").write_text(json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return document


def oracle_worker(connection, problem):
    try:
        _, objective = oracle(problem)
        connection.send(dict(state="accepted", objective=objective))
    except Exception as error:
        connection.send(dict(state="oracle-failed", reason=f"{type(error).__name__}: {error}"))


def bounded_oracle(problem, limits, deadline):
    parent, child = mp.get_context("spawn").Pipe()
    process = mp.get_context("spawn").Process(target=oracle_worker, args=(child, problem), daemon=True)
    process.start()
    child.close()
    start = time.monotonic()
    try:
        while not parent.poll(0.01):
            if not process.is_alive():
                return dict(state="oracle-failed", reason=f"Oracle worker exited {process.exitcode}")
            rss, _ = process_memory(process.pid)
            if rss > limits["process_memory_limit_bytes"]:
                return dict(state="oracle-failed", reason="Oracle memory limit")
            if time.monotonic() - start > limits["trial_timeout_seconds"] or time.monotonic() > deadline:
                return dict(state="oracle-failed", reason="Oracle time limit")
        return parent.recv()
    finally:
        if process.is_alive():
            process.terminate()
        process.join(5)
        parent.close()
