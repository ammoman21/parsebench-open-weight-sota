#!/usr/bin/env python
"""
Formatting-prompt probe. Patches `_NANO_PROMPTS` (a module global read by
`_nano_payload:2698`) for one variant, runs the text_formatting group over the
subset, and reports the score plus how many markers the model actually emitted.

    python ourparser/probe/run_probe.py v1_minimal

Always run `v0_control` first: if the control does not match the shipped pipeline's
score on this same subset, the rig is wrong and no variant result means anything.

Uses --force and a per-variant output dir, because the runner silently skips
documents whose .result.json already exists (runner.py:264-292, force defaults
False) — that is what made an earlier probe report zero work done.
"""
from __future__ import annotations
import json, os, re, subprocess, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "parsebench" / "src"))

from ourparser.probe.prompts import VARIANTS  # noqa: E402

MARKERS = {
    "bold_**": r"\*\*[^*\n]+\*\*", "bold_<b>": r"<b>", "strike_~~": r"~~[^~\n]+~~",
    "strike_tag": r"</?(s|del|strike)>", "sup": r"<sup>", "sub": r"<sub>",
}

def count_markers(out_dir: Path) -> Counter:
    c = Counter()
    for p in out_dir.rglob("*.raw.json"):
        try:
            ro = json.loads(p.read_text()).get("raw_output") or {}
        except Exception:
            continue
        md = ro.get("markdown") or ""
        for name, pat in MARKERS.items():
            c[name] += len(re.findall(pat, md))
    return c

def main() -> None:
    variant = sys.argv[1] if len(sys.argv) > 1 else "v0_control"
    if variant not in VARIANTS:
        sys.exit(f"unknown variant {variant!r}; have {sorted(VARIANTS)}")

    if not os.environ.get("KDL_NANO_ENDPOINT_URL"):
        sys.exit("REFUSING TO RUN: KDL_NANO_ENDPOINT_URL is not set. Serve the model and\n"
                 "  export KDL_NANO_ENDPOINT_URL=http://127.0.0.1:18000/v1\n"
                 "Without it the provider errors immediately and a zero-marker result would be\n"
                 "meaningless — it would mean 'nothing ran', not 'the model emitted nothing'.")

    out_dir = ROOT / "parsebench" / "output" / f"probe_{variant}"
    env = dict(os.environ)
    env["PARSEBENCH_PROMPT_VARIANT"] = variant
    env.setdefault("LLAMACLOUD_BENCH_LLM_NORMALIZATION", "off")

    cmd = ["uv", "run", "python", str(ROOT / "ourparser" / "probe" / "_inner.py"),
           "run", "kdl_frontier_nano_patched",
           "--group", os.environ.get("PROBE_GROUP", "text_formatting"),
           "--input_dir", os.environ.get("PROBE_DATA", str(ROOT / "parsebench" / "data_probe")),
           "--output_dir", str(out_dir),
           "--force", "True",
           "--max_concurrent", "8"]
    print(f"=== probe: {variant} ===")
    print("prompt(s) patched:", {k: repr(v[:70] + "…") for k, v in VARIANTS[variant].items()})
    subprocess.run(cmd, cwd=ROOT / "parsebench", env=env, check=False)

    reps = list(out_dir.rglob("_evaluation_report.json"))
    rep = reps[0] if reps else out_dir / "_missing.json"
    if rep.exists():
        d = json.loads(rep.read_text())
        a = d.get("aggregate_metrics", {})
        print(f"\nscored docs: {d.get('successful')} failed: {d.get('failed')}")
        for k in ("avg_semantic_formatting", "avg_rule_pass_rate",
                  "avg_rule_is_bold_pass_rate", "avg_rule_is_strikeout_pass_rate",
                  "avg_rule_is_sup_pass_rate", "avg_rule_is_sub_pass_rate"):
            if k in a:
                print(f"  {k:34s} {a[k]*100:.2f}")
    else:
        print("\nNO EVALUATION REPORT — inspect the run output above")

    # Establish that work actually happened BEFORE interpreting any marker count.
    # A run that processed nothing produces the same zero as a model that emitted
    # nothing, and conflating those two sent an earlier probe to a false conclusion.
    summs = list(out_dir.rglob("_summary.json"))
    summ = summs[0] if summs else out_dir / "_missing.json"
    processed = None
    if summ.exists():
        try:
            sd = json.loads(summ.read_text())
            processed = sd.get("successful", 0)
            print(f"\nrunner summary: successful={sd.get('successful')} "
                  f"failed={sd.get('failed')} skipped={sd.get('skipped')}")
        except Exception:
            pass

    print("\nmarkers the model actually emitted:")
    c = count_markers(out_dir)
    if not processed:
        print("  INCONCLUSIVE — the run processed 0 documents, so a zero marker count means")
        print("  'nothing ran', NOT 'the model emitted nothing'. Fix the run and repeat.")
    elif sum(c.values()) == 0:
        print(f"  NONE across {processed} documents that did run. The model does not produce")
        print("  markup when asked -> prompting cannot fix this dimension; a fine-tune would be")
        print("  required. (Valid conclusion: work was done and no markers appeared.)")
    else:
        for k, v in c.most_common():
            print(f"  {k:12s} {v}")

if __name__ == "__main__":
    main()
