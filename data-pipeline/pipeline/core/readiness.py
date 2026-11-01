"""Deterministic, standard-library readiness over the scientific artifact inventory."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
from ..io.formats import write_json

SCHEMA = "softqp.readiness/v2"
CATALOG_REL = "docs/contracts/catalog.md"
STATUSES = ("real", "active")


def parse_catalog(text):
    section = text.split("## Contracts", 1)[1].split("\n## ", 1)[0]
    table = [
        [c.strip() for c in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.startswith("|")
    ]
    if len(table) < 2:
        raise ValueError("contract catalog has no table")
    return [dict(zip([h.lower() for h in table[0]], cells)) for cells in table[2:]]


def _json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def compute(*, repo_root, derived_root, models_dir=None, catalog_path=None, version=None):
    root = Path(repo_root)
    derived = Path(derived_root)
    raw = (Path(catalog_path) if catalog_path else root / CATALOG_REL).read_bytes().replace(b"\r\n", b"\n")
    version = version or (root / "VERSION").read_text(encoding="utf-8").strip()
    deployment = _json(derived / "manifests/index.json")
    science = _json(derived / "softqp/index.json")
    contracts = []
    for row in parse_catalog(raw.decode("utf-8")):
        rid = row["id"]
        status = row.get("status", "real")
        if rid == "readiness":
            continue
        if status not in STATUSES:
            raise ValueError(f"{rid}: invalid status {status}")
        entry = dict(
            id=rid,
            version=row["version"],
            status=status,
            provenance="real",
            state="available",
            reason=None,
            missing=[],
        )

        def state(value, en, es, missing=None, provenance="real"):
            entry.update(
                state=value, reason=dict(en=en, es=es), missing=sorted(missing or []), provenance=provenance
            )

        if status == "active":
            kind = row["provider"].split(":", 1)[0]
            state(
                "provider",
                "Served by its declared provider; the producer is incomplete.",
                "Servido por su proveedor declarado; el productor está incompleto.",
                provenance=kind,
            )
        elif rid == "api":
            state(
                "missing",
                "The API lane is dormant; the browser reads static artifacts.",
                "La API está inactiva; el navegador lee artefactos estáticos.",
                provenance=None,
            )
        elif rid in ("case-index", "case-manifest", "softqp-index", "softqp-case-result"):
            inventory = science if rid.startswith("softqp-") else deployment
            if not inventory:
                state(
                    "missing",
                    "The scientific inventory has not been baked.",
                    "El inventario científico no ha sido generado.",
                    provenance=None,
                )
            else:
                absent = []
                if rid == "case-manifest":
                    absent = [
                        c["manifest_path"]
                        for c in inventory["cases"]
                        if not (derived / c["manifest_path"]).is_file()
                    ]
                elif rid == "softqp-case-result":
                    absent = [
                        "softqp/" + c["path"]
                        for c in inventory["cases"]
                        if not (derived / "softqp" / c["path"]).is_file()
                    ]
                if absent:
                    state(
                        "partial",
                        "Declared scientific files are absent.",
                        "Faltan archivos científicos declarados.",
                        absent,
                    )
                elif deployment and deployment.get("engine_version") != version:
                    state(
                        "stale",
                        f"Baked by {deployment.get('engine_version')}; the product is {version}.",
                        f"Generado por {deployment.get('engine_version')}; el producto es {version}.",
                    )
        contracts.append(entry)
    return dict(
        schema=SCHEMA,
        product_version=version,
        catalog_sha256=hashlib.sha256(raw).hexdigest(),
        contracts=contracts,
    )


def write(derived_root, doc):
    return write_json(Path(derived_root) / "readiness.json", doc)
