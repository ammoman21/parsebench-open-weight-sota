#!/usr/bin/env python
"""Inner entry point: applies the prompt patch, then hands off to ParseBench's CLI."""
from __future__ import annotations
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "parsebench" / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

import ourparser.provider  # noqa: E402,F401  registers the patched pipelines
from ourparser.probe.prompts import VARIANTS  # noqa: E402
from parse_bench.inference.providers.parse import kdl_frontier_nano as K  # noqa: E402
from parse_bench.cli import main  # noqa: E402

variant = os.environ.get("PARSEBENCH_PROMPT_VARIANT", "v0_control")
patch = VARIANTS[variant]
# _NANO_PROMPTS is read by _nano_payload:2698 as a module global, so mutating the
# dict in place is sufficient and survives into the async workers.
K._NANO_PROMPTS.update(patch)
print(f"[probe] applied prompt variant {variant!r}: stages {sorted(patch)}", flush=True)

if __name__ == "__main__":
    main()
