#!/usr/bin/env python
"""
Launcher for the patched pipelines — the smallest shim the benchmark's design requires.

WHY A LAUNCHER IS NEEDED AT ALL
-------------------------------
`ourparser.provider` registers its provider and its pipelines through ParseBench's own
public `register_provider` / `register_pipeline` functions, so no benchmark source file
has to change. But ParseBench's command-line entry point (`parse-bench`, defined in
`parsebench/pyproject.toml` -> `parse_bench.cli`) has no plugin hook and no
"extra modules to import" setting: it imports only its own built-in provider list
(`parse_bench/inference/providers/parse/__init__.py`). An externally-registered pipeline
is therefore invisible to `parse-bench run` unless something imports our module first.

This file is that something. It imports `ourparser.provider` (which performs the
registration) and then hands control to ParseBench's own unmodified command-line
interface. Use it exactly as you would use `parse-bench`:

    KDL_NANO_ENDPOINT_URL=http://localhost:8000/v1 \\
    python ourparser/run_patched.py run kdl_frontier_nano_patched \\
        --input_dir parsebench/data --output_dir parsebench/output/kdl_frontier_nano_patched

LABEL CAPTURE (set this for the diagnostic run)
-----------------------------------------------
Set PARSEBENCH_LABEL_CAPTURE=<dir> and the run records, for every element, the model's
raw layout label alongside the category it was mapped to, plus whether that raw label was
present in NATIVE_LAYOUT_CATEGORY_MAP at all. Unmapped labels silently become "Text",
which is the suspected cause of the Visual Grounding classification deficit. The saved
run artifacts keep only the mapped category, so this capture is the ONLY way to learn the
model's actual label vocabulary — and once captured, every candidate map fix becomes
measurable by replay with no further GPU time.

    PARSEBENCH_LABEL_CAPTURE=runs/labels \\
    KDL_NANO_ENDPOINT_URL=http://localhost:8000/v1 \\
    python ourparser/run_patched.py run kdl_frontier_nano_patched ...

Registered pipeline names:
  kdl_frontier_nano_patched     the submitted patch set   (emission_set=genuine_abcd)
  kdl_frontier_nano_aggressive  disclosed, not submitted  (emission_set=aggressive_abcd)

To run the submitted set without the borderline heading-gate relaxation, pass
`--config_override '{"emission_set": "genuine_abc"}'` if the benchmark's runner supports
a config override for the pipeline, or register a third pipeline name in
`ourparser/provider.py`.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.environ.get("PARSEBENCH_SRC", os.path.join(_ROOT, "parsebench", "src"))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ourparser.provider  # noqa: E402,F401  — import registers provider and pipelines
from ourparser import instrument  # noqa: E402
from parse_bench.cli import main  # noqa: E402

if __name__ == "__main__":
    if instrument.capture_dir() is None:
        main()
    else:
        # label_capture() restores the wrapped function and flushes the sidecar on exit,
        # including on exception, so a crashed run still yields whatever it observed.
        with instrument.label_capture():
            try:
                main()
            finally:
                print("\n" + instrument.report(), flush=True)
