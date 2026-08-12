"""
The two low-weight Semantic Formatting sub-scores: `normalized_latex` and
`normalized_code_block` (1/5 weight each, `evaluators/parse.py:511-517`).

Two known emission defects, both fixable with no GPU:

1. LATEX. `Formula` elements are wrapped in a ```` ```latex ```` fence
   (`_nano_format_formula`, `kdl_frontier_nano.py:2911-2917`). `LatexRule`
   (`rules_formatting.py:497-535`) only recognises `$…$`, `$$…$$`, `\\(…\\)` and
   `\\[…\\]` delimiters — a fence is invisible to it. Our `is_latex` pass rate is
   0.4607, i.e. the credit we do get comes from formulas that happen to reach the
   markdown some other way (inside `Text` elements).

2. CODE BLOCKS. `is_code_block` is 0.000. `CodeBlockRule` (`rules_formatting.py:570+`)
   needs a fenced block whose language tag matches the annotation. The layout label
   `code` is mapped to `Text` (`kdl_frontier_nano.py:549`), so code regions are
   recognised with the plain text prompt and emitted as bare paragraphs — no fence, no
   language. There is nothing at emission level to fix: the region is never even
   labelled as code. This script confirms that by checking whether any `is_code_block`
   annotation's snippet is present in our markdown at all.

Run:  ../.venv/bin/python scripts/latex_code_patch.py
"""

from __future__ import annotations

import collections
import json
import os
import re
import sys

import semfmt_lib as L

sys.path.insert(0, os.path.join(L.PB_ROOT, "src"))
from parse_bench.evaluation.metrics.parse.rules_formatting import (  # noqa: E402
    _extract_latex_formulas,
    _normalize_latex_formula,
)
from parse_bench.inference.providers.parse import kdl_frontier_nano as K  # noqa: E402

FENCE_LATEX_RE = re.compile(r"(?ms)^[ \t]*```latex[ \t]*\n(.*?)\n[ \t]*```[ \t]*$")


def latex_fence_to_dollars(md: str) -> str:
    """
    Rewrite ```` ```latex\\n BODY \\n``` ```` into `$$ BODY $$`.

    This is exactly what a fixed `_nano_format_formula` (`:2911-2917`) would emit.
    Block form (`$$`) is used because `Formula` elements are standalone blocks; the
    grader normalises both forms identically (`_extract_latex_formulas`, `:497-510`).
    """
    def repl(m: re.Match) -> str:
        body = m.group(1).strip()
        # The provider already converted \( \) / \[ \] to $ / $$ inside the body
        # (`:2863-2874`); strip any leftover delimiters so we do not double-wrap.
        body = body.strip("$").strip()
        return f"$$ {body} $$" if body else ""

    return FENCE_LATEX_RE.sub(repl, md)


def main() -> None:
    corpus = list(L.iter_markdown_corpus())

    # --- how many documents even have a ```latex fence? ---
    n_fence = sum(1 for _s, md, _r in corpus if "```latex" in md)
    n_latex_rules = sum(
        1 for _s, _m, rows in corpus for r in rows if r["type"] == "is_latex"
    )
    latex_docs = {s for s, _m, rows in corpus if any(r["type"] == "is_latex" for r in rows)}
    print(f"documents with a ```latex fence            : {n_fence}/{len(corpus)}")
    print(f"documents carrying is_latex rules          : {len(latex_docs)}")
    print(f"is_latex rules                             : {n_latex_rules}")
    overlap = {s for s, md, rows in corpus
               if "```latex" in md and any(r["type"] == "is_latex" for r in rows)}
    print(f"documents with BOTH (where the fix can pay): {len(overlap)}")

    base = L.measure_markdown_patch(None, corpus)
    patched = L.measure_markdown_patch(latex_fence_to_dollars, corpus)
    d = 100 * (patched["semfmt"] - base["semfmt"])
    print(f"\nLATEX FENCE -> $$ …  $$")
    print(f"  SemFmt {base['semfmt'] * 100:.2f} -> {patched['semfmt'] * 100:.2f}  "
          f"({d:+.2f} SemFmt, {d / 5:+.2f} Overall)")
    print(f"  is_latex {base['per_type'].get('is_latex', 0):.4f} -> "
          f"{patched['per_type'].get('is_latex', 0):.4f}")

    # --- is_code_block: is the annotated code even present? ---
    print("\nCODE BLOCKS")
    present = absent = 0
    langs = collections.Counter()
    for _s, md, rows in corpus:
        for r in rows:
            if r["type"] != "is_code_block":
                continue
            payload = L.rule_payload(r)
            langs[payload.get("language")] += 1
            code = (payload.get("code") or "").strip()
            probe = re.sub(r"\s+", " ", code)[:60]
            if probe and re.sub(r"\s+", " ", md).find(probe) >= 0:
                present += 1
            else:
                absent += 1
    print(f"  is_code_block rules: {present + absent}  languages={dict(langs)}")
    print(f"  annotated snippet present in our markdown : {present}")
    print(f"  annotated snippet absent entirely         : {absent}")
    print(f"  fenced code blocks we emit (any language) : "
          f"{sum(1 for _s, md, _r in corpus if re.search(r'^[ \t]*```', md, re.M))} docs")
    print("  -> the layout label `code` is remapped to `Text` at kdl_frontier_nano.py:549,")
    print("     so no emission-level change can produce a language-tagged fence; the")
    print("     category must be preserved through the layout contract first.")

    json.dump({"latex_base": base["per_type"].get("is_latex"),
               "latex_patched": patched["per_type"].get("is_latex"),
               "semfmt_base": base["semfmt"], "semfmt_patched": patched["semfmt"],
               "d_overall": d / 5,
               "code_present": present, "code_absent": absent},
              open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "_latex_code_patch.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
