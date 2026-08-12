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
from parse_bench.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
