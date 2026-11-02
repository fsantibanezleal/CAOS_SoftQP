from pipeline.softqp_cases import cases
from pipeline.softqp_run import run_case, bake


def test_case_catalog_covers_fifteen_declared_ids():
    assert [c.id for c in cases()] == [f"C{i:02}" for i in range(1, 16)]


def test_scalar_methods_share_objective_and_hard_policy():
    result = run_case(cases()[0])
    solved = [r for r in result["runs"] if r["state"] == "available"]
    assert len(solved) == 4
    objectives = [r["result"]["metrics"]["objective"] for r in solved]
    assert max(objectives) - min(objectives) < 1e-6


def test_grouped_reference_matches_explicit_lift():
    result = run_case(next(c for c in cases() if c.id == "C05"))
    values = [r["result"]["metrics"]["objective"] for r in result["runs"] if r["state"] == "available"]
    assert len(values) == 2
    assert max(values) - min(values) < 1e-6


def test_bake_writes_hashed_inventory_outside_committed_data(tmp_path):
    index = bake(tmp_path, selected=["C01", "C02"])
    assert len(index["cases"]) == 2
    import hashlib

    for row in index["cases"]:
        assert hashlib.sha256((tmp_path / row["path"]).read_bytes()).hexdigest() == row["sha256"]
