"""Strict v2 labels require independently pinned supervised native evidence."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
import test_native_labels as native_controls

from pipeline.learned_comparison import contracts as c
from pipeline.learned_comparison import native_labels as n
from pipeline.learned_comparison import stream_inputs as stream
from test_stream_inputs import put


supervised = native_controls.supervised


def bound_context(plan, run):
    return replace(
        plan.context,
        native_run=run,
        expected_native_manifest_sha256=run.sha256,
        native_input_preflight=plan.preflight,
    )


def test_real_supervised_labels_cross_strict_writer_reader_and_p1(supervised, tmp_path):
    _, plan, _, run, scope, pending = supervised
    context = bound_context(plan, run)
    protocol = c.strict_loads(plan.preflight.receipt_bytes)["protocol_ref"]
    labels = deepcopy(pending)
    catalog = dict(context.catalog)
    for row in run.document["rows"]:
        if not row["input"]["cold_eligible"]:
            continue
        slot = next(item for item in labels if item["frame_id"] == row["input"]["frame"]["artifact_id"])
        state, reason = n._label_disposition(row)
        ref = None
        if row["label"] is not None:
            document = c.strict_loads((run.root / row["label"]["path"]).read_bytes())
            name = "bridge-" + row["label"]["path"]
            written = stream.write_stream_artifact(
                document, name, context,
                expected_population_sha256=run.document["population_sha256"],
            )
            observed = stream.read_stream_artifact(
                context.root / name, context, expected_sha256=written.raw_sha256,
                expected_population_sha256=run.document["population_sha256"],
            )
            assert written == observed
            ref = dict(kind=stream.LABELS, artifact_id=written.artifact_id,
                       path=name, sha256=written.raw_sha256)
            catalog[written.artifact_id] = ref
        slot.update(state="provider" if state == "available" else state, reason=reason, ref=ref)
    context = replace(context, catalog=catalog)
    descriptor = stream.derive_stream_payload(context, protocol, **scope, labels=labels)
    context, ref = put(context, protocol, stream.STREAM, "bridge-p1", descriptor)
    p1 = stream.preflight_stream(context, descriptor_id=ref["artifact_id"],
                                 expected_descriptor_sha256=ref["sha256"])
    projections = {role: run.project_role(role, tmp_path / (role + ".json")) for role in plan.roles}
    trusts = n.bind_labeled_preflight(
        plan, run, p1, expected_manifest_sha256=run.sha256,
        expected_labeled_preflight_sha256=p1.sha256, projection_hashes=projections,
    )
    assert {trust.role for trust in trusts} == set(plan.roles)
    # An actual observed accepted result cannot be removed by declaring it missing.
    forged = c.strict_loads(p1.receipt_bytes)
    available = next(item for item in forged["labels"] if item["state"] == "provider")
    available.update(state="missing", reason="invented omission", ref=None)
    omitted = replace(p1, receipt_bytes=c.canonical_bytes(forged))
    with pytest.raises(ValueError, match="native label disposition"):
        n.bind_labeled_preflight(
            plan, run, omitted, expected_manifest_sha256=run.sha256,
            expected_labeled_preflight_sha256=omitted.sha256, projection_hashes=projections,
        )


def test_missing_attestation_refuses_success_and_oracle_failure_before_metrics(supervised):
    _, plan, _, run, _, _ = supervised
    context = SimpleNamespace(**{**vars(plan.context), "allow_fixture": False})
    records = {item["ref"]["artifact_id"]: item["ref"]
               for item in c.strict_loads(plan.preflight.receipt_bytes)["records"]}
    for row in run.document["rows"]:
        if row["label"] is None:
            continue
        document = c.strict_loads((run.root / row["label"]["path"]).read_bytes())
        frame = stream._load(plan.context, row["input"]["frame"], stream.FRAME, document["protocol_ref"])
        source = stream._load(plan.context, records[frame["payload"]["source_ref"]["artifact_id"]],
                              stream.SOURCE, document["protocol_ref"])
        problem = stream._problem(plan.context, frame, source)
        with pytest.raises(c.ContractError, match="source-run attestation unavailable"):
            stream._label(context, document, row["input"]["frame"], problem,
                          run.document["population_sha256"])


def test_native_pin_fixture_and_p0_ancestry_cannot_be_self_replaced(supervised):
    _, plan, _, run, _, _ = supervised
    context = bound_context(plan, run)
    with pytest.raises(c.ContractError, match="independently expected manifest"):
        replace(context, expected_native_manifest_sha256="0" * 64)
    with pytest.raises(c.ContractError, match="input preflight"):
        replace(context, native_input_preflight=None)
    with pytest.raises(c.ContractError, match="fixture ancestry"):
        replace(context, allow_fixture=False)
    edited = c.strict_loads(plan.preflight.receipt_bytes)
    edited["population_sha256"] = "f" * 64
    different_p0 = replace(plan.preflight, receipt_bytes=c.canonical_bytes(edited))
    with pytest.raises(c.ContractError, match="fixture ancestry"):
        replace(context, native_input_preflight=different_p0)
    with pytest.raises(c.ContractError, match="fixture ancestry"):
        replace(context, generator_sha256="f" * 64)
