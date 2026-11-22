"""Isolated published-SDK process for streaming training and calibration."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import time


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(encode(value))


def publish(path, raw):
    temporary = path.with_suffix(".unpublished")
    with temporary.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink()


def read_json(path):
    with path.open("rb") as handle:
        raw = handle.read(64 * 2**20 + 1)
    value = json.loads(raw)
    if len(raw) > 64 * 2**20 or encode(value) != raw:
        raise ValueError("noncanonical or oversized worker message")
    return value


def wait(path):
    while not path.exists():
        time.sleep(0.005)
    return read_json(path)


class Channel:
    def __init__(self, root, nonce, *, require_live=None):
        self.root, self.nonce, self.index = root, nonce, 0
        self.require_live = require_live

    def authorize(self, scope, phase, head, epoch):
        if self.require_live is None:
            return
        response = self.emit("authorize", {"phase": phase, "head": head, "epoch": epoch})
        expected = digest(["softqp.r4.learning-permit/1", self.nonce, scope, phase, head, epoch])
        if response != {"permit": expected}:
            raise ValueError("scientific learning mutation permit differs")
        self.require_live()

    def emit(self, operation, payload):
        index = self.index
        event = {"nonce": self.nonce, "index": index, "operation": operation, "payload": payload}
        publish(self.root / f"event-{index:07d}.json", encode(event))
        reply = wait(self.root / f"reply-{index:07d}.json")
        if reply["event_sha256"] != digest(event):
            raise ValueError("worker event identity differs")
        (self.root / f"reply-{index:07d}.json").unlink()
        self.index += 1
        return reply["payload"]


def _arrays(transform):
    import numpy as np
    from scipy.sparse import csc_matrix

    def dense(value):
        return csc_matrix(
            (np.asarray(value["data"], dtype="<f8"), value["indices"], value["indptr"]), shape=value["shape"]
        ).toarray()

    return (
        dense(transform["P"]),
        np.asarray(transform["q"], dtype="<f8"),
        dense(transform["A"]),
        np.array([-np.inf if x is None else x for x in transform["lower"]], dtype="<f8"),
        np.array([np.inf if x is None else x for x in transform["upper"]], dtype="<f8"),
    )


def _clean(values):
    if isinstance(values, list):
        return [_clean(value) for value in values]
    return values or 0.0 if type(values) is float else values


def _graph(packet):
    from dataclasses import asdict
    from softqp.learning import graph, parameters

    side = graph.OneSidedLift.from_interval(*_arrays(packet["transform"]))
    actual = side.graph()
    graph_identity = {
        "node_features": _clean(actual.x.tolist()),
        "edge_index": actual.edge_index.T.tolist(),
        "edge_weight": _clean(actual.edge_weight.tolist()),
        "row_map": [asdict(row) for row in side.row_map],
    }
    if digest(graph_identity) != packet["feature_sha256"]:
        raise ValueError("SDK graph differs from sealed role feature")
    label = packet["label"]
    labels = graph.Labels(
        parameters.cpu64([value or 0 for value in label["labels"]]),
        parameters.torch.tensor(label["mask"], dtype=parameters.torch.bool),
    )
    return graph.GraphFrame(actual, labels)


class LazyFrames:
    """SDK SourceUnit asks for one ordinal, and only then does a role read occur."""

    def __init__(self, channel, role, frames, method, normalizer=None, *, observation_model=None):
        self.channel, self.role, self.frames = channel, role, tuple(frames)
        self.method, self.normalizer, self.observation_model = method, normalizer, observation_model

    def __len__(self):
        return len(self.frames)

    def __iter__(self):
        for index in range(len(self.frames)):
            yield self[index]

    def __getitem__(self, index):
        from softqp.learning import fixed_point, graph, parameters

        item = self.frames[index]
        packet = self.channel.emit("frame", {"role": self.role, "frame_id": item})
        if self.method == "learned_daqp":
            frame = _graph(packet)
            if self.observation_model is not None:
                with parameters.torch.no_grad():
                    predicted = self.observation_model.probabilities(frame.graph)
                self.channel.emit(
                    "observation",
                    {
                        "frame_id": item,
                        "probabilities": predicted.tolist(),
                        "target": frame.labels.target.tolist(),
                        "mask": frame.labels.mask.tolist(),
                    },
                )
                return graph.Observation(predicted, frame.labels, frame.graph.inequality_mask)
            return frame
        frame = fixed_point.FixedPointProblem(*_arrays(packet["transform"]))
        features = frame.features()
        expected = digest(
            {
                "raw": _clean(features.tolist()),
                "normalized": _clean(self.normalizer.transform(features).tolist()),
            }
        )
        if expected != packet["feature_sha256"]:
            raise ValueError("SDK fixed-point coordinates differ from sealed role feature")
        return frame


def units(channel, inventory, role, method, normalizer=None, model=None):
    from softqp.learning.training import SourceUnit, balance_sources

    return balance_sources(
        [
            SourceUnit(
                row["source_id"],
                row["family"],
                row["regime"],
                role,
                LazyFrames(channel, role, row["frames"], method, normalizer, observation_model=model),
            )
            for row in inventory[role]
        ],
        role,
    )


def baseline(trainer):
    from softqp.learning.parameters import torch

    result = 0.0
    with torch.no_grad():
        for unit, weight in trainer.train:
            for frame in unit.frames:
                result += float(trainer.loss(trainer.model, frame)) * (weight / len(unit.frames))
    return result


_PARTS = {
    "metadata": "json",
    "initial": "f64",
    "current": "f64",
    "best": "f64",
    "moments": "f64",
    "rng": "u8",
}


def emit_snapshot(channel, trainer, measured, class_data):
    from dataclasses import asdict

    snapshot = trainer.snapshot()
    payload = {
        "head": trainer.model.head,
        "epoch": trainer.history[-1].epoch,
        "snapshot_sha256": snapshot.sha256,
        "initial_train_objective": measured,
        "stopped": trainer.stopped,
        "class_statistics": class_data,
        "initialization": [asdict(item) for item in trainer.model.initialization],
        "files": {},
    }
    for name, suffix in _PARTS.items():
        raw = getattr(snapshot, name)
        path = channel.root / f"snapshot-{name}.{suffix}"
        publish(path, raw)
        payload["files"][name] = {"path": path.name, "sha256": sha(raw), "bytes": len(raw)}
    channel.emit("epoch", payload)


def _resume(channel, trainer, selection):
    from softqp.learning.training import NumericResume

    parts = {}
    for name, suffix in _PARTS.items():
        raw = (channel.root / f"resume-{trainer.model.head}-{name}.{suffix}").read_bytes()
        if sha(raw) != selection["files"][name]["sha256"]:
            raise ValueError("fresh SDK resume segment digest differs")
        parts[name] = raw
    snapshot = NumericResume(**parts)
    trainer.restore(snapshot, expected_sha256=selection["snapshot_sha256"])


def train(channel, task):
    from softqp.learning import fixed_point, graph
    from softqp.learning.training import HeadTrainer

    scope_identity = task.get("permit_scope")
    for head in task["heads"]:
        name = head["id"]
        channel.emit("head", {"head": name})
        channel.authorize(scope_identity, "start", name, 0)
        method = task["method"]
        if method == "learned_osqp":
            normal = head["normalizer"]
            norm = fixed_point.Normalizer.from_admitted(
                normal["mean"], normal["scale"], normal["fit_source_ids"], normal["source_weights"]
            )
            model = fixed_point.L2WSHead(head["n"], head["m"], task["seed"])
            training = units(channel, task["inventory"], "train", method, norm)
            validation = units(channel, task["inventory"], "validation", method, norm)
            scope = set(head["sources"])
            training = tuple((unit, weight) for unit, weight in training if unit.source_id in scope)
            validation = tuple((unit, weight) for unit, weight in validation if unit.source_id in scope)

            def loss(model, frame):
                return frame.loss(model, norm)

            classes = None
        else:
            training = units(channel, task["inventory"], "train", method)
            validation = units(channel, task["inventory"], "validation", method)
            statistics = graph.fit_classes(training)
            model = graph.ActiveSetGNN(task["seed"], statistics.positive_prior)

            def loss(model, frame):
                return frame.loss(model, statistics)

            classes = dict(
                N0=statistics.mass0,
                N1=statistics.mass1,
                weight0=statistics.weights[0],
                weight1=statistics.weights[1],
                positive_prior=statistics.positive_prior,
            )
        trainer = HeadTrainer(model, training, validation, loss, source_sha256=head["source_sha256"])
        measured = baseline(trainer)
        if name in task["resume"]:
            _resume(channel, trainer, task["resume"][name])
        else:
            channel.authorize(scope_identity, "snapshot", name, 0)
            emit_snapshot(channel, trainer, measured, classes)
        while not trainer.stopped and trainer.history[-1].epoch < task["epoch_cap"]:
            epoch = trainer.history[-1].epoch + 1
            channel.authorize(scope_identity, "advance", name, epoch)
            trainer.advance()
            channel.authorize(scope_identity, "snapshot", name, epoch)
            emit_snapshot(channel, trainer, measured, classes)


def calibrate(channel, task):
    from softqp.learning import graph, parameters

    channel.authorize(task.get("permit_scope"), "start", None, 0)
    if task["method"] == "learned_osqp":
        return {"state": "not-applicable", "values": None}
    model = graph.ActiveSetGNN(task["seed"], task["positive_prior"])
    weights = (channel.root / "frozen.f64").read_bytes()
    parameters.load_weights(model, weights, expected_sha256=task["weights_sha256"])
    population = units(channel, task["inventory"], "calibration", task["method"], model=model)
    return {"state": "calibrated", "values": graph.calibrate(population)}


def main(root, nonce):
    boot = wait(root / "boot.json")
    native = Path(__file__).with_name("native_labels.py")
    if boot["nonce"] != nonce or sha(native.read_bytes()) != boot["native_sha256"]:
        raise ValueError("worker bootstrap source custody differs")
    source_admission = runpy.run_path(str(native))["_profile_checks"]
    started = time.perf_counter()
    audit = source_admission({"runtime": boot["runtime"]})
    publish(
        root / "installed.json",
        encode(
            {"nonce": nonce, "audit": audit, "seconds": time.perf_counter() - started, "pid": os.getpid()}
        ),
    )
    if wait(root / "import-ack.json")["installed_sha256"] != sha((root / "installed.json").read_bytes()):
        raise ValueError("missing import acknowledgement")
    started = time.perf_counter()
    from softqp.learning import fixed_point, graph  # noqa: F401
    from softqp.learning.parameters import torch

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    publish(
        root / "ready.json",
        encode({"nonce": nonce, "pid": os.getpid(), "seconds": time.perf_counter() - started}),
    )
    _dispatch(Channel(root, nonce), boot["task"])


def main_verified(root, nonce, *, require_live, audit, installed, import_seconds):
    """Fixed scientific leaf. Runtime admission and SDK import are guardian-owned."""
    root = Path(root)
    if installed["nonce"] != nonce or installed["pid"] != os.getpid() or audit["distributions"] != 49:
        raise ValueError("scientific child import custody differs")
    require_live()
    boot = wait(root / "boot.json")
    task = boot["task"]
    if boot["nonce"] != nonce or "permit_scope" not in task:
        raise ValueError("missing independently governed learning mutation scope")
    from softqp.learning.parameters import torch

    if torch.get_num_threads() != 1 or torch.get_num_interop_threads() != 1:
        raise ValueError("verified SDK CPU thread policy differs")
    publish(
        root / "ready.json",
        encode({"nonce": nonce, "pid": os.getpid(), "seconds": import_seconds}),
    )
    _dispatch(Channel(root, nonce, require_live=require_live), task)


def _dispatch(channel, task):
    try:
        result = calibrate(channel, task) if task["operation"] == "calibrate" else train(channel, task)
    except (ArithmeticError, RuntimeError, ValueError) as error:
        channel.emit("failed", {"reason": f"{type(error).__name__}: {error}"})
    else:
        channel.emit("complete", {"result": result})


if __name__ == "__main__":
    root, unique = sys.argv[1:]
    main(Path(root), unique)
