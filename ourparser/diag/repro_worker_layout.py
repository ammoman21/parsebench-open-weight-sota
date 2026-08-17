"""Diagnostic: replicate the exact evaluation worker call for one failed layout example.

Reproduces what EvaluationRunner does for a cross-evaluation task:
  1. load the saved .result.json,
  2. model_dump() it,
  3. ship it to a ProcessPoolExecutor worker running _evaluate_single_worker,
and prints the worker's error, so we can see the real failure mechanism instead of
guessing. Read-only: writes nothing.
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_ROOT, os.path.join(_ROOT, "parsebench", "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ourparser.provider  # noqa: F401  — mimic the original run: pipeline registered in parent

from parse_bench.evaluation.runner import _evaluate_single_worker  # noqa: E402
from parse_bench.schemas.pipeline_io import InferenceResult  # noqa: E402
from parse_bench.test_cases.loader import load_test_cases  # noqa: E402


def main() -> None:
    base = Path(_ROOT) / "parsebench" / "output" / "it5_full" / "kdl_frontier_nano_patched"
    rep = json.loads((base / "layout" / "_evaluation_report.json").read_text())
    fail = next(r for r in rep["per_example_results"] if not r.get("success"))
    ex = fail["example_id"]
    print("replaying failed example:", ex)

    result_path = base / (ex + ".result.json")
    inf = InferenceResult.model_validate(json.loads(result_path.read_text()))
    inf_dict = inf.model_dump()

    tcs = load_test_cases(
        root_dir=Path(_ROOT) / "parsebench" / "data",
        require_test_json=False,
        product_type=None,
    )
    tc = next(t for t in tcs if t.test_id == fail["test_id"])
    print("test case type:", type(tc).__name__)
    tc_dict = tc.model_dump()

    # Same argument tuple the runner builds for a cross-eval task (mode=True).
    task = (inf_dict, tc_dict, "layout_detection", True, "layout_detection", "basic", False, False, False)

    with ProcessPoolExecutor(max_workers=1) as ex_pool:
        out = ex_pool.submit(_evaluate_single_worker, *task).result(timeout=480)
    print("worker success:", out.get("success"))
    print("worker error:", out.get("error"))
    n_metrics = len(out.get("metrics") or [])
    print("n metrics:", n_metrics)


if __name__ == "__main__":
    main()
