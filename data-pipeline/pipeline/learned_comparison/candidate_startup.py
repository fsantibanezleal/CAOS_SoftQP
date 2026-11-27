"""Prospective cohorts and observed steady/cold accounting for candidate bakes."""

from collections import defaultdict
from math import fsum
from statistics import median

from . import contracts as c
from .evaluation import is_sha256


def verify_startup(doc, *, expected_roster, frozen_heads):
    c.ensure(
        set(doc) == {"schema", "slot_floor", "nonce", "pid", "profile_sha256", "policy_sha256",
                     "launch_ns", "ready_ns", "installed", "imported", "heads", "fixture_only"}
        and doc["schema"] == "softqp.r4.candidate-startup/1"
        and type(doc["fixture_only"]) is bool
        and type(doc["slot_floor"]) is int and doc["slot_floor"] >= 0
        and is_sha256(doc["profile_sha256"]) and is_sha256(doc["policy_sha256"])
        and type(doc["pid"]) is int and doc["pid"] > 0
        and type(doc["launch_ns"]) is type(doc["ready_ns"]) is int,
        "candidate startup shape differs",
    )
    ids = {"nonce": doc["nonce"], "pid": doc["pid"]}
    install, imported = doc["installed"], doc["imported"]
    c.ensure(
        {key: install[key] for key in ids} == {key: imported[key] for key in ids} == ids
        and set(imported) == set(ids) | {"start_ns", "end_ns"}
        and install["audit"]["distributions"] == 49 and install["audit"]["full_files"] is True
        and install["audit"]["profile_sha256"] == doc["profile_sha256"]
        and 0 < install["seconds"] < 600
        and doc["launch_ns"] < imported["start_ns"] < imported["end_ns"] < doc["ready_ns"]
        and imported["end_ns"] - imported["start_ns"] < 180 * 10**9,
        "candidate startup process/scan/import evidence differs",
    )
    by_seed = defaultdict(list)
    previous_end = imported["end_ns"]
    for row in doc["heads"]:
        method, seed = row["method"], row["seed"]
        by_seed[method, seed].append(row)
        if "failure" not in row:
            c.ensure(
                set(row) == {"method", "seed", "head", "start_ns", "end_ns", "checkpoint_sha256",
                             "weights_sha256", "preprocessing_sha256", "projection_sha256",
                             "calibration_sha256"}
                and all(is_sha256(row[name]) for name in ("weights_sha256", "preprocessing_sha256"))
                and previous_end <= row["start_ns"] < row["end_ns"] <= doc["ready_ns"],
                "candidate startup preload interval or evidence differs",
            )
            previous_end = row["end_ns"]
    c.ensure(list(by_seed) == [(row["method"], row["seed"]) for row in expected_roster],
             "candidate startup roster keys differ")
    for expected in expected_roster:
        method, seed = expected["method"], expected["seed"]
        rows = by_seed[method, seed]
        if "failure" in expected:
            c.ensure(rows == [{**expected, "head": None}], "candidate startup changed typed model absence")
            continue
        domain = {"graph"} if method == "learned_daqp" else {row["id"] for row in frozen_heads}
        heads = [row["head"] for row in rows]
        c.ensure(
            bool(heads) and heads == sorted(set(heads))
            and (set(heads) <= domain if doc["fixture_only"] else set(heads) == domain)
            and all(all(row[name] == expected[name] for name in
                        ("checkpoint_sha256", "projection_sha256", "calibration_sha256")) for row in rows),
            "candidate startup changed frozen head inventory or checkpoint binding",
        )


def cohort_plan(authority, schedule):
    by_cell = {}
    for row in authority.matrix["heads"]:
        for cell in row["members"]:
            c.ensure(cell not in by_cell, "duplicate learned OSQP cohort mapping")
            by_cell[cell] = row["id"]
    cohorts = defaultdict(set)
    first = {}
    for method, seed, family, regime, unit, frame, phase, rep in schedule:
        head = (by_cell[f"{family}:r{regime}"] if method == "learned_osqp" else
                "graph" if method == "learned_daqp" else None)
        key = (method, seed, head)
        cohorts[key].add((family, regime, unit, frame))
        c.ensure(phase == "warmup" or key in first, "cohort lacks prospective first contact")
        first.setdefault(key, (method, seed, family, regime, unit, frame, phase, rep))
    return [{"key": list(key), "frames": [list(v) for v in sorted(cohorts[key])],
             "first": list(first[key])} for key in sorted(cohorts)]


def _setup(result):
    native = result.get("native")
    if not isinstance(native, dict):
        return None
    for field in ("setup_seconds", "setup_time", "setup_wall_seconds"):
        duration = native.get(field)
        if type(duration) in {int, float} and 0 < duration < 10:
            return {"field": field, "seconds": duration}
    return None


class TimingCohorts:
    """Accumulate the independently rechecked status stream once."""

    def __init__(self, plan):
        self.frames = {}
        self.first = {}
        self.states = {}
        for row in plan:
            group = tuple(row["key"])
            self.first[tuple(row["first"])] = group
            self.states[group] = {
                "eligible": len(row["frames"]), "observed": [], "workers": set(), "setup": None,
            }
            for frame in row["frames"]:
                key = (*group[:2], *frame)
                c.ensure(key not in self.frames, "duplicate prospective cohort frame")
                self.frames[key] = group
        self.pending = defaultdict(list)
        self.startups = set()

    def observe(self, slot, trial, numeric):
        group = self.frames[tuple(slot)]
        state = self.states[group]
        if (*slot, trial["phase"], trial["rep"]) in self.first:
            state["setup"] = _setup(numeric)
        state["workers"].add(numeric["startup_sha256"])
        self.startups.add(numeric["startup_sha256"])
        if trial["state"] == "accepted" and trial["phase"] == "measured":
            self.pending[tuple(slot)].append(trial["full_cost_ns"])

    def finish_frame(self, row):
        if row["state"] == "incompatible":
            return
        key = tuple(row["key"])
        group = self.frames.pop(key)
        values = self.pending.pop(key, [])
        if row["state"] == "accepted":
            c.ensure(len(values) == 5, "cohort median lacks all measured repetitions")
            self.states[group]["observed"].append(median(values))

    def rows(self, startups):
        c.ensure(not self.frames and not self.pending, "candidate timing cohort was truncated")
        for key, state in self.states.items():
            startup = next(iter(state["workers"])) if len(state["workers"]) == 1 else None
            observed = len(state["observed"])
            reason = None
            if observed != state["eligible"]:
                reason = "incomplete-eligible-frames"
            elif startup is None or startup not in startups:
                reason = "no-single-observed-cold-configuration"
            elif state["setup"] is None:
                reason = "prospectively-keyed-native-setup-unobserved"
            mean = fsum(state["observed"]) / observed if reason is None else None
            cold = startups[startup]["ready_ns"] - startups[startup]["launch_ns"] if reason is None else None
            yield {
                "key": list(key), "eligible_frames": state["eligible"], "accepted_frames": observed,
                "setup": state["setup"], "startup_sha256": startup, "steady_mean_ns": mean,
                "cold_launch_to_ready_ns": cold, "reason": reason,
                "batch": [{"size": size, "per_frame_ns": mean + cold / size if reason is None else None}
                          for size in (1, 10, 100)],
            }
