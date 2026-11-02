"""Required source/data notices must survive packaging and attribution edits."""

from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]


def validate_attribution(root):
    credit = " ".join((root / "ATTRIBUTION.md").read_text(encoding="utf-8").split())
    assert "synthetic model authored by the OSQPSlack Project Contributors" in credit
    assert "2e5d5ce8968207d0838d08942a8af7bdda64f634" in credit
    assert "synthetic models, not measured building records" in credit
    licenses = (root / "LICENSES.md").read_text(encoding="utf-8")
    energy = next(row for row in licenses.splitlines()
                  if row.startswith("|") and "data-pipeline/pipeline/energy_reference.py" in row)
    assert "OSQPSlack" in energy and "2e5d5ce8968207d0838d08942a8af7bdda64f634" in energy
    assert "MIT" in energy and "data/licenses/OSQPSlack-MIT.txt" in energy
    assert "CC BY 4.0" in licenses and "separate repository" in licenses
    notice = " ".join((root / "data/licenses/OSQPSlack-MIT.txt").read_text(encoding="utf-8").split())
    assert "Copyright (c) 2026 The OSQPSlack Project Contributors" in notice
    assert "Permission is hereby granted" in notice and "included in all copies" in notice
    source = (root / "data-pipeline/pipeline/energy_reference.py").read_text(encoding="utf-8")
    assert source.startswith("# Adapted from OSQPSlack (MIT), Copyright 2026 The OSQPSlack Project Contributors.")


@pytest.mark.parametrize("mutation", ["missing-inventory", "missing-notice", "false-author", "false-field-data"])
def test_adversarial_third_party_credit_and_redistribution(tmp_path, mutation):
    validate_attribution(ROOT)
    for relative in ("ATTRIBUTION.md", "LICENSES.md", "data/licenses/OSQPSlack-MIT.txt",
                     "data-pipeline/pipeline/energy_reference.py"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    if mutation == "missing-inventory":
        (tmp_path / "LICENSES.md").unlink()
    elif mutation == "missing-notice":
        (tmp_path / "data/licenses/OSQPSlack-MIT.txt").unlink()
    else:
        path = tmp_path / "ATTRIBUTION.md"
        source = path.read_text(encoding="utf-8")
        source = source.replace("the OSQPSlack Project Contributors", "this product's author") if mutation == "false-author" else source.replace("synthetic models, not measured", "measured")
        path.write_text(source, encoding="utf-8")
    with pytest.raises((AssertionError, FileNotFoundError)):
        validate_attribution(tmp_path)
