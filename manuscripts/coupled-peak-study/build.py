"""Verify evidence-derived result macros, then compile the native LaTeX report."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
# Immutable acceptance anchors for this completed study, not a general plotting input.
EVIDENCE_REVIEW = "f5ade8cca3ff79c91bda6386f78245a419e292574451c3c821d0436c9aa6bff0"
FIGURE_REVIEW = "8e84650a25abd49c4ade51bf7254226d3890d87dd1698c1efa9d660f52fdbbf9"


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--refresh-results", action="store_true")
    args = parser.parse_args()
    expected = result_macros()
    path = HERE / "results.tex"
    if args.refresh_results:
        path.write_text(expected, encoding="utf-8", newline="\n")
        print("Evidence-derived numeric macros refreshed; no PDF built.")
        return
    if not path.is_file() or path.read_text(encoding="utf-8") != expected:
        raise ValueError("Result macros differ from the accepted summary; review --refresh-results.")
    spec = importlib.util.spec_from_file_location("manuscript_compiler", ROOT / "scripts/build_manuscript.py")
    compiler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compiler)
    print(compiler.build(HERE / "main.tex", args.output))


if __name__ == "__main__":
    main()
