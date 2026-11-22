"""Adversarial browser gate for the workbench Focus visualization stage."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_adversarial_focus_preserves_context_and_displays_visualization():
    result = subprocess.run(
        ["node", "--test", "scripts/check_focus_mode.test.mjs"],
        cwd=ROOT / "frontend",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
