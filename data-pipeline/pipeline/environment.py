"""Public numerical provenance without local paths, host names or credential material."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import softqp


def environment():
    packages = {}
    for name in ["numpy", "scipy", "osqp", "softqp", "daqp", "elastiqp"]:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not-installed"
    direct = json.loads(importlib.metadata.distribution("softqp").read_text("direct_url.json") or "{}")
    installed_revision = direct.get("vcs_info", {}).get("commit_id")
    revision = (
        installed_revision if isinstance(installed_revision, str) and len(installed_revision) == 40 else None
    )
    dirty = False if revision else None
    source = Path(softqp.__file__).resolve().parents[2]
    try:
        if (
            not (source / "pyproject.toml").is_file()
            or (source / "src/softqp/__init__.py").resolve() != Path(softqp.__file__).resolve()
        ):
            raise OSError("not an editable source checkout")
        commit = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
        if len(commit) == 40 and all(c in "0123456789abcdef" for c in commit):
            revision = commit
            dirty = bool(
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(source),
                        "status",
                        "--porcelain",
                        "--",
                        "src",
                        "native",
                        "setup.py",
                        "pyproject.toml",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                ).stdout.strip()
            )
    except (OSError, subprocess.SubprocessError):
        pass
    from softqp import ext_builtin

    binary_hash = hashlib.sha256(Path(ext_builtin.__file__).read_bytes()).hexdigest()
    return dict(
        python=platform.python_version(),
        platform=platform.platform(),
        packages=packages,
        engine_revision=revision,
        engine_source_dirty=dirty,
        native_binary_sha256=binary_hash,
    )
