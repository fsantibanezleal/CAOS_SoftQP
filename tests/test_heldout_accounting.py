"""Protected roots cannot enter actual recursive held-out disk accounting."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.learned_comparison import contracts as c
from pipeline.learned_comparison import heldout_inputs as h


@pytest.mark.parametrize("position", ["inside", "equal", "containing"])
def test_adversarial_protected_accounting_overlap_refuses_before_walk(tmp_path, monkeypatch, position):
    work, protected = tmp_path / "work", tmp_path / "protected"
    work.mkdir()
    nested = protected / "nested"
    nested.mkdir(parents=True)
    (nested / "private.bin").write_bytes(b"protected")
    extra = {"inside": nested, "equal": protected, "containing": tmp_path}[position]
    scope = {k: str(work / k) for k in ("test_root", "native_root", "proof_root", "frontier_root")}
    scope["artifact_roots"] = [str(work), str(extra)]
    state = SimpleNamespace(policy_bytes=c.canonical_bytes({"scope": scope}),
                            context=SimpleNamespace(root=work, forbidden_roots=(protected,)))

    def forbidden_walk(*_args, **_kwargs):
        pytest.fail("protected accounting overlap reached recursive filesystem traversal")

    monkeypatch.setattr(Path, "iterdir", forbidden_walk)
    with pytest.raises(c.ContractError, match="quota roots.*protected"):
        h._quota_existing(state)


def test_legal_parent_and_sibling_accounting_preserve_actual_byte_count(tmp_path):
    work, sibling, protected = (tmp_path / name for name in ("work", "sibling", "protected"))
    for path in (work, sibling, protected):
        path.mkdir()
    nested = work / "nested"
    nested.mkdir()
    (nested / "payload.bin").write_bytes(b"visible")
    (sibling / "other.bin").write_bytes(b"other")
    (protected / "private.bin").write_bytes(b"protected")
    scope = {k: str(nested / k) for k in ("test_root", "native_root", "proof_root", "frontier_root")}
    scope["artifact_roots"] = [str(work), str(sibling)]
    state = SimpleNamespace(policy_bytes=c.canonical_bytes({"scope": scope}),
                            context=SimpleNamespace(root=nested, forbidden_roots=(protected,)))
    assert h._quota_existing(state) == len(b"visibleother")
