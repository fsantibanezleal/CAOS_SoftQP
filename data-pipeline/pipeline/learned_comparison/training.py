"""Source-bound product orchestration for the published SoftQP learning SDK."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import math
import os
from pathlib import Path
import secrets
import struct
import time

from . import contracts as c
from . import native_labels as native
from . import phase_inputs as phase
from . import stream_inputs as stream
from . import training_worker as worker

METHODS = ("learned_osqp", "learned_daqp")
PARTS = worker._PARTS
RUN = "learning-training-run/1.0.0"
FROZEN = "learning-frozen-inference/1.0.0"
CALIBRATION = "learning-stream-calibration/2.0.0"
_LIMIT = 8 * 2**30


LEARNING_REQUEST = "softqp.r4.learning-request/1"
LEARNING_POLICY = "softqp.r4.learning-policy/1"
_JOB_SECONDS = 48 * 3600
_MIN_FREE = 20 * 2**30


def _shape(value, expected, reason):
    c.ensure(type(value) is dict and set(value) == expected, reason)
    return value


def _checked_scope_file(parent, ref):
    _shape(ref, {"path", "sha256"}, "invalid governed receipt reference")
    phase._hash(ref["sha256"])
    return _read_ref(parent, ref)


@dataclass(frozen=True)
class _RegisteredRuntime:
    custody: object
    operation: str
    request_sha256: str
    profile_sha256: str
    policy_sha256: str
    output_root: Path

    @property
    def sha256(self):
        return self.profile_sha256

    def verify(self):
        from softqp_runtime_custody import read_active_learning_policy

        raw = read_active_learning_policy(
            self.custody,
            operation=self.operation,
            request_sha256=self.request_sha256,
            source_file=Path(__file__).resolve(),
            profile_sha256=self.profile_sha256,
        )
        _equal(c.digest(raw), self.policy_sha256, "reviewed owned learning policy changed")
        return c.strict_loads(raw)

    def open_worker(self, root, nonce, expected_boot_sha256):
        from softqp_runtime_custody import open_learning_worker

        self.verify()
        return open_learning_worker(
            self.custody,
            operation=self.operation,
            request_sha256=self.request_sha256,
            source_file=Path(__file__).resolve(),
            root=root,
            nonce=nonce,
            expected_boot_sha256=expected_boot_sha256,
        )


class LearningBudget:
    """Measure only independently declared scientific artifact roots, once per physical file."""

    def __init__(self, roots, job, *, prior_seconds=0.0, committed_bytes=0, started=None):
        import shutil

        self.roots = tuple(sorted({phase._exact_directory(Path(p)) for p in roots}, key=str))
        c.ensure(bool(self.roots), "independent artifact accounting roots required")
        _equal(job.parent.resolve(strict=True), job.parent, "learning workspace path alias")
        c.ensure(any(job.is_relative_to(root) for root in self.roots), "job outside accounted roots")
        c.ensure(shutil.disk_usage(job.parent).free >= _MIN_FREE, "learning workspace below 20 GiB free")
        self.started = time.monotonic() if started is None else started
        self.prior_seconds = prior_seconds
        c.ensure(
            type(committed_bytes) is int and 0 <= committed_bytes <= _LIMIT,
            "invalid independently measured committed artifact size",
        )
        self.committed_bytes = committed_bytes
        self.deadline = self.started + _JOB_SECONDS - prior_seconds
        self.high_water = 0
        self.check()

    def check(self, extra_bytes=0):
        c.ensure(time.monotonic() < self.deadline, "cumulative learning-job deadline exceeded")
        seen, total = set(), self.committed_bytes
        for root in self.roots:
            for path in root.rglob("*"):
                info = phase._path_stat(path)
                if path.is_file() and (info.st_dev, info.st_ino) not in seen:
                    seen.add((info.st_dev, info.st_ino))
                    total += info.st_size
        self.high_water = max(self.high_water, total + extra_bytes)
        c.ensure(total + extra_bytes <= _LIMIT, "aggregate learning artifact disk budget exceeded")
        return total


def _equal(value, expected, message):
    c.ensure(value == expected, message)


def _json_ref(path, value):
    raw = c.canonical_bytes(value)
    worker.publish(path, raw)
    return dict(path=path.name, sha256=c.digest(raw))


def _json_file(root, ref):
    raw = _read_ref(root, ref)
    doc = c.strict_loads(raw)
    _equal(raw, c.canonical_bytes(doc), "noncanonical learning receipt")
    return doc


def _read_ref(root, ref):
    path = root.joinpath(*phase._path_parts(ref["path"]))
    phase._path_stat(path)
    _equal(path.resolve(strict=True).parts, path.parts, "learning file path alias")
    raw = path.read_bytes()
    _equal(c.digest(raw), ref["sha256"], "learning stored bytes differ")
    if "bytes" in ref:
        _equal(len(raw), ref["bytes"], "learning numeric byte count differs")
    return raw


@dataclass(frozen=True)
class FixtureRuntime:
    """Explicit excluded-control runtime. Scientific launch is a separate reviewed capability."""

    raw: bytes
    sha256: str

    @classmethod
    def load(cls, path, *, expected_sha256):
        raw = Path(path).read_bytes()
        _equal(c.digest(raw), expected_sha256, "independent fixture runtime digest differs")
        result = cls(raw, expected_sha256)
        result.verify()
        return result

    def verify(self):
        _equal(c.digest(self.raw), self.sha256, "fixture runtime authority digest differs")
        spec = c.strict_loads(self.raw)
        _equal(spec["lane"], "excluded-software-fixture", "runtime is outside fixture lane")
        for name in ("python", "base_python", "python_dll", "wheel"):
            path = Path(spec["runtime"][name])
            c.ensure(path.is_absolute(), "runtime path must be absolute")
            _equal(native._file_sha(path), spec["runtime"][name + "_sha256"], "runtime file identity differs")
        pipeline = Path(__file__).parent
        names = {
            "training.py",
            "training_worker.py",
            "native_labels.py",
            "stream_inputs.py",
            "phase_inputs.py",
            "contracts.py",
        }
        _equal(set(spec["product_sources"]), names, "fixture source inventory differs")
        for name in names:
            _equal(
                native._file_sha(pipeline / name),
                spec["product_sources"][name],
                "fixture product source differs",
            )
        return spec


def _readers(p1, role, proofs, fixture):
    c.ensure(isinstance(role, stream.StreamingPhaseReader), "expected a strict v2 role reader")
    _equal(role.preflight_sha256, p1, "training phase points to another preflight")
    _equal(role.fixture_only, fixture, "training fixture policy differs")
    proof = proofs.get(role.role)
    if proof is not None:
        c.ensure(isinstance(proof, native.NativeRoleProof), "expected actual native role proof")
        _equal(
            (proof.trust.role, proof.trust.labeled_preflight_sha256),
            (role.role, p1),
            "native role proof differs",
        )


def _expected_phase(receipt, reader):
    records = {
        row["ref"]["artifact_id"]: row["ref"] for row in receipt["records"] if row["role"] == reader.role
    }
    _equal(
        {k: dict(row["ref"]) for k, row in reader._records.items()},
        records,
        "role physical inventory reduced",
    )
    logical = {
        (row["frame_id"], row["representation"]): row["logical_sha256"]
        for row in receipt["logical"]
        if row["role"] == reader.role
    }
    _equal(dict(reader._logical), logical, "role logical inventory reduced")
    _equal(dict(reader._descriptor), receipt["descriptor"], "role descriptor identity differs")
    _equal(
        dict(reader._normalizers),
        {row["head_id"]: c.canonical_bytes(row) for row in receipt["normalizers"]},
        "role normalizer inventory differs",
    )
    expected_labels = {row["frame_id"]: row for row in receipt["labels"] if row["role"] == reader.role}
    actual_labels = {key: dict(row) for key, row in reader._labels.items()}
    _equal(actual_labels, expected_labels, "role label slots differ")


@dataclass(frozen=True)
class TrainingPlan:
    context: c.AdmissionContext
    protocol_ref: c.Reference
    p1: object
    train: stream.StreamingPhaseReader
    validation: stream.StreamingPhaseReader
    proofs: object
    fixture_policy: bytes | None
    authority: object = None

    @classmethod
    def admit(
        cls,
        authority,
        *,
        context,
        protocol_ref,
        labeled_preflight,
        expected_preflight_sha256,
        train,
        validation,
        native_role_proofs,
        expected_policy_sha256,
        fixture_policy=None,
    ):
        _equal(labeled_preflight.sha256, expected_preflight_sha256, "independently expected P1 differs")
        receipt = c.strict_loads(labeled_preflight.receipt_bytes)
        _equal(receipt["protocol_ref"], protocol_ref, "role protocol identity differs")
        _equal((train.role, validation.role), ("train", "validation"), "wrong training roles")
        if context.allow_fixture:
            c.ensure(fixture_policy is not None, "independent excluded training policy required")
            _equal(c.digest(fixture_policy), expected_policy_sha256, "independent fixture policy differs")
            policy = c.strict_loads(fixture_policy)
            _equal(policy["lane"], "excluded-software-fixture", "fixture policy lane differs")
            _equal(policy["p1"], expected_preflight_sha256, "fixture policy scope differs")
            _equal(
                policy["phases"],
                {"train": train.manifest_sha256, "validation": validation.manifest_sha256},
                "fixture independently expected phase differs",
            )
        else:
            from .authority import require_i1

            c.ensure(fixture_policy is None, "scientific training cannot use a fixture policy")
            require_i1(authority, "train-model", context=context, protocol_ref=protocol_ref)
            _equal(
                receipt["identities"]["learning_policy_sha256"],
                expected_policy_sha256,
                "scientific learning-policy digest differs",
            )
        for reader in (train, validation):
            _readers(labeled_preflight.sha256, reader, native_role_proofs, context.allow_fixture)
            _expected_phase(receipt, reader)
        return cls(
            context,
            dict(protocol_ref),
            labeled_preflight,
            train,
            validation,
            dict(native_role_proofs),
            fixture_policy,
            authority,
        )


def _inventory(readers, proofs, method):
    representation = "mlp-v1" if method == "learned_osqp" else "graph-v1"
    inventory, locations = {}, {}
    for reader in readers:
        groups = {}
        current = set()
        proof = proofs.get(reader.role)
        if method == "learned_daqp":
            c.ensure(
                isinstance(proof, native.NativeRoleProof), "native label proof required for graph training"
            )
        for frame_id, kind in reader.logical_keys:
            if kind != representation:
                continue
            problem = reader.read_problem(frame_id)
            source = problem["source"]
            t = problem["transform"]
            head = f"H-{t['n']}-{t['m']}" if method == "learned_osqp" else "graph"
            c.ensure((reader.role, frame_id) not in locations, "duplicate frame")
            key = (source["source_id"], source["parent_id"], problem["original_sha256"])
            current.add(key)
            group = groups.setdefault(
                source["source_id"],
                {
                    "source_id": source["source_id"],
                    "family": source["family"],
                    "regime": source["regime"],
                    "frames": [],
                    "count": source["frame_count"],
                    "head": head,
                    "parent": source["parent_id"],
                },
            )
            _equal(
                (group["head"], group["parent"], group["family"], group["regime"], group["count"]),
                (head, source["parent_id"], source["family"], source["regime"], source["frame_count"]),
                "source frames change group identity",
            )
            if method == "learned_daqp":
                _equal(
                    proof.verify(reader, frame_id)["state"], "accepted", "required graph label unavailable"
                )
            group["frames"].append((source["frame"], frame_id))
            locations[(reader.role, frame_id)] = head
        previous = locations.get(("role", "train"), ())
        if reader.role != "train":
            for offset in range(3):
                c.ensure(
                    not ({key[offset] for key in current} & {key[offset] for key in previous}),
                    "source, parent or original overlap crosses training roles",
                )
        locations[("role", reader.role)] = current
        inventory[reader.role] = []
        for group in sorted(groups.values(), key=lambda item: item["source_id"]):
            frames = sorted(group.pop("frames"))
            _equal([i for i, _ in frames], list(range(group.pop("count"))), "incomplete whole-source frames")
            inventory[reader.role].append({**group, "frames": [frame_id for _, frame_id in frames]})
        c.ensure(inventory[reader.role], "no eligible role source")
    return inventory, locations


def _boot(owned_root, runtime, spec, task, *, permit_scope=None):
    if permit_scope is not None:
        nonce = secrets.token_hex(16)
        task = {**task, "permit_scope": permit_scope}
        boot = {
            "nonce": nonce,
            "task": task,
            "authority": {
                "operation": runtime.operation,
                "request_sha256": runtime.request_sha256,
                "policy_sha256": runtime.policy_sha256,
                "profile_sha256": runtime.profile_sha256,
            },
        }
        return runtime.open_worker(owned_root, nonce, c.digest(c.canonical_bytes(boot))), boot
    nonce = secrets.token_hex(16)
    source = Path(worker.__file__).resolve()
    executable = Path(spec["runtime"]["python"])
    command = [
        str(executable),
        "-I",
        "-S",
        "-B",
        "-X",
        f"pycache_prefix={owned_root / 'unused-cache'}",
        str(source),
        str(owned_root),
        nonce,
    ]
    child = native._OwnedWorker(owned_root, command, executable, nonce=nonce)
    return child, {
        "nonce": nonce,
        "native_sha256": spec["product_sources"]["native_labels.py"],
        "runtime": spec["runtime"],
        "task": task,
    }


def _serve(child, boot, service, deadline, *, distributions=45):
    from ..coupled_resources import process_memory

    root = child.root
    _json_ref(root / "boot.json", boot)
    installed = child.wait_file(root / "installed.json", 600)
    c.ensure(
        installed["pid"] in child._pids()
        and installed["nonce"] == boot["nonce"]
        and installed["audit"]["full_files"] is True
        and installed["audit"]["distributions"] == distributions,
        "invalid owned installed-file custody",
    )
    _json_ref(root / "import-ack.json", {"installed_sha256": worker.digest(installed)})
    ready = child.wait_file(root / "ready.json", 180)
    _equal((ready["pid"], ready["nonce"]), (installed["pid"], boot["nonce"]), "invalid SDK import custody")
    index = 0
    peak = 0
    while True:
        path = root / f"event-{index:07d}.json"
        event = child.wait_file(path, deadline - time.monotonic())
        _, parent_peak = process_memory(os.getpid())
        peak = max(peak, parent_peak + child.peak_rss)
        c.ensure(peak <= _LIMIT, "training combined RSS budget exceeded")
        _equal(
            (event["index"], event["nonce"]), (index, boot["nonce"]), "owned worker event sequence differs"
        )
        operation, payload = event["operation"], event["payload"]
        response = service(operation, payload) if operation not in ("complete", "failed") else None
        _json_ref(
            root / f"reply-{index:07d}.json", {"event_sha256": worker.digest(event), "payload": response}
        )
        path.unlink()
        index += 1
        if operation in ("complete", "failed"):
            _equal(child.process.wait(timeout=30), 0, "owned SDK worker did not exit cleanly")
            return operation, payload, {"installed": installed, "ready": ready, "peak_rss_bytes": peak}


def _frame_packet(readers, proofs, locations, method, payload, head):
    role, frame_id = payload["role"], payload["frame_id"]
    c.ensure(
        role in readers and locations.get((role, frame_id)) == head, "SDK requested an unadmitted role/frame"
    )
    reader = readers[role]
    problem = reader.read_problem(frame_id)
    representation = "mlp-v1" if method == "learned_osqp" else "graph-v1"
    feature = reader.read_feature(frame_id, representation).document
    _equal(feature["transform_sha256"], problem["transform_sha256"], "frame/feature transform differs")
    packet = {"transform": problem["transform"]}
    if method == "learned_osqp":
        parity = {
            "raw": [float(v) or 0.0 for v in feature["raw_values"]],
            "normalized": [float(v) or 0.0 for v in feature["values"]],
        }
    else:
        result = proofs[role].verify(reader, frame_id)
        _equal(result["state"], "accepted", "native graph label does not qualify")
        values = result["label"]["payload"]
        packet["label"] = {"labels": values["labels"], "mask": values["mask"]}
        graph = feature["graph"]
        parity = {
            "node_features": [[float(v) or 0.0 for v in row] for row in graph["node_features"]],
            "edge_weight": [float(v) or 0.0 for v in graph["edge_weight"]],
            "edge_index": graph["edge_index"],
            "row_map": graph["row_map"],
        }
    packet["feature_sha256"] = worker.digest(parity)
    return packet


def _snapshot_hash(parts):
    hasher = hashlib.sha256()
    for name in PARTS:
        blob = parts[name]
        hasher.update(len(blob).to_bytes(8, "little"))
        hasher.update(blob)
    return hasher.hexdigest()


def _snapshot_parts(root, snapshot):
    _equal(set(snapshot["files"]), set(PARTS), "SDK resume part inventory differs")
    parts = {name: _read_ref(root, snapshot["files"][name]) for name in PARTS}
    _equal(_snapshot_hash(parts), snapshot["snapshot_sha256"], "SDK length-prefixed resume digest differs")
    return parts


class EpochStore:
    def __init__(self, root, work, heads, seed, method):
        self.root, self.work, self.heads, self.seed, self.method = root, work, heads, seed, method
        self.latest = {}
        self.journal = []
        self.bytes_kept = 0

    def capture(self, message):
        import json

        head = message["head"]
        c.ensure(head in self.heads, "worker emitted an undeclared head")
        epoch = message["epoch"]
        previous = self.latest.get(head)
        _equal(epoch, previous["epoch"] + 1 if previous else 0, "epoch sequence differs")
        incoming = message["files"]
        _equal(
            [incoming[key]["path"] for key in PARTS],
            [f"snapshot-{key}.{suffix}" for key, suffix in PARTS.items()],
            "SDK staging file paths differ",
        )
        source = _snapshot_parts(self.work, message)
        metadata = json.loads(source["metadata"])
        identity = metadata["identity"]
        _equal(
            (identity["head"], identity["seed"], identity["source_sha256"], identity["method"]),
            (
                head,
                self.seed,
                self.heads[head]["source_sha256"],
                "L-1" if self.method == "learned_osqp" else "L-2",
            ),
            "SDK head resume identity differs",
        )
        _equal(metadata["history"][-1]["epoch"], epoch, "SDK observed history epoch differs")
        size = sum(math.prod(shape) * 8 for _, shape in identity["parameters"])
        _equal(
            [len(source[k]) for k in ("initial", "current", "best")], [size] * 3, "SDK weight shape differs"
        )
        _equal(len(source["moments"]), size * 2 if epoch else 0, "SDK native moment shape differs")
        if previous:
            _equal(
                c.digest(source["initial"]),
                previous["files"]["initial"]["sha256"],
                "immutable head initialization differs",
            )
            _equal(
                message["initial_train_objective"],
                previous["initial_train_objective"],
                "measured baseline changed",
            )
        retained = dict(message, files={})
        for part, raw in source.items():
            if part == "initial" and previous:
                retained["files"][part] = previous["files"][part]
            else:
                suffix = PARTS[part]
                name = f"{head}-{epoch:03d}-{part}.{suffix}"
                file = self.root / name
                worker.publish(file, raw)
                retained["files"][part] = {"path": name, "sha256": c.digest(raw), "bytes": len(raw)}
                self.bytes_kept += len(raw)
        c.ensure(self.bytes_kept <= _LIMIT, "owned training artifact disk budget exceeded")
        _snapshot_parts(self.root, retained)
        record = {
            "snapshot": retained,
            "prior": self.journal[-1] if self.journal else None,
            "epoch_zero_projection": {
                "train_baseline": "measured-no-update",
                "moment_buffers": "derived-zero-step",
            },
        }
        commit = _json_ref(self.root / f"epoch-{head}-{epoch:03d}.json", record)
        self.journal.append(commit)
        pointer = self.root / f"{head}-latest.json"
        pending = self.root / f"{head}-pointer-{epoch:03d}.json"
        _json_ref(pending, commit)
        if previous:
            _equal(c.strict_loads(pointer.read_bytes()), previous["commit"], "owned latest pointer replaced")
            os.replace(pending, pointer)
        else:
            os.link(pending, pointer)
            pending.unlink()
        _equal(c.strict_loads(pointer.read_bytes()), commit, "published latest pointer bytes differ")
        self.latest[head] = {**retained, "commit": commit}
        for entry in incoming.values():
            (self.work / entry["path"]).unlink()
        if previous:
            for part, ref in previous["files"].items():
                if part != "initial":
                    _read_ref(self.root, ref)
                    (self.root / ref["path"]).unlink()
                    self.bytes_kept -= ref["bytes"]

    def adopt(self, previous_root, snapshot):
        parts = _snapshot_parts(previous_root, snapshot)
        head = snapshot["head"]
        adopted = {**snapshot, "files": {}}
        for name, raw in parts.items():
            path = self.root / f"inherited-{head}-{name}.{PARTS[name]}"
            worker.publish(path, raw)
            adopted["files"][name] = {"path": path.name, "sha256": c.digest(raw), "bytes": len(raw)}
            self.bytes_kept += len(raw)
        record = _json_ref(
            self.root / f"inherited-{head}.json", {"snapshot": adopted, "prior_run": snapshot["commit"]}
        )
        _json_ref(self.root / f"{head}-latest.json", record)
        self.journal.append(record)
        self.latest[head] = {**adopted, "commit": record}


def _heads(plan, method, seed, inventory):
    groups = [group for rows in inventory.values() for group in rows]
    required = sorted({g["head"] for g in groups})
    if not plan.context.allow_fixture:
        golden = (
            [h["id"] for h in plan.context.authority.matrix["heads"]]
            if method == "learned_osqp"
            else ["graph"]
        )
        _equal(required, sorted(golden), "registered learning head domain reduced")
    heads = []
    for name in required:
        roles = {role: [g for g in rows if g["head"] == name] for role, rows in inventory.items()}
        c.ensure(all(roles.values()), "head missing train or validation sources")
        normals = None
        if method == "learned_osqp":
            normals = c.strict_loads(plan.train._normalizers[name])
            _equal(
                plan.train._normalizers[name],
                plan.validation._normalizers[name],
                "validation normalizer relabeled",
            )
            _equal(
                normals["fit_source_ids"],
                sorted(g["source_id"] for g in roles["train"]),
                "head normalizer fit sources differ",
            )
        source = {
            "protocol": plan.protocol_ref,
            "preflight": plan.p1.sha256,
            "population": plan.train._population,
            "descriptor": dict(plan.train._descriptor),
            "phases": {"train": plan.train.manifest_sha256, "validation": plan.validation.manifest_sha256},
            "proofs": {role: asdict(proof.trust) for role, proof in plan.proofs.items()},
            "learning_policy": plan.train._identities["learning_policy_sha256"],
            "source_lock": plan.context.source_lock_sha256,
            "dependency_lock": plan.context.dependency_lock_sha256,
            "method": method,
            "seed": seed,
            "head": name,
            "inventory": roles,
            "normalizer": normals["sha256"] if normals else None,
        }
        sizes = [int(value) for value in name.split("-")[1:]] if normals else (0, 0)
        heads.append(
            {
                "id": name,
                "n": sizes[0],
                "m": sizes[1],
                "normalizer": normals,
                "sources": [g["source_id"] for rows in roles.values() for g in rows],
                "source_sha256": c.digest(c.canonical_bytes(source)),
            }
        )
    return heads


def _numeric(root, name, pieces):
    path = root / name
    scratch = path.with_suffix(".unpublished")
    total = 0
    hasher = hashlib.sha256()
    with scratch.open("xb") as handle:
        for raw in pieces:
            handle.write(raw)
            hasher.update(raw)
            total += len(raw)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(scratch, path)
    finally:
        scratch.unlink()
    return {
        "path": name,
        "sha256": hasher.hexdigest(),
        "byte_count": total,
        "format": "raw-uint8" if name.endswith(".u8") else "raw-float64-le",
    }


def _project_checkpoints(plan, store, method, seed, *, scientific_stop):
    import json

    root = store.root
    names = sorted(store.heads)
    _equal(sorted(store.latest), names, "checkpoint head inventory reduced")
    latest = [store.latest[name] for name in names]
    _equal(scientific_stop, all(row["stopped"] for row in latest), "checkpoint stopped inventory differs")

    def part(row, key):
        return _read_ref(root, row["files"][key])

    initial = _numeric(root, "bundle-initial.f64", (part(row, "initial") for row in latest))
    current = _numeric(root, "bundle-current.f64", (part(row, "current") for row in latest))
    best = _numeric(root, "bundle-best.f64", (part(row, "best") for row in latest))

    def moment_pieces():
        for half in (0, 1):
            for row in latest:
                actual = part(row, "moments")
                size = row["files"]["initial"]["bytes"]
                yield actual[half * size : (half + 1) * size] if actual else b"\0" * size

    moments = _numeric(root, "bundle-adamw.f64", moment_pieces())
    rng = _numeric(root, "bundle-epoch-rng.u8", (part(row, "rng") for row in latest))
    histories, offsets, stream_receipts, init_unchanged = [], [], [], []
    best_epoch, epoch = {}, {}
    layout, order_receipts = [], []
    for name, row in zip(names, latest, strict=True):
        data = json.loads(part(row, "metadata"))
        best_epoch[name] = data["best_epoch"]
        epoch[name] = row["epoch"]
        if row["files"]["initial"]["sha256"] == row["files"]["best"]["sha256"]:
            init_unchanged.append(name)
        head_history = data["history"]
        order_receipts.append(
            [
                name,
                [
                    [entry["epoch"], entry["order_seed"], entry["permutation_sha256"]]
                    for entry in head_history
                ],
            ]
        )
        for item in head_history:
            history = {
                key: item[key]
                for key in (
                    "epoch",
                    "train_objective",
                    "validation_objective",
                    "optimizer_steps",
                    "gradient_finite",
                    "gradient_nonzero",
                )
            }
            if history["train_objective"] is None:
                _equal(history["epoch"], 0, "noninitial SDK epoch objective missing")
                history["train_objective"] = row["initial_train_objective"]
            histories.append({"head_id": name, **history})
        layout.extend({"head_id": name, **record} for record in row["initialization"])
    count = sum(math.prod(row["shape"]) for row in layout)
    adam = []
    index = 0
    for item in layout:
        size = math.prod(item["shape"])
        joined = item["head_id"] + "/" + item["name"]
        adam.append(
            {
                "parameter": joined,
                "shape": item["shape"],
                "first_moment_offset": index,
                "second_moment_offset": count + index,
            }
        )
        number = item["initialization_seed"]
        if item["initialization_rule"].startswith("xavier"):
            stream_receipts.append({"parameter": joined, "seed": number, "sha256": item["sha256"]})
        offsets.append((item, index, size))
        index += size
    class_stats = latest[0]["class_statistics"]
    if method == "learned_daqp":
        class_stats = {**class_stats, "labels": [dict(value["ref"]) for value in plan.train._labels.values()]}
    full_heads = len(names) == 14 or method == "learned_daqp"
    coverage = (
        "complete-bundle"
        if full_heads and not plan.context.allow_fixture
        else (
            "graph-contract-fixture"
            if method == "learned_daqp"
            else ("complete-bundle" if len(names) == 14 else "single-head-contract-fixture")
        )
    )
    model_context = replace(plan.context, root=root, catalog={})

    def write_checkpoint(role, selected):
        with (root / selected["path"]).open("rb") as handle:
            params = []
            for item, offset, size in offsets:
                raw = handle.read(size * 8)
                params.append(
                    {**item, "offset": offset, "count": size, "dtype": "float64-le", "sha256": c.digest(raw)}
                )
        architecture = dict(
            method=method,
            dtype="float64",
            coverage=coverage,
            head_ids=names,
            parameter_count=count,
            parameters=params,
        )
        payload = {
            "feature_stream": dict(plan.train._descriptor),
            "population_sha256": plan.train._population,
            "preflight_sha256": plan.p1.sha256,
            "phase_manifest_sha256": {
                "train": plan.train.manifest_sha256,
                "validation": plan.validation.manifest_sha256,
            },
            "method": method,
            "seed": seed,
            "role": role,
            "architecture": architecture,
            "architecture_sha256": c.digest(c.canonical_bytes(architecture)),
            "weights": selected,
            "initial_weights": initial,
            "best_weights": best,
            "initial_weights_sha256": initial["sha256"],
            "epoch": epoch,
            "best_epoch": best_epoch,
            "normalizer_sha256": [
                norm["normalizer"]["sha256"]
                for norm in store.heads.values()
                if norm["normalizer"] is not None
            ],
            "training_evidence": "real-produced",
            "history": histories,
            "class_statistics": class_stats,
            "learning_policy_sha256": plan.train._identities["learning_policy_sha256"],
            "optimizer": {
                "name": "AdamW",
                "learning_rate": 0.001,
                "weight_decay": 0.0001 if method == "learned_osqp" else 0.01,
                "beta1": 0.9,
                "beta2": 0.999,
                "eps": 1e-8,
                "amsgrad": False,
                "state_file": moments,
                "step_count": sum(row["optimizer_steps"] for row in histories),
                "tensors": adam,
            },
            "rng": {
                "streams": stream_receipts,
                "epoch_order_sha256": c.digest(c.canonical_bytes(order_receipts)),
                "state_file": rng,
            },
        }
        document = stream.stream_document(
            stream.CHECKPOINT, f"{method}-{seed}-{role}", payload, model_context, plan.protocol_ref
        )
        artifact = stream.write_stream_artifact(
            document, f"checkpoint-{role}.json", model_context, train=plan.train, validation=plan.validation
        )
        ref = {"path": f"checkpoint-{role}.json", "sha256": artifact.raw_sha256}
        return ref

    every_head_trained = all(
        row["epoch"] > 0
        and any(x["gradient_nonzero"] for x in json.loads(part(row, "metadata"))["history"])
        and row["files"]["initial"]["sha256"] != row["files"]["current"]["sha256"]
        for row in latest
    )
    if not every_head_trained:
        return {}, init_unchanged
    checkpoints = {"latest": write_checkpoint("latest", current)}
    if best["sha256"] != initial["sha256"] and (scientific_stop or plan.context.allow_fixture):
        checkpoints["final"] = write_checkpoint("final", best)
    return checkpoints, init_unchanged


def _validate(kind, document):
    path = c.SCHEMAS / f"softqp-{kind}.schema.json"
    c._validator(path.read_bytes()).validate(document)


def _exact_plan(plan, operation):
    if not plan.context.allow_fixture:
        from .authority import require_i1

        require_i1(plan.authority, operation, context=plan.context, protocol_ref=plan.protocol_ref)
        c.ensure(plan.fixture_policy is None, "scientific training cannot use a fixture policy")
    else:
        c.ensure(plan.fixture_policy is not None, "independent excluded-fixture policy required")


@dataclass(frozen=True)
class TrainingRun:
    root: Path
    raw: bytes
    sha256: str

    def __post_init__(self):
        _equal(c.digest(self.raw), self.sha256, "detached training run digest differs")

    @property
    def document(self):
        return c.strict_loads(self.raw)


def _require_launch_runtime(plan, runtime, operation):
    if plan.context.allow_fixture:
        c.ensure(type(runtime) is FixtureRuntime, "expected excluded fixture runtime custody")
    else:
        c.ensure(
            type(runtime) is _RegisteredRuntime and runtime.operation == operation,
            "genuine reviewed learning-worker custody required",
        )
        _equal(
            plan.authority.runtime_profile_sha256,
            runtime.profile_sha256,
            "I1-approved profile differs from live learning runtime",
        )
    return runtime.verify()


def _permit(nonce, scope, phase, head, epoch):
    return c.digest(c.canonical_bytes(["softqp.r4.learning-permit/1", nonce, scope, phase, head, epoch]))


def _verify_role_manifest(reader):
    raw = phase._open_bytes(reader._root, "phase-inputs.json")
    _equal(c.digest(raw), reader.manifest_sha256, "role manifest bytes changed during learning")


def _scientific_permits(authorize, budget, nonce, scope, heads):
    def admit(payload):
        _shape(payload, {"phase", "head", "epoch"}, "invalid learning mutation permit")
        action, head, epoch = payload["phase"], payload["head"], payload["epoch"]
        c.ensure(action in ("start", "advance", "snapshot"), "unknown learning mutation phase")
        c.ensure(head in heads or (head is None and action == "start"), "unadmitted learning permit head")
        c.ensure(type(epoch) is int and 0 <= epoch <= 100, "unadmitted learning permit epoch")
        authorize()
        budget.check()
        return {"permit": _permit(nonce, scope, action, head, epoch)}

    return admit


def supervise_training(
    plan, runtime, *, method, seed, destination, resume=None, fixture_stop_after=None, budget_roots=()
):
    """Run actual isolated SDK operations on the exact independent plan."""
    started = time.monotonic()
    _exact_plan(plan, "train-model")
    spec = _require_launch_runtime(plan, runtime, "train-model")
    fixture = plan.context.allow_fixture
    c.ensure(method in METHODS and seed in c.SEEDS, "unregistered method/seed")
    if fixture:
        policy = c.strict_loads(plan.fixture_policy)
        c.ensure(
            type(fixture_stop_after) is int
            and 1 <= fixture_stop_after <= policy["max_fixture_epochs"] <= 100,
            "short fixture stop lacks independent policy",
        )
        cap = fixture_stop_after
    else:
        c.ensure(fixture_stop_after is None, "scientific epoch schedule is fixed")
        cap = 100
    for reader in (plan.train, plan.validation):
        receipt = c.strict_loads(plan.p1.receipt_bytes)
        _expected_phase(receipt, reader)
    inventory, locations = _inventory((plan.train, plan.validation), plan.proofs, method)
    heads = _heads(plan, method, seed, inventory)
    scoped_heads = {row["id"]: row for row in heads}
    root = phase._external_destination(Path(destination), plan.p1.source_root, plan.p1.forbidden_roots)
    prior = None
    prior_seconds = 0.0
    previous = None
    if resume is not None:
        prior_root, expected_sha = resume
        previous = read_training_run(
            prior_root, expected_manifest_sha256=expected_sha, plan=plan, runtime=runtime
        )
        prior = previous.sha256
        document = previous.document
        _equal(
            (document["method"], document["seed"], document["heads"]),
            (method, seed, sorted(scoped_heads)),
            "resume selected another job",
        )
        prior_seconds = document["elapsed_seconds"]
        if not fixture:
            c.ensure(
                document["state"] == "failed" and document["snapshots"],
                "scientific resume needs an authorized failed run with a complete epoch",
            )
    budget = (
        None
        if fixture
        else LearningBudget(
            budget_roots,
            root,
            prior_seconds=prior_seconds,
            started=started,
        )
    )
    root.mkdir()
    work = root / "worker"
    store = EpochStore(root, work, scoped_heads, seed, method)
    inherited = {}
    if previous is not None:
        for item in previous.document["snapshots"]:
            store.adopt(previous.root, item)
            inherited[item["head"]] = store.latest[item["head"]]
        if budget:
            budget.check()
    task = {
        "operation": "train",
        "method": method,
        "seed": seed,
        "heads": heads,
        "inventory": inventory,
        "epoch_cap": cap,
        "resume": inherited,
    }
    permit_scope = (
        None
        if fixture
        else c.digest(
            c.canonical_bytes(
                {
                    "runtime": runtime.sha256,
                    "policy": runtime.policy_sha256,
                    "p1": plan.p1.sha256,
                    "phases": [plan.train.manifest_sha256, plan.validation.manifest_sha256],
                    "prior": prior,
                    "heads": sorted(scoped_heads),
                    "method": method,
                    "seed": seed,
                }
            )
        )
    )

    def authorize_training():
        _exact_plan(plan, "train-model")
        for reader in (plan.train, plan.validation):
            _verify_role_manifest(reader)
        runtime.verify()

    if not fixture:
        authorize_training()
    child, boot = _boot(work, runtime, spec, task, permit_scope=permit_scope)
    permits = (
        None
        if fixture
        else _scientific_permits(authorize_training, budget, boot["nonce"], permit_scope, scoped_heads)
    )
    custody = None
    state, reason = "failed", None
    start = time.monotonic()
    active_head = None
    reader_by_role = {reader.role: reader for reader in (plan.train, plan.validation)}
    try:
        for head, snapshot in inherited.items():
            for name, data in _snapshot_parts(root, snapshot).items():
                worker.publish(work / f"resume-{head}-{name}.{PARTS[name]}", data)

        def service(operation, payload):
            nonlocal active_head
            if operation == "authorize" and permits is not None:
                if payload["phase"] != "start":
                    _equal(payload["head"], active_head, "learning permit head changed")
                return permits(payload)
            if operation == "head":
                c.ensure(payload["head"] in scoped_heads, "worker requested unknown head")
                active_head = payload["head"]
            elif operation == "frame":
                return _frame_packet(reader_by_role, plan.proofs, locations, method, payload, active_head)
            elif operation == "epoch":
                _equal(payload["head"], active_head, "SDK epoch escaped active head")
                if budget:
                    authorize_training()
                    budget.check(extra_bytes=sum(item["bytes"] for item in payload["files"].values()))
                store.capture(payload)
                if budget:
                    budget.check()
            else:
                raise c.ContractError("unapproved worker IPC operation")

        event, data, custody = _serve(
            child,
            boot,
            service,
            start + _JOB_SECONDS if fixture else budget.deadline,
            distributions=45 if fixture else 49,
        )
        if event == "failed":
            reason = data["reason"]
        else:
            state = "fixture-exercise" if fixture else "completed"
    except (OSError, ValueError, TimeoutError) as error:
        reason = str(error)
    finally:
        child.close()
    checkpoints, unchanged = {}, []
    if state in ("fixture-exercise", "completed"):
        try:
            if budget:
                authorize_training()
                c.ensure(all(row["stopped"] for row in store.latest.values()), "unreached scientific stop")
                needed = sum(
                    5 * row["files"]["initial"]["bytes"] + row["files"]["rng"]["bytes"]
                    for row in store.latest.values()
                )
                budget.check(extra_bytes=needed)
            checkpoints, unchanged = _project_checkpoints(
                plan,
                store,
                method,
                seed,
                scientific_stop=all(row["stopped"] for row in store.latest.values()),
            )
            if budget:
                budget.check()
                if "final" not in checkpoints:
                    state, reason = (
                        "selection-unqualified",
                        "frozen selection failed the registered final gate",
                    )
        except (OSError, ValueError, TimeoutError) as error:
            if fixture:
                raise
            state, reason = "failed", str(error)
            checkpoints = {}
    document = {
        "format": RUN,
        "fixture_only": fixture,
        "state": state,
        "reason": reason,
        "method": method,
        "seed": seed,
        "runtime_sha256": runtime.sha256,
        "preflight_sha256": plan.p1.sha256,
        "protocol": plan.protocol_ref,
        "population_sha256": plan.train._population,
        "phases": {"train": plan.train.manifest_sha256, "validation": plan.validation.manifest_sha256},
        "heads": sorted(scoped_heads),
        "source_sha256": {key: value["source_sha256"] for key, value in scoped_heads.items()},
        "prior_run_sha256": prior,
        "worker": custody,
        "journal": store.journal,
        "snapshots": [store.latest[key] for key in sorted(store.latest)],
        "checkpoints": checkpoints,
        "selected_initial_heads": unchanged,
        "elapsed_seconds": prior_seconds + time.monotonic() - (start if fixture else budget.started),
    }
    if budget:
        document["resources"] = {"peak_disk_bytes": budget.high_water, "policy_sha256": runtime.policy_sha256}
    _validate("learning-training-run", document)
    ref = _json_ref(root / "training-run.json", document)
    return read_training_run(root, expected_manifest_sha256=ref["sha256"], plan=plan, runtime=runtime)


def read_training_run(root, *, expected_manifest_sha256, plan, runtime):
    _exact_plan(plan, "train-model")
    _require_launch_runtime(plan, runtime, "train-model")
    root = phase._exact_directory(Path(root))
    ref = {"path": "training-run.json", "sha256": expected_manifest_sha256}
    raw = _read_ref(root, ref)
    run = TrainingRun(root, raw, expected_manifest_sha256)
    data = _json_file(root, ref)
    _validate("learning-training-run", data)
    _equal(
        (
            data["fixture_only"],
            data["runtime_sha256"],
            data["preflight_sha256"],
            data["phases"],
            data["protocol"],
            data["population_sha256"],
        ),
        (
            plan.context.allow_fixture,
            runtime.sha256,
            plan.p1.sha256,
            {"train": plan.train.manifest_sha256, "validation": plan.validation.manifest_sha256},
            plan.protocol_ref,
            plan.train._population,
        ),
        "training run independently trusted scope differs",
    )
    inventory, _ = _inventory((plan.train, plan.validation), plan.proofs, data["method"])
    heads = _heads(plan, data["method"], data["seed"], inventory)
    _equal(data["heads"], [row["id"] for row in heads], "fresh run head inventory differs")
    _equal(
        data["source_sha256"],
        {row["id"]: row["source_sha256"] for row in heads},
        "fresh run source identity differs",
    )
    for entry in data["journal"]:
        _json_file(root, entry)
    for snapshot in data["snapshots"]:
        _snapshot_parts(root, snapshot)
        _equal(
            _json_file(root, snapshot["commit"])["snapshot"]["snapshot_sha256"],
            snapshot["snapshot_sha256"],
            "latest snapshot not bound to committed epoch",
        )
        _equal(
            c.strict_loads((root / f"{snapshot['head']}-latest.json").read_bytes()),
            snapshot["commit"],
            "latest resume pointer is stale",
        )
    context = replace(plan.context, root=root, catalog={})
    for role, checkpoint in data["checkpoints"].items():
        artifact = stream.read_stream_artifact(
            root / checkpoint["path"],
            context,
            expected_sha256=checkpoint["sha256"],
            train=plan.train,
            validation=plan.validation,
        )
        _equal(
            (artifact.payload["role"], artifact.payload["method"], artifact.payload["seed"]),
            (role, data["method"], data["seed"]),
            "run checkpoint identity differs",
        )
    return run


@dataclass(frozen=True)
class FrozenInference:
    root: Path
    raw: bytes
    sha256: str

    @property
    def document(self):
        return c.strict_loads(self.raw)


def publish_frozen_inference(run, destination, *, expected_run_sha256):
    _equal(
        (c.digest(run.raw), run.sha256),
        (expected_run_sha256, expected_run_sha256),
        "independent run digest differs",
    )
    manifest = run.document
    c.ensure("final" in manifest["checkpoints"], "no qualified selected checkpoint")
    selected = manifest["checkpoints"]["final"]
    checkpoint = _json_file(run.root, selected)
    payload = checkpoint["payload"]
    target = phase._external_destination(Path(destination), run.root, (c.ROOT,))
    target.mkdir()
    weights = _numeric(target, "selected.f64", [_read_ref(run.root, payload["weights"])])
    ckpt = _json_ref(target / "checkpoint-final.json", checkpoint)
    _equal(ckpt["sha256"], selected["sha256"], "frozen checkpoint stored identity changed")
    contents = {
        "format": FROZEN,
        "fixture_only": manifest["fixture_only"],
        "run_sha256": run.sha256,
        "checkpoint": ckpt,
        "weights": weights,
        "method": manifest["method"],
        "seed": manifest["seed"],
        "preflight_sha256": manifest["preflight_sha256"],
        "population_sha256": manifest["population_sha256"],
        "protocol": manifest["protocol"],
        "selected_initial_heads": manifest["selected_initial_heads"],
    }
    _validate("learning-frozen-inference", contents)
    receipt = _json_ref(target / "frozen-inference.json", contents)
    return read_frozen_inference(
        target,
        expected_receipt_sha256=receipt["sha256"],
        expected_run_sha256=expected_run_sha256,
        expected_checkpoint_sha256=selected["sha256"],
        allow_fixture=True,
    )


def read_frozen_inference(
    root, *, expected_receipt_sha256, expected_run_sha256, expected_checkpoint_sha256, allow_fixture=False
):
    root = phase._exact_directory(Path(root))
    raw = _read_ref(root, {"path": "frozen-inference.json", "sha256": expected_receipt_sha256})
    frozen = FrozenInference(root, raw, expected_receipt_sha256)
    data = frozen.document
    _validate("learning-frozen-inference", data)
    c.ensure(not data["fixture_only"] or allow_fixture is True, "inference fixture lane refused")
    _equal(
        (data["run_sha256"], data["checkpoint"]["sha256"]),
        (expected_run_sha256, expected_checkpoint_sha256),
        "independent frozen inference identity differs",
    )
    doc = _json_file(root, data["checkpoint"])
    c._validator((c.SCHEMAS / "softqp-learning-stream-checkpoint.schema.json").read_bytes()).validate(doc)
    payload = doc["payload"]
    _equal(
        (
            payload["role"],
            payload["method"],
            payload["seed"],
            payload["preflight_sha256"],
            payload["population_sha256"],
            doc["protocol_ref"],
        ),
        (
            "final",
            data["method"],
            data["seed"],
            data["preflight_sha256"],
            data["population_sha256"],
            data["protocol"],
        ),
        "frozen selected checkpoint metadata differs",
    )
    _equal(data["weights"]["sha256"], payload["weights"]["sha256"], "frozen selected weights differ")
    values = _read_ref(root, data["weights"])
    _equal(len(values), payload["architecture"]["parameter_count"] * 8, "frozen weight shape differs")
    c.ensure(
        all(math.isfinite(value) for (value,) in struct.iter_unpack("<d", values)), "frozen weights nonfinite"
    )
    for item in payload["architecture"]["parameters"]:
        start = item["offset"] * 8
        _equal(
            c.digest(values[start : start + item["count"] * 8]),
            item["sha256"],
            "frozen tensor digest differs",
        )
    return frozen


@dataclass(frozen=True)
class CalibrationPlan:
    context: c.AdmissionContext
    calibration: stream.StreamingPhaseReader
    frozen: FrozenInference
    proof: native.NativeRoleProof | None
    expected_calibration_manifest_sha256: str
    expected_receipt_sha256: str
    expected_run_sha256: str
    expected_checkpoint_sha256: str
    authority: object = None

    @classmethod
    def admit(
        cls,
        authority,
        *,
        context,
        calibration,
        frozen_inference,
        native_role_proof,
        expected_policy_sha256,
        expected_calibration_manifest_sha256,
        expected_receipt_sha256,
        expected_run_sha256,
        expected_checkpoint_sha256,
    ):
        frozen = read_frozen_inference(
            frozen_inference.root,
            expected_receipt_sha256=expected_receipt_sha256,
            expected_run_sha256=expected_run_sha256,
            expected_checkpoint_sha256=expected_checkpoint_sha256,
            allow_fixture=context.allow_fixture,
        )
        data = frozen.document
        _equal(
            calibration.manifest_sha256,
            expected_calibration_manifest_sha256,
            "independently expected calibration manifest differs",
        )
        _equal(
            (
                calibration.role,
                calibration.preflight_sha256,
                calibration._population,
                calibration.fixture_only,
            ),
            ("calibration", data["preflight_sha256"], data["population_sha256"], data["fixture_only"]),
            "calibration role or population differs",
        )
        _equal(
            calibration._identities["learning_policy_sha256"],
            expected_policy_sha256,
            "calibration policy differs",
        )
        if not context.allow_fixture:
            from .authority import require_i1

            require_i1(authority, "calibrate-model", context=context, protocol_ref=data["protocol"])
        if data["method"] == "learned_daqp":
            _readers(
                data["preflight_sha256"],
                calibration,
                {"calibration": native_role_proof},
                data["fixture_only"],
            )
            c.ensure(
                isinstance(native_role_proof, native.NativeRoleProof),
                "calibration requires actual native proof",
            )
        return cls(
            context,
            calibration,
            frozen,
            native_role_proof,
            expected_calibration_manifest_sha256,
            expected_receipt_sha256,
            expected_run_sha256,
            expected_checkpoint_sha256,
            authority,
        )


def _require_calibration_authority(plan):
    if not plan.context.allow_fixture:
        from .authority import require_i1

        require_i1(
            plan.authority,
            "calibrate-model",
            context=plan.context,
            protocol_ref=plan.frozen.document["protocol"],
        )


def supervise_calibration(plan, runtime, destination, *, budget_roots=(), committed_bytes=0):
    started = time.monotonic()
    _require_calibration_authority(plan)
    spec = _require_launch_runtime(plan, runtime, "calibrate-model")
    fixture = plan.context.allow_fixture
    frozen = read_frozen_inference(
        plan.frozen.root,
        expected_receipt_sha256=plan.expected_receipt_sha256,
        expected_run_sha256=plan.expected_run_sha256,
        expected_checkpoint_sha256=plan.expected_checkpoint_sha256,
        allow_fixture=fixture,
    )
    data = frozen.document
    method, seed = data["method"], data["seed"]
    reader = plan.calibration
    _equal(
        reader.manifest_sha256,
        plan.expected_calibration_manifest_sha256,
        "independently expected calibration manifest differs",
    )
    c.ensure(
        reader.role == "calibration" and reader.preflight_sha256 == data["preflight_sha256"],
        "calibration is not bound to chosen checkpoint phase",
    )
    checkpoint = _json_file(frozen.root, data["checkpoint"])["payload"]
    inventory = locations = {}
    if method == "learned_daqp":
        inventory, locations = _inventory((reader,), {"calibration": plan.proof}, method)
    target = phase._external_destination(Path(destination), reader._root, (c.ROOT, frozen.root))
    budget = (
        None
        if fixture
        else LearningBudget(
            budget_roots,
            target,
            committed_bytes=committed_bytes,
            started=started,
        )
    )
    target.mkdir()
    task = {
        "operation": "calibrate",
        "method": method,
        "seed": seed,
        "inventory": inventory,
        "weights_sha256": data["weights"]["sha256"],
        "positive_prior": checkpoint["class_statistics"]["positive_prior"]
        if method == "learned_daqp"
        else None,
    }
    permit_scope = (
        None
        if fixture
        else c.digest(
            c.canonical_bytes(
                {
                    "runtime": runtime.sha256,
                    "policy": runtime.policy_sha256,
                    "preflight": data["preflight_sha256"],
                    "phase": reader.manifest_sha256,
                    "frozen": frozen.sha256,
                    "method": method,
                    "seed": seed,
                }
            )
        )
    )

    def authorize_calibration():
        _require_calibration_authority(plan)
        _verify_role_manifest(reader)
        runtime.verify()

    if not fixture:
        authorize_calibration()
    child, boot = _boot(target / "worker", runtime, spec, task, permit_scope=permit_scope)
    permits = (
        None
        if fixture
        else _scientific_permits(authorize_calibration, budget, boot["nonce"], permit_scope, ())
    )
    observations = {}
    custody = None
    try:
        if method == "learned_daqp":
            worker.publish(child.root / "frozen.f64", _read_ref(frozen.root, data["weights"]))

        def service(operation, payload):
            if operation == "authorize" and permits is not None:
                _equal(payload, {"phase": "start", "head": None, "epoch": 0}, "calibration mutation scope")
                return permits(payload)
            if operation == "frame":
                return _frame_packet(
                    {"calibration": reader}, {"calibration": plan.proof}, locations, method, payload, "graph"
                )
            _equal(operation, "observation", "unapproved calibration IPC operation")
            frame = payload["frame_id"]
            _equal(locations.get(("calibration", frame)), "graph", "calibration observation outside phase")
            values = payload["probabilities"]
            c.ensure(
                all(math.isfinite(value) and 0 <= value <= 1 for value in values),
                "invalid observed probabilities",
            )
            signed = plan.proof.verify(reader, frame)["label"]["payload"]
            _equal(
                (payload["mask"], payload["target"]),
                (signed["mask"], [value or 0 for value in signed["labels"]]),
                "calibration observation masks differ",
            )
            raw = struct.pack(f"<{len(values)}d", *values)
            previous = observations.get(frame)
            if previous is None:
                name = f"scores-{len(observations):06d}.f64"
                ref = _numeric(target, name, [raw])
                observations[frame] = {
                    "frame_id": frame,
                    "probabilities": ref,
                    "mask_sha256": c.digest(
                        c.canonical_bytes(
                            {"mask": signed["mask"], "target": [value or 0 for value in signed["labels"]]}
                        )
                    ),
                }
            else:
                _equal(previous["probabilities"]["sha256"], c.digest(raw), "repeat graph observation differs")

        event, payload, custody = _serve(
            child,
            boot,
            service,
            time.monotonic() + _JOB_SECONDS if fixture else budget.deadline,
            distributions=45 if fixture else 49,
        )
        if budget:
            authorize_calibration()
            budget.check()
    except (OSError, ValueError, TimeoutError) as error:
        if fixture:
            raise
        event, payload = "failed", {"reason": str(error)}
    finally:
        child.close()
    if event == "failed":
        failure = payload["reason"]
        result = {"state": "failed", "values": None}
    else:
        failure = None
        result = payload["result"]
        if method == "learned_daqp":
            _equal(
                set(observations),
                {key for (role, key) in locations if role == "calibration"},
                "calibration observation count differs",
            )
    document = {
        "format": CALIBRATION,
        "fixture_only": fixture,
        **result,
        "reason": failure,
        "method": method,
        "seed": seed,
        "runtime_sha256": runtime.sha256,
        "preflight_sha256": data["preflight_sha256"],
        "population_sha256": data["population_sha256"],
        "phase_sha256": reader.manifest_sha256,
        "frozen_sha256": frozen.sha256,
        "checkpoint": data["checkpoint"],
        "observations": sorted(observations.values(), key=lambda row: row["frame_id"]),
        "worker": custody,
    }
    if budget:
        document["resources"] = {
            "peak_disk_bytes": budget.high_water,
            "policy_sha256": runtime.policy_sha256,
            "elapsed_seconds": time.monotonic() - budget.started,
        }
    _validate("learning-stream-calibration", document)
    ref = _json_ref(target / "calibration.json", document)
    return read_calibration(target, expected_sha256=ref["sha256"], plan=plan, runtime=runtime)


def read_calibration(root, *, expected_sha256, plan, runtime):
    _require_calibration_authority(plan)
    _require_launch_runtime(plan, runtime, "calibrate-model")
    root = phase._exact_directory(Path(root))
    data = _json_file(root, {"path": "calibration.json", "sha256": expected_sha256})
    _validate("learning-stream-calibration", data)
    independent = read_frozen_inference(
        plan.frozen.root,
        expected_receipt_sha256=plan.expected_receipt_sha256,
        expected_run_sha256=plan.expected_run_sha256,
        expected_checkpoint_sha256=plan.expected_checkpoint_sha256,
        allow_fixture=plan.context.allow_fixture,
    )
    frozen = independent.document
    _equal(
        (
            data["fixture_only"],
            data["runtime_sha256"],
            data["method"],
            data["seed"],
            data["frozen_sha256"],
            data["phase_sha256"],
            data["population_sha256"],
            data["preflight_sha256"],
            data["checkpoint"],
        ),
        (
            plan.context.allow_fixture,
            runtime.sha256,
            frozen["method"],
            frozen["seed"],
            independent.sha256,
            plan.calibration.manifest_sha256,
            frozen["population_sha256"],
            frozen["preflight_sha256"],
            frozen["checkpoint"],
        ),
        "independently expected calibration ancestry differs",
    )
    if data["state"] == "not-applicable":
        _equal(
            (data["method"], data["observations"], data["values"]),
            ("learned_osqp", [], None),
            "L2WS calibration acquired graph outputs",
        )
    if data["state"] == "calibrated":
        _equal(data["method"], "learned_daqp", "classifier calibration method differs")
        expected = sorted(
            key for key, representation in plan.calibration.logical_keys if representation == "graph-v1"
        )
        _equal(
            [row["frame_id"] for row in data["observations"]], expected, "calibration eligible keys reduced"
        )
        scores = data["values"]["scores"]
        _equal(len(scores), 9, "calibration threshold grid differs")
        winner = max(range(9), key=lambda index: (scores[index], index))
        _equal(
            (data["values"]["threshold"], data["values"]["f1"]),
            ((winner + 1) / 10, scores[winner]),
            "invalid calibration optimum or exact tie selection",
        )
    observations = []
    for item in data["observations"]:
        raw = _read_ref(root, item["probabilities"])
        label = plan.proof.verify(plan.calibration, item["frame_id"])["label"]["payload"]
        _equal(len(raw), 8 * len(label["mask"]), "calibration local probability shape differs")
        c.ensure(
            all(0 <= number <= 1 for (number,) in struct.iter_unpack("<d", raw)),
            "calibration probability domain",
        )
        _equal(
            item["mask_sha256"],
            c.digest(
                c.canonical_bytes(
                    {"mask": label["mask"], "target": [value or 0 for value in label["labels"]]}
                )
            ),
            "calibration local label mask differs",
        )
        source = plan.calibration.read_problem(item["frame_id"])["source"]
        probabilities = struct.unpack(f"<{len(raw) // 8}d", raw)
        observations.append(
            (
                source,
                [
                    (score, truth)
                    for score, truth, keep in zip(probabilities, label["labels"], label["mask"], strict=True)
                    if keep
                ],
            )
        )
    if data["state"] == "calibrated":
        _equal(
            data["values"],
            _check_calibration_metrics(observations),
            "replayed local calibration metrics differ",
        )
    return data


def _check_calibration_metrics(observations):
    """Independent receipts check; the producer still uses SDK calibration."""
    ordered = sorted(observations, key=lambda row: (row[0]["source_id"], row[0]["frame"]))
    families = {}
    for source, _ in ordered:
        families.setdefault(source["family"], {}).setdefault(source["regime"], set()).add(source["source_id"])
    groups, points = {}, []
    counts = [0, 0]
    zero_masks = 0
    for source, values in ordered:
        by_regime = families[source["family"]]
        source_weight = 1 / (len(families) * len(by_regime) * len(by_regime[source["regime"]]))
        frame_count = source["frame_count"]
        group = groups.setdefault(source["source_id"], (source_weight, frame_count, []))
        group[2].append(values)
        if not values:
            zero_masks += 1
        for p, y in values:
            counts[y] += 1
            points.append((p, y, (source_weight / frame_count) / len(values)))
    c.ensure(bool(points), "all calibration masks empty")

    def macro(threshold):
        scores = []
        for weight, size, frames in groups.values():
            tp = fp = fn = 0.0
            for frame in frames:
                tp += sum(score > threshold and truth == 1 for score, truth in frame) / size
                fp += sum(score > threshold and truth == 0 for score, truth in frame) / size
                fn += sum(score <= threshold and truth == 1 for score, truth in frame) / size
            denominator = 2 * tp + fp + fn
            scores.append(weight * (2 * tp / denominator if denominator else 0.0))
        return sum(scores)

    grid = [i / 10 for i in range(1, 10)]
    scores = [macro(threshold) for threshold in grid]
    winner = max(range(9), key=lambda index: (scores[index], index))
    mass = sum(w for _, _, w in points)
    brier = sum(w * (p - truth) ** 2 for p, truth, w in points) / mass
    buckets = [[] for _ in range(10)]
    for point in points:
        buckets[min(int(point[0] * 10), 9)].append(point)
    ece = sum(
        abs(sum(w * p for p, _, w in bucket) - sum(w * truth for _, truth, w in bucket)) / mass
        for bucket in buckets
        if bucket
    )
    return {
        "threshold": grid[winner],
        "scores": scores,
        "f1": scores[winner],
        "brier": brier,
        "ece": ece,
        "class_counts": counts,
        "mask_count": sum(counts),
        "zero_mask_frames": zero_masks,
    }


def registered_jobs():
    """The six exact R4 method/seed jobs, each with separately governed launch policy."""
    return tuple((method, seed) for method in METHODS for seed in c.SEEDS)


def registered_learning_request(operation, method, seed, *, resume=None):
    c.ensure(operation in ("train-model", "calibrate-model"), "unknown registered learning operation")
    c.ensure((method, seed) in registered_jobs() and type(seed) is int, "unregistered learning job")
    if resume is not None:
        c.ensure(operation == "train-model", "calibration has no resume path")
        _shape(resume, {"root", "sha256"}, "invalid registered resume reference")
        phase._hash(resume["sha256"])
        c.ensure(Path(resume["root"]).is_absolute(), "registered resume root must be absolute")
    return c.canonical_bytes(
        dict(
            schema=LEARNING_REQUEST,
            operation=operation,
            method=method,
            seed=seed,
            resume=resume,
        )
    )


def _registered_role(role, config, governance, preflight):
    _shape(config, {"root", "manifest_sha256", "projection", "trust"}, "invalid registered phase policy")
    reader = stream.StreamingPhaseReader(
        Path(config["root"]),
        role=role,
        expected_manifest_sha256=config["manifest_sha256"],
        expected_preflight_sha256=preflight.sha256,
        allow_fixture=False,
    )
    trust_data = _shape(
        config["trust"], set(native.NativeRoleTrust.__dataclass_fields__), "invalid native role trust policy"
    )
    trust = native.NativeRoleTrust(**trust_data)
    _equal(
        (trust.role, trust.labeled_preflight_sha256, trust.fixture_only),
        (role, preflight.sha256, False),
        "independent native projection scope differs",
    )
    projection = config["projection"]
    _checked_scope_file(governance, projection)
    _equal(projection["sha256"], trust.projection_sha256, "native projection digest policy differs")
    proof = native.NativeRoleProof.load(governance / projection["path"], trust, allow_fixture=False)
    return reader, proof


def dispatch_registered_learning(raw, custody):
    """Registered scientific parent entrypoint. Only the verified platform can invoke it."""
    from softqp_runtime_custody import read_active_learning_policy

    from .authority import load_i1_authority
    from .generator import _dispatch_context

    request = _shape(
        c.strict_loads(raw),
        {"schema", "operation", "method", "seed", "resume"},
        "invalid registered learning request",
    )
    op, method, seed, resume = (request[k] for k in ("operation", "method", "seed", "resume"))
    _equal(
        raw,
        registered_learning_request(op, method, seed, resume=resume),
        "registered learning request bytes differ",
    )
    request_sha = c.digest(raw)
    source = Path(__file__).resolve()
    raw_policy = read_active_learning_policy(
        custody, operation=op, request_sha256=request_sha, source_file=source
    )
    policy = _shape(
        c.strict_loads(raw_policy),
        {
            "schema",
            "operation",
            "request_sha256",
            "profile_sha256",
            "admission",
            "scope",
            "output_root",
            "artifact_roots",
        },
        "invalid scientific learning policy",
    )
    _equal(
        (policy["schema"], policy["operation"], policy["request_sha256"]),
        (LEARNING_POLICY, op, request_sha),
        "registered learning policy identity differs",
    )
    output_root = phase._exact_directory(Path(policy["output_root"]))
    runtime = _RegisteredRuntime(
        custody, op, request_sha, policy["profile_sha256"], c.digest(raw_policy), output_root
    )
    runtime.verify()

    admission = _shape(
        policy["admission"],
        {"approval", "product_root", "engine_root", "design_root", "output_root", "locks", "protocol"},
        "invalid registered learning authority setup",
    )
    trust, context, protocol = _dispatch_context(admission)
    authority = load_i1_authority(trust=trust, context=context, protocol_ref=protocol)
    _equal(
        authority.runtime_profile_sha256,
        runtime.profile_sha256,
        "I1-approved profile differs from live learning runtime",
    )
    role_names = ("train", "validation") if op == "train-model" else ("calibration",)
    keyset = {"roles", "preflight", "resume"}
    if op == "calibrate-model":
        keyset.update(("frozen", "committed_artifact_receipt"))
    scope = _shape(policy["scope"], keyset, "invalid registered learning phase scope")
    _equal(scope["resume"], resume, "independently approved resume differs")
    preflight_raw = _checked_scope_file(trust.governance_root, scope["preflight"])
    p1_doc = c.strict_loads(preflight_raw)
    _equal(p1_doc["fixture_only"], False, "excluded phase cannot authorize scientific learning")
    p1 = phase.PhasePreflight(
        Path(p1_doc["source_root"]),
        tuple(Path(p) for p in p1_doc["forbidden_roots"]),
        preflight_raw,
    )
    _equal(p1_doc["protocol_ref"], protocol, "governed phase protocol differs")
    roles = _shape(scope["roles"], set(role_names), "registered learning roles differ")
    admitted = {role: _registered_role(role, roles[role], trust.governance_root, p1) for role in role_names}
    for reader, _ in admitted.values():
        _expected_phase(p1_doc, reader)
    policy_sha = context.authority.manifest["normative_sha256"]["learning-spec.md"]
    _equal(
        p1_doc["identities"]["learning_policy_sha256"], policy_sha, "learning specification identity differs"
    )
    roots = tuple(phase._exact_directory(Path(path)) for path in policy["artifact_roots"])
    necessary_roots = [output_root, *(r._root for r, _ in admitted.values())]
    if op == "train-model":
        necessary_roots.append(p1.source_root)
    if resume is not None:
        necessary_roots.append(phase._exact_directory(Path(resume["root"])))
    if op == "calibrate-model":
        frozen_policy = _shape(
            scope["frozen"],
            {"root", "receipt_sha256", "run_sha256", "checkpoint_sha256"},
            "invalid frozen-calibration authority",
        )
        necessary_roots.append(phase._exact_directory(Path(frozen_policy["root"])))
        raw_accounting = _checked_scope_file(trust.governance_root, scope["committed_artifact_receipt"])
        account = _shape(
            c.strict_loads(raw_accounting),
            {
                "schema",
                "preflight_sha256",
                "phase_sha256",
                "frozen_sha256",
                "excluded_roots",
                "committed_bytes",
            },
            "invalid calibration committed-artifact accounting",
        )
        _equal(
            (
                raw_accounting,
                account["schema"],
                account["preflight_sha256"],
                account["phase_sha256"],
                account["frozen_sha256"],
            ),
            (
                c.canonical_bytes(account),
                "softqp.r4.committed-artifacts/1",
                p1.sha256,
                admitted["calibration"][0].manifest_sha256,
                frozen_policy["receipt_sha256"],
            ),
            "independent calibration accounting identity differs",
        )
        excluded = tuple(Path(p) for p in account["excluded_roots"])
        c.ensure(
            all(root.is_absolute() and ".." not in root.parts for root in excluded)
            and p1.source_root in excluded,
            "calibration accounting lacks a committed global root",
        )
        c.ensure(
            not any(
                prior.is_relative_to(root) or root.is_relative_to(prior)
                for prior in excluded
                for root in roots
            ),
            "calibration would access committed artifact roots",
        )
        c.ensure(
            not any(context.root.is_relative_to(prior) for prior in excluded),
            "calibration approval protocol must be staged apart from excluded artifacts",
        )

    c.ensure(
        all(any(needed.is_relative_to(root) for root in roots) for needed in necessary_roots),
        "independent artifact quota omits a registered scientific root",
    )
    c.ensure(
        not any(
            base.is_relative_to(root)
            for base in (trust.product_root, trust.engine_root, trust.governance_root)
            for root in roots
        ),
        "quota roots include protected project or governance data",
    )
    if op == "train-model":
        plan = TrainingPlan.admit(
            authority,
            context=context,
            protocol_ref=protocol,
            labeled_preflight=p1,
            expected_preflight_sha256=scope["preflight"]["sha256"],
            train=admitted["train"][0],
            validation=admitted["validation"][0],
            native_role_proofs={role: proof for role, (_, proof) in admitted.items()},
            expected_policy_sha256=policy_sha,
        )
        key = f"{method}-{seed}"
        if resume is not None:
            key += "-resume-" + resume["sha256"][:16]
        result = supervise_training(
            plan,
            runtime,
            method=method,
            seed=seed,
            destination=output_root / key,
            resume=None if resume is None else (Path(resume["root"]), resume["sha256"]),
            budget_roots=roots,
        )
        manifest, sha, state = "training-run.json", result.sha256, result.document["state"]
    else:
        frozen = read_frozen_inference(
            frozen_policy["root"],
            expected_receipt_sha256=frozen_policy["receipt_sha256"],
            expected_run_sha256=frozen_policy["run_sha256"],
            expected_checkpoint_sha256=frozen_policy["checkpoint_sha256"],
            allow_fixture=False,
        )
        _equal(
            (frozen.document["method"], frozen.document["seed"]),
            (method, seed),
            "calibration request differs from chosen model",
        )
        reader, proof = admitted["calibration"]
        plan = CalibrationPlan.admit(
            authority,
            context=context,
            calibration=reader,
            frozen_inference=frozen,
            native_role_proof=proof,
            expected_policy_sha256=policy_sha,
            expected_calibration_manifest_sha256=roles["calibration"]["manifest_sha256"],
            expected_receipt_sha256=frozen_policy["receipt_sha256"],
            expected_run_sha256=frozen_policy["run_sha256"],
            expected_checkpoint_sha256=frozen_policy["checkpoint_sha256"],
        )
        key = f"calibration-{method}-{seed}"
        result = supervise_calibration(
            plan,
            runtime,
            output_root / key,
            budget_roots=roots,
            committed_bytes=account["committed_bytes"],
        )
        manifest, sha, state = "calibration.json", c.digest(c.canonical_bytes(result)), result["state"]
    runtime.verify()
    return {
        "schema": "softqp.r4.learning-result/1",
        "request_sha256": request_sha,
        "policy_sha256": runtime.policy_sha256,
        "operation": op,
        "method": method,
        "seed": seed,
        "manifest": {"path": f"{key}/{manifest}", "sha256": sha},
        "state": state,
    }
