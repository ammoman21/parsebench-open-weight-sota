#!/usr/bin/env python
"""
Build a small ParseBench subset for the formatting-prompt probe.

WHY: the runner has no --limit flag, only --input_dir and --group. A full run is
2,079 pages / ~70 min / ~$3.30. The probe only needs a signal on the
text_formatting dimension (476 docs), so we assemble a directory containing N of
those documents plus the PDFs they reference, and point --input_dir at it.

Selection is DETERMINISTIC and rule-weighted: documents are ranked by how many
formatting rules they carry, then sampled evenly across that ranking, so the
subset is not accidentally all trivial pages. Prints the rule coverage it achieved.
"""
from __future__ import annotations
import json, shutil, sys
from pathlib import Path
from collections import defaultdict

SRC = Path("parsebench/data")
DEST = Path("parsebench/data_probe")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40

def main() -> None:
    recs = [json.loads(l) for l in (SRC / "text_formatting.jsonl").open()]
    by_pdf: dict[str, list] = defaultdict(list)
    for r in recs:
        by_pdf[r["pdf"]].append(r)

    # rank by rule count, then take an even spread so easy and hard pages both appear
    ranked = sorted(by_pdf.items(), key=lambda kv: -len(kv[1]))
    if N >= len(ranked):
        chosen = ranked
    else:
        step = len(ranked) / N
        chosen = [ranked[int(i * step)] for i in range(N)]

    if DEST.exists():
        shutil.rmtree(DEST)
    (DEST / "docs" / "text").mkdir(parents=True, exist_ok=True)

    kept, missing = [], 0
    for pdf, rs in chosen:
        src = SRC / pdf
        if not src.exists():
            missing += 1
            continue
        dst = DEST / pdf
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        kept.extend(rs)

    (DEST / "text_formatting.jsonl").write_text(
        "\n".join(json.dumps(r) for r in kept) + "\n"
    )
    for aux in ("eval.yaml", "README.md"):
        if (SRC / aux).exists():
            shutil.copy2(SRC / aux, DEST / aux)

    print(f"subset -> {DEST}")
    print(f"  documents: {len({r['pdf'] for r in kept})} of {len(by_pdf)} "
          f"({len({r['pdf'] for r in kept})*100//len(by_pdf)}%)")
    print(f"  rules:     {len(kept)} of {len(recs)} ({len(kept)*100//len(recs)}%)")
    if missing:
        print(f"  WARNING: {missing} selected PDFs missing from source; skipped")
    print("  NOTE: subset scores are NOT comparable to full-corpus scores. "
          "Use it only to compare prompt variants against each other on this same subset.")

if __name__ == "__main__":
    main()
