"""Diagnostic 2: inspect adapter matching INSIDE a spawned worker process.

Ships the same serialized inference-result dict to a child process and prints, from
within the child: the registered adapter keys, the resolved provider name, the
deserialized output type, and each adapter class's matches() verdict. Read-only.
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

import ourparser.provider  # noqa: F401


def probe(inference_result_dict: dict) -> str:
    lines: list[str] = []
    from parse_bench.evaluation.layout_adapters import list_layout_adapters
    from parse_bench.evaluation.layout_adapters.registry import (
        _LAYOUT_ADAPTER_REGISTRY,
        resolve_layout_provider_name,
    )
    from parse_bench.schemas.parse_output import ParseOutput
    from parse_bench.schemas.pipeline_io import InferenceResult

    lines.append(f"child pid={os.getpid()} __mp_main__={('__mp_main__' in sys.modules)}")
    lines.append(f"ourparser.provider imported: {'ourparser.provider' in sys.modules}")
    lines.append(f"adapter keys: {list_layout_adapters()}")
    try:
        ir = InferenceResult.model_validate(inference_result_dict)
    except Exception as e:
        return "\n".join(lines + [f"VALIDATION FAILED: {e!r}"])
    lines.append(f"output type: {type(ir.output).__module__}.{type(ir.output).__name__}")
    lines.append(f"isinstance ParseOutput: {isinstance(ir.output, ParseOutput)}")
    lp = getattr(ir.output, "layout_pages", None)
    lines.append(f"layout_pages: {None if lp is None else len(lp)}")
    lines.append(f"resolved provider: {resolve_layout_provider_name(ir)!r}")
    for reg in _LAYOUT_ADAPTER_REGISTRY:
        try:
            verdict = reg.adapter_cls.matches(ir)
        except Exception as e:  # noqa: BLE001
            verdict = f"raised {e!r}"
        lines.append(f"matches {reg.adapter_cls.__name__} (keys={reg.keys}, prio={reg.priority}): {verdict}")
    return "\n".join(lines)


def main() -> None:
    base = Path(_ROOT) / "parsebench" / "output" / "it5_full" / "kdl_frontier_nano_patched"
    rep = json.loads((base / "layout" / "_evaluation_report.json").read_text())
    fail = next(r for r in rep["per_example_results"] if not r.get("success"))
    from parse_bench.schemas.pipeline_io import InferenceResult

    inf = InferenceResult.model_validate(json.loads((base / (fail["example_id"] + ".result.json")).read_text()))
    with ProcessPoolExecutor(max_workers=1) as pool:
        print(pool.submit(probe, inf.model_dump()).result(timeout=300))


if __name__ == "__main__":
    main()
