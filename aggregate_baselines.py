"""Aggregate BFCL sweep results into the per-category gap table Track B consumes.

Reads every `bfcl_runs/run<N>/score/**/BFCL_v4_<category>_score.json` produced by
`run_sweep.sh` and emits, per category: mean accuracy and standard deviation across
the independent runs, the item count, and the most common failure modes.

Why mean and standard deviation rather than a single number: the harness exposes no
seed flag, so runs cannot be replicated exactly. vLLM's continuous batching changes
the order of floating-point reductions depending on which requests share a batch,
which makes results mildly nondeterministic even at temperature 0.001. Reporting the
spread is the honest form of the result.

The failure-mode tally exists because "Java is weak" is not actionable but "Java
fails by passing a string where a HashMap is expected" is. BFCL labels each wrong
answer with an `error_type` such as `type_error:simple`, and those labels are what
Track B's failure-driven top-up (contract section 6.3) should be aimed at.

Deterministic: output depends only on the files read, never on wall-clock or
unseeded randomness. Same inputs twice produces byte-identical output.

Usage:
    .venv/bin/python aggregate_baselines.py [--runs-dir bfcl_runs] [--model Qwen_Qwen3-14B-FC]
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import NamedTuple

# Matches the harness's score filenames, e.g. "BFCL_v4_simple_java_score.json".
SCORE_FILE_RE = re.compile(r"^BFCL_v4_(?P<category>.+)_score\.json$")


class CategoryResult(NamedTuple):
    """One category's outcome across all independent runs."""

    category: str
    accuracies: list[float]  # one entry per run, as a percentage
    total_count: int
    failure_modes: Counter  # error_type -> count, summed across runs

    @property
    def mean(self) -> float:
        return statistics.mean(self.accuracies)

    @property
    def stdev(self) -> float:
        # stdev is undefined for a single sample; report 0.0 and let the run count
        # column tell the reader the spread is simply not yet measured.
        return statistics.stdev(self.accuracies) if len(self.accuracies) > 1 else 0.0


def read_score_file(path: Path) -> tuple[float, int, Counter]:
    """Return (accuracy_pct, total_count, failure_mode_counts) for one score file.

    The harness writes a summary object on the first line and one object per
    incorrect item on the lines after it.
    """
    failure_modes: Counter = Counter()
    accuracy = 0.0
    total = 0

    with path.open() as handle:
        for line_number, line in enumerate(handle):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if line_number == 0:
                accuracy = float(record["accuracy"]) * 100.0
                total = int(record["total_count"])
            else:
                # Absent error_type means the harness recorded a failure it could
                # not classify; bucket it explicitly rather than dropping it.
                failure_modes[record.get("error_type", "unclassified")] += 1

    return accuracy, total, failure_modes


def collect(runs_dir: Path, model: str) -> list[CategoryResult]:
    """Gather every category's results across all run<N> directories."""
    per_category: dict[str, list[float]] = {}
    per_category_total: dict[str, int] = {}
    per_category_failures: dict[str, Counter] = {}

    # sorted() keeps output stable regardless of filesystem enumeration order.
    for run_dir in sorted(runs_dir.glob("run*")):
        score_root = run_dir / "score" / model
        if not score_root.is_dir():
            continue
        for score_file in sorted(score_root.rglob("BFCL_v4_*_score.json")):
            match = SCORE_FILE_RE.match(score_file.name)
            if not match:
                continue
            category = match.group("category")
            accuracy, total, failures = read_score_file(score_file)

            per_category.setdefault(category, []).append(accuracy)
            per_category_total[category] = total
            per_category_failures.setdefault(category, Counter()).update(failures)

    return [
        CategoryResult(
            category=category,
            accuracies=accuracies,
            total_count=per_category_total[category],
            failure_modes=per_category_failures[category],
        )
        for category, accuracies in sorted(per_category.items())
    ]


def render(results: list[CategoryResult], model: str) -> str:
    """Render the gap table as markdown, weakest category first."""
    if not results:
        return f"No score files found for model {model}.\n"

    lines: list[str] = []
    lines.append(f"## Per-category baseline gaps — `{model}`\n")
    lines.append(
        "Sorted weakest first. **Mean** and **SD** (standard deviation) are across "
        "independent runs; SD of 0.00 with 1 run means the spread has not been "
        "measured yet, not that the result is stable.\n"
    )
    lines.append("| Category | Items | Runs | Mean | SD | Top failure mode |")
    lines.append("|---|---:|---:|---:|---:|---|")

    for result in sorted(results, key=lambda r: r.mean):
        top = result.failure_modes.most_common(1)
        # Failure counts are summed over runs, so normalise to per-run for honesty.
        top_label = (
            f"`{top[0][0]}` ({top[0][1] / len(result.accuracies):.0f}/run)"
            if top
            else "none"
        )
        lines.append(
            f"| {result.category} | {result.total_count} | {len(result.accuracies)} "
            f"| {result.mean:.2f}% | {result.stdev:.2f} | {top_label} |"
        )

    lines.append("\n### Failure-mode detail\n")
    for result in sorted(results, key=lambda r: r.mean):
        if not result.failure_modes:
            continue
        runs = len(result.accuracies)
        breakdown = ", ".join(
            f"`{mode}` {count / runs:.0f}"
            for mode, count in result.failure_modes.most_common(5)
        )
        lines.append(f"- **{result.category}** (per run): {breakdown}")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", default="bfcl_runs", type=Path)
    parser.add_argument("--model", default="Qwen_Qwen3-14B-FC")
    args = parser.parse_args()

    results = collect(args.runs_dir, args.model)
    print(render(results, args.model))


if __name__ == "__main__":
    main()
