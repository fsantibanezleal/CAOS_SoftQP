"""Fresh raw projections stay inside a sealed role and never build numerics."""

from collections import Counter
from pathlib import Path
import os

import pytest
import test_stream_inputs as stream_controls

from pipeline.learned_comparison import contracts as c
from pipeline.learned_comparison import stream_inputs as stream


source_bundle = stream_controls.source_bundle
bundle = stream_controls.bundle


@pytest.fixture
def local_reader(bundle, tmp_path):
    context, _, _, _, _, ref, _ = bundle
    p0 = stream.preflight_stream(context, descriptor_id=ref["artifact_id"],
                                 expected_descriptor_sha256=ref["sha256"])
    root = tmp_path / "train"
    sha = stream.materialize_stream_phase(p0, root, role="train", expected_preflight_sha256=p0.sha256)
    reader = stream.StreamingPhaseReader(root, role="train", expected_manifest_sha256=sha,
                                        expected_preflight_sha256=p0.sha256, allow_fixture=True)
    return context, reader, root


def test_sealed_pair_reads_two_local_files_without_numerical_work(local_reader, monkeypatch):
    context, reader, root = local_reader
    expected = reader.read_problem("trajectory-00")
    unavailable = context.root.with_name("raw-projection-global-unavailable")
    context.root.rename(unavailable)
    opened = Counter()
    original = Path.open

    def observe(path, *args, **kwargs):
        if kwargs.get("mode", args[0] if args else "r") == "rb":
            opened[path] += 1
        return original(path, *args, **kwargs)

    def no_numerics(*_args, **_kwargs):
        pytest.fail("raw broker projection reconstructed numerical inputs")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(Path, "open", observe)
            patch.setattr(stream, "_reconstruct", no_numerics)
            patch.setattr(stream, "_feature", no_numerics)
            pair = reader.read_sealed_frame_pair("trajectory-00")
        assert sum(opened.values()) == 2 and len(opened) == 2
        assert all(path.is_relative_to(root) for path in opened)
        assert c.digest(pair["source_raw"]) == pair["source_ref"]["sha256"]
        assert c.digest(pair["frame_raw"]) == pair["frame_ref"]["sha256"]
        actual = stream._reconstruct(c.strict_loads(pair["source_raw"])["payload"],
                                     c.strict_loads(pair["frame_raw"])["payload"])
        assert actual == expected
        pair["source_ref"]["artifact_id"] = "caller-mutation"
        assert reader.read_sealed_frame_pair("trajectory-00")["source_ref"]["artifact_id"] != "caller-mutation"
    finally:
        unavailable.rename(context.root)


def test_sealed_pair_refuses_same_size_same_time_mutation_and_hardlink(local_reader, tmp_path):
    _, reader, root = local_reader
    pair = reader.read_sealed_frame_pair("trajectory-00")
    path = root / reader._records["trajectory-00"]["path"]
    raw, facts = path.read_bytes(), path.stat()
    path.write_bytes(raw[:-1] + b"]")
    os.utime(path, ns=(facts.st_atime_ns, facts.st_mtime_ns))
    try:
        with pytest.raises(c.ContractError, match="stored byte mismatch"):
            reader.read_sealed_frame_pair("trajectory-00")
    finally:
        path.write_bytes(raw)
    assert reader.read_sealed_frame_pair("trajectory-00")["frame_raw"] == pair["frame_raw"]
    alias = tmp_path / "external-frame-alias.json"
    os.link(path, alias)
    try:
        with pytest.raises(c.ContractError, match="hard-link alias"):
            reader.read_sealed_frame_pair("trajectory-00")
    finally:
        alias.unlink()


def test_sealed_pair_cannot_resolve_another_role_or_absent_frame(local_reader):
    _, reader, _ = local_reader
    for frame_id in ("single-validation", "single-calibration", "single-test", "absent"):
        with pytest.raises(c.ContractError, match="absent from stream role"):
            reader.read_sealed_frame_pair(frame_id)
