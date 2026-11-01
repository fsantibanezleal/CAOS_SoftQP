"""Validate raw campaign evidence and publish its checksummed reader inventory."""

import hashlib
import json
from pathlib import Path
import shutil
from .softqp_run import validate_document
from .softqp_stream import export_stream


def verify_campaign(folder):
    from .softqp_campaign import instances, summarize
    from jsonschema import Draft202012Validator

    folder = Path(folder)
    campaign = json.loads((folder / "campaign.json").read_text(encoding="utf-8"))
    validate_document(campaign, "softqp-campaign")
    for item in campaign["artifacts"]:
        raw = (folder / item["path"]).read_bytes()
        if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError(f"Campaign artifact integrity mismatch: {item['path']}")
    datasets = json.loads((folder / "datasets.json").read_text(encoding="utf-8"))
    validate_document(datasets, "softqp-datasets")
    trials = []
    schemas = Path(__file__).resolve().parents[2] / "docs/contracts/schemas"
    trial_validator = Draft202012Validator(json.loads((schemas / "softqp-trial.schema.json").read_text(encoding="utf-8")))

    def reject_constant(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")

    for line in (folder / "trials.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line, parse_constant=reject_constant)
        trial_validator.validate(row)
        trials.append(row)
    splits = sorted({row["split"] for row in datasets})
    plan = [s for split in splits for s in instances(campaign["protocol"], split)]
    if {r["id"] for r in plan} != {r["id"] for r in datasets} or len(plan) != len(datasets):
        raise ValueError("Dataset inventory is incomplete or contains repeated instances")
    expected = {(s["id"], method, repetition) for s in plan for method in campaign["protocol"]["methods"]
                for repetition in range(-campaign["protocol"]["repetitions"]["warmup_per_backend"],
                                        campaign["protocol"]["repetitions"]["measured"])}
    actual = {(r["id"], r["method"], r["repetition"]) for r in trials}
    if actual != expected or len(actual) != len(trials):
        raise ValueError("Trial evidence has missing or duplicate method/instance/repetition cells")
    plan_map = {s["id"]: s for s in plan}
    for row in datasets + trials:
        if any(row[key] != value for key, value in plan_map[row["id"]].items()):
            raise ValueError("Recorded instance differs from the preregistered grid")
    if campaign["planned_instances"] != len(plan) or campaign["completed_instances"] != len(plan):
        raise ValueError("Campaign counts disagree with its raw dataset inventory")
    recomputed = summarize(trials, campaign["protocol"])
    for name, value in recomputed.items():
        if campaign[name] != value:
            raise ValueError(f"Campaign summary differs from raw trials: {name}")
    return campaign


def publish_experiments(campaign_folder, output):
    source, output = Path(campaign_folder).resolve(), Path(output).resolve()
    if source == output:
        raise ValueError("Raw evidence and published output must use separate directories")
    campaign = verify_campaign(source)
    output.mkdir(parents=True, exist_ok=True)
    names = [("campaign.json", "softqp-campaign"), ("datasets.json", "softqp-datasets"),
             ("trials.jsonl", "softqp-trial"), ("trials.csv", "csv")]
    for name, _ in names:
        shutil.copyfile(source / name, output / name)
    export_stream(output)
    stream = json.loads((output / "stream.json").read_text(encoding="utf-8"))
    validate_document(stream, "softqp-stream")
    names.append(("stream.json", "softqp-stream"))
    index = dict(schema_version="softqp.experiments/v1", protocol_id=campaign["protocol"]["protocol_id"],
                 state="measured" if "heldout" in {c["split"] for c in campaign["cells"]} else "development",
                 artifacts=[dict(path=name, schema=schema, bytes=(output / name).stat().st_size,
                                 sha256=hashlib.sha256((output / name).read_bytes()).hexdigest())
                            for name, schema in names])
    validate_document(index, "softqp-experiment-index")
    (output / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8", newline="\n")
    return index
