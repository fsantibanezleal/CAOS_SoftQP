"""Thin deployment manifests around the validated scientific inventory."""

from pathlib import Path
import importlib.metadata
import json
from ..io.formats import write_json

ROOT = Path(__file__).resolve().parents[3]


def export_manifests(derived):
    derived = Path(derived)
    index = json.loads((derived / "softqp/index.json").read_text(encoding="utf-8"))
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    entries = []
    for entry in index["cases"]:
        relative = "softqp/" + entry["path"]
        path = derived / relative
        doc = json.loads(path.read_text(encoding="utf-8"))
        manifest = dict(
            schema="softqp.manifest/v1",
            case_id=entry["case_id"],
            title=entry["title"],
            category=entry["category"],
            engine=dict(package="softqp", version=importlib.metadata.version("softqp")),
            product_version=version,
            seed=doc["seed"],
            source=doc["source"],
            artifact=dict(path=relative, bytes=path.stat().st_size, sha256=entry["sha256"], format="json"),
            lane="precompute",
            gate=dict(
                lane="precompute",
                reasons=[
                    dict(
                        en="Native C extension; no browser solver has passed parity and resource gates.",
                        es="Extensión nativa C; ningún solver de navegador ha superado paridad y recursos.",
                    )
                ],
            ),
        )
        write_json(derived / f"manifests/{entry['case_id']}.json", manifest)
        entries.append(
            dict(
                case_id=entry["case_id"],
                title=entry["title"],
                category=entry["category"],
                manifest_path=f"manifests/{entry['case_id']}.json",
            )
        )
    result = dict(
        schema="softqp.artifact-index/v1",
        engine_version=version,
        n_cases=len(entries),
        default_case=index["default_case"],
        cases=entries,
        files=["softqp/index.json"],
    )
    experimental = derived / "experiments/index.json"
    if experimental.is_file():
        evidence = json.loads(experimental.read_text(encoding="utf-8"))
        result["files"] += ["experiments/index.json"] + [
            "experiments/" + artifact["path"] for artifact in evidence["artifacts"]
        ]
    write_json(derived / "manifests/index.json", result)
    return result
