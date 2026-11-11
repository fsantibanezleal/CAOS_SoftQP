"""Verify evidence-derived result macros, then compile the native LaTeX report."""

import argparse
import hashlib
import importlib.util
import json
from collections import defaultdict
from statistics import median
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
# Immutable acceptance anchors for this completed study, not a general plotting input.
EVIDENCE_REVIEW = "f5ade8cca3ff79c91bda6386f78245a419e292574451c3c821d0436c9aa6bff0"
FIGURE_REVIEW = "9230f67cb683db55b530f1e6465ef43cc5280ea27ded04687febbb769706ea91"


def canonical_digest(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def result_macros():
    path = HERE / "results/summary/summary.json"
    manifest = json.loads((path.parent / "SHA256SUMS.json").read_text(encoding="utf-8"))
    evidence = json.loads((HERE / "results/reviews/final-campaign-evidence-review.json").read_text(encoding="utf-8"))
    figures = json.loads((HERE / "results/reviews/figure-review.json").read_text(encoding="utf-8"))
    expected_names = {"summary.json", "observation-states.png", "observation-states.svg",
                      "primary-full-population.png", "primary-full-population.svg"}
    if (canonical_digest(evidence) != EVIDENCE_REVIEW or evidence["decision"] != "ACCEPT_EVIDENCE"
            or canonical_digest(figures) != FIGURE_REVIEW or figures["decision"] != "ACCEPT_FIGURES"
            or figures["evidence_review_sha256"] != EVIDENCE_REVIEW
            or set(manifest) != expected_names
            or manifest != {"summary.json": figures["summary_sha256"], **figures["figure_sha256"]}):
        raise ValueError("Independent acceptance does not bind this complete summary and figure inventory.")
    for name, digest in manifest.items():
        if Path(name).name != name or hashlib.sha256((path.parent / name).read_bytes()).hexdigest() != digest:
            raise ValueError("An independently reviewed summary or figure changed.")
    summary = json.loads(path.read_text(encoding="utf-8"))
    primary = summary["primary"]
    if (summary["evidence_review_sha256"] != EVIDENCE_REVIEW
            or summary["protocol_sha256"] != evidence["protocol_sha256"]
            or summary["source_commit"] != evidence["source_commit"]
            or summary["counts"] != evidence["measured_states"]
            or {key: primary[key] for key in evidence["primary"]} != evidence["primary"]):
        raise ValueError("Manuscript quantities differ from the accepted complete-study evidence.")
    values = {"PrimaryEstimate": f'{100 * primary["estimate"]:.6f}',
              "PrimaryLower": f'{100 * primary["confidence_interval"][0]:.6f}',
              "PrimaryUpper": f'{100 * primary["confidence_interval"][1]:.6f}',
              "PrimaryFailed": primary["failed_pairs"],
              "PrimaryPopulation": primary["denominator"],
              "SummaryDigest": hashlib.sha256(path.read_bytes()).hexdigest()}
    states = {"Accepted": "accepted", "AccuracyRejected": "accuracy-rejected",
              "Incompatible": "incompatible", "OracleFailed": "oracle-failed", "Timeout": "timeout"}
    for split, counts in summary["counts"].items():
        for macro, state in states.items():
            values[split.capitalize() + macro] = counts.get(state, 0)
    return "% Numeric export from the reviewed summary; no new inference.\n" + "".join(
        "\\newcommand{\\" + key + "}{" + str(value) + "}\n" for key, value in values.items())



def component_table():
    """Derive descriptive matched contrasts from the frozen measurements."""
    def frozen(path, digest):
        raw = (ROOT / path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f"Frozen component evidence changed: {path}")
        return raw

    prefix = "data/derived/experiments/"
    trials = frozen(prefix + "trials.jsonl", "67c3d72a7b62d414d0a0f1b61fc18b5450b6a43c191ab6b7f78ac2c96fe39e39")
    stream = json.loads(frozen(prefix + "stream.json", "faab5d6a0d5397748360906b0c5b73d0462cd045c164b67dd963b973f2719f3e"))
    summary = json.loads(frozen(
        "manuscripts/coupled-peak-study/results/summary/summary.json",
        "c82bf30bb53c7c10d464fc446bd2b99ee774b581dbe3f4dced86194e1fe54c6d",
    ))
    rows = []

    def timing(label, values, first, second):
        pairs = [(row[first], row[second]) for row in values if first in row and second in row]
        effect = median(100 * (1 - b / a) for a, b in pairs)
        rows.append((label, len(pairs), "$" + rf"{effect:.2f}\%$"))

    methods = (("lifted", "Lifted OSQP"), ("asymmetric", "Original-row OSQP"), ("daqp", "DAQP"))
    for method, label in methods:
        values = [
            {r["mode"]: r["elapsed_seconds"] for r in frame["runs"]
             if r["method"] == method and r["state"] == "accepted"}
            for frame in stream["frames"]
        ]
        timing(f"C12 cold to warm: {label}", values, "cold", "warm")

    values = [r["median_seconds"] for r in summary["primary"]["pairs"]]
    timing("Grouped epigraph to row split (default)", values, "epigraph-default", "row-split-default")
    timing("Grouped epigraph to row split (fixed)", values, "epigraph-fixed", "row-split-fixed")

    matched = defaultdict(dict)
    for raw in trials.splitlines():
        row = json.loads(raw)
        if (row["split"] == "robustness" and row["family"] == "asymmetric-elastic"
                and not row["warmup"] and row["state"] == "accepted" and row["condition"] in {1, 10**6}):
            key = (row["method"], row["seed"], row["repetition"])
            matched[key][row["condition"]] = row["normalized_gap"]
    for method, label in methods:
        deltas = [v[10**6] - v[1] for key, v in matched.items() if key[0] == method and len(v) == 2]
        mantissa, exponent = f"{median(deltas):.2e}".split("e")
        rows.append((f"Condition $1$ to $10^6$: {label}", len(deltas),
                     "$" + rf"{mantissa}\times 10^{{{int(exponent)}}}$"))

    header = r"""\begin{table}[htbp]\centering\small
\caption{Matched descriptive contrasts from retained observations. Positive timing reduction means the second configuration took less time. Conditioning rows report the change in normalized objective discrepancy.}\label{tab:component-comparisons}
\begin{tabularx}{\textwidth}{@{}Xrr@{}}\toprule
Contrast & Matched pairs & Median paired effect\\\midrule
"""
    body = "".join(f"{label} & {count} & {effect}\\\\\n" for label, count, effect in rows)
    return header + body + "\\bottomrule\n\\end{tabularx}\n\\end{table}\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--refresh-results", action="store_true")
    args = parser.parse_args()
    expected = result_macros()
    path = HERE / "results.tex"
    component_path = HERE / "generated/component-comparisons.tex"
    components = component_table()
    if args.refresh_results:
        path.write_text(expected, encoding="utf-8", newline="\n")
        component_path.write_text(components, encoding="utf-8", newline="\n")
        print("Evidence-derived numeric macros refreshed; no PDF built.")
        return
    if not path.is_file() or path.read_text(encoding="utf-8") != expected:
        raise ValueError("Result macros differ from the accepted summary; review --refresh-results.")
    if not component_path.is_file() or component_path.read_text(encoding="utf-8") != components:
        raise ValueError("Component table differs from frozen measurements; review --refresh-results.")
    spec = importlib.util.spec_from_file_location("manuscript_compiler", ROOT / "scripts/build_manuscript.py")
    compiler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compiler)
    print(compiler.build(HERE / "main.tex", args.output))


if __name__ == "__main__":
    main()
