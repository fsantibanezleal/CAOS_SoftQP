"""Prospective R4 source equations and factored source/frame serialization."""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, replace
import os
from pathlib import Path
import tempfile
from time import monotonic
from types import MappingProxyType
from weakref import WeakKeyDictionary

import numpy as np

from . import authority as i1
from . import contracts as c
from . import stream_inputs as stream
from .authority import (
    ApprovalTrust,
    I1Authority,
    _GeneratorWorkerScope,
    _json,
    _reference,
    _require_generator_scope,
    _shape,
    claim_generator_draw,
    generator_worker_policy,
    load_i1_authority,
    require_i1,
)


SPLITS = MappingProxyType({"train": 32, "validation": 8, "calibration": 8, "test": 8})
REGIMES = MappingProxyType({
    "N01": (0, .25, .5, 1, 2, 4),
    "N02": (0, .25, .5, 1, 2, 4),
    "N03": (0, .1, .2, .4, .8, 1.6),
    "N04": (.5, .75, 1, 1.25, 1.5, 2),
    "N05": (.5, .75, 1, 1.5, 2, 4),
    "N06": (.05, .1, .2, .3, .5, .8),
    "N07": (0, 2, 4, 8, 12, 16),
    "N08": (1, 10, 100, 1000, 10000, 100000),
    "N09": (.2, .4, .8, 1.2, 1.6, 2),
    "N10": (.1, .2, .3, .4, .6, .8),
    "N11": (.05, .1, .2, .4, .8, 1.6),
    "N12": (0, .2, .4, .6, .8, 1),
    "N13": (.25, .5, 1, 2, 4, 8),
    "N14": (.25, .5, 1, 2, 4, 8),
    "N15": (.1, .25, .5, 1, 2, 4),
})
_ENTROPY_PREFIX = (20261105, 903)
_FIXTURE_PREFIX = c._GENERATOR_FIXTURE_ENTROPY_PREFIX
_DT = .2
_MPC_HORIZON = 20
_THERMAL_HORIZON = 16
_REGIME_UNITS = {"N06": "fraction", "N07": "count", "N09": "m", "N10": "m", "N12": "m/s"}
_ATTRIBUTION = "SoftQP R4 authored synthetic QP equations"
_THERMAL_ATTRIBUTION = (
    "SoftQP R4 authored two-zone RC equations, adapted from CAOS SoftQP coupled_cases.py (MIT) "
    "at bbdd7909b2ee523881383764eb969eaab079d4de"
)
_GENERATOR_FILE = Path(__file__)
_LOADED_GENERATOR_SHA256 = c.digest(_GENERATOR_FILE.read_bytes())
_REGISTERED_UNITS = WeakKeyDictionary()
_SLOT_KEYS = ("family", "regime", "split", "unit")


class RegistrationUnavailable(c.ContractError):
    """The independent I1 source/lock/registration trust root is unavailable."""


def _digest(value):
    return c.digest(c.canonical_bytes(value))


def generator_sha256():
    """Identity of the actual generator module bytes, independent of a payload claim."""
    c.ensure(c.digest(_GENERATOR_FILE.read_bytes()) == _LOADED_GENERATOR_SHA256,
             "generator source changed after import")
    return _LOADED_GENERATOR_SHA256


@dataclass(frozen=True)
class SourceSlot:
    family: str
    regime: int
    split: str
    unit: int

    def __post_init__(self):
        if (
            self.family not in REGIMES
            or self.split not in SPLITS
            or type(self.regime) is not int
            or not 0 <= self.regime < 6
            or type(self.unit) is not int
            or not 0 <= self.unit < SPLITS[self.split]
        ):
            raise ValueError("unknown R4 family, regime or source slot")

    @property
    def frame_count(self):
        return 32 if self.family == "N12" else 1

    @property
    def source_id(self):
        return f"{self.family}-r{self.regime}-{self.split}-u{self.unit:02d}"

    def entropy(self, stream_code, *, fixture=False):
        if type(stream_code) is not int or stream_code not in (0, 1, 2):
            raise ValueError("unknown R4 RNG stream")
        prefix = _FIXTURE_PREFIX if fixture else _ENTROPY_PREFIX
        return [*prefix, int(self.family[1:]), self.regime, list(SPLITS).index(self.split), self.unit, stream_code]


def source_slots(authority):
    """Enumerate the exact source inventory without constructing an RNG or a QP."""
    rows = authority.matrix["rows"]
    actual = {(row["case_id"], row["regime"]) for row in rows}
    expected = {(family, regime) for family in REGIMES for regime in range(6)}
    c.ensure(len(rows) == len(expected) and actual == expected, "R4 source cell inventory differs")
    c.ensure(authority.matrix["split_units"] == SPLITS, "R4 source split inventory differs")
    for family, regime in sorted(actual):
        for split, count in SPLITS.items():
            for unit in range(count):
                yield SourceSlot(family, regime, split, unit)


def frame_keys(authority):
    """Family, regime, split, unit and frame keys in source-plan order."""
    for slot in source_slots(authority):
        for frame in range(slot.frame_count):
            yield slot.family, slot.regime, slot.split, slot.unit, frame


def _values(array):
    values = np.array(array, dtype=np.float64, copy=True)
    if not np.isfinite(values).all():
        raise ValueError("nonfinite generated coefficient or parameter")
    values[values == 0] = 0.0
    return values


def _mirrored(temporary):
    upper = np.triu(_values(temporary))
    return upper + np.triu(upper, k=1).T


def _rng(entropy):
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(entropy)))


def _parameter(name, value, unit, code):
    return {"name": name, "value": _values(value).reshape(-1).tolist(), "unit": unit, "stream": code}


def _state_sha_parameters(states, stage, code):
    raw = bytes.fromhex(_digest(states))
    return _parameter(f"pcg64_stream_{code}_{stage}_sha256", list(raw), "sha256-octets", code)


def _pd(rng, n, condition):
    raw = rng.normal(size=(n, n))
    Q, R = np.linalg.qr(raw, mode="reduced")
    Q *= np.where(np.diag(R) < 0, -1.0, 1.0)
    scale = rng.uniform(.8, 1.2)
    eigenvalues = np.geomspace(1, condition, n, dtype=np.float64)
    temporary = ((Q * eigenvalues) @ Q.T) * scale
    parameters = [
        _parameter("curvature_scale", scale, "dimensionless", 0),
        _parameter("pd_normal_matrix", raw, "dimensionless", 0),
    ]
    return _mirrored(temporary), temporary, parameters


def _psd(rng, n, rank):
    permutation = rng.permutation(n)
    scale = rng.uniform(.8, 1.2)
    diagonal = np.zeros(n)
    diagonal[permutation[:rank]] = scale * np.geomspace(1, 10, rank, dtype=np.float64)
    P = np.diag(diagonal)
    return P, P.copy(), [
        _parameter("curvature_scale", scale, "dimensionless", 0),
        _parameter("diagonal_permutation", permutation, "index", 0),
        _parameter("requested_rank", rank, "count", 0),
    ]


def _certificate(P, temporary, *, condition=None, diagonal=False):
    temporary = np.asarray(temporary, dtype=np.float64)
    c.ensure(np.isfinite(temporary).all(), "nonfinite temporary Hessian constructor")
    rank, pivots = c.exact_curvature(_values(P).tolist())
    c.ensure(diagonal or rank == len(P), "generator requires an exact positive definite stored Hessian")
    support = []
    if diagonal:
        c.ensure(np.array_equal(P, np.diag(np.diag(P))), "exact diagonal recipe became dense")
        support = np.flatnonzero(np.diag(P) > 0).tolist()
        c.ensure(rank == len(support), "exact diagonal support differs from rank")
    actual = float(np.linalg.cond(P, p=2)) if rank == len(P) else None
    c.ensure(actual is None or np.isfinite(actual), "generator condition is nonrepresentable")
    return {
        "kind": "exact-diagonal-PSD" if diagonal else "exact-rational-LDL",
        "rank": rank,
        "pivots": [] if diagonal else pivots,
        "diagonal_support": support,
        "temporary_constructor_sha256": _digest(temporary.tolist()),
        "requested_condition": condition,
        "actual_condition": actual,
    }


def _random_rows(rng, count, n, density):
    mask = rng.uniform(size=(count, n)) < density
    normal = rng.normal(size=(count, n))
    rows = np.where(mask, normal / np.sqrt(max(1, density * n)), 0.0)
    parameters = [
        _parameter("requested_random_row_density", density, "fraction", 0),
        _parameter("sampled_mask_density", mask.mean(), "fraction", 0),
        _parameter("actual_random_row_density", np.count_nonzero(rows) / rows.size, "fraction", 0),
    ]
    bits = mask.reshape(-1)
    for offset in range(0, bits.size, 1024):
        parameters.append(_parameter(f"random_row_mask_{offset:04d}", bits[offset:offset + 1024], "bool", 0))
    return rows, parameters


def _soft_intervals(rng, count):
    center = rng.uniform(-.1, .1, size=count)
    half_width = rng.uniform(.3, .6, size=count)
    return center - half_width, center + half_width, [
        _parameter("soft_interval_centers", center, "dimensionless", 1),
        _parameter("soft_interval_half_widths", half_width, "dimensionless", 1),
    ]


def _penalty(soft, *, linear=.3, quadratic=2., ratio=1., grouped=False):
    if grouped:
        linear = quadratic = 0.0
    return {
        "soft": soft.tolist(),
        "lower_linear": np.where(soft, linear, 0.0).tolist(),
        "upper_linear": np.where(soft, linear * ratio, 0.0).tolist(),
        "lower_quadratic": np.where(soft, quadratic, 0.0).tolist(),
        "upper_quadratic": np.where(soft, quadratic * ratio, 0.0).tolist(),
    }


def _group(group_id, rows, ratio, price, quadratic):
    return {"group_id": group_id, "rows": rows, "lower_scale": [1.] * len(rows),
            "upper_scale": [ratio] * len(rows), "linear": price, "quadratic": quadratic}


def _static(P, A, soft, *, linear=.3, quadratic=2., ratio=1., groups=(),
            variable_units=None, row_units=None, peak_unit="dimensionless",
            objective="synthetic-operating-cost"):
    m, n = A.shape
    return {
        "n": n,
        "m": m,
        "P": c.csc(_values(P).tolist(), n),
        "A": c.csc(_values(A).tolist(), n),
        "penalty": _penalty(soft, linear=linear, quadratic=quadratic, ratio=ratio, grouped=bool(groups)),
        "groups": list(groups),
        "units": {
            "variable": variable_units or ["dimensionless"] * n,
            "row": row_units or ["dimensionless"] * m,
            "peak": [peak_unit] * len(groups),
            "objective": objective,
            "D_x": [1.] * n,
            "D_r": [1.] * m,
            "D_t": [1.] * len(groups),
            "S_f": 1.,
        },
        "formulation": "peak" if groups else "separable",
    }


def _vectors(q, lower, upper):
    if np.isnan(lower).any() or np.isnan(upper).any() or np.isposinf(lower).any() or np.isneginf(upper).any():
        raise ValueError("invalid generated interval")
    if np.any(lower > upper):
        raise ValueError("reversed generated interval")
    return {
        "q": _values(q).tolist(),
        "lower": [None if np.isneginf(x) else 0.0 if x == 0 else float(x) for x in lower],
        "upper": [None if np.isposinf(x) else 0.0 if x == 0 else float(x) for x in upper],
    }


def _scalar(family, value, coefficient, operating):
    curvature = coefficient.uniform(.8, 1.2)
    lower = operating.uniform(-1.1, -.9)
    upper = lower + 2
    jitter = operating.uniform(.95, 1.05)
    distance = value * jitter
    target = lower - distance if family == "N01" else upper + distance
    P = np.array([[curvature]])
    static = _static(P, np.eye(1), np.array([True]), ratio=1 if family == "N01" else 2)
    return static, _certificate(P, P), [_vectors([-curvature * target], np.array([lower]), np.array([upper]))], [
        _parameter("curvature", curvature, "dimensionless", 0),
        _parameter("interval_lower", lower, "dimensionless", 1),
        _parameter("distance_jitter", jitter, "dimensionless", 1),
        _parameter("unconstrained_target", target, "dimensionless", 1),
    ]


def _conflicting(family, value, coefficient, operating):
    n, condition = (2, 5) if family == "N03" else (8, 10)
    P, temporary, parameters = _pd(coefficient, n, condition)
    A = np.concatenate([np.eye(n)] * (2 if family == "N03" else 3))
    lower = np.r_[np.full(n, -np.inf), np.full(n, value / 2)]
    upper = np.r_[np.full(n, -value / 2), np.full(n, np.inf)]
    if family == "N11":
        lower, upper = np.r_[lower, np.full(n, -1.)], np.r_[upper, np.ones(n)]
    q = operating.normal(0, 3, size=n)
    # LC-010 preserves the symmetric row declaration. A null side masks its
    # nominal common price and creates no separate penalty side.
    static = _static(P, A, np.ones(len(A), dtype=bool), quadratic=0.)
    return static, _certificate(P, temporary, condition=condition), [_vectors(q, lower, upper)], parameters


_BOX_SHAPES = {
    "N04": (2, 6), "N05": (8, 24), "N06": (32, 80), "N07": (16, 40),
    "N08": (32, 80), "N15": (16, 40),
}


def _box_family(family, value, coefficient, operating):
    n, m = _BOX_SHAPES[family]
    condition = {"N04": 5, "N07": None, "N08": value}.get(family, 10)
    if family == "N07":
        P, temporary, parameters = _psd(coefficient, n, value)
    else:
        P, temporary, parameters = _pd(coefficient, n, condition)
    density = {"N06": value, "N08": .2, "N15": .2}.get(family, 1.)
    random_rows, row_parameters = _random_rows(coefficient, m - n, n, density)
    A = np.concatenate((np.eye(n), random_rows))
    parameters.extend(row_parameters)
    parameters.append(_parameter("actual_full_row_density", np.count_nonzero(A) / A.size, "fraction", 0))
    lo, up, interval_parameters = _soft_intervals(operating, m - n)
    parameters.extend(interval_parameters)
    base_q = operating.normal(0, 3, size=n)
    q = base_q * value if family == "N04" else base_q
    if family == "N04":
        parameters.append(_parameter("unscaled_linear_term", base_q, "dimensionless", 1))
    box = 1 if family == "N04" else 2
    groups = ()
    if family == "N05":
        groups = tuple(_group(g, list(range(n + 4*g, n + 4*(g + 1))), value, .5, 1.) for g in range(4))
    static = _static(P, A, np.arange(m) >= n, ratio=2 if family == "N08" else 1,
                     quadratic=.3 * value if family == "N15" else 2., groups=groups)
    curvature = _certificate(P, temporary, condition=condition, diagonal=family == "N07")
    if family == "N07":
        c.ensure(curvature["rank"] == value, "exact diagonal rank differs from regime")
    return static, curvature, [_vectors(q, np.r_[np.full(n, -box), lo], np.r_[np.full(n, box), up])], parameters


@dataclass(frozen=True)
class MPCModel:
    mass: float
    position_weight: float
    velocity_weight: float
    force_weight: float

    @property
    def F(self):
        return np.array([[1., _DT], [0., 1.]])

    @property
    def B(self):
        return np.array([_DT**2 / (2 * self.mass), _DT / self.mass])

    def response(self):
        """Shape [horizon, position/velocity, input horizon] for forecasts."""
        k, j = np.indices((_MPC_HORIZON, _MPC_HORIZON))
        causal = k >= j
        position = np.where(causal, self.B[0] + (k - j) * _DT * self.B[1], 0.)
        velocity = np.where(causal, self.B[1], 0.)
        return np.stack((position, velocity), axis=1)

    def offset(self, state):
        steps = np.arange(1., _MPC_HORIZON + 1)
        return np.column_stack((state[0] + steps * _DT * state[1], np.repeat(state[1], _MPC_HORIZON)))

    def advance(self, state, force):
        return self.F @ state + self.B * force


def _mpc_family(family, value, coefficient, operating):
    parameters = []
    model = MPCModel(coefficient.uniform(.8, 1.2), coefficient.uniform(2.7, 3.3),
                     coefficient.uniform(.27, .33), coefficient.uniform(.09, .11))
    for name, value_, unit in (
        ("mass", model.mass, "kg"), ("position_weight", model.position_weight, "synthetic-operating-cost/m^2"),
        ("velocity_weight", model.velocity_weight, "synthetic-operating-cost/(m/s)^2"),
        ("force_weight", model.force_weight, "synthetic-operating-cost/N^2"),
        ("sample_interval", _DT, "s"), ("prediction_horizon", _MPC_HORIZON, "count"),
    ):
        parameters.append(_parameter(name, value_, unit, 0))

    if family == "N09":
        jitter = operating.uniform(.95, 1.05)
        position, limit = value * jitter, 2.
        parameters.append(_parameter("initial_position_jitter", jitter, "dimensionless", 1))
    elif family == "N10":
        position, limit = operating.uniform(1.14, 1.26), value
    else:
        position, limit = operating.uniform(.8, 1.6), .4
    velocity = operating.uniform(-.1, .1)
    parameters.extend((
        _parameter("initial_position", position, "m", 1),
        _parameter("initial_velocity", velocity, "m/s", 1),
        _parameter("position_limit", limit, "m", 1),
        _parameter("velocity_limit", 1.5, "m/s", 1),
        _parameter("force_limit", 1., "N", 1),
    ))
    h = _MPC_HORIZON
    response = model.response()
    G = response.reshape(2 * h, h)
    W = np.tile([model.position_weight, model.velocity_weight], h)
    temporary = G.T @ (W[:, None] * G) + model.force_weight * np.eye(h)
    P = _mirrored(temporary)
    A = np.concatenate((np.eye(h), response[:, 0, :], response[:, 1, :]))
    static = _static(P, A, np.arange(3*h) >= h, ratio=1 if family == "N09" else 2,
                     variable_units=["N"] * h, row_units=["N"] * h + ["m"] * h + ["m/s"] * h)
    base_lower = np.r_[np.full(h, -1.), np.full(h, -limit), np.full(h, -1.5)]
    base_upper = np.r_[np.ones(h), np.full(h, limit), np.full(h, 1.5)]
    state = np.array([position, velocity])
    frame_vectors, frame_parameters = [], []
    for frame in range(32 if family == "N12" else 1):
        before = state.copy()
        impulse = value if frame == 8 else -.75 * value if frame == 20 else 0.
        state[1] += impulse
        offset = model.offset(state)
        offsets = np.r_[np.zeros(h), offset[:, 0], offset[:, 1]]
        frame_vectors.append(_vectors(G.T @ (W * offset.reshape(-1)),
                                      base_lower - offsets, base_upper - offsets))
        dynamics = []
        if family == "N12":
            force = np.clip(-.5 * state[0] - .2 * state[1], -1., 1.)
            after = model.advance(state, force)
            for stage, vector in (("pre_impulse", before), ("post_impulse", state), ("next_pre_impulse", after)):
                dynamics.extend((
                    _parameter(stage + "_position", vector[0], "m", 2),
                    _parameter(stage + "_velocity", vector[1], "m/s", 2),
                ))
            dynamics.append(_parameter("impulse_velocity", impulse, "m/s", 2))
            dynamics.append(_parameter("held_reference_force", force, "N", 2))
            state = after
        frame_parameters.append(dynamics)
    return static, _certificate(P, temporary), frame_vectors, parameters, frame_parameters


def _thermal_family(family, value, coefficient, operating):
    h = _THERMAL_HORIZON
    a, b = zip(*[(coefficient.uniform(.88, .94), coefficient.uniform(.22, .30)) for _ in range(2)])
    phase = operating.uniform(0., 2 * np.pi, size=2)
    offset = operating.uniform(0., 24.)
    initial = 21.5 + .5 * np.sin(phase)
    hours = np.arange(h)
    daylight = np.sin(2 * np.pi * (hours + offset) / 24.)
    outside = 8. + 3. * daylight
    price = .2 + .08 * daylight

    temperatures = 2 * (h + 1)
    heats = 2 * h
    n, m = temperatures + heats, temperatures + 2 * heats
    P = np.diag(np.r_[np.full(temperatures, .002), np.full(heats, .04)])
    q = np.r_[np.full(temperatures, -22 * .002), np.tile(price, 2)]
    A = np.zeros((m, n))
    lower, upper = np.zeros(m), np.zeros(m)
    anchor = np.zeros(n)
    for zone in range(2):
        first_t = zone * (h + 1)
        first_heat = temperatures + zone * h
        A[first_t, first_t] = 1
        lower[first_t] = upper[first_t] = anchor[first_t] = initial[zone]
        for hour in range(h):
            j, j_heat = first_t + hour, first_heat + hour
            A[j + 1, j + 1] = 1
            A[j + 1, j] = -a[zone]
            A[j + 1, j_heat] = -b[zone]
            forcing = (1. - a[zone]) * outside[hour]
            lower[j + 1] = upper[j + 1] = forcing
            anchor[j + 1] = a[zone] * anchor[j] + forcing
            A[j_heat, j_heat] = 1
            upper[j_heat] = 6.
            A[j_heat + heats, j + 1] = 1
            lower[j_heat + heats], upper[j_heat + heats] = 21., 23.
    groups = ()
    if family == "N13":
        groups = tuple(_group(g, list(range(n+g*h, n+(g+1)*h)), 1.5, 5.*value, 1.) for g in range(2))
    static = _static(P, A, np.arange(m) >= n, quadratic=.4, ratio=value, groups=groups,
                     variable_units=["degreeC"] * temperatures + ["kWh"] * heats,
                     row_units=["degreeC"] * temperatures + ["kWh"] * heats + ["degreeC"] * heats,
                     peak_unit="degreeC", objective="synthetic-currency")
    parameters = [
        _parameter("retention", a, "dimensionless", 0),
        _parameter("heater_gain", b, "degreeC/kWh", 0),
        _parameter("initial_temperature_phase", phase, "radian", 1),
        _parameter("daytime_offset", offset, "hour", 1),
        _parameter("initial_temperatures", initial, "degreeC", 1),
        _parameter("outside_forecast", outside, "degreeC", 1),
        _parameter("hourly_heating_prices", price, "synthetic-currency/kWh", 1),
        _parameter("zero_heat_temperature_anchor", anchor[:temperatures], "degreeC", 1),
    ]
    return static, _certificate(P, P, diagonal=True), [_vectors(q, lower, upper)], parameters


@dataclass(frozen=True, eq=False)
class GeneratedUnit:
    """One source's shared coefficients and thin original-coordinate frame vectors."""

    slot: SourceSlot
    fixture: bool
    identity: str
    static: dict
    curvature: dict
    vectors: tuple
    observations: tuple
    generator_digest: str

    def frame_id(self, frame):
        if type(frame) is not int or not 0 <= frame < self.slot.frame_count:
            raise ValueError("invalid source frame")
        return f"{self.identity}-f{frame:02d}"

    def problem(self, frame):
        self.frame_id(frame)
        original = {**self.static, **self.vectors[frame]}
        original_sha256 = _digest(original)
        transform = c.canonical_transform(original)
        return {
            "source": {**self.observations[frame], "input_sha256": original_sha256},
            "generator_sha256": self.generator_digest,
            "original": original,
            "original_sha256": original_sha256,
            "curvature": self.curvature,
            "transform": transform,
            "transform_sha256": _digest(transform),
            "physical_calibration": {
                "scale_policy": "canonical-reference-magnitudes-one",
                "calibration_sha256": _digest(original["units"]),
            },
            "expected_control": None,
        }

    def numeric_identity(self):
        return _digest([self.static, self.curvature, list(self.vectors), list(self.observations)])


def generate_registered_unit(slot, *, context, protocol_ref, authority=None):
    """Generate the exact scientific source after independent I1 admission."""
    if type(slot) is not SourceSlot:
        raise TypeError("generation requires a validated SourceSlot")
    if type(authority) is not I1Authority or not authority.allows("generate-source"):
        raise RegistrationUnavailable("independently authenticated I1 source, runtime lock and registration unavailable")
    unit = _construct_unit(slot, fixture=False, authority=authority, context=context, protocol_ref=protocol_ref)
    _REGISTERED_UNITS[unit] = (authority, unit.numeric_identity())
    return unit


def generate_fixture_unit(slot):
    """Exercise the exact equations under the excluded engineering entropy namespace."""
    return _construct_unit(slot, fixture=True)


def _construct_unit(slot, *, fixture, authority=None, context=None, protocol_ref=None):
    if type(slot) is not SourceSlot:
        raise TypeError("generation requires a validated SourceSlot")
    source_sha256 = generator_sha256()
    if not fixture:
        claim_generator_draw(authority, context=context, protocol_ref=protocol_ref,
                             generator_slot=_slot_key(slot))
        c.ensure(source_sha256 == context.generator_sha256, "active generator source differs from I1")
    coef, operating, perturbation = generators = tuple(
        _rng(slot.entropy(code, fixture=fixture)) for code in range(3)
    )
    initial = tuple(rng.bit_generator.state for rng in generators)
    family = slot.family
    value = REGIMES[family][slot.regime]
    varying_parameters = [[] for _ in range(slot.frame_count)]
    if family in {"N01", "N02"}:
        static, curvature, frames, parameters = _scalar(family, value, coef, operating)
    elif family in {"N03", "N11"}:
        static, curvature, frames, parameters = _conflicting(family, value, coef, operating)
    elif family in _BOX_SHAPES:
        static, curvature, frames, parameters = _box_family(family, value, coef, operating)
    elif family in {"N09", "N10", "N12"}:
        static, curvature, frames, parameters, varying_parameters = _mpc_family(family, value, coef, operating)
    else:
        static, curvature, frames, parameters = _thermal_family(family, value, coef, operating)
    parameters.append(_parameter("regime_value", value, _REGIME_UNITS.get(family, "dimensionless"),
                                 2 if family == "N12" else 1))
    for code, rng in enumerate(generators):
        parameters.extend((
            _state_sha_parameters(initial[code], "initial", code),
            _state_sha_parameters(rng.bit_generator.state, "final", code),
        ))
    c.ensure(perturbation.bit_generator.state == initial[2], "unregistered perturbation RNG draw")
    c.ensure(len(frames) == slot.frame_count, "generated frame inventory")
    for side in ("lower", "upper"):
        mask = [bound is not None for bound in frames[0][side]]
        c.ensure(all([x is not None for x in frame[side]] == mask for frame in frames),
                 "source changes finite-bound masks across frames")
        static[side + "_finite"] = mask
    identity = "fixture-" + slot.source_id if fixture else slot.source_id
    observations = tuple({
        "source_id": identity,
        "parent_id": identity + "-parent",
        "family": family,
        "regime": slot.regime,
        "split": slot.split,
        "unit_index": slot.unit,
        "frame": i,
        "frame_count": slot.frame_count,
        "entropy": slot.entropy(0, fixture=fixture),
        "rng_state": initial[0],
        "rng_state_sha256": _digest(initial[0]),
        "state_origin": "contract-fixture" if fixture else "generator-produced",
        "parameters": sorted(parameters + varying_parameters[i], key=lambda p: p["name"]),
        "attribution": _THERMAL_ATTRIBUTION if family in {"N13", "N14"} else _ATTRIBUTION,
        "license": "MIT",
    } for i in range(slot.frame_count))
    return GeneratedUnit(slot, fixture, identity, static, curvature, tuple(frames), observations, source_sha256)


def write_fixture_unit(unit, *, context, protocol_ref, directory=""):
    """Publish one fixture source and its vector files through the real v2 writer.

    The independently configured fixture context binds each expected original
    and source-record digest. The exact source reference is created only after
    the source writer succeeds.
    """
    if type(unit) is not GeneratedUnit or unit.fixture is not True or not context.allow_fixture:
        raise RegistrationUnavailable("scientific source writing requires independent I1 admission")
    return _write_unit(unit, context=context, protocol_ref=protocol_ref, directory=directory)


def write_registered_unit(unit, *, context, protocol_ref, authority=None, directory=""):
    """Publish one registered source and its thin frame vectors."""
    if type(unit) is not GeneratedUnit or unit.fixture is not False or (
        _REGISTERED_UNITS.get(unit) != (authority, unit.numeric_identity())
    ):
        raise RegistrationUnavailable("scientific writing requires an admitted scientific source")
    require_i1(authority, "generate-source", context=context, protocol_ref=protocol_ref,
               generator_slot=_slot_key(unit.slot))
    return _write_unit(unit, context=context, protocol_ref=protocol_ref, directory=directory)


def _slot_key(slot):
    return tuple(getattr(slot, name) for name in _SLOT_KEYS)


def _dispatch_context(policy):
    approval = _shape(policy["approval"], {"root", "index", "reviewer"}, "invalid generator approval policy")
    approval_ref = _shape(approval["index"], {"path", "sha256"}, "invalid generator approval index reference")
    protocol = _shape(policy["protocol"], {"id", "payload_sha256", "registration_sha256", "ref"},
                      "invalid generator protocol policy")
    protocol_ref = _shape(protocol["ref"], {"artifact_id", "kind", "path", "sha256"},
                          "invalid generator protocol reference")
    locks = _shape(policy["locks"], {"source", "dependency", "producer"}, "invalid generator lock inventory")
    roots = {
        name: Path(policy[name])
        for name in ("product_root", "engine_root", "design_root", "output_root")
    }
    governance_root = Path(approval["root"])
    for root in (*roots.values(), governance_root):
        c.ensure(root.is_absolute() and root.is_dir() and root.resolve(strict=True).parts == root.parts,
                 "generator requires exact independently configured directories")
    trust = ApprovalTrust(
        governance_root, approval_ref["path"], approval_ref["sha256"], approval["reviewer"],
        roots["product_root"], roots["engine_root"],
    )
    design = c.Authority.load(roots["design_root"])
    generator = _GENERATOR_FILE.read_bytes()
    source, dependency, producer = (
        _reference(governance_root, locks[name]) for name in ("source", "dependency", "producer")
    )
    context = c.AdmissionContext(
        root=roots["output_root"], authority=design, protocol_id=protocol["id"],
        protocol_sha256=protocol["payload_sha256"], registration_sha256=protocol["registration_sha256"],
        source_lock_sha256=c.digest(source), dependency_lock_sha256=c.digest(dependency),
        generator_sha256=c.digest(generator), producer_source_sha256=c.digest(producer),
        settings_hashes={}, source_lock_bytes=source, dependency_lock_bytes=dependency,
        generator_source_bytes=generator, producer_source_bytes=producer,
        catalog={protocol_ref["artifact_id"]: protocol_ref}, problem_hashes={}, source_records={},
        fit_source_ids=(),
        expected_result_keys=design.keys("method-status") + design.keys("control-status"),
        expected_diagnostic_keys=design.keys("diagnostic-status"),
        forbidden_roots=(roots["product_root"], roots["engine_root"], roots["design_root"], governance_root),
    )
    return trust, context, protocol_ref


def dispatch_registered_request(raw: bytes, custody) -> dict:
    """Fixed engine-owned worker entrypoint for one independently approved source."""
    policy, request_sha256, policy_sha256 = generator_worker_policy(custody, raw)
    request = _shape(_json(raw), {"schema", "slot"}, "invalid registered generator request")
    _shape(policy, {
        "schema", "slot", "approval", "product_root", "engine_root", "design_root", "output_root",
        "locks", "protocol",
    }, "invalid governed generator launch policy")
    c.ensure(request["schema"] == "softqp.r4.generate-source-request/1"
             and policy["schema"] == "softqp.r4.generate-source-policy/1", "unknown generator dispatch schema")
    slot = SourceSlot(**_shape(request["slot"], _SLOT_KEYS, "invalid generator request slot"))
    approved_slot = SourceSlot(**_shape(policy["slot"], _SLOT_KEYS, "invalid governed generator slot"))
    c.ensure(slot == approved_slot, "generator request slot was not independently approved")
    trust, context, protocol_ref = _dispatch_context(policy)
    scope = _GeneratorWorkerScope(custody, request_sha256, policy_sha256, _slot_key(slot))
    approval = load_i1_authority(trust=trust, context=context, protocol_ref=protocol_ref, generator_scope=scope)
    destination = context.root / slot.source_id
    c.ensure(not destination.exists() and not destination.is_symlink(), "registered source output already exists")
    unit = generate_registered_unit(slot, context=context, protocol_ref=protocol_ref, authority=approval)
    problem_hashes, source_records = _unit_hashes(unit)
    publish_context = replace(context, problem_hashes=problem_hashes, source_records=source_records)
    _require_generator_scope(scope, _slot_key(slot))
    destination.mkdir()
    try:
        source_ref, frame_refs = write_registered_unit(
            unit, context=publish_context, protocol_ref=protocol_ref, authority=approval, directory=slot.source_id,
        )
    except Exception:
        # A partial publication stays available for diagnosis and cannot be
        # mistaken for a completed source receipt or overwritten by a retry.
        try:
            destination.rmdir()
        except OSError:
            pass
        raise
    return {
        "schema": "softqp.r4.generate-source-result/1", "request_sha256": request_sha256,
        "policy_sha256": policy_sha256, "slot": request["slot"],
        "protocol_sha256": context.protocol_sha256, "registration_sha256": context.registration_sha256,
        "generator_sha256": context.generator_sha256, "source": source_ref, "frames": list(frame_refs),
        "problem_hashes": problem_hashes, "source_records": source_records,
    }


def _write_unit(unit, *, context, protocol_ref, directory):
    c.ensure(unit.generator_digest == context.generator_sha256 == generator_sha256(),
             "generator source bytes differ from the admitted context")
    identity = "fixture-" + unit.slot.source_id if unit.fixture else unit.slot.source_id
    origin = "contract-fixture" if unit.fixture else "generator-produced"
    c.ensure(unit.identity == identity, "generated source identity")
    for frame, (vectors, observation) in enumerate(zip(unit.vectors, unit.observations, strict=True)):
        artifact_id = unit.frame_id(frame)
        original_sha256 = _digest({**unit.static, **vectors})
        c.ensure(
            observation["state_origin"] == origin
            and observation["entropy"] == unit.slot.entropy(0, fixture=unit.fixture)
            and context.problem_hashes.get(artifact_id) == original_sha256
            and context.source_records.get(artifact_id) == _digest({**observation, "input_sha256": original_sha256}),
            "generated frame input/source provenance differs from the sealed context",
        )
    c.ensure(len(unit.vectors) == unit.slot.frame_count, "generated frame inventory")

    def output_path(name):
        path = name + ".json"
        return directory + "/" + path if directory else path

    source_id = unit.identity + "-source"
    source_path = output_path(source_id)
    first = unit.problem(0)
    document = stream.stream_document(stream.SOURCE, source_id, stream.factor_source(first), context, protocol_ref)
    source = stream.write_stream_artifact(document, source_path, context)
    source_ref = dict(kind=stream.SOURCE, artifact_id=source_id, path=source_path, sha256=source.raw_sha256)
    child = replace(context, catalog={**context.catalog, source_id: source_ref})
    frame_refs = []
    for frame in range(unit.slot.frame_count):
        artifact_id = unit.frame_id(frame)
        path = output_path(artifact_id)
        payload = stream.factor_frame(first if frame == 0 else unit.problem(frame), source_ref)
        document = stream.stream_document(stream.FRAME, artifact_id, payload, child, protocol_ref)
        artifact = stream.write_stream_artifact(document, path, child)
        frame_refs.append(dict(kind=stream.FRAME, artifact_id=artifact_id, path=path, sha256=artifact.raw_sha256))
    return source_ref, tuple(frame_refs)


_CAMPAIGN_REQUEST = "softqp.r4.generate-campaign-request/1"
_CAMPAIGN_POLICY = "softqp.r4.generate-campaign-policy/1"
_CAMPAIGN_PLAN = "softqp.r4.generate-campaign-plan/1"
_CAMPAIGN_FRONTIER = "softqp.r4.generate-campaign-frontier/1"
_CAMPAIGN_ROW = "softqp.r4.generate-campaign-row/1"
_SHARED_POLICY = ("approval", "product_root", "engine_root", "design_root", "output_root", "locks", "protocol")


def _win_kernel():
    c.ensure(os.name == "nt", "durable campaign requires the admitted Windows filesystem")
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _require_local_ntfs(root):
    kernel = _win_kernel()
    volume_path = kernel.GetVolumePathNameW
    volume_path.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
    volume_path.restype = wintypes.BOOL
    drive_type = kernel.GetDriveTypeW
    drive_type.argtypes = (wintypes.LPCWSTR,)
    drive_type.restype = wintypes.UINT
    volume_info = kernel.GetVolumeInformationW
    volume_info.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
                            wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID,
                            wintypes.LPWSTR, wintypes.DWORD)
    volume_info.restype = wintypes.BOOL
    volume, filesystem = ctypes.create_unicode_buffer(32768), ctypes.create_unicode_buffer(32)
    c.ensure(volume_path(str(root), volume, len(volume))
             and drive_type(volume.value) == 3
             and volume_info(volume.value, None, 0, None, None, None, filesystem, len(filesystem))
             and filesystem.value == "NTFS", "campaign storage requires independently scoped local NTFS")


@contextmanager
def _campaign_lease(path):
    kernel = _win_kernel()
    open_file = kernel.CreateFileW
    open_file.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                          wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    open_file.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL
    c._refuse_reparse(path)
    c.ensure(path.is_file(), "missing independently provisioned campaign lease")
    # GENERIC_READ, no sharing, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT.
    handle = open_file(str(path), 0x80000000, 0, None, 3, 0x00200000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise c.ContractError("campaign lease is held or unavailable") from ctypes.WinError(ctypes.get_last_error())
    try:
        c._refuse_reparse(path)
        yield
    finally:
        close(handle)


def _durable_move(source, target, *, overwrite=False):
    """Same-directory NTFS rename with Windows write-through, never cross-volume copy."""
    c.ensure(source.parent == target.parent, "durable campaign rename requires the same directory")
    c._refuse_reparse(target)
    kernel = _win_kernel()
    move = kernel.MoveFileExW
    move.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
    move.restype = wintypes.BOOL
    if not move(str(source), str(target), 0x8 | int(overwrite)):
        raise ctypes.WinError(ctypes.get_last_error())


def _durable_write(path, raw, *, overwrite=False):
    c._refuse_reparse(path)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".pending-", delete=False) as handle:
        pending = Path(handle.name)
        try:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            handle.close()
            pending.unlink()
            raise
    try:
        _durable_move(pending, path, overwrite=overwrite)
    finally:
        pending.unlink(missing_ok=True)


def _durable_directory(path):
    c._refuse_reparse(path)
    pending = Path(tempfile.mkdtemp(dir=path.parent, prefix=".pending-dir-"))
    try:
        _durable_move(pending, path)
    finally:
        if pending.exists():
            pending.rmdir()


def _directory_chain(root, parts):
    current = root
    for part in parts:
        current /= part
        c._refuse_reparse(current)
        if not current.exists():
            _durable_directory(current)
        c.ensure(current.is_dir(), "campaign directory path owner differs")
    return current


def _campaign_file(path):
    c._refuse_reparse(path)
    c.ensure(path.is_file() and path.stat().st_size <= 16 * 2**20, "invalid bounded campaign record")
    return path.read_bytes()


def _campaign_frontier(path, expected, plan_sha256, count):
    raw = _campaign_file(path)
    c.ensure(c.digest(raw) == expected, "independent campaign frontier changed or rolled back")
    frontier = _shape(_json(raw), {"schema", "plan_sha256", "next", "last_sha256", "attempt"},
                      "invalid campaign frontier")
    index, previous = frontier["next"], frontier["last_sha256"]
    c.ensure(frontier["schema"] == _CAMPAIGN_FRONTIER and frontier["plan_sha256"] == plan_sha256
             and type(index) is int and 0 <= index <= count
             and (previous is None if index == 0 else i1._hex(previous)), "frontier does not name the approved plan")
    attempt = frontier["attempt"]
    if attempt is not None:
        _shape(attempt, {"ordinal", "intent_sha256", "ready_sha256"}, "invalid independent in-flight attempt")
        c.ensure(type(attempt["ordinal"]) is int and attempt["ordinal"] == index < count
                 and i1._hex(attempt["intent_sha256"])
                 and (attempt["ready_sha256"] is None or i1._hex(attempt["ready_sha256"])),
                 "invalid independent in-flight attempt")
    return raw, index, previous, attempt


def _campaign_entry(shared, slot):
    record = dict(zip(_SLOT_KEYS, _slot_key(slot), strict=True))
    request = c.canonical_bytes({"schema": "softqp.r4.generate-source-request/1", "slot": record})
    policy = c.canonical_bytes({**shared, "schema": "softqp.r4.generate-source-policy/1", "slot": record})
    return {"slot": record, "request_sha256": c.digest(request), "policy_sha256": c.digest(policy)}, request, policy


def _stage_context(context, stage, protocol_ref):
    return replace(context, root=stage, catalog={protocol_ref["artifact_id"]: protocol_ref})


def _unit_hashes(unit):
    problem_hashes, source_records = {}, {}
    for frame, (vectors, source) in enumerate(zip(unit.vectors, unit.observations, strict=True)):
        identity = unit.frame_id(frame)
        original = _digest({**unit.static, **vectors})
        problem_hashes[identity] = original
        source_records[identity] = _digest({**source, "input_sha256": original})
    return problem_hashes, source_records


def _campaign_result(context, entry, source, frames, problem_hashes, source_records):
    return {
        **entry, "protocol_sha256": context.protocol_sha256,
        "registration_sha256": context.registration_sha256, "generator_sha256": context.generator_sha256,
        "source": source, "frames": list(frames), "problem_hashes": problem_hashes, "source_records": source_records,
    }


def _check_campaign_result(context, protocol_ref, slot, entry, result):
    keys = {"slot", "request_sha256", "policy_sha256", "protocol_sha256", "registration_sha256",
            "generator_sha256", "source", "frames", "problem_hashes", "source_records"}
    _shape(result, keys, "invalid campaign source receipt")
    c.ensure(all(result[key] == value for key, value in entry.items())
             and all(result[key] == getattr(context, key) for key in
                     ("protocol_sha256", "registration_sha256", "generator_sha256")), "campaign source receipt identity")
    source_id = ("fixture-" if context.allow_fixture else "") + slot.source_id
    frame_ids = tuple(f"{source_id}-f{frame:02d}" for frame in range(slot.frame_count))
    refs = (result["source"], *result["frames"])
    wanted = tuple(zip((stream.SOURCE, *((stream.FRAME,) * len(frame_ids))),
                       (source_id + "-source", *frame_ids), strict=True))
    c.ensure(len(refs) == len(wanted)
             and set(result["problem_hashes"]) == set(result["source_records"]) == set(frame_ids),
             "campaign source/frame inventory differs")
    for ref, (kind, artifact_id) in zip(refs, wanted, strict=True):
        _shape(ref, {"kind", "artifact_id", "path", "sha256"}, "invalid campaign file reference")
        c.ensure((ref["kind"], ref["artifact_id"], ref["path"]) ==
                 (kind, artifact_id, f"{slot.source_id}/{artifact_id}.json"), "campaign artifact path owner differs")
    admitted = replace(
        context, catalog={protocol_ref["artifact_id"]: protocol_ref, **{r["artifact_id"]: r for r in refs}},
        problem_hashes=result["problem_hashes"], source_records=result["source_records"],
    )
    for ref in refs:
        path = c.safe_path(context.root, ref["path"], must_exist=True)
        observed = stream.read_stream_artifact(path, admitted, expected_sha256=ref["sha256"])
        c.ensure((observed.kind, observed.artifact_id) == (ref["kind"], ref["artifact_id"]),
                 "stored campaign artifact identity differs")
    return refs


def _stage_campaign_unit(context, protocol_ref, stage, slot, entry, make_unit):
    protocol_raw = i1._read(context.root, protocol_ref["path"], protocol_ref["sha256"])
    protocol_parts = c._relative_parts(protocol_ref["path"])
    protocol_parent = _directory_chain(stage, protocol_parts[:-1])
    _durable_write(protocol_parent / protocol_parts[-1], protocol_raw)
    _durable_directory(stage / slot.source_id)
    unit = make_unit()
    problem_hashes, source_records = _unit_hashes(unit)
    staged = replace(_stage_context(context, stage, protocol_ref),
                     problem_hashes=problem_hashes, source_records=source_records)
    source, frames = _write_unit(unit, context=staged, protocol_ref=protocol_ref, directory=slot.source_id)
    result = _campaign_result(context, entry, source, frames, problem_hashes, source_records)
    for ref in _check_campaign_result(staged, protocol_ref, slot, entry, result):
        path = c.safe_path(stage, ref["path"], must_exist=True)
        _durable_write(path, i1._read(stage, ref["path"], ref["sha256"]), overwrite=True)
    return result


def _publish_campaign_unit(context, protocol_ref, attempt, stage, slot, entry, result):
    refs = _check_campaign_result(_stage_context(context, stage, protocol_ref), protocol_ref, slot, entry, result)
    marker = attempt / "publish.json"
    target_dir = context.root / slot.source_id
    mark = c.canonical_bytes({"result_sha256": _digest(result)})
    if marker.exists():
        c.ensure(_campaign_file(marker) == mark, "campaign publication ownership differs")
    else:
        c._refuse_reparse(target_dir)
        c.ensure(not target_dir.exists(), "campaign destination already has another owner")
        _durable_write(marker, mark)
    _directory_chain(context.root, (slot.source_id,))
    expected_names = {Path(ref["path"]).name for ref in refs}
    c.ensure(all(path.name in expected_names for path in target_dir.iterdir()),
             "campaign destination contains an unexpected path owner")
    for ref in refs:
        raw = i1._read(stage, ref["path"], ref["sha256"])
        target = c.safe_path(context.root, ref["path"], must_exist=False)
        if target.exists():
            c.ensure(i1._read(context.root, ref["path"], ref["sha256"]) == raw,
                     "previous campaign publication differs from staged bytes")
        else:
            _durable_write(target, raw)
    _check_campaign_result(context, protocol_ref, slot, entry, result)


def _release_committed_stage(stage, protocol_ref, result):
    """Remove only stage bytes whose exact output now sits behind the durable frontier."""
    refs = (protocol_ref, result["source"], *result["frames"])
    paths = [c.safe_path(stage, ref["path"], must_exist=True) for ref in refs]
    parents = {ancestor for path in paths for ancestor in path.parents if ancestor.is_relative_to(stage)}
    for path in paths:
        path.unlink()
    for path in sorted(parents, key=lambda parent: len(parent.parts), reverse=True):
        path.rmdir()


def _campaign_row(journal, ordinal):
    return journal / f"{ordinal:05d}.json"


def _read_committed_row(context, protocol_ref, journal, plan_sha256, predecessor, ordinal, slot, entry):
    raw = _campaign_file(_campaign_row(journal, ordinal))
    row = _shape(_json(raw), {"schema", "plan_sha256", "ordinal", "predecessor", "result"},
                 "invalid campaign completion record")
    c.ensure(row["schema"] == _CAMPAIGN_ROW and row["plan_sha256"] == plan_sha256
             and row["ordinal"] == ordinal and row["predecessor"] == predecessor, "campaign ledger chain differs")
    _check_campaign_result(context, protocol_ref, slot, entry, row["result"])
    return c.digest(raw)


def _run_campaign(context, protocol_ref, *, plan_sha256, slots, entries, frontier_path,
                  expected_frontier_sha256, end, max_wall_seconds, authorize):
    started = monotonic()

    def check_time():
        c.ensure(monotonic() - started < max_wall_seconds, "campaign wall-time budget exhausted")

    journal = context.root / ".generation"
    journal_identity = c.canonical_bytes({"plan_sha256": plan_sha256})
    c._refuse_reparse(journal)
    _require_local_ntfs(context.root)
    _require_local_ntfs(frontier_path.parent)
    with (
        _campaign_lease(frontier_path.with_name(frontier_path.name + ".lease")),
        _campaign_lease(context.root / ".generation.lease"),
    ):
        raw, start, pinned, in_flight = _campaign_frontier(
            frontier_path, expected_frontier_sha256, plan_sha256, len(slots),
        )

        def advance(index, last, attempt):
            nonlocal raw
            c.ensure(_campaign_file(frontier_path) == raw, "independent frontier changed during publication")
            raw = c.canonical_bytes({
                "schema": _CAMPAIGN_FRONTIER, "plan_sha256": plan_sha256, "next": index,
                "last_sha256": last, "attempt": attempt,
            })
            _durable_write(frontier_path, raw, overwrite=True)
            c.ensure(_campaign_file(frontier_path) == raw, "independent frontier publication failed")

        c.ensure(type(end) is int and start <= end <= len(slots), "campaign shard is not the authorized pending suffix")
        predecessor = None
        for ordinal in range(start):
            check_time()
            predecessor = _read_committed_row(
                context, protocol_ref, journal, plan_sha256, predecessor, ordinal, slots[ordinal], entries[ordinal],
            )
        c.ensure(predecessor == pinned, "campaign ledger does not reach independent frontier")
        if journal.exists():
            c.ensure(_campaign_file(journal / "plan.json") == journal_identity, "campaign journal plan owner differs")
            known_ordinals = range(min(start + 1, len(slots)))
            known = {"plan.json", *(name for ordinal in known_ordinals
                                    for name in (f"{ordinal:05d}.json", f"attempt-{ordinal:05d}"))}
            c.ensure(all(path.name in known for path in journal.iterdir()),
                     "campaign journal contains an unauthorized successor or path")
        for ordinal in range(start, end):
            check_time()
            slot, entry = slots[ordinal], entries[ordinal]
            row_path = _campaign_row(journal, ordinal)
            attempt = journal / f"attempt-{ordinal:05d}"
            stage, ready = attempt / "artifacts", attempt / "ready.json"
            intent = c.canonical_bytes({
                "plan_sha256": plan_sha256, "ordinal": ordinal, "predecessor": predecessor, **entry,
            })
            with authorize(ordinal, slot, entry) as (make_unit, check_active):
                check_active()
                if not journal.exists():
                    _durable_directory(journal)
                    _durable_write(journal / "plan.json", journal_identity)
                if attempt.exists():
                    c.ensure(in_flight is not None and _campaign_file(attempt / "intent.json") == intent
                             and in_flight["intent_sha256"] == c.digest(intent),
                             "campaign attempt lacks its independent intent identity")
                    c.ensure(ready.is_file() and in_flight["ready_sha256"] is not None,
                             "ambiguous campaign attempt after intent: redraw refused")
                    ready_raw = _campaign_file(ready)
                    c.ensure(c.digest(ready_raw) == in_flight["ready_sha256"],
                             "staged campaign bytes differ from independently anchored attempt")
                    result = _json(ready_raw)
                else:
                    c._refuse_reparse(context.root / slot.source_id)
                    c.ensure(in_flight is None and not (context.root / slot.source_id).exists()
                             and not row_path.exists(),
                             "campaign source output has no authorized attempt")
                    _durable_directory(attempt)
                    _durable_write(attempt / "intent.json", intent)
                    in_flight = {"ordinal": ordinal, "intent_sha256": c.digest(intent), "ready_sha256": None}
                    advance(ordinal, predecessor, in_flight)
                    _durable_directory(stage)
                    check_time()
                    check_active()
                    result = _stage_campaign_unit(context, protocol_ref, stage, slot, entry, make_unit)
                    ready_raw = c.canonical_bytes(result)
                    _durable_write(ready, ready_raw)
                    check_time()
                    check_active()
                    in_flight["ready_sha256"] = c.digest(ready_raw)
                    advance(ordinal, predecessor, in_flight)
                check_time()
                check_active()
                _publish_campaign_unit(context, protocol_ref, attempt, stage, slot, entry, result)
                check_time()
                check_active()
                completion = c.canonical_bytes({
                    "schema": _CAMPAIGN_ROW, "plan_sha256": plan_sha256,
                    "ordinal": ordinal, "predecessor": predecessor, "result": result,
                })
                if row_path.exists():
                    c.ensure(_campaign_file(row_path) == completion, "unexpected campaign completion successor")
                else:
                    _durable_write(row_path, completion)
                predecessor = _read_committed_row(
                    context, protocol_ref, journal, plan_sha256, predecessor, ordinal, slot, entry,
                )
                check_time()
                check_active()
                advance(ordinal + 1, predecessor, None)
                in_flight = None
                _release_committed_stage(stage, protocol_ref, result)
        check_time()
        return {
            "schema": "softqp.r4.generate-campaign-result/1", "plan_sha256": plan_sha256,
            "frontier_sha256": c.digest(raw), "next": end,
            "complete": end == len(slots), "source_count": end,
            "frame_count": sum(slot.frame_count for slot in slots[:end]),
        }


def dispatch_registered_campaign(raw: bytes, custody) -> dict:
    """Fixed owned-worker route for an independently pinned canonical campaign."""
    policy, request_sha256 = i1.campaign_worker_policy(custody, raw)
    request = _shape(_json(raw), {"schema", "plan_sha256"}, "invalid campaign request")
    _shape(policy, {"schema", "plan", "frontier", "end", "max_wall_seconds", *_SHARED_POLICY},
           "invalid governed campaign policy")
    c.ensure(request["schema"] == _CAMPAIGN_REQUEST and policy["schema"] == _CAMPAIGN_POLICY,
             "unknown campaign dispatch schema")
    c.ensure(type(policy["max_wall_seconds"]) is int and 0 < policy["max_wall_seconds"] <= 86400,
             "invalid independently approved campaign wall-time budget")
    shared = {key: policy[key] for key in _SHARED_POLICY}
    trust, context, protocol_ref = _dispatch_context(shared)
    plan_raw = _reference(trust.governance_root, policy["plan"])
    plan_sha256 = c.digest(plan_raw)
    c.ensure(plan_sha256 == request["plan_sha256"], "campaign plan differs from independent request")
    plan = _shape(_json(plan_raw), {"schema", "profile_sha256", "protocol_sha256", "registration_sha256",
                                  "generator_sha256", "entries"}, "invalid campaign plan")
    c.ensure(plan["schema"] == _CAMPAIGN_PLAN and i1._hex(plan["profile_sha256"])
             and all(plan[key] == getattr(context, key) for key in
                     ("protocol_sha256", "registration_sha256", "generator_sha256")),
             "campaign plan scope differs from I1 context")
    i1.campaign_worker_policy(custody, raw, profile_sha256=plan["profile_sha256"])
    slots = tuple(source_slots(context.authority))
    entries = [_campaign_entry(shared, slot)[0] for slot in slots]
    c.ensure(c.canonical_bytes(entries) == c.canonical_bytes(plan["entries"]), "campaign full slot inventory differs")
    frontier = _shape(policy["frontier"], {"path", "sha256"}, "invalid independent campaign frontier reference")
    frontier_path = c.safe_path(trust.governance_root, frontier["path"], must_exist=True)

    @contextmanager
    def authorize(ordinal, slot, entry):
        actual, request_bytes, policy_bytes = _campaign_entry(shared, slot)
        c.ensure(entry == actual, "campaign scoped request changed")
        with i1.activate_campaign_slot(
            custody, request_sha256, request_bytes, policy_bytes, ordinal=ordinal,
        ) as child:
            live_policy, req, pol = generator_worker_policy(child, request_bytes)
            c.ensure(req == entry["request_sha256"] and pol == entry["policy_sha256"]
                     and c.canonical_bytes(live_policy) == policy_bytes, "campaign child approval changed")
            scope = _GeneratorWorkerScope(child, req, pol, _slot_key(slot))
            authority = load_i1_authority(trust=trust, context=context, protocol_ref=protocol_ref, generator_scope=scope)

            def check_active():
                require_i1(authority, "generate-source", context=context, protocol_ref=protocol_ref,
                           generator_slot=_slot_key(slot))

            def make_unit():
                return generate_registered_unit(slot, context=context, protocol_ref=protocol_ref, authority=authority)

            yield make_unit, check_active

    return _run_campaign(
        context, protocol_ref, plan_sha256=plan_sha256, slots=slots, entries=entries,
        frontier_path=frontier_path, expected_frontier_sha256=frontier["sha256"],
        end=policy["end"], max_wall_seconds=policy["max_wall_seconds"], authorize=authorize,
    )
