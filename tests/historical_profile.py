"""Explicit prerequisite for positive controls tied to the immutable source study."""

import json
from pathlib import Path

import pytest

from pipeline.environment import environment


def require_registered_engine():
    root = Path(__file__).resolve().parents[1]
    expected = json.loads((root / "docs/design/experiments-v1.json").read_text(encoding="utf-8"))["engine_source"]
    actual = environment()
    revision, dirty = actual["engine_revision"], actual["engine_source_dirty"]
    if revision != expected or dirty is not False:
        pytest.skip(f"Local-only exact-source positive: expected clean {expected}; "
                    f"observed revision={revision!r}, dirty={dirty!r}. Use the declared historical-source profile.")
