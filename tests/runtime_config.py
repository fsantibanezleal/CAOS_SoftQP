"""Explicit external runtimes for excluded software fixtures."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys

import pytest


def _nomination(prefix, required, optional=()):
    names = {suffix: f"SOFTQP_{prefix}_{suffix}" for suffix in (*required, *optional)}
    values = {suffix: os.environ[name] for suffix, name in names.items() if name in os.environ}
    if not values:
        pytest.skip(f"excluded runtime fixture is not nominated; set {', '.join(names[k] for k in required)}")
    missing = [names[key] for key in required if not values.get(key)]
    if missing:
        pytest.fail(f"incomplete excluded runtime nomination: {', '.join(missing)}")
    return values


def _path(value, *, directory=False):
    path = Path(value)
    if not value or not path.is_absolute() or not (path.is_dir() if directory else path.is_file()):
        pytest.fail(f"invalid nominated {'directory' if directory else 'file'}: {value!r}")
    return path.resolve(strict=True)


@dataclass(frozen=True)
class SDK45:
    python: Path
    profile: Path
    wheel: Path


def sdk45():
    values = _nomination("SDK45_FIXTURE", ("PYTHON", "PROFILE", "WHEEL"))
    return SDK45(_path(values["PYTHON"]), _path(values["PROFILE"], directory=True), _path(values["WHEEL"]))


@dataclass(frozen=True)
class Native49:
    snapshot: Path
    python: Path
    tools: Path
    profile_sha256: str
    base_python: Path


def native49():
    values = _nomination(
        "NATIVE49_FIXTURE", ("SNAPSHOT", "PYTHON", "TOOLS", "PROFILE_SHA256"), ("BASE_PYTHON",)
    )
    digest = values["PROFILE_SHA256"]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        pytest.fail(
            "SOFTQP_NATIVE49_FIXTURE_PROFILE_SHA256 must be an independently pinned lowercase SHA-256"
        )
    snapshot = _path(values["SNAPSHOT"], directory=True)
    _path(str(snapshot / "profile" / "provenance.json"))
    _path(str(snapshot / "profile" / "verify.py"))
    _path(str(snapshot / "source"), directory=True)
    return Native49(
        snapshot,
        _path(values["PYTHON"]),
        _path(values["TOOLS"], directory=True),
        digest,
        _path(values.get("BASE_PYTHON", sys._base_executable)),
    )
